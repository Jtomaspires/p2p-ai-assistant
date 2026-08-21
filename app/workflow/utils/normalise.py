"""Invoice-reference normalization."""

import re


def normalize_reference(reference: str | None) -> str:
    """Remove common separators and OCR noise, then uppercase the reference."""
    if not reference:
        return ""
    cleaned = re.sub(r"[/\-_.\s]", "", reference)
    cleaned = re.sub(r"[*#]", "", cleaned)
    return cleaned.upper()
