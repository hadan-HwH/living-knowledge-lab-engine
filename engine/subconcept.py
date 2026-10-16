"""하위개념 분해 게이트 — 문서 안 여러 개념을 뽑되 불확실성을 가져간다(소유자 방법론
[[uncertainty-carrying-methodology]]). quote 왕복(지어냄 0) + commitment 어휘 강제.

commitment = 성숙도 축(representation-method의 commitment_level 계승):
  frozen(확정·동결) | working(적용 중) | hypothesis(제안·미검증) | exploratory(탐색·비전).
낮은 성숙도를 억지로 올리지 않는다 — "100% 확실"이라 굳히는 것을 경계.
"""
from __future__ import annotations

import re

COMMITMENT_VOCAB = ("frozen", "working", "hypothesis", "exploratory")


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def verify_subconcepts(subconcepts, sections, articles=None):
    """quote가 **이 회차에 준 원문 어디에든** 실재해야 채택. 어휘 위반은 별도 기록."""
    corpus = [_norm(s["text"]) for s in sections]
    for a in articles or []:
        corpus += [_norm(t.get("text") or "") for t in (a.get("texts") or [])]
    ok, rejected = [], []
    violations = {"commitment_vocab": [], "confidence_vocab": []}
    for sc in subconcepts:
        if sc.get("commitment") not in COMMITMENT_VOCAB:
            violations["commitment_vocab"].append(sc.get("anchor"))
        if sc.get("confidence") not in ("high", "medium", "low"):
            violations["confidence_vocab"].append(sc.get("anchor"))
        q = _norm(sc.get("quote", ""))
        if q and any(q in c for c in corpus):
            ok.append(sc)
        else:
            rejected.append({**sc, "verdict": "quote_not_found"})
    n = len(subconcepts)
    return {"ok": ok, "rejected": rejected,
            "totals": {"n": n, "ok": len(ok), "rejected": len(rejected),
                       "pass_rate": (len(ok) / n) if n else None},
            "contract_violations": violations}


def verify_relations(relations, subconcepts, sections):
    """하위개념 간 관계 게이트 — 자유 명명 어휘를 관찰(미리 고정 안 함), quote 왕복
    (관계가 원문 근거), 양끝 실재. 실패는 고치지 않고 기록. INV 관계 축 패턴 계승."""
    from collections import Counter
    sids = {s["sid"] for s in subconcepts}
    corpus = [_norm(s["text"]) for s in sections]
    ok, rejected, vocab = [], [], Counter()
    for r in relations:
        if r.get("from") not in sids or r.get("to") not in sids:
            rejected.append({**r, "verdict": "unknown_endpoint"})
            continue
        q = _norm(r.get("quote", ""))
        if not (q and any(q in c for c in corpus)):
            rejected.append({**r, "verdict": "quote_not_found"})
            continue
        vocab[r.get("rel") or "unknown"] += 1
        ok.append(r)
    n = len(relations)
    return {"ok": ok, "rejected": rejected, "vocab": dict(vocab),
            "totals": {"n": n, "ok": len(ok), "rejected": len(rejected),
                       "pass_rate": (len(ok) / n) if n else None}}
