"""Temperatures fitted on labelled claim/evidence rows, written to calibration.json and read by the Scorer."""
import json
from pathlib import Path

PATH = Path("calibration.json")


def load(path=PATH):
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text())["temperature_by_type"]


def fit(data_path, out=PATH, model=None, min_rows=50):
    """data_path: JSON lines {"claim", "evidence", "label"} with label one of scorer.VERDICTS."""
    from decider.calibrate import collect, fit_by_type
    from decider.infer import Decider
    from laya import scorer

    examples = []
    for line in Path(data_path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["label"] not in scorer.VERDICTS:
            raise ValueError(f"label must be one of {scorer.VERDICTS}, got {row['label']!r}")
        state, questions = scorer.verify_request(row["claim"], [row["evidence"]])
        examples.append((state, questions, {"p0": row["label"]}))
    fitted = fit_by_type(collect(Decider(model or scorer.MODEL), examples), min_rows)
    if not fitted["temperature_by_type"]:
        raise ValueError(f"need at least {min_rows} rows to fit, got {len(examples)}")
    Path(out).write_text(json.dumps(fitted, indent=1))
    return fitted
