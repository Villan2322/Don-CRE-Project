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
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": [{"type": "text", "text": reply_text}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        })
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


async def test_ocr_call_is_accepted_by_the_sdk(requests, monkeypatch):
    result = await OCRAgent().process(b"%PDF-1.4 fake scan", "scan.pdf", page_count=1)
    assert result["document_readable"] is False or result["cleaned_text"]
    body = json.loads(requests[0].content)
    assert body["messages"][0]["content"][0]["type"] == "document"
    assert body["messages"][0]["content"][0]["source"]["media_type"] == "application/pdf"


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
