"""Rule-based claim candidates: witness statements (not questions) of at least three words."""
import re

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"“'(A-Z0-9])")


def split_sentences(text):
    return [s.strip() for s in _SPLIT.split(text) if len(s.split()) >= 3 and not s.strip().endswith("?")]


def candidates(segments):
    """-> [(segment id, sentence)] for every witness segment."""
    return [(s["id"], sent) for s in segments if s["role"] == "witness" for sent in split_sentences(s["english"])]
