from conftest import FakeEvidence, FakeScorer
from fastapi.testclient import TestClient

from laya import web
from laya.transcribe import TranscribeError

web.app.dependency_overrides[web.get_scorer] = FakeScorer
web.app.dependency_overrides[web.get_evidence] = lambda: FakeEvidence(enabled=False)
client = TestClient(web.app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200 and "laya" in r.text


def test_segments_from_text_then_analyze():
    segs = client.post("/api/segments", data={"text": "Q: Where?\nA: At home all night."}).json()["segments"]
    assert [s["role"] for s in segs] == ["interviewer", "witness"]
    r = client.post("/api/analyze", json={"segments": segs})
    assert r.status_code == 200
    assert r.json()["claims"][0]["verdict"] == "evidence_unavailable"


def test_segments_requires_input():
    assert client.post("/api/segments", data={"text": "  "}).status_code == 400


def test_bad_audio_is_400():
    def broken(path, size):
        raise TranscribeError("cannot decode")
    web.app.dependency_overrides[web.get_transcriber] = lambda: broken
    try:
        r = client.post("/api/segments", files={"audio": ("x.wav", b"junk", "audio/wav")})
    finally:
        del web.app.dependency_overrides[web.get_transcriber]
    assert r.status_code == 400 and "audio" in r.json()["detail"]


def test_unknown_role_rejected():
    seg = {"id": 0, "original": "x", "english": "x", "role": "judge"}
    assert client.post("/api/analyze", json={"segments": [seg]}).status_code == 400
