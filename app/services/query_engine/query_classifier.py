from __future__ import annotations

from typing import Literal

from app.services.query_engine.ai_client import ask_llm


QueryRoute = Literal["structured", "semantic", "hybrid"]


def _heuristic_classify(question: str) -> QueryRoute:
    q = question.lower()
    structured_keywords = ["count", "sum", "avg", "average", "min", "max", "group by", "top", "median", "percentile"]
    semantic_keywords = ["similar", "about", "relevant", "find text", "contains", "meaning", "search"]
    if any(k in q for k in structured_keywords) and any(k in q for k in semantic_keywords):
        return "hybrid"
    if any(k in q for k in structured_keywords):
        return "structured"
    if any(k in q for k in semantic_keywords):
        return "semantic"
    return "hybrid"


def classify(question: str) -> QueryRoute:
    # Try LLM-driven classification; fallback to heuristics
    prompt = (
        "Read the user question and classify the best route as one of: structured, semantic, hybrid.\n"
        "Return ONLY one word: structured | semantic | hybrid.\n\nQuestion: "
        + question
    )
    res = ask_llm(prompt).strip().lower()
    if res in ("structured", "semantic", "hybrid"):
        return res  # type: ignore[return-value]
    return _heuristic_classify(question)



