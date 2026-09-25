from conftest import FakeEvidence

from laya import claims, segments
from laya.evidence import EvidenceError, parse_passages
from laya.pipeline import aggregate, analyze

TRANSCRIPT = """Q: Where were you?
A: At home all night. Obama was the first black president in USA history.
I think so.
Q: Who was with you?
A: Why does that matter?"""


def test_parse_text_roles_and_continuation():
    s = segments.parse_text(TRANSCRIPT)
    assert [x["role"] for x in s] == ["interviewer", "witness", "witness", "interviewer", "witness"]
    assert s[1]["english"].startswith("At home")


def test_turns_join_consecutive_answers():
    t = segments.turns(segments.parse_text(TRANSCRIPT))
    assert [(q["id"], a) for q, a, _ in t] == [(0, 1), (3, 4)]
    assert t[0][2].endswith("I think so.")


def test_claim_candidates_only_witness_sentences():
    c = claims.candidates(segments.parse_text(TRANSCRIPT))
    assert c == [(1, "At home all night."), (1, "Obama was the first black president in USA history."),
                 (2, "I think so.")]


def p(sup, con, nc, sourced=True):
    return {"sourced": sourced, "p": {"supports": sup, "contradicts": con, "not_covered": nc}}


def test_aggregate_rules():
    assert aggregate([]) == ("evidence_unavailable", None)
    assert aggregate([p(.1, .1, .8), p(.2, .2, .6)]) == ("not_covered", None)
    assert aggregate([p(.7, .1, .2), p(.1, .8, .1)]) == ("contradicted", 1)
    # unsourced counts half: .9 * .5 < .6
    assert aggregate([p(.9, .05, .05, sourced=False), p(.05, .6, .35)]) == ("contradicted", 1)


def test_parse_passages_citations_and_fallback():
    msg = {"content": "Barack Obama became the first African American president in 2009.",
           "annotations": [{"type": "url_citation", "url_citation": {"url": "https://a", "title": "A", "start_index": 0, "end_index": 12}},
                           {"type": "url_citation", "url_citation": {"url": "https://a", "start_index": 0, "end_index": 5}},
                           {"type": "url_citation", "url_citation": {"url": "https://b", "content": "B body"}}]}
    out = parse_passages(msg)
    assert [(x["url"], x["text"], x["sourced"]) for x in out] == [("https://a", "Barack Obama", True), ("https://b", "B body", True)]
    assert parse_passages({"content": "plain", "annotations": []}) == [
        {"text": "plain", "url": None, "title": None, "sourced": False}]


def test_analyze_without_key(scorer):
    r = analyze(segments.parse_text(TRANSCRIPT), scorer, FakeEvidence(enabled=False))
    assert r["calibrated"] is False and "OPENROUTER_API_KEY" in r["notes"][0]
    verdicts = [c["verdict"] for c in r["claims"]]
    assert verdicts == ["evidence_unavailable", "evidence_unavailable", "not_checkable"]
    assert [e["evasion"] for e in r["evasion"]] == [0.6, 0.6]


def test_analyze_with_evidence(scorer):
    ev = FakeEvidence([{"text": "he was", "url": "https://x", "title": None, "sourced": True},
                       {"text": "he was not", "url": "https://y", "title": None, "sourced": True}])
    r = analyze(segments.parse_text("A: Obama was the first black president."), scorer, ev)
    c = r["claims"][0]
    assert c["verdict"] == "contradicted" and c["deciding_passage"] == 1 and c["passages"][1]["p"]["contradicts"] == 0.8
    assert "No interviewer" in r["notes"][0]


def test_analyze_evidence_error_continues(scorer):
    r = analyze(segments.parse_text("A: Obama was the first black president."), scorer,
                FakeEvidence(error=EvidenceError("HTTPStatusError: 401")))
    assert r["claims"][0]["verdict"] == "evidence_unavailable"
    assert any("401" in n for n in r["notes"])
