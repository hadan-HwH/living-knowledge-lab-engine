"""스켈레톤 → reducer events 매핑 (Track-E-lite 2단계).

parsers.py(Tier A)가 뽑은 결정 스켈레톤을 A-reducer가 소비하는 후보 event 원장으로 투영한다.
extraction-strategy 원칙 그대로: **신뢰 가능한 구조(체인·날짜·anchor)만 자동, 의미는 flag.**

  - target/option은 anchor 기반 placeholder(`{prefix}.T.{base}` / `o_{D-N}`)다.
    실제 의미 target(예: INV.disabled_state_name)으로의 개명은 owner adjudication —
    그래서 모든 event에 `confidence: proposal`을 박는다.
  - supersede 체인은 base anchor로 접어 한 target 위에 올린다 (ingest_wevolley와 동일 규칙).
  - 못 정하는 것(취소선인데 관계 없음·dangling·fan-in/out)은 지어내지 않고 flags로 남긴다.

출력은 확정이 아니라 제안(proposal) 원장이다. reducer에 바로 넣어 자동 대조는 가능하되,
gold 승격은 adjudication을 거친 뒤에만 한다.
"""
from __future__ import annotations

import re
from collections import Counter

# 내용 셀 변경 마커 — 코퍼스 실측(205행 중 구조 마커 1 vs 내용 마커 32)이 근거.
# 자동 관계 생성이 아니라 adjudication 후보 flag 전용 (Track-E-lite: 의미는 안 지어냄).
_CHANGE_MARKER = re.compile(r"정정|폐기|대체|번복|취소|재정의|재통합|supersede")
_DECISION_REF = re.compile(r"D-\d+")


def skeleton_to_events(parsed, prefix, corpus=None):
    """parse() 출력 → {"events": [...], "flags": [...]}.

    events는 reducer.project_authority가 그대로 fold할 수 있는 필드를 갖춘다.
    flags는 owner adjudication이 필요한 지점의 사람용 문장 목록이다.
    """
    decisions = parsed.get("decisions", [])
    by_id = {d["decision_id"]: d for d in decisions}
    flags = []

    # 0. epoch 별칭 정규화 — 앵커는 신 스킴(<APP>-D-N)인데 취소선·비고 셀은 구 스킴(D-N)으로
    #    가리키는 혼재가 실 코퍼스에 있다(aa0a005 inv: D-7318 행이 "**D-8812로 정정**").
    #    정규화 없이는 구형 참조가 dangling으로 떨어져 **supersede가 조용히 소실**된다
    #    (false-current 직결). 접두사는 이 로그에서 관측 유도 — 하드코딩 없음.
    #    정규화 후 같은 관계가 두 표기로 중복될 수 있어 순서 보존 dedup까지가 한 벌이다
    #    (안 접으면 fan-in 오탐 → usable에서 빠져 관계가 또 소실).
    from decision_alias import canonical, scope_prefix_map
    prefix_map = scope_prefix_map(decisions)
    scope_of = {d["decision_id"]: d.get("scope") for d in decisions}

    def _canon(ref, peer):
        """ref를 정본 표기로. scope는 ref 자신의 것이 없으면(구형 미등록) 상대편에서 빌린다
        — 관계의 두 항은 같은 결정 로그(=같은 scope)에서 온다."""
        return canonical(ref, scope_of.get(ref) or scope_of.get(peer), prefix_map)

    rels, seen_rel = [], set()
    for newer, older in parsed.get("supersede_relations", []):
        pair = (_canon(newer, older), _canon(older, newer))
        if pair not in seen_rel:
            seen_rel.add(pair)
            rels.append(pair)

    # 1. 관계 선별 — 모르는 anchor·모호한 위상은 자동 원장에서 제외하고 flag
    valid = []
    for newer, older in rels:
        if newer not in by_id or older not in by_id:
            flags.append(f"dangling: ({newer} → {older}) 미지 anchor — 관계 미반영, adjudication 필요")
            continue
        valid.append((newer, older))
    fan_in = {n for n, c in Counter(n for n, _ in valid).items() if c > 1}
    fan_out = {o for o, c in Counter(o for _, o in valid).items() if c > 1}
    for n in sorted(fan_in):
        flags.append(f"fan-in: {n}이 복수 결정을 supersede — target 병합/축 분해 모호, adjudication 필요")
    for o in sorted(fan_out):
        flags.append(f"fan-out: {o}를 복수 결정이 supersede — 부분/축 supersede 의심, adjudication 필요")
    usable = [(n, o) for n, o in valid if n not in fan_in and o not in fan_out]

    supersedes_map = {n: o for n, o in usable}         # newer -> older

    def _base(idx):                                    # 체인을 원조 결정까지 따라 내려간다
        seen = set()
        while idx in supersedes_map and idx not in seen:
            seen.add(idx)
            idx = supersedes_map[idx]
        return idx

    superseded_anchors = {o for _, o in usable}

    # 2. 결정 → 후보 event (스켈레톤이 아는 것만; 의미 명명은 proposal)
    events = []
    for d in decisions:
        did = d["decision_id"]
        ev = {
            "event_id": f"{prefix}.auto.{did}",
            "type": "supersede" if did in supersedes_map else "adopt",
            "target": f"{prefix}.T.{_base(did)}",
            "option": f"o_{did}",
            "authority_level": "product",              # 스켈레톤은 위임 위계를 모름 — 기본값
            "scope": d.get("scope"),
            "valid_at": d.get("date"),
            "recorded_at": d.get("date"),              # 로그 재구성 시점은 adjudication에서 정정
            "source": [did],
            "articles": d.get("articles", []),
            "confidence": "proposal",
        }
        if corpus:
            ev["corpus"] = corpus
        if did in supersedes_map:
            ev["supersedes"] = f"o_{supersedes_map[did]}"
        events.append(ev)

        # 취소선(죽음 힌트)인데 아무도 이 결정을 supersede하지 않음 → 종결 행위 미상
        if "~~" in (d.get("status") or "") and did not in superseded_anchors:
            flags.append(f"lifecycle 미상: {did} 취소선인데 supersede 관계 없음 — "
                         f"종결 행위(revoke/supersede) adjudication 필요 (현재 원장상 false-current 위험)")

        # 내용 셀 변경 마커 → 관계 후보 flag (구조 관계로 이미 잡힌 결정은 중복 flag 안 함)
        content = d.get("content") or ""
        if _CHANGE_MARKER.search(content) and did not in supersedes_map:
            refs = sorted({x for x in _DECISION_REF.findall(content) if x != did})
            if refs:
                flags.append(f"content 관계 후보: {did} 내용이 {', '.join(refs)} 언급+변경 마커 — "
                             f"supersede/부분/정정 여부 adjudication 필요")
            else:
                flags.append(f"content 변경 마커: {did} 내용에 변경 표현(대상 결정 미상 — "
                             f"정책서 조항 폐기 등 cross-artifact 가능) — adjudication 필요")

    events.sort(key=lambda e: (str(e.get("valid_at")), e["event_id"]))
    return {"events": events, "flags": flags}
