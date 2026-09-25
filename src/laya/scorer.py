"""decider-2b readouts. The request builders are shared with calibration so fitted temperatures match served questions."""
from laya import calibration

MODEL = "Mapika/decider-2b"
VERDICTS = ("supports", "contradicts", "not_covered")
EVASION_LEVELS = [
    "answers the question directly",
    "answers only part of the question",
    "deflects or changes the subject",
    "refuses or evades the question entirely",
]


def checkable_request(sentences):
    state = {"sentences": {f"s{i}": s for i, s in enumerate(sentences)}}
    questions = {f"s{i}": {"type": "noul",
                           "instructions": f"Does `sentences.s{i}` state a specific fact about the world that could be "
                                           "checked against a reliable source?"}
                 for i in range(len(sentences))}
    return state, questions


def verify_request(claim, passages):
    state = {"claim": claim, "evidence": {f"p{i}": p for i, p in enumerate(passages)}}
    criteria = {"supports": "The evidence states or directly implies that the claim is true",
                "contradicts": "The evidence states or directly implies that the claim is false",
                "not_covered": "The evidence does not say whether the claim is true or false"}
    questions = {f"p{i}": {"type": "choice", "criteria": criteria,
                           "instructions": f"Compared with `evidence.p{i}`, is `claim` supported, contradicted, "
                                           "or not covered?"}
                 for i in range(len(passages))}
    return state, questions


def evasion_request(question, answer):
    state = {"question": question, "answer": answer}
    questions = {"evasion": {"type": "score", "criteria": EVASION_LEVELS,
                             "instructions": "How does `answer` respond to `question`?"}}
    return state, questions


class Scorer:
    def __init__(self, model=MODEL, calibration_path=calibration.PATH):
        from decider.infer import Decider
        temps = calibration.load(calibration_path)
        self.model = model
        self.calibrated = temps is not None
        self.d = Decider(model)
        if temps:                                   # fitted types override, the model config keeps the others
            self.d.T_by_type = {**self.d.T_by_type, **temps}

    def _ask(self, request):
        return self.d.system_one(*request)["answers"]

    def checkable(self, sentences):
        if not sentences:
            return []
        a = self._ask(checkable_request(sentences))
        return [a[f"s{i}"]["noul"] for i in range(len(sentences))]

    def verify(self, claim, passages):
        """-> one {supports, contradicts, not_covered} probability dict per passage."""
        a = self._ask(verify_request(claim, passages))
        return [{k: a[f"p{i}"]["probabilities"][k] for k in VERDICTS} for i in range(len(passages))]

    def evasion(self, question, answer):
        """Expected evasion level scaled to 0..1."""
        return self._ask(evasion_request(question, answer))["evasion"]["score"] / (len(EVASION_LEVELS) - 1)
