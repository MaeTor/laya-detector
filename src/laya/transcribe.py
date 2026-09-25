"""Audio -> segments with faster-whisper: the original-language text and its English translation."""
from laya.segments import segment

DEFAULT_SIZE = "small"


class TranscribeError(Exception):
    pass


def _original_for(t0, t1, originals):
    """Original-language text of the segments whose midpoint falls in [t0, t1]."""
    return " ".join(s.text.strip() for s in originals if t0 <= (s.start + s.end) / 2 <= t1)


def transcribe(path, size=DEFAULT_SIZE):
    from faster_whisper import WhisperModel

    model = WhisperModel(size)
    try:
        originals, info = model.transcribe(str(path), task="transcribe")
        originals = list(originals)
    except Exception as e:                       # PyAV raises several error types for undecodable input
        raise TranscribeError(f"cannot decode {path}: {e}") from e
    if info.language == "en":
        return [segment(i, s.text.strip(), t0=s.start, t1=s.end) for i, s in enumerate(originals)]
    english, _ = model.transcribe(str(path), task="translate", language=info.language)
    return [segment(i, s.text.strip(), original=_original_for(s.start, s.end, originals), lang=info.language,
                    t0=s.start, t1=s.end)
            for i, s in enumerate(english)]
