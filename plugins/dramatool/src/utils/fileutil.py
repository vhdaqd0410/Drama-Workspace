from pathlib import Path


def parse_dropped_path(raw_text: str) -> Path | None:
    text = raw_text.strip().strip("\"'")
    if not text:
        return None
    candidate = Path(text)
    if candidate.exists():
        return candidate
    if text.startswith("file://"):
        parsed = Path(text[7:])
        if parsed.exists():
            return parsed
    return None
