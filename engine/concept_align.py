"""개념 canon-aware 정렬 — 새 앱 하위개념을 기존 공유 그래프 정본에 병합(사일로 방지).

게이트(전부 결정론):
  ① 병합 대상이 정본 인덱스에 실재해야(지어낸 앵커 거부 = 관계 왕복 게이트에 해당).
  ② 명단(new_subconcepts) 밖 sid 제안은 error(phantom 방어).
  ③ 전건 커버·분할(각 하위개념은 merged/new/ambiguous 중 정확히 하나).
under-merge 규율: 낮은 확신(low) 병합은 자동 병합 않고 ambiguous로 flag(소유자 검토).
commitment(성숙도)는 가변이되 개념 어휘(같은 개념=같은 정본)는 정형화 — [[uncertainty-carrying-methodology]]."""
from __future__ import annotations


def align_concepts(proposals, canonical_index, new_subconcepts):
    """proposals: [{sid, target: <정본앵커>|"NEW"|"AMBIGUOUS", confidence, evidence?}].
    canonical_index: 유효한 정본 앵커 집합. new_subconcepts: 커버되어야 할 sid 명단."""
    valid = set(new_subconcepts)
    merged, new, ambiguous, errors, syn = [], [], [], [], {}
    seen = set()
    for p in proposals:
        sid = p.get("sid")
        if sid not in valid:
            errors.append({"sid": sid, "reason": "명단 밖 sid(phantom)"})
            continue
        if sid in seen:
            errors.append({"sid": sid, "reason": "중복 제안"})
            continue
        seen.add(sid)
        target = p.get("target")
        conf = p.get("confidence", "low")
        if target in ("NEW", None):
            new.append({**p})
        elif target == "AMBIGUOUS":
            ambiguous.append({**p})
        elif target in canonical_index:
            if conf == "low":                         # under-merge: 낮은 확신은 flag
                ambiguous.append({**p, "downgraded": True})
            else:
                merged.append({**p})
                syn[sid] = target                     # provenance: 새 표면 → 정본
        else:
            errors.append({"sid": sid, "reason": f"정본 인덱스에 없는 대상 '{target}'(지어냄)"})
    uncovered = valid - seen
    for sid in uncovered:
        errors.append({"sid": sid, "reason": "미제안(누락)"})
    return {"merged": merged, "new": new, "ambiguous": ambiguous,
            "synonym_record": syn, "errors": errors,
            "stats": {"n": len(valid), "merged": len(merged), "new": len(new),
                      "ambiguous": len(ambiguous), "errors": len(errors)}}
