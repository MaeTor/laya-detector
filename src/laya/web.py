"""Web UI: step 1 builds segments (text or audio), step 2 analyzes them."""
import tempfile
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from laya import segments as S
from laya.pipeline import analyze

STATIC = Path(__file__).parent / "static"
load_dotenv()
app = FastAPI(title="laya")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@cache
def get_scorer():
    from laya.scorer import Scorer
    return Scorer()


@cache
def get_evidence():
    from laya.evidence import Evidence
    return Evidence()


def get_transcriber():
    from laya.transcribe import transcribe
    return transcribe


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/segments")
def build_segments(text: str = Form(""), audio: UploadFile | None = File(None), whisper_size: str = Form("small"),
                   transcribe=Depends(get_transcriber)):
    from laya.transcribe import TranscribeError
    if audio is None or not audio.filename:
        if not text.strip():
            raise HTTPException(400, "Paste a transcript or choose an audio file.")
        return {"segments": S.parse_text(text)}
    with tempfile.NamedTemporaryFile(suffix=Path(audio.filename).suffix) as f:
        f.write(audio.file.read())
        f.flush()
        try:
            return {"segments": transcribe(f.name, whisper_size)}
        except TranscribeError as e:
            raise HTTPException(400, f"Could not read the audio file: {e}")


class Segment(BaseModel):
    id: int
    t0: float | None = None
    t1: float | None = None
    lang: str = "en"
    original: str
    english: str
    role: str


class AnalyzeRequest(BaseModel):
    segments: list[Segment]


@app.post("/api/analyze")
def run(req: AnalyzeRequest, scorer=Depends(get_scorer), evidence=Depends(get_evidence)):
    segs = [s.model_dump() for s in req.segments]
    bad = [s["id"] for s in segs if s["role"] not in S.ROLES]
    if bad:
        raise HTTPException(400, f"Unknown role on segments {bad}; use one of {S.ROLES}.")
    return analyze(segs, scorer, evidence)
