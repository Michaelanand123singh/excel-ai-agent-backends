from __future__ import annotations

from typing import Any, Dict, List


def fuse(sql_rows: List[Dict[str, Any]], semantic_results: List[Dict], max_preview: int = 5) -> Dict[str, Any]:
    preview_rows = sql_rows[:max_preview] if sql_rows else []
    preview_sem = semantic_results[:max_preview] if semantic_results else []
    summary = {
        "sql_count": len(sql_rows),
        "semantic_count": len(semantic_results),
    }
    return {
        "summary": summary,
        "preview": {
            "sql_rows": preview_rows,
            "semantic": preview_sem,
        },
    }



