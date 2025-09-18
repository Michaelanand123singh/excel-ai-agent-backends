from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.cache import get_redis_client
from app.services.vector_store.similarity_search import search as semantic_search
from app.services.query_engine.ai_client import ask_llm
from app.models.database.query import Query as QueryModel
from app.services.query_engine.query_classifier import classify
from app.services.query_engine.intent_recognizer import extract_intents
from app.services.query_engine.context_manager import add_message, get_history
from app.services.query_engine.response_generator import fuse
from app.services.query_engine.confidence_scorer import score as score_confidence


def _guess_table_name(file_id: int) -> str:
    return f"ds_{file_id}"


def _generate_sql(question: str, table: str) -> str:
    # Prompt LLM to produce a safe SQL limited to the given table
    prompt = (
        "You are an assistant that translates a user question into a single ANSI SQL query. "
        f"Use only the table named {table}. "
        "Return ONLY the SQL without explanation. Limit rows to 50. Avoid dangerous statements."
        f"\nQuestion: {question}\nSQL:"
    )
    sql = ask_llm(prompt).strip().strip("` ")
    # Guardrails: ensure basic shape
    if not sql.lower().startswith("select") or table not in sql:
        # Fallback heuristics
        q = question.lower()
        if "count" in q:
            return f"SELECT COUNT(*) as count FROM {table}"
        if "sum" in q and "amount" in q:
            return f"SELECT COALESCE(SUM(amount),0) as sum_amount FROM {table}"
        return f"SELECT * FROM {table} LIMIT 50"
    # Ensure a LIMIT exists
    if " limit " not in sql.lower():
        sql += " LIMIT 50"
    return sql


def _run_sql(db: Session, sql: str) -> List[Dict[str, Any]]:
    result = db.execute(text(sql))
    rows = [dict(r._mapping) for r in result]
    return rows


def answer_question(db: Session, user_id: int, question: str, file_id: int) -> Dict[str, Any]:
    import time
    import asyncio
    import json
    from concurrent.futures import ThreadPoolExecutor
    
    start_time = time.perf_counter()
    cache = get_redis_client()
    cache_key = f"q:{user_id}:{file_id}:{hash(question)}"
    
    # Check cache first
    cached = cache.get(cache_key)
    if cached:
        result = json.loads(cached)
        result["cached"] = True
        result["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
        return result

    # Fast heuristic classification (avoid LLM call for common patterns)
    route = _fast_classify(question)
    table = _guess_table_name(file_id)
    
    # Parallel processing for better performance
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit tasks in parallel
        sql_future = executor.submit(_get_sql_results, question, table, route, db)
        semantic_future = executor.submit(_get_semantic_results, question, file_id, route)
        intents_future = executor.submit(_get_intents, question)
        
        # Wait for results
        sql_rows = sql_future.result()
        semantic_results = semantic_future.result()
        intents = intents_future.result()

    latency_ms = int((time.perf_counter() - start_time) * 1000)
    fused = fuse(sql_rows, semantic_results)
    confidence = score_confidence(len(sql_rows), semantic_results)
    answer_text = f"Found {fused['summary']['sql_count']} rows and {fused['summary']['semantic_count']} semantic matches"
    
    result = {
        "answer": answer_text,
        "cached": False,
        "route": route,
        "intents": intents,
        "sql": {"query": intents.get('generated_sql', ''), "rows": sql_rows[:20]},
        "semantic": semantic_results,
        "fused": fused,
        "confidence": confidence,
        "latency_ms": latency_ms,
    }
    
    # Cache the full result for 10 minutes
    cache.setex(cache_key, 600, json.dumps(result))
    
    # Async persistence (don't block response)
    try:
        rec = QueryModel(user_id=user_id, question=question, response=answer_text, latency_ms=latency_ms)
        db.add(rec)
        db.commit()
    except Exception:
        db.rollback()
    
    return result


def _fast_classify(question: str) -> str:
    """Fast heuristic classification without LLM calls."""
    q = question.lower()
    structured_keywords = ["count", "sum", "avg", "average", "min", "max", "group by", "top", "median", "percentile", "total", "how many"]
    semantic_keywords = ["similar", "about", "relevant", "find text", "contains", "meaning", "search", "what is", "explain"]
    
    has_structured = any(k in q for k in structured_keywords)
    has_semantic = any(k in q for k in semantic_keywords)
    
    if has_structured and has_semantic:
        return "hybrid"
    elif has_structured:
        return "structured"
    elif has_semantic:
        return "semantic"
    else:
        return "hybrid"  # Default to hybrid for unknown patterns


def _get_sql_results(question: str, table: str, route: str, db: Session) -> List[Dict[str, Any]]:
    """Get SQL results with optimized query generation."""
    if route not in ("structured", "hybrid"):
        return []
    
    sql = _generate_fast_sql(question, table)
    try:
        return _run_sql(db, sql)
    except Exception:
        return []


def _get_semantic_results(question: str, file_id: int, route: str) -> List[Dict]:
    """Get semantic search results."""
    if route not in ("semantic", "hybrid"):
        return []
    
    collection = f"ds_{file_id}"
    try:
        return semantic_search(question, top_k=5, collection_name=collection)
    except Exception:
        return []


def _get_intents(question: str) -> Dict:
    """Get intents with fallback to fast heuristics."""
    try:
        return extract_intents(question)
    except Exception:
        # Fast fallback
        q = question.lower()
        return {
            "metrics": ["count"] if "count" in q else [],
            "filters": [],
            "group_by": [],
            "limit": 50,
            "generated_sql": _generate_fast_sql(question, "table")
        }


def _generate_fast_sql(question: str, table: str) -> str:
    """Generate SQL using fast heuristics instead of LLM."""
    q = question.lower()
    
    # Common patterns
    if "count" in q:
        if "group by" in q:
            # Extract group by field (simple heuristic)
            words = q.split()
            group_idx = words.index("by") if "by" in words else -1
            if group_idx > 0 and group_idx < len(words) - 1:
                group_field = words[group_idx + 1]
                return f"SELECT {group_field}, COUNT(*) as count FROM {table} GROUP BY {group_field} LIMIT 50"
            else:
                return f"SELECT COUNT(*) as count FROM {table}"
        else:
            return f"SELECT COUNT(*) as count FROM {table}"
    
    if "sum" in q and "amount" in q:
        return f"SELECT COALESCE(SUM(amount), 0) as sum_amount FROM {table}"
    
    if "average" in q or "avg" in q:
        return f"SELECT AVG(amount) as avg_amount FROM {table}"
    
    if "top" in q or "highest" in q:
        return f"SELECT * FROM {table} ORDER BY amount DESC LIMIT 10"
    
    if "lowest" in q or "min" in q:
        return f"SELECT * FROM {table} ORDER BY amount ASC LIMIT 10"
    
    # Default: return sample data
    return f"SELECT * FROM {table} LIMIT 50"


