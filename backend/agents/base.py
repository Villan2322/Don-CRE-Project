import json
import os
import re
from typing import Optional

import anthropic

DEFAULT_MODEL = "claude-sonnet-4-5"


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
            self._client = anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
                max_retries=3,
            )
        return self._client

    async def call_llm(self, system_prompt: str, user_message: str,
                       max_tokens: int = 4000, temperature: float = 0.0) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        if response.stop_reason == "max_tokens":
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
