import re


_SPACE_RE = re.compile(r"\s+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_PUNCT_GLUE_RE = re.compile(r"([.!?,:;])(?=[A-Za-z])")
_SENTENCE_START_RE = re.compile(r"(^|(?<=[.!?]\s))([a-z])")


def normalize_transcript(text: str) -> str:
    cleaned = text.strip()
    cleaned = _CAMEL_RE.sub(" ", cleaned)
    cleaned = _PUNCT_GLUE_RE.sub(r"\1 ", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned)
    if not cleaned:
        return ""
    cleaned = _SENTENCE_START_RE.sub(lambda m: f"{m.group(1)}{m.group(2).upper()}", cleaned)
    return cleaned
