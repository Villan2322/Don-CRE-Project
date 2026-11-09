import json
import os
import re
from typing import Optional

import anthropic

DEFAULT_MODEL = "claude-sonnet-5-5"


def make_client() -> anthropic.AsyncAnthropic:
    """Claude client. ANTHROPIC_WORKSPACE_ID is only needed for keys not scoped to a workspace."""
    headers = {}
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        headers["anthropic-workspace-id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    return anthropic.AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        max_retries=3,
        default_headers=headers or None,
    )


# Errors that mean no call will ever succeed until someone fixes the account or key.
FATAL_API_ERRORS = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
)


def fatal_api_message(error: BaseException) -> str | None:
    """A plain explanation if this error means the API key or account is unusable, else None."""
    text = str(error)
    low = text.lower()
    if isinstance(error, FATAL_API_ERRORS) or "x-api-key" in low or "api key" in low \
            or "workspace" in low or "credit balance" in low:
        return f"Anthropic rejected the request — check ANTHROPIC_API_KEY on the server. Details: {text[:300]}"
    return None


def thinking_off(model: str) -> dict:
    """Request args that stop the model spending its output budget on thinking.

    Transcription and extraction are copying jobs; on newer models, default
    thinking can use most of max_tokens before any answer is written.
    """
    match = re.match(r"claude-[a-z]+-(\d+)", model)
    if match and int(match.group(1)) >= 5:
        return {"thinking": {"type": "between_tools"}}
    return {}


async def complete(client: anthropic.AsyncAnthropic, *, model: str, max_tokens: int,
                   messages: list, system: Optional[str] = None) -> tuple[str, str]:
    """One Claude call, streamed so long outputs aren't refused. Returns (text, stop_reason)."""
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages, **thinking_off(model)}
    if system:
        kwargs["system"] = system
    async with client.messages.stream(**kwargs) as stream:
        message = await stream.get_final_message()
    text = "".join(block.text for block in message.content if block.type == "text")
    return text, message.stop_reason


class BaseAgent:
    """Shared Claude client and JSON parsing for every LLM-backed agent."""

    def __init__(self, name: str = "BaseAgent", system_prompt: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self._client: Optional[anthropic.AsyncAnthropic] = None
        self.model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = make_client()
        return self._client

    async def call_llm(self, system_prompt: str, user_message: str,
                       max_tokens: int = 4000) -> str:
        text, stop_reason = await complete(
            self.client, model=self.model, max_tokens=max_tokens, system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        if stop_reason == "max_tokens":
            raise ValueError(
                f"{self.name}: response hit the {max_tokens}-token limit and was cut off"
            )
        return text

    def _parse_json_response(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        candidate = self._extract_json(text)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return {"_parse_error": "Could not extract JSON", "_raw": text[:500]}

    def _extract_json(self, text: str) -> str:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            return match.group(1).strip()
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group(0)
        return text
