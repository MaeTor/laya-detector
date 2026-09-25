import pytest


class FakeScorer:
    model = "fake"
    calibrated = False

    def checkable(self, sentences):
        return [0.1 if s.lower().startswith("i think") else 0.9 for s in sentences]

    def verify(self, claim, passages):
        return [{"supports": 0.1, "contradicts": 0.8, "not_covered": 0.1} if "not" in p else
                {"supports": 0.7, "contradicts": 0.1, "not_covered": 0.2} for p in passages]

    def evasion(self, question, answer):
        return 0.6


class FakeEvidence:
    model = "fake-llm"

    def __init__(self, passages=None, enabled=True, error=None):
        self.passages, self.enabled, self.error = passages or [], enabled, error

    def fetch(self, claim):
        if self.error:
            raise self.error
        return [dict(p) for p in self.passages]


@pytest.fixture
def scorer():
    return FakeScorer()
