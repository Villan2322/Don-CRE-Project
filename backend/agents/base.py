import asyncio
import json
import os
import re
from typing import Any, Optional

from openai import AsyncOpenAI


class BaseAgent:
    def __init__(self, name: str = "BaseAgent", system_prompt: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self._client: Optional[AsyncOpenAI] = None
        self.model = os.environ.get("CLAUDE_MODEL", "anthropic/claude-sonnet-4-5")

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = (
                os.environ.get("AI_GATEWAY_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_API_KEY")
                or "missing-key"
            )
            self._client = AsyncOpenAI(
                base_url="https://gateway.vercel.ai/v1",
                api_key=api_key,
            )
        return self._client

    async def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content or ""

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
        text = text.strip()
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
        text = text.strip()
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            return match.group(1).strip()
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return match.group(0)
        return text
