from __future__ import annotations

from typing import Dict, List, Any, Tuple


# Canonical header names as confirmed by the user
CANONICAL_HEADERS_ORDERED: List[str] = [
    "Potential Buyer 1",
    "Item_Description",
    "Quantity",
    "UQC",
    "Unit_Price",
    "Potential Buyer 2",
    "Potential Buyer 1 Contact Details",
    "Potential Buyer 1 email id",
]


def expected_headers() -> List[str]:
    return CANONICAL_HEADERS_ORDERED.copy()


def validate_headers(incoming_headers: List[str]) -> Tuple[bool, str]:
    # Trim and normalize
    normalized = [str(h).strip() for h in incoming_headers]
    expected = expected_headers()
    missing = [h for h in expected if h not in normalized]
    if missing:
        return False, f"Header mismatch. Missing required headers: {missing}. Got: {normalized}"
    # Order or extra columns do not fail ingestion
    return True, ""


def derive_part_number(item_description: Any) -> str | None:
    if not isinstance(item_description, str):
        return None
    # Heuristic: take the longest token with letters+digits and at least 3 chars
    tokens = [t.strip(" ,;:\t\n\r()[]{}") for t in item_description.split()]
    candidates = [t for t in tokens if any(c.isalpha() for c in t) and any(c.isdigit() for c in t) and len(t) >= 3]
    if not candidates:
        # fallback: first token >= 3
        candidates = [t for t in tokens if len(t) >= 3]
    return candidates[0] if candidates else None


def normalize_and_validate_row(row: Dict[str, Any]) -> Dict[str, Any]:
    # Keep only canonical columns; fill missing as None
    normalized: Dict[str, Any] = {h: row.get(h) for h in CANONICAL_HEADERS_ORDERED}
    # Coerce Quantity to int when possible
    q = normalized.get("Quantity")
    if isinstance(q, str):
        s = q.replace(",", "").strip()
        try:
            normalized["Quantity"] = int(float(s))
        except Exception:
            pass
    # Coerce Unit_Price to float when possible
    up = normalized.get("Unit_Price")
    if isinstance(up, str):
        s = up.replace(",", "").strip()
        try:
            normalized["Unit_Price"] = float(s)
        except Exception:
            pass
    # Derive part_number from Item_Description
    part = derive_part_number(normalized.get("Item_Description"))
    normalized["part_number"] = part
    return normalized

