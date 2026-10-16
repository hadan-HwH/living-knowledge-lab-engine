"""결정 ID 별칭 층 — 1회성 epoch 경계 (설계: docs/2-method/decision-axis-design.md §2.1).

소유자의 전 문서·결정 고유번호 부여(`D-N`→`<APP>-D-N`, 전역 고유·스킴 안정 선언)를
읽기 시점 정규화로 흡수한다. 원장(gold·구 스냅샷·판정)은 무수정 — 상시 마이그레이션
기구가 아니라 epoch 경계(≤5a0a004 구 스킴 / ≥0a0a001 신 스킴) 전용.

scope→접두사는 하드코딩 없이 그 scope의 결정 로그 행에서 관측 유도(데이터-선언 원칙).
"""
from __future__ import annotations

import re

FULL = re.compile(r"^([A-Z][A-Z0-9]*)-D-\d+$")     # 신 스킴 <APP>-D-N
SHORT = re.compile(r"^D-\d+$")                     # 구 스킴 D-N
REF = re.compile(r"\b(?:[A-Z][A-Z0-9]*-)?D-\d+\b")   # 텍스트 추출용(전체형 우선 매치)


def is_decision_ref(s):
    """전체형·구형 결정 참조인가 (조항 ID는 아님)."""
    return bool(FULL.match(s) or SHORT.match(s))


def canonical(ref, scope, prefix_map):
    """정본 표기 — 전체형은 그대로(전역 고유), 구형은 scope 접두사로 승격.
    접두사 미상 scope(잔존 구 스킴 로그)는 구형 유지(scope 내 대조로 후퇴)."""
    if FULL.match(ref):
        return ref
    prefix = prefix_map.get(scope)
    return f"{prefix}-{ref}" if prefix and SHORT.match(ref) else ref


def variants(ref, scope, prefix_map):
    """매칭용 양형 집합 — 원장(구형 표기)과 신 스냅샷(전체형)을 무수정으로 잇는다."""
    m = FULL.match(ref)
    if m:
        return {ref, ref[len(m.group(1)) + 1:]}
    return {ref, canonical(ref, scope, prefix_map)}


def scope_prefix_map(decisions):
    """파싱된 결정 로그에서 scope→접두사 관측 유도. 전체형 ID가 있는 scope만,
    단일 접두사로 수렴할 때만 채택(혼재 scope는 미상 처리 — 지어내지 않기)."""
    seen = {}
    for d in decisions:
        m = FULL.match(d["decision_id"])
        if m:
            seen.setdefault(d.get("scope"), set()).add(m.group(1))
    return {s: next(iter(p)) for s, p in seen.items() if len(p) == 1}
