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

    async def __call__(self, agent, system_prompt, user_message, max_tokens=4000):
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


def test_a_rejected_api_key_fails_the_job_with_a_clear_message(client, monkeypatch):
    async def rejected(self, *args, **kwargs):
        raise RuntimeError("Error code: 400 - This API key is not scoped to a workspace")

    monkeypatch.setattr(base.BaseAgent, "call_llm", rejected)
    files = [("files", (name, text.encode(), "text/plain")) for name, text in FILE_TEXT.items()]
    resp = client.post("/api/analyze", data={"deal_name": "x"}, files=files)
    job, _ = wait_for(client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert "check ANTHROPIC_API_KEY" in job["error"] and "workspace" in job["error"]


def test_health_verify_reports_a_bad_key(client, monkeypatch):
    import main

    class Boom:
        class messages:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("invalid x-api-key")

    monkeypatch.setattr(main, "make_client", lambda: Boom)
    body = client.get("/api/health?verify=true").json()
    assert body["anthropic_key_works"] is False and "x-api-key" in body["anthropic_error"]


# ── adding documents to an earlier run ───────────────────────────────────────

def _files(*names):
    return [("files", (n, FILE_TEXT[n].encode(), "text/plain")) for n in names]


def _carry_file(analysis, drop=()):
    carry = dict(analysis["carry"])
    keep = [d for d in carry["documents"] if d["filename"] not in drop]
    ids = {d["doc_id"] for d in keep}
    carry.update(documents=keep, extractions=[e for e in carry["extractions"] if e["doc_id"] in ids])
    return ("prior", ("prior.json", json.dumps(carry).encode(), "application/json"))


def _run_api(client, files, data=None):
    resp = client.post("/api/analyze", data={"deal_name": "Sterling Test", "as_of": AS_OF, **(data or {})}, files=files)
    assert resp.status_code == 202, resp.text
    job, _ = wait_for(client, resp.json()["job_id"])
    assert job["status"] == "done", job
    return job["result"]["analysis"]


def test_adding_a_document_reads_only_the_new_file(fake_claude, client):
    first = _run_api(client, _files("stirling_aug_2025.txt", "boa_lease.txt", "escambia_pa.txt"))
    assert not first["leaseAudit"]["available"]  # no BOMA yet
    fake_claude.calls.clear()

    second = _run_api(client, _files("boma_measurements.csv") + [_carry_file(first)])
    extract_calls = [c for c in fake_claude.calls if c == "UniversalExtractor"]
    assert len(extract_calls) == 2  # classify + extract the BOMA file only
    assert second["leaseAudit"]["available"]
    assert second["rsfReconciliation"]["alertTriggered"]
    docs = {d["filename"]: d for d in second["documents"]}
    assert set(docs) == {"stirling_aug_2025.txt", "boa_lease.txt", "escambia_pa.txt", "boma_measurements.csv"}
    assert docs["boa_lease.txt"]["carried"] and not docs["boma_measurements.csv"]["carried"]
    first_docs = {d["filename"]: d for d in first["documents"]}
    assert docs["boa_lease.txt"]["uploadedAt"] == first_docs["boa_lease.txt"]["uploadedAt"]
    assert docs["boma_measurements.csv"]["uploadedAt"] != first_docs["boa_lease.txt"]["uploadedAt"]
    assert len(second["carry"]["documents"]) == 4
    assert second["scoreBreakdown"]["documentCoverage"]["reasons"][0]["text"].startswith("4 of 4")


def test_removing_a_document_reruns_without_reading_anything(fake_claude, client):
    full = _run_api(client, _files("stirling_aug_2025.txt", "boa_lease.txt", "boma_measurements.csv"))
    fake_claude.calls.clear()
    fewer = _run_api(client, [_carry_file(full, drop={"boma_measurements.csv"})])
    assert fake_claude.calls == ["SynthesisAgent"]
    assert not fewer["leaseAudit"]["available"]
    assert {d["filename"] for d in fewer["documents"]} == {"stirling_aug_2025.txt", "boa_lease.txt"}


def test_a_new_file_with_the_same_name_replaces_the_old_one(fake_claude, client):
    first = _run_api(client, _files("stirling_aug_2025.txt", "boa_lease.txt"))
    second = _run_api(client, _files("boa_lease.txt") + [_carry_file(first)])
    names = [d["filename"] for d in second["documents"]]
    assert names.count("boa_lease.txt") == 1
    assert not next(d for d in second["documents"] if d["filename"] == "boa_lease.txt")["carried"]


def test_bad_prior_is_rejected(client):
    bad = ("prior", ("prior.json", b'{"version": 1, "documents": "nope", "extractions": []}', "application/json"))
    resp = client.post("/api/analyze", data={"deal_name": "x"}, files=_files("boa_lease.txt") + [bad])
    assert resp.status_code == 400 and "malformed" in resp.json()["detail"]
    old = ("prior", ("prior.json", b'{"documents": []}', "application/json"))
    resp = client.post("/api/analyze", data={"deal_name": "x"}, files=_files("boa_lease.txt") + [old])
    assert resp.status_code == 400 and "older version" in resp.json()["detail"]


def test_nothing_new_and_nothing_carried_is_rejected(client):
    resp = client.post("/api/analyze", data={"deal_name": "x"})
    assert resp.status_code in (400, 422)


# ── keep-awake ───────────────────────────────────────────────────────────────

async def test_keep_awake_pings_health_on_a_timer(monkeypatch):
    import asyncio
    import main
    hits = []
    monkeypatch.setattr(main, "_ping", lambda url: hits.append(url) or 200)
    task = asyncio.create_task(main.keep_awake("https://example.onrender.com/", 0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    assert hits and set(hits) == {"https://example.onrender.com/health"}


async def test_keep_awake_survives_a_failed_ping(monkeypatch):
    import asyncio
    import main
    calls = []

    def flaky(url):
        calls.append(url)
        raise OSError("network down")

    monkeypatch.setattr(main, "_ping", flaky)
    task = asyncio.create_task(main.keep_awake("https://x.onrender.com", 0.01))
    await asyncio.sleep(0.05)
    assert not task.done() and len(calls) >= 2  # keeps going after failures
    task.cancel()


def test_keep_awake_is_off_without_a_render_url(monkeypatch):
    import main
    monkeypatch.setattr(main, "KEEP_AWAKE_URL", "")
    started = []
    monkeypatch.setattr(main, "keep_awake", lambda *a: started.append(a))
    with TestClient(main.app) as c:
        assert c.get("/health").status_code == 200
    assert started == []
