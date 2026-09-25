"""Segments: the unit every later stage reads. Built from text lines or from a transcription."""
import re

ROLES = ("interviewer", "witness")
_PREFIX = re.compile(r"^\s*([QA])\s*:\s*", re.IGNORECASE)


def segment(id, english, role="witness", original=None, lang="en", t0=None, t1=None):
    return {"id": id, "t0": t0, "t1": t1, "lang": lang, "original": original if original is not None else english,
            "english": english, "role": role}


def parse_text(text):
    """One segment per non-blank line. `Q:` marks the interviewer, `A:` the witness; an unprefixed line keeps the role of
    the line before it (witness at the start)."""
    out, role = [], "witness"
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _PREFIX.match(line)
        if m:
            role = "interviewer" if m.group(1).upper() == "Q" else "witness"
            line = line[m.end():]
        out.append(segment(len(out), line.strip(), role))
    return out


def turns(segments):
    """Interviewer→witness pairs: each interviewer segment with the witness segments right after it, joined.
    -> [(question segment, first answer segment id, answer text)]"""
    out = []
    for i, s in enumerate(segments):
        if s["role"] != "interviewer":
            continue
        answer = []
        for t in segments[i + 1:]:
            if t["role"] != "witness":
                break
            answer.append(t)
        if answer:
            out.append((s, answer[0]["id"], " ".join(t["english"] for t in answer)))
    return out
