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
        self.model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "")
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
        return await asyncio.get_event_loop().run_in_executor(None, _call)

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
