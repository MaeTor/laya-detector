"""laya CLI: transcribe, analyze, serve, calibrate."""
import json
from pathlib import Path

import typer
from dotenv import load_dotenv

from laya import segments as S

app = typer.Typer(no_args_is_help=True, help="Evidence-consistency checker. Scores contradiction with sources and "
                                             "evasiveness; it does not detect lies.")
AUDIO_HELP = "faster-whisper model size (tiny, base, small, medium, large-v3)"


def load_segments(path, whisper_size):
    """.txt (Q:/A: lines), .json (segments from `laya transcribe`), anything else is read as audio."""
    from laya.transcribe import TranscribeError, transcribe
    if path.suffix == ".txt":
        return S.parse_text(path.read_text())
    if path.suffix == ".json":
        return json.loads(path.read_text())["segments"]
    try:
        return transcribe(path, whisper_size)
    except TranscribeError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


@app.command("transcribe")
def transcribe_cmd(audio: Path, out: Path = typer.Option(..., "-o", help="segments JSON; edit each role, then analyze it"),
                   whisper_size: str = typer.Option("small", help=AUDIO_HELP)):
    """Audio -> segments JSON (original + English). Set each segment's role to interviewer or witness."""
    segs = load_segments(audio, whisper_size)
    out.write_text(json.dumps({"segments": segs}, indent=1, ensure_ascii=False))
    typer.echo(f"{len(segs)} segments -> {out}")


def _pct(x):
    return f"{x * 100:5.1f}%"


def render(report):
    flag = "calibrated" if report["calibrated"] else "UNCALIBRATED"
    typer.echo(f"model {report['model']} ({flag}) · evidence {report['evidence_model']}\n")
    for n in report["notes"]:
        typer.echo(f"note: {n}")
    typer.echo("\nClaims")
    for c in report["claims"]:
        typer.echo(f"  [{c['verdict']:>20}] {c['text']}  (checkable {_pct(c['checkable'])})")
        for i, p in enumerate(c["passages"]):
            mark = "*" if i == c["deciding_passage"] else " "
            src = p["url"] or "unsourced LLM text"
            typer.echo(f"     {mark} sup {_pct(p['p']['supports'])} con {_pct(p['p']['contradicts'])} "
                       f"n/c {_pct(p['p']['not_covered'])}  {src}")
    typer.echo("\nEvasion")
    seg = {s["id"]: s for s in report["segments"]}
    for e in report["evasion"]:
        typer.echo(f"  {_pct(e['evasion'])}  Q: {seg[e['question_segment']]['english']}")


@app.command()
def analyze(path: Path, json_out: Path = typer.Option(None, "--json", help="write the full report here"),
            whisper_size: str = typer.Option("small", help=AUDIO_HELP)):
    """Score a .txt transcript (Q:/A: lines), a segments .json, or an audio file."""
    from laya.evidence import Evidence
    from laya.pipeline import analyze as run
    from laya.scorer import Scorer

    load_dotenv()
    report = run(load_segments(path, whisper_size), Scorer(), Evidence())
    if json_out:
        json_out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    render(report)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Web UI."""
    import uvicorn
    uvicorn.run("laya.web:app", host=host, port=port)


@app.command()
def calibrate(data: Path, out: Path = Path("calibration.json"), min_rows: int = 50):
    """Fit decider temperatures on JSON lines {"claim", "evidence", "label": supports|contradicts|not_covered}."""
    from laya.calibration import fit
    typer.echo(json.dumps(fit(data, out, min_rows=min_rows), indent=1))
