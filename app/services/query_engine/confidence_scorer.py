from __future__ import annotations

from typing import List, Dict


def score(sql_rows_count: int, semantic_matches: List[Dict]) -> float:
    s = 0.0
    # Reward presence of SQL results
    if sql_rows_count > 0:
        s += 0.5
        if sql_rows_count > 10:
            s += 0.1
    # Reward semantic matches
    if semantic_matches:
        s += 0.3
        if len(semantic_matches) > 3:
            s += 0.1
    # Clamp 0..1
    return max(0.0, min(1.0, s))



