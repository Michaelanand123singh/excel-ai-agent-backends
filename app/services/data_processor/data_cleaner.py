from __future__ import annotations

from typing import Any, Dict
from app.services.data_processor.schema_def import normalize_and_validate_row


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    # Normalize strings
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        # Try boolean coercion
        low = stripped.lower()
        if low in ("true", "yes", "y", "1"):
            return True
        if low in ("false", "no", "n", "0"):
            return False
        # Try numeric coercion
        try:
            if "." in stripped or "e" in stripped.lower():
                return float(stripped)
            return int(stripped)
        except Exception:
            pass
        return stripped
    # Pass through primitives
    if isinstance(value, (int, float, bool)):
        return value
    # Leave dict/list as-is for JSONB columns
    return value


def clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
    base = {k: _clean_value(v) for k, v in (row or {}).items()}
    # Normalize to canonical schema and derive part_number
    return normalize_and_validate_row(base)


