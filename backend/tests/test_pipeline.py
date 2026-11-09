"""End-to-end runs of the LangGraph pipeline and the API with Claude stubbed out."""

import io
import json
import re
import time

import openpyxl
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

import agents.base as base
from agents.document_parsing import DocumentParsingAgent
from agents.ocr_agent import OCRAgent
from graph import graph
from state import initial_state
from tests.fixtures import AS_OF, CLASSIFY_BY_FILE, EXTRACT_BY_TYPE, FILE_TEXT, SYNTHESIS_RESPONSE


class FakeClaude:
    """Answers the three prompt kinds the pipeline sends."""

    def __init__(self, fail_synthesis=False):
        self.fail_synthesis = fail_synthesis
        self.calls = []

    async def __call__(self, agent, system_prompt, user_message, max_tokens=4000, temperature=0.0):
        self.calls.append(agent.name)
        if user_message.rstrip().endswith("Classify this document."):
            name = re.search(r"Filename: (.+)", user_message).group(1).strip()
            return json.dumps({"document_type": CLASSIFY_BY_FILE.get(name, "OTHER"), "confidence": 0.95,
                               "reasoning": "test"})
        if agent.name == "SynthesisAgent":
            if self.fail_synthesis:
                raise RuntimeError("overloaded")
            assert "COMPUTED METRICS" in user_message  # synthesis gets the code-computed figures
            return json.dumps(SYNTHESIS_RESPONSE)
        doc_type = re.search(r"Document type: (\w+)", user_message).group(1)
        return "```json\n" + json.dumps(EXTRACT_BY_TYPE[doc_type]) + "\n```"


@pytest.fixture
def fake_claude(monkeypatch):
    fake = FakeClaude()

    async def call(self, *args, **kwargs):
        return await fake(self, *args, **kwargs)

    monkeypatch.setattr(base.BaseAgent, "call_llm", call)
    return fake


def package():
    return ({name: text.encode() for name, text in FILE_TEXT.items()},
            {name: "text/csv" if name.endswith(".csv") else "text/plain" for name in FILE_TEXT})


async def run(files, types):
    return await graph.ainvoke(initial_state("deal-1", "Sterling Test", files, types, AS_OF))


async def test_full_package_runs_end_to_end(fake_claude):
    result = await run(*package())
    assert result["pipeline_stage"] == "completed"
    assert result["pipeline_errors"] == []
    report = result["report"]
    assert report["dealName"] == "Sterling Test"
    assert len(report["tenants"]) == 6
    assert report["rsfReconciliation"]["alertTriggered"]
    assert report["propertyAddress"] == "5041 Bayou Blvd, Pensacola, FL 32503"
    assert any(f["source"] == "ai_review" for f in report["redFlags"])
    assert report["executiveSummary"]
    statuses = {d["filename"]: d["status"] for d in report["documents"]}
    assert statuses["site_photo_notes.txt"] == "SKIPPED"
    assert statuses["boa_lease.txt"] == "PROCESSED"
    # four extractions ran in parallel, plus five classifications and one synthesis
    assert fake_claude.calls.count("UniversalExtractor") == 9
    assert fake_claude.calls.count("SynthesisAgent") == 1


async def test_synthesis_failure_still_returns_the_computed_report(monkeypatch):
    fake = FakeClaude(fail_synthesis=True)

    async def call(self, *args, **kwargs):
        return await fake(self, *args, **kwargs)

    monkeypatch.setattr(base.BaseAgent, "call_llm", call)
    result = await run(*package())
    assert result["pipeline_stage"] == "completed"
    assert result["report"]["score"] > 0
    assert any("AI review unavailable" in e for e in result["report"]["pipelineErrors"])
    assert all(f["source"] == "computed" for f in result["report"]["redFlags"])


async def test_nothing_extractable_still_completes(fake_claude):
    result = await run({"site_photo_notes.txt": FILE_TEXT["site_photo_notes.txt"].encode()},
                       {"site_photo_notes.txt": "text/plain"})
    assert result["pipeline_stage"] == "completed"
    assert result["report"]["tenants"] == []
    assert result["report"]["tier"] == "RED"


async def test_unsupported_and_unreadable_files_are_reported(fake_claude):
    files = {"model.numbers": b"\x00\x01", "boa_lease.txt": FILE_TEXT["boa_lease.txt"].encode()}
    result = await run(files, {"model.numbers": "application/octet-stream", "boa_lease.txt": "text/plain"})
    docs = {d["filename"]: d for d in result["report"]["documents"]}
    assert docs["model.numbers"]["status"] == "FAILED"
    assert "Unsupported" in docs["model.numbers"]["note"]
    assert docs["boa_lease.txt"]["status"] == "PROCESSED"


async def test_scanned_pdf_goes_through_ocr(fake_claude, monkeypatch):
    seen = {}

    async def fake_ocr(self, file_content, filename, page_count=None):
        seen["file"] = filename
        return {"document_readable": True, "cleaned_text": FILE_TEXT["boa_lease.txt"], "confidence": None,
                "ocr_issues_found": [], "pages_processed": page_count}

    monkeypatch.setattr(OCRAgent, "process", fake_ocr)
    blank = io.BytesIO()
    canvas.Canvas(blank).save()  # one blank page: no text layer
    result = await run({"boa_lease.pdf": blank.getvalue()}, {"boa_lease.pdf": "application/pdf"})
    assert seen["file"] == "boa_lease.pdf"
    doc = result["report"]["documents"][0]
    assert doc["ocr"] is True


# ── parser ───────────────────────────────────────────────────────────────────

def test_parser_reads_text_pdf_and_flags_scans():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for line in range(12):
        c.drawString(72, 720 - line * 14, f"Annual Base Rent: $104,029.20 Net Rentable Area 10,508 square feet {line}")
    c.save()
    parser = DocumentParsingAgent()
    text_pdf = parser.check("lease.pdf", buf.getvalue(), "application/pdf")
    assert not text_pdf.needs_ocr and "10,508" in text_pdf.extracted_text

    blank = io.BytesIO()
    canvas.Canvas(blank).save()
    assert parser.check("scan.pdf", blank.getvalue(), "application/pdf").needs_ocr
    assert parser.check("screenshot.png", b"\x89PNG", "image/png").needs_ocr


def test_parser_reads_xlsx():
    wb = openpyxl.Workbook()
    wb.active.title = "Square Footage Breakdown"
    wb.active.append(["Suite", "Tenant", "Rentable SF"])
    wb.active.append(["Suite 200", "Bank of America", 10548.77])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = DocumentParsingAgent().check("boma.xlsx", buf.getvalue(), "")
    assert parsed.is_parseable and "Bank of America\t10548.77" in parsed.extracted_text


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from main import app
    with TestClient(app) as c:  # keeps the event loop alive for background jobs
        yield c


def wait_for(client, job_id, timeout=30):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        seen.append(job["stage"])
        if job["status"] in ("done", "failed"):
            return job, seen
        time.sleep(0.05)
    raise AssertionError(f"job did not finish; stages seen: {seen}")


def test_analyze_runs_as_a_job_and_returns_the_dashboard_payload(fake_claude, client):
    files = [("files", (name, text.encode(), "text/plain")) for name, text in FILE_TEXT.items()]
    resp = client.post("/api/analyze", data={"deal_name": "Sterling Test", "as_of": AS_OF}, files=files)
    assert resp.status_code == 202, resp.text
    job, stages = wait_for(client, resp.json()["job_id"])
    assert job["status"] == "done", job
    body = job["result"]
    assert body["pipeline_stage"] == "completed"
    assert body["analysis"]["tier"] in ("GREEN", "YELLOW", "ORANGE", "RED")
    assert len(body["analysis"]["tenants"]) == 6
    assert job["stage"] == "Done"


def test_a_crashing_pipeline_marks_the_job_failed(client, monkeypatch):
    import main

    async def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")
        yield  # pragma: no cover

    monkeypatch.setattr(main.graph, "astream", boom)
    resp = client.post("/api/analyze", data={"deal_name": "x"}, files=[("files", ("a.txt", b"hello", "text/plain"))])
    job, _ = wait_for(client, resp.json()["job_id"])
    assert job["status"] == "failed" and "disk on fire" in job["error"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_upload_size_limit(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "MAX_UPLOAD_MB", 0.001)
    resp = client.post("/api/analyze", data={"deal_name": "x"},
                       files=[("files", ("big.txt", b"x" * 5000, "text/plain"))])
    assert resp.status_code == 413


def test_analyze_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from main import app
    resp = TestClient(app).post("/api/analyze", data={"deal_name": "x"},
                                files=[("files", ("a.txt", b"hello", "text/plain"))])
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_health(client):
    assert client.get("/api/health").json()["anthropic_key_configured"] is True
    assert client.get("/health").json() == {"status": "ok"}


def test_password_protects_everything_but_health(monkeypatch):
    import base64 as b64
    import main
    monkeypatch.setattr(main, "APP_PASSWORD", "s3cret")
    c = TestClient(main.app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/health").status_code == 401
    assert c.get("/api/health").headers["www-authenticate"].startswith("Basic")
    bad = "Basic " + b64.b64encode(b"don:wrong").decode()
    assert c.get("/api/health", headers={"Authorization": bad}).status_code == 401
    good = "Basic " + b64.b64encode(b"don:s3cret").decode()
    assert c.get("/api/health", headers={"Authorization": good}).status_code == 200
