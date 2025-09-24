from __future__ import annotations

from typing import Iterable, List, Tuple


# Central configuration for part number processing
PART_NUMBER_CONFIG: dict = {
    "separators": ['-', '/', ',', '*', '&', '~', '.', '%'],
    "min_similarity": 0.6,
    "db_batch_size": 5000,
    "token_min_overlap": 0.4,
    "format_variations": True,
    "enable_db_fuzzy": True,
    "max_response_time_ms": 2000,
    "use_parallel_search": True,
    "precompute_normalized": True,
}


def _is_separator(ch: str) -> bool:
    return ch in PART_NUMBER_CONFIG["separators"]


def normalize(text: str, level: int = 1) -> str:
    """Normalize a part number according to the requested level.

    level 1: original (trim + collapse inner spaces)
    level 2: remove configured separators only
    level 3: keep alphanumerics only
    """
    if text is None:
        return ""
    s = str(text).strip()
    if level <= 1:
        return " ".join(s.split())
    if level == 2:
        return "".join(ch for ch in s if not _is_separator(ch))
    # level >= 3
    return "".join(ch for ch in s if ch.isalnum())


def separator_tokenize(text: str) -> List[str]:
    """Split on configured separators and also extract alphanumeric chunks."""
    if not text:
        return []
    tokens: List[str] = []
    current = []
    for ch in text:
        if _is_separator(ch) or ch.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    # Further split each token into alphanumeric chunks
    chunks: List[str] = []
    for tok in tokens:
        buf: List[str] = []
        last_is_alnum = None
        for ch in tok:
            is_alnum = ch.isalnum()
            if last_is_alnum is None:
                buf.append(ch)
                last_is_alnum = is_alnum
            elif is_alnum == last_is_alnum:
                buf.append(ch)
            else:
                if buf:
                    chunks.append("".join(buf))
                buf = [ch]
                last_is_alnum = is_alnum
        if buf:
            chunks.append("".join(buf))
    # Filter empties
    return [c for c in chunks if c]


def levenshtein(a: str, b: str, max_distance: int | None = None) -> int:
    """Compute Levenshtein distance with optional early-exit bound."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure a is the shorter
    if len(a) > len(b):
        a, b = b, a
    previous_row = list(range(len(a) + 1))
    for i, bc in enumerate(b, start=1):
        current_row = [i]
        # Optional band: if max_distance is set, we can prune
        # Keep simple for now; early exit if growing beyond bound
        min_in_row = current_row[0]
        for j, ac in enumerate(a, start=1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (ac != bc)
            val = min(insertions, deletions, substitutions)
            current_row.append(val)
            if val < min_in_row:
                min_in_row = val
        previous_row = current_row
        if max_distance is not None and min(previous_row) > max_distance:
            # Exceeded band everywhere
            return max_distance + 1
    return previous_row[-1]


def similarity_score(a: str, b: str) -> float:
    """Return similarity in [0,1] based on Levenshtein over max length."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    d = levenshtein(a, b)
    m = max(len(a), len(b))
    if m == 0:
        return 1.0
    return 1.0 - (d / m)


def token_overlap(a_tokens: Iterable[str], b_tokens: Iterable[str]) -> float:
    a_set = {t.lower() for t in a_tokens if t}
    b_set = {t.lower() for t in b_tokens if t}
    if not a_set or not b_set:
        return 0.0
    inter = len(a_set & b_set)
    union = len(a_set | b_set)
    return inter / union if union else 0.0


def generate_format_variants(text: str) -> List[Tuple[str, int]]:
    """Return [(variant, normalization_level)] in progressive order."""
    l1 = normalize(text, 1)
    l2 = normalize(text, 2)
    l3 = normalize(text, 3)
    seen = set()
    out: List[Tuple[str, int]] = []
    for s, lvl in [(l1, 1), (l2, 2), (l3, 3)]:
        key = (s.lower(), lvl)
        if s and key not in seen:
            out.append((s, lvl))
            seen.add(key)
    return out


