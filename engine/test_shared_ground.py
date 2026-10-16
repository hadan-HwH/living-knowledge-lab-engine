"""공통 지반 축 — 같은 것을 말하는 두 개념이 서로를 모르면 안 된다 (불변식 14).

  wevolley#sc-analytics-blind-spot   "analytics 스텁·호출처 0건"     frozen·high
  wevolley#sc-posthog-http-capture   "PostHog capture HTTP API 전송"  frozen·high

둘 다 `lib/analytics.ts` 이야기다. 그런데 `crosscheck.yaml`은 `conflicts: []`에
`checked_concepts: 297`을 찍었다. 못 잡은 게 아니라 **잡을 수 없었다** —
`crosscheck_concept`은 이름 그대로 **한 개념 안**의 층간 값만 대조한다.
두 진술이 서로 다른 개념에 앉으면 구조적으로 만나지 않는다.

여기서 하는 일은 모순 **판정**이 아니다(그건 의미 판정이라 결정론 밖).
"이 둘은 같은 코드 단위를 근거로 삼는데 그래프가 둘을 잇지 않았다"까지만 말한다.
사람이 볼 목록을 만드는 게 목적이지 결론을 지어내는 게 아니다."""
from __future__ import annotations

from shared_ground import (fragment_units, fragment_mentions,
                           shared_ground_report)

# 실 정본 구조 축약
CONCEPTS = [
    {"anchor": "wevolley#sc-analytics-blind-spot", "commitment": "frozen", "confidence": "high",
     "name": "행동 데이터 0 — analytics 스텁·호출처 0건"},
    {"anchor": "wevolley#sc-posthog-http-capture", "commitment": "frozen", "confidence": "high",
     "name": "PostHog은 RN SDK 대신 capture HTTP API"},
    {"anchor": "wevolley#sc-approval-gate", "commitment": "frozen", "confidence": "high",
     "name": "승인 게이트"},
]
BODIES = {
    # 실 정본 그대로 — 이 개념은 **코드 조각이 없다**. 근거는 산문뿐이고
    # 그 산문이 백틱으로 `lib/analytics.ts`를 지목한다. 연결 신호는 거기서 나온다.
    "wevolley#sc-analytics-blind-spot": [
        {"key": "quote",
         "text": "`lib/analytics.ts`의 `trackEvent`가 `console.log` 스텁이고 호출처 0건"},
    ],
    "wevolley#sc-posthog-http-capture": [
        {"key": "lib.analytics|content", "text": "PostHog capture HTTP API로 직접 전송한다."},
        {"key": "lib.analytics.identifyUser|fields.signature", "text": "export function identifyUser("},
    ],
    "wevolley#sc-approval-gate": [
        {"key": "lib.community.approve|fields.signature", "text": "export function approve("},
    ],
}


def test_fragment_units_keep_both_symbol_and_module():
    """지반은 심볼과 그 모듈을 **둘 다** 든다 — 산문이 파일을 지목할 수도(`lib/analytics.ts`)
    심볼을 지목할 수도(`identifyUser`) 있어서 한쪽만 들면 절반을 놓친다."""
    assert fragment_units(BODIES["wevolley#sc-posthog-http-capture"]) == {
        "lib.analytics", "lib.analytics.identifyUser"}


def test_document_axis_is_deliberately_excluded_from_ground():
    """문서 공유는 신호가 아니라 잡음이다 — 실측 2,703쌍이 나왔다(같은 카탈로그면 전부).
    코드 축만 지반으로 친다."""
    frags = [{"key": "planning/reference/catalog#D1|content", "text": "x"}]
    assert fragment_units(frags) == set()


def test_mentions_read_backticked_identifiers_from_prose():
    """지반이 없는 개념도 본문이 코드를 지목하면 이어질 수 있다."""
    frags = [{"key": "quote", "text": "`lib/analytics.ts`의 `trackEvent`가 스텁"}]
    assert fragment_mentions(frags) == {"lib.analytics", "trackEvent"}


def test_mentions_ignore_prose_and_dead_fragments():
    assert fragment_mentions([{"key": "quote", "text": "`상태: 백로그`"}]) == set()
    assert fragment_mentions([{"key": "quote", "text": "`lib/x.ts`", "removed_at": "a"}]) == set()


def test_quote_key_has_no_unit():
    assert fragment_units([{"key": "quote", "text": "x"}]) == set()


def test_dead_fragments_do_not_ground_a_concept():
    frags = [{"key": "lib.analytics|content", "text": "x", "removed_at": "abc"}]
    assert fragment_units(frags) == set()


# ── 실사고 재현 ──────────────────────────────────────────────────────────

def test_finds_the_analytics_pair():
    """정확히 이 한 쌍이 나와야 한다."""
    r = shared_ground_report(CONCEPTS, BODIES, relations=[])
    assert r["ok"] is False
    assert [(p["a"], p["b"]) for p in r["ungrounded_pairs"]] == [
        ("wevolley#sc-analytics-blind-spot", "wevolley#sc-posthog-http-capture")]
    assert r["ungrounded_pairs"][0]["shared_units"] == ["lib.analytics"]


def test_related_concepts_are_not_flagged():
    """그래프가 이미 둘을 이었으면 사각지대가 아니다."""
    rel = [{"from": "wevolley#sc-analytics-blind-spot",
            "to": "wevolley#sc-posthog-http-capture", "canonical": "superseded_by"}]
    assert shared_ground_report(CONCEPTS, BODIES, relations=rel)["ok"] is True


def test_relation_direction_does_not_matter():
    rel = [{"from": "wevolley#sc-posthog-http-capture",
            "to": "wevolley#sc-analytics-blind-spot", "canonical": "part_of"}]
    assert shared_ground_report(CONCEPTS, BODIES, relations=rel)["ok"] is True


def test_shared_hub_alone_does_not_connect_two_spokes():
    """실 정본이 정확히 이 모양이었다 — 둘 다 허브에 붙어 있을 뿐 서로는 모른다."""
    rel = [{"from": "wevolley#sc-analytics-blind-spot", "to": "hub", "canonical": "triggers"},
           {"from": "wevolley#sc-posthog-http-capture", "to": "hub", "canonical": "part_of"}]
    assert shared_ground_report(CONCEPTS, BODIES, relations=rel)["ok"] is False


def test_unrelated_concepts_sharing_nothing_are_not_flagged():
    assert not any("sc-approval-gate" in (p["a"], p["b"])
                   for p in shared_ground_report(CONCEPTS, BODIES, [])["ungrounded_pairs"])


def test_only_confident_claims_are_flagged():
    """양쪽 다 확정(frozen·high)일 때만 본다 — 가설끼리 겹치는 건 정상이다.
    오탐을 줄이지 않으면 297개념에서 목록이 수백 줄이 되고 아무도 안 본다."""
    concepts = [{**CONCEPTS[0]}, {**CONCEPTS[1], "commitment": "hypothesis"}]
    assert shared_ground_report(concepts, BODIES, [])["ok"] is True


def test_deterministic_and_sorted():
    r1 = shared_ground_report(CONCEPTS, BODIES, [])
    r2 = shared_ground_report(CONCEPTS, BODIES, [])
    assert r1 == r2
    for p in r1["ungrounded_pairs"]:
        assert p["a"] < p["b"]      # 쌍은 정렬된 한 방향으로만 나온다(중복 금지)


def test_empty_inputs():
    assert shared_ground_report([], {}, [])["ok"] is True
