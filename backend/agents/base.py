import os
from openai import OpenAI
from typing import Any, Optional
import json


class BaseAgent:
    """Base class for all document analysis agents."""
    
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.client = OpenAI(
            base_url="https://gateway.vercel.ai/v1",
            api_key=os.environ.get("AI_GATEWAY_API_KEY", "dummy-key"),
        )
        self.model = "anthropic/claude-sonnet-4-20250514"
    
    async def analyze(self, content: str, context: Optional[dict] = None) -> dict:
        """Run analysis on the provided content."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self._format_input(content, context)}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = response.choices[0].message.content
            return json.loads(result) if result else {}
        except Exception as e:
            return {"error": str(e), "agent": self.name}
    
    def _format_input(self, content: str, context: Optional[dict] = None) -> str:
        """Format input for the agent. Override in subclasses for custom formatting."""
        if context:
            return f"Context: {json.dumps(context)}\n\nContent to analyze:\n{content}"
        return f"Content to analyze:\n{content}"
