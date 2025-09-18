from __future__ import annotations

from typing import Any, Dict, List


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def validate_row(row: Dict[str, Any], required_fields: List[str] | None = None, max_str_len: int = 4000) -> bool:
    """Basic row validation.
    - Ensures required fields are present and non-null
    - Rejects strings above max_str_len
    - Allows scalars and JSON-serializable objects (dict/list)
    """
    if row is None or not isinstance(row, dict):
        return False
    # Required fields check
    if required_fields:
        for field in required_fields:
            if field not in row or row[field] is None or (isinstance(row[field], str) and row[field].strip() == ""):
                return False
    for key, value in row.items():
        # Limit string size
        if isinstance(value, str) and len(value) > max_str_len:
            return False
        # Scalars OK; dict/list OK for JSONB
        if not (_is_scalar(value) or isinstance(value, (dict, list))):
            return False
    return True


