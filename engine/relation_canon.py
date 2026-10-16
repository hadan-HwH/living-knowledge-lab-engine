"""관계 어휘 정형화 — 자유 추출 → 정본 수렴 (소유자 지적 2026-08-01).

"어휘를 자유롭게 냅두면 증식하는 바이러스 쓰레기. 같은 의미/개념인데 언어 표현만 다르면
정형화하는 자동화를 거쳐야 — 동의어를 기록 남기는 것과 별개로." → term_layer 원칙(정본 term
+ 표면 변이)을 관계에 적용.

구분(소유자): commitment(성숙도)=가변, 어휘(표현)=정형화 대상. 이 둘을 혼동 말 것.

메커니즘(전부 결정론):
  자유 추출(Tier B)이 표면 어휘를 뱉음 → canonicalize가 정본으로 매핑(동의어 사전) →
  역방향은 뒤집어 정본 방향 기록 → 미매핑은 버리지 않고 flag(정본 후보 = 점진 형식화).
동의어→정본 매핑은 synonym_record로 별도 보존(provenance).
"""
from __future__ import annotations


def canonicalize(relations, registry):
    """표면 rel → 정본. registry: {canonical: {synonyms:[...], inverse_of?: str}}.
    역방향 어휘는 from/to 뒤집어 정본 방향. 미매핑은 canonical=None + unmapped flag."""
    surf_to_canon = {}
    inverse_surfaces = {}
    for canon, spec in registry.items():
        for s in spec.get("synonyms", []):
            surf_to_canon[s] = canon
        inv = spec.get("inverse_of")
        if inv:
            inverse_surfaces[inv] = canon        # inv 표면 = canon의 역 → 뒤집어 canon
        for iv in spec.get("inverses", []):      # 정본당 역방향 다수(스케일에서 필수)
            inverse_surfaces[iv] = canon
    out, syn_record, unmapped = [], {}, []
    for r in relations:
        rel = r.get("rel")
        if rel in surf_to_canon:
            canon = surf_to_canon[rel]
            out.append({**r, "canonical": canon, "surface": rel})
            if rel != canon:
                syn_record[rel] = canon
        elif rel in inverse_surfaces:
            canon = inverse_surfaces[rel]
            out.append({**r, "from": r["to"], "to": r["from"],
                        "canonical": canon, "surface": rel, "flipped": True})
            syn_record[rel] = f"{canon} (inverse)"
        else:
            out.append({**r, "canonical": None, "surface": rel})
            if rel not in unmapped:
                unmapped.append(rel)
    return {"relations": out, "synonym_record": syn_record,
            "unmapped": unmapped,
            "stats": {"n": len(relations),
                      "canonicalized": sum(1 for o in out if o["canonical"]),
                      "unmapped": len(unmapped)}}



#: 계약이 허용한 제안 표기 — 미등록 어휘(계약 위반)와 구별해서 센다.
NEW_PROPOSAL = "NEW"


def registered_vocabulary(registry_doc):
    """canon-extensions.yaml 문서 → 유효 어휘 집합. **데이터 선언에서만** 온다.
    `not_a_relation`(관계가 아니라고 판정된 표면)은 어휘가 아니다 — 통과시키면 그 판정이
    무의미해진다."""
    core = set(registry_doc.get("core_13") or [])
    ext = {e.get("family") for e in (registry_doc.get("extensions") or []) if e.get("family")}
    return core | ext


def validate_vocabulary(relations, registry_doc):
    """관계 목록의 `canonical`을 등록 어휘와 대조. 결정론(정렬·중복 제거).

    반환: {ok, new_proposals, unregistered:[정렬된 미등록 어휘]}.
    ★NEW와 미등록을 가른다: NEW는 계약이 허용한 제안 절차(소유자 승격 대기)이고,
    미등록은 계약 위반이다. 섞으면 판정 큐가 오염된다.
    `canonical` 필드 자체가 없는 행도 조용히 통과시키지 않는다."""
    vocab = registered_vocabulary(registry_doc)
    ok = new = 0
    bad = set()
    for r in relations or []:
        c = r.get("canonical")
        if c == NEW_PROPOSAL:
            new += 1
        elif c in vocab:
            ok += 1
        else:
            bad.add(c if c else "(없음)")
    return {"ok": ok, "new_proposals": new, "unregistered": sorted(bad)}
