"""segments -> report. Every score in the report comes from the Scorer (decider-2b)."""
from laya import claims as C
from laya.evidence import EvidenceError
from laya.segments import turns

CHECKABLE_MIN = 0.5
UNSOURCED_WEIGHT = 0.5


def aggregate(passages):
    """Claim verdict from scored passages (a decision rule over calibrated per-passage probabilities).
    -> (verdict, deciding passage index or None)"""
    if not passages:
        return "evidence_unavailable", None
    if all(p["p"]["not_covered"] > 0.5 for p in passages):
        return "not_covered", None

    def strength(p):
        return (1.0 if p["sourced"] else UNSOURCED_WEIGHT) * max(p["p"]["supports"], p["p"]["contradicts"])

    i = max(range(len(passages)), key=lambda j: strength(passages[j]))
    p = passages[i]["p"]
    return ("supported" if p["supports"] >= p["contradicts"] else "contradicted"), i


def analyze(segments, scorer, evidence):
    notes = []
    if not evidence.enabled:
        notes.append("OPENROUTER_API_KEY is not set: no evidence was fetched.")

    cands = C.candidates(segments)
    checkable = scorer.checkable([s for _, s in cands])
    claims = []
    for (seg, text), chk in zip(cands, checkable):
        claim = {"id": len(claims), "segment": seg, "text": text, "checkable": chk, "verdict": "not_checkable",
                 "deciding_passage": None, "passages": []}
        claims.append(claim)
        if chk < CHECKABLE_MIN:
            continue
        passages = []
        if evidence.enabled:
            try:
                passages = evidence.fetch(text)
            except EvidenceError as e:
                notes.append(f"Evidence failed for claim {claim['id']}: {e}")
        if passages:
            for p, probs in zip(passages, scorer.verify(text, [p["text"] for p in passages])):
                p["p"] = probs
        claim["passages"] = passages
        claim["verdict"], claim["deciding_passage"] = aggregate(passages)

    pairs = turns(segments)
    if not pairs:
        notes.append("No interviewer→witness turns: evasion was not scored.")
    evasion = [{"question_segment": q["id"], "answer_segment": a, "evasion": scorer.evasion(q["english"], answer)}
               for q, a, answer in pairs]

    return {"calibrated": scorer.calibrated, "model": scorer.model, "evidence_model": evidence.model, "notes": notes,
            "segments": segments, "claims": claims, "evasion": evasion}
