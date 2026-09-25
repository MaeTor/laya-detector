# laya-detector

Evidence-consistency checker for investigations, journalism and testimony review.

laya takes an interview (typed transcript or audio in any Whisper-supported language) and returns two kinds of score:

* **claims**: for each factual statement the witness makes, whether web evidence **supports** or **contradicts** it,
  with the sources and per-passage probabilities behind the verdict;
* **evasion**: for each question/answer turn, how directly the answer responds to the question, from 0 (direct) to 1
  (evades entirely).

Every score comes from one model, [decider-2b](https://github.com/Mapika/decider), running in-process. The web-search LLM
only gathers evidence passages; it never gives a verdict.

> [!IMPORTANT]
> laya does **not** detect lies. Its scores measure inconsistency with retrieved sources and evasiveness, not
> truthfulness or intent. They stay uncalibrated for this task until you run `laya calibrate` on labelled claims, and
> every report says so.

## How it works

| stage | component | output |
|---|---|---|
| Transcribe | faster-whisper, on-device (`transcribe` + `translate`) | segments with original text, English text, timings |
| Roles | `Q:` / `A:` prefixes, or edited by hand after transcription | each segment marked `interviewer` or `witness` |
| Claims | rule-based sentence split of witness speech, then decider-2b: *"checkable fact about the world?"* | candidate claims with a `checkable` probability |
| Evidence | OpenRouter LLM (`deepseek/deepseek-v4.1-flash`) with the `openrouter:web_search` tool | up to 5 passages per claim, with URL and title when cited |
| Verify | decider-2b choice per (claim, passage) | `P(supports)`, `P(contradicts)`, `P(not_covered)` |
| Evasion | decider-2b score per interviewer→witness turn, over 4 levels | expected level scaled to 0..1 |
| Report | JSON, rendered by the CLI and the web UI | claims, verdicts, sources, evasion, notes |

```
audio ─► transcribe ─► segments ─┬─► claims ─► evidence ─► verify ─┐
text  ─► parse Q:/A: ─┘          └─► evasion ──────────────────────┴─► report
```

decider-2b always reads the English text. Transcription and scoring run locally; CUDA, MPS or CPU is picked
automatically. Only evidence gathering calls the network.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env        # set OPENROUTER_API_KEY
```

Without a key everything still runs: claims are found and evasion is scored, but every checkable claim gets
`evidence_unavailable` and the report carries a note.

```bash
uv run laya analyze interview.txt
```

Output shape (illustrative values):

```
model Mapika/decider-2b (UNCALIBRATED) · evidence deepseek/deepseek-v4.1-flash

Claims
  [        contradicted] The bridge opened in 1998.  (checkable  94.0%)
     * sup   4.1% con  87.6% n/c   8.3%  https://example.org/bridge-history
       sup  12.0% con  41.2% n/c  46.8%  https://example.org/city-archive

Evasion
   71.3%  Q: Where were you on the night of the ninth?
```

## Usage

### Text transcripts

One segment per non-blank line. `Q:` marks the interviewer, `A:` the witness; an unprefixed line keeps the role of the
line before it (witness at the start).

```text
Q: Where were you on the night of the ninth?
A: I was at home. The bridge was closed that week anyway.
Q: Who can confirm that?
A: I don't see why that matters.
```

```bash
uv run laya analyze interview.txt --json report.json
```

### Audio

Transcribe first, set each segment's `role` to `interviewer` or `witness`, then analyze the segments file:

```bash
uv run laya transcribe interview.m4a -o segs.json --whisper-size small
# edit "role" in segs.json
uv run laya analyze segs.json --json report.json
```

Non-English audio keeps both texts: `original` in the detected language and `english` from Whisper's translation.
`--whisper-size` takes `tiny`, `base`, `small` (default), `medium` or `large-v3`.

`laya analyze` also accepts an audio file directly, but every segment then defaults to `witness`, so no evasion is scored.

### Web UI

```bash
uv run laya serve           # http://127.0.0.1:8000
```

Two steps on one page: paste text or upload audio and fix the roles, then analyze to get verdict chips, probability bars,
sources and evasion per turn. Light and dark themes, keyboard reachable, WCAG 2.2 AA contrast.

## Report

`--json` writes the full report, and `POST /api/analyze` returns the same shape:

```json
{
  "calibrated": false,
  "model": "Mapika/decider-2b",
  "evidence_model": "deepseek/deepseek-v4.1-flash",
  "notes": [],
  "segments": [{"id": 0, "t0": 1.2, "t1": 4.8, "lang": "fr", "original": "...", "english": "...", "role": "witness"}],
  "claims": [{
    "id": 0, "segment": 0, "text": "...", "checkable": 0.93,
    "verdict": "contradicted", "deciding_passage": 0,
    "passages": [{"text": "...", "url": "https://...", "title": "...", "sourced": true,
                  "p": {"supports": 0.05, "contradicts": 0.88, "not_covered": 0.07}}]
  }],
  "evasion": [{"question_segment": 3, "answer_segment": 4, "evasion": 0.71}]
}
```

### Claim verdicts

| verdict | meaning |
|---|---|
| `supported` / `contradicted` | the deciding passage's larger label |
| `not_covered` | every passage has `P(not_covered) > 0.5` |
| `evidence_unavailable` | no passages: no API key, or the evidence request failed (see `notes`) |
| `not_checkable` | `checkable < 0.5`; listed but not sent for evidence |

The deciding passage is the one with the highest `w · max(P(supports), P(contradicts))`, where `w = 1.0` for a cited
source and `0.5` for unsourced LLM text. This is a decision rule over the model's probabilities, not a model output.

## Calibration

decider-2b's probabilities are not tuned for testimony out of the box. Fit per-type temperatures on your own labelled
claims:

```jsonl
{"claim": "The bridge opened in 1998.", "evidence": "The bridge was inaugurated in May 2001.", "label": "contradicts"}
```

```bash
uv run laya calibrate labelled.jsonl     # 50+ rows; writes calibration.json
```

`label` is one of `supports`, `contradicts`, `not_covered`. The scorer loads `calibration.json` from the working
directory when present, and the report switches from `UNCALIBRATED` to `calibrated`. Calibration uses the same request
builders as scoring, so fitted temperatures match the questions actually asked.

## Configuration

| setting | where | default |
|---|---|---|
| `OPENROUTER_API_KEY` | `.env` | blank: evidence skipped |
| Whisper model size | `--whisper-size` / web form | `small` |
| Server address | `laya serve --host --port` | `127.0.0.1:8000` |
| Calibration file | `laya calibrate --out` | `calibration.json` |
| Minimum calibration rows | `laya calibrate --min-rows` | `50` |

## Development

```bash
uv sync
uv run pytest
```

Tests use a fake scorer and fake evidence, so they need no GPU and no network. Real models are exercised through the
CLI.

```
src/laya/
  cli.py          transcribe · analyze · serve · calibrate
  web.py          FastAPI app + static UI
  pipeline.py     segments -> report, verdict aggregation
  segments.py     text parsing, interviewer→witness turns
  transcribe.py   faster-whisper transcribe + translate
  claims.py       rule-based claim candidates
  evidence.py     OpenRouter web-search passages
  scorer.py       decider-2b requests
  calibration.py  temperature fitting
```

## Limitations

* **Not a lie detector.** A `contradicted` verdict means the retrieved sources disagree with the statement. Sources can
  be wrong, outdated or about something else.
* **Evidence is only as good as the search.** Each claim gets one LLM web search and at most five passages. Unsourced
  LLM text is kept but down-weighted.
* **Claim finding is rule-based.** Sentences of three or more words that are not questions become candidates; decider
  then filters for checkable facts. Claims split across sentences or implied by context are missed.
* **Roles matter.** Evasion needs interviewer→witness turns. Audio has no speaker diarization, so roles are set by hand.
* **English scoring.** Non-English speech is scored on Whisper's translation, and translation errors carry through.
* **Uncalibrated by default.** Treat probabilities as relative until you fit `calibration.json` on data like yours.
* **Privacy.** Claim text is sent to OpenRouter and its search provider. Transcripts, audio and scoring stay local.

## Licence

Code is [Apache-2.0](LICENSE). decider-2b, Whisper models and the OpenRouter models you use keep their own terms.
