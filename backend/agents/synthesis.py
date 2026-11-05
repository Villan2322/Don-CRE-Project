"""
Synthesis Agent

The qualitative review pass. It reads every extraction plus the metrics
already computed in code, and returns the judgment calls code can't make:
lease-level risks, cross-document conflicts, an executive summary, and
what to request next. It never produces the numbers on the dashboard.
"""

import json
from typing import Any

from .base import BaseAgent
from config.extraction_prompts import SYNTHESIS_PROMPT

SYNTHESIS_MAX_TOKENS = 8000


class SynthesisAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="SynthesisAgent", system_prompt=SYNTHESIS_PROMPT)

    async def synthesize_deal(self, extractions: list[dict], metrics: dict,
                              deal_name: str) -> dict[str, Any]:
        grouped: dict[str, list] = {}
        for ext in extractions:
            grouped.setdefault(ext.get("doc_type", "OTHER"), []).append({
                "filename": ext.get("filename"),
                "extraction": slim(ext.get("extraction", {})),
            })

        user_message = (
            f"Deal: {deal_name}\n"
            f"Document types present: {', '.join(sorted(grouped)) or 'none'}\n\n"
            f"COMPUTED METRICS:\n{json.dumps(metrics, indent=2, default=str)}\n\n"
            f"EXTRACTIONS:\n{json.dumps(grouped, indent=2, default=str)}\n\n"
            "Return the review JSON."
        )
        response = await self.call_llm(self.system_prompt, user_message,
                                       max_tokens=SYNTHESIS_MAX_TOKENS)
        parsed = self._parse_json_response(response)
        if "_parse_error" in parsed:
            raise ValueError(f"Synthesis returned unparseable JSON: {parsed.get('_raw', '')[:300]}")
        return parsed


def slim(obj: Any) -> Any:
    """Collapse {value, confidence, source_text} objects to their value to cut tokens."""
    if isinstance(obj, dict):
        if "value" in obj and ("confidence" in obj or "source_text" in obj):
            return obj["value"]
        return {k: slim(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [slim(item) for item in obj]
    return obj
