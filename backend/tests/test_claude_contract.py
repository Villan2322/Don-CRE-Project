"""
Contract tests: run the real Anthropic SDK against a fake HTTP server.

The other tests stub out call_llm entirely, which is how an SDK upgrade that
rejected our arguments reached production unnoticed. These go through the
SDK's own argument checks and request building, so that can't happen again.
"""

import json

import anthropic
import httpx2 as httpx
import pytest

import agents.base as base
from agents.ocr_agent import OCRAgent
from agents.universal_extractor import UniversalExtractor


def fake_api(requests, reply_text='{"document_type": "LEASE", "confidence": 0.9, "reasoning": "x"}'):
    """Answers like the real Messages API does when streaming (server-sent events)."""
    def event(name, data):
        return f"event: {name}\ndata: {json.dumps(data)}\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = "".join([
            event("message_start", {"type": "message_start", "message": {
                "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
                "content": [], "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1}}}),
            event("content_block_start", {"type": "content_block_start", "index": 0,
                                          "content_block": {"type": "text", "text": ""}}),
            event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                          "delta": {"type": "text_delta", "text": reply_text}}),
            event("content_block_stop", {"type": "content_block_stop", "index": 0}),
            event("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                    "usage": {"output_tokens": 10}}),
            event("message_stop", {"type": "message_stop"}),
        ])
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())
    return handler


@pytest.fixture
def requests(monkeypatch):
    sent = []
    real_factory = base.make_client

    def client_factory():
        real = real_factory()
        return real.with_options(http_client=httpx.AsyncClient(transport=httpx.MockTransport(fake_api(sent))))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test")
    monkeypatch.setattr(base, "make_client", client_factory)
    return sent


async def test_classify_and_extract_calls_are_accepted_by_the_sdk(requests):
    agent = UniversalExtractor()
    result = await agent.classify_document("LEASE AGREEMENT between ...", "lease.pdf")
    assert result["doc_type"] == "LEASE"
    body = json.loads(requests[0].content)
    assert body["model"] == base.DEFAULT_MODEL
    assert body["max_tokens"] == 500
    assert "temperature" not in body
    assert body["stream"] is True
    assert body["thinking"] == {"type": "between_tools"}


async def test_ocr_splits_long_scans_into_batches(requests):
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(7):
        c.showPage()
    c.save()
    result = await OCRAgent().process(buf.getvalue(), "scan.pdf", page_count=7)
    assert len(requests) == 3  # pages 1-3, 4-6, 7
    prompts = sorted(json.loads(r.content)["messages"][0]["content"][1]["text"] for r in requests)
    assert any('"=== Page 4 ==="' in p for p in prompts)
    first = json.loads(requests[0].content)["messages"][0]["content"][0]
    assert first["type"] == "document" and first["source"]["media_type"] == "application/pdf"
    assert result["document_readable"]


async def test_workspace_header_is_sent_when_configured(requests, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_123")
    await UniversalExtractor().classify_document("text", "a.pdf")
    assert requests[0].headers["anthropic-workspace-id"] == "wrkspc_123"


async def test_auth_failures_are_flagged_fatal():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
    error = anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)
    assert base.fatal_api_message(error)
    assert base.fatal_api_message(ValueError("JSON was cut off")) is None
