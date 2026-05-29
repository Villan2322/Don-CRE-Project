import json
import os
import re
from typing import Any, Optional
import anthropic


class BaseAgent:
    def __init__(self, name: str = "BaseAgent", system_prompt: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self._client: Optional[anthropic.Anthropic] = None
        self._use_gateway = False
        self._base_model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    @property
    def model(self) -> str:
        # The Vercel AI Gateway routes by "provider/model"; the native Anthropic
        # API uses the bare model id.
        if self._use_gateway and not self._base_model.startswith("anthropic/"):
            return f"anthropic/{self._base_model}"
        return self._base_model

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()

            if api_key:
                # Production: real Anthropic API key (direct to Anthropic).
                kwargs: dict[str, Any] = {"api_key": api_key}
                if base_url:
                    kwargs["base_url"] = base_url
                self._client = anthropic.Anthropic(**kwargs)
            else:
                # Fallback: route through the Vercel AI Gateway using its auth
                # token (used for local/sandbox testing). The Anthropic SDK
                # appends /v1/messages to the base URL.
                auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
                gateway_url = base_url or "https://ai-gateway.vercel.sh"
                if not auth_token:
                    raise RuntimeError(
                        "No Anthropic credentials found. Set ANTHROPIC_API_KEY "
                        "(production) or ANTHROPIC_AUTH_TOKEN (gateway)."
                    )
                self._use_gateway = True
                self._client = anthropic.Anthropic(
                    auth_token=auth_token,
                    base_url=gateway_url,
                )
        return self._client

    async def call_llm(self, system_prompt: str, user_message: str,
                       max_tokens: int = 4000, temperature: float = 0.1) -> str:
        import asyncio

        def _call():
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text

        # Retry transient errors (rate limits, overloaded, timeouts) with
        # exponential backoff so a single 429/529 does not fail the pipeline.
        max_attempts = 5
        last_error: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                return await asyncio.get_event_loop().run_in_executor(None, _call)
            except Exception as e:  # noqa: BLE001 - re-raised after retries
                last_error = e
                status = getattr(e, "status_code", None)
                retriable = status in (408, 409, 429, 500, 502, 503, 504, 529)
                if not retriable or attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(min(2 ** attempt, 30))
        raise last_error if last_error else RuntimeError("LLM call failed")

    async def analyze(self, content: str, context: Optional[dict] = None) -> dict:
        user_content = self._format_input(content, context)
        try:
            text = await self.call_llm(self.system_prompt, user_content)
            return self._parse_json_response(text)
        except Exception as e:
            return {"error": str(e), "agent": self.name}

    def _format_input(self, content: str, context: Optional[dict] = None) -> str:
        if context:
            return f"Context: {json.dumps(context)}\n\nContent to analyze:\n{content}"
        return f"Content to analyze:\n{content}"

    def _parse_json_response(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"_parse_error": "Could not extract JSON", "_raw": text[:500]}

    def _extract_json(self, text: str) -> str:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            return match.group(1).strip()
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group(0)
        return text
