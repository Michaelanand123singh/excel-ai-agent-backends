from __future__ import annotations

from typing import Dict, List

from app.services.query_engine.ai_client import ask_llm


def extract_intents(question: str) -> Dict:
    """Return simple intent fields for downstream logic.

    Example output:
    {
        "metrics": ["count", "sum(amount)"],
        "filters": ["country = 'US'"],
        "group_by": ["country"],
        "limit": 50
    }
    """
    prompt = (
        "Extract metrics, filters, and group_by fields from the question.\n"
        "Return a compact JSON with keys: metrics (list), filters (list), group_by (list), limit (int).\n"
        f"Question: {question}\nJSON:"
    )
    text = ask_llm(prompt)
    # Best-effort JSON parsing; tolerate LLM noise
    import json
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not a dict")
    except Exception:
        data = {}
    # Normalize
    def _list(v) -> List[str]:
        return [str(x) for x in v] if isinstance(v, list) else []
    return {
        "metrics": _list(data.get("metrics", [])),
        "filters": _list(data.get("filters", [])),
        "group_by": _list(data.get("group_by", [])),
        "limit": int(data.get("limit", 50) or 50),
    }



