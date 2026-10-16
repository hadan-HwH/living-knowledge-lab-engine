"""아카이브 종결 축 — 정본이 "그 문제는 이미 풀렸다"를 배울 수 있어야 한다 (불변식 12).

핵심은 문서가 **스스로 답을 가리키고 있었다**는 것이다:

    ### D1. 제품 분석 … → [24 상세 문서 §D1](../작업완료/24-scalability-product-infra.md)

이건 사람이 쓴 링크지 추론이 아니다. 엔진은 이 문장을 **텍스트로 먹고 따라가지 않았다.**
따라가는 건 결정론이다(LLM 0) — 이 층은 그 포인터를 읽어 "이 주장에는 종결 문서가
있는데 코퍼스가 그걸 안 읽었다"를 표시한다. 판정은 하지 않는다(그건 사람 몫)."""
from __future__ import annotations

from archive_closure import (archive_links_in, archive_reference_report,
                             demote_unresolved_claims)

ARCHIVE = ("작업완료",)

# 실제 카탈로그 D1 헤딩 그대로
D1_HEADING = ("D1. 제품 분석 — 퍼널·리텐션 가시화 (재정의·상향 — 2026-06-03) "
              "→ [24 상세 문서 §D1](../작업완료/24-scalability-product-infra.md)")


def test_finds_archive_link_in_heading():
    """헤딩 안 마크다운 링크가 아카이브를 가리키면 잡는다."""
    assert archive_links_in(D1_HEADING, ARCHIVE) == ["../작업완료/24-scalability-product-infra.md"]


def test_finds_archive_link_in_body_text():
    text = "- **개선 효과**: 자세히는 [22번](../작업완료/22-launch-polish.md) 참조."
    assert archive_links_in(text, ARCHIVE) == ["../작업완료/22-launch-polish.md"]


def test_ignores_links_to_live_documents():
    text = "관련: [백로그](../backlog/33-club-treasury.md)"
    assert archive_links_in(text, ARCHIVE) == []


def test_ignores_bare_path_mentions_without_link():
    """링크가 아니면 포인터가 아니다 — 산문 언급으로 종결을 주장하지 않는다."""
    assert archive_links_in("작업완료 폴더를 참고하라", ARCHIVE) == []


def test_archive_segment_matching_is_slug_normalized():
    """폴더 번호는 순번이다 — `2-작업완료`도 같은 구역(registry 원칙)."""
    assert archive_links_in("[x](../2-작업완료/24-foo.md)", ARCHIVE) == ["../2-작업완료/24-foo.md"]


def test_no_archive_segments_declared_means_no_claims():
    """선언이 없으면 아무것도 안 한다 — 엔진은 폴더 이름을 모른다(제네릭 원칙)."""
    assert archive_links_in(D1_HEADING, ()) == []


# ── 개념 축 ──────────────────────────────────────────────────────────────

BODIES = {
    "wevolley#sc-analytics-blind-spot": [
        {"key": "quote", "text": "`trackEvent`가 `console.log` 스텁이고 호출처 0건"},
        {"key": f"planning/reference/improvement-catalog#{D1_HEADING}|content",
         "text": "- **현재(검증)**: analytics가 스텁이고 호출처 0건"},
    ],
    "wevolley#sc-approval-gate": [
        {"key": "planning/reference/x#H|content", "text": "승인 게이트는 awaiting_approval"},
    ],
}


def test_report_flags_concept_pointing_at_unread_resolution():
    """실사고 재현 — 이 개념 하나가 정확히 걸려야 한다."""
    r = archive_reference_report(BODIES, ARCHIVE, ingested_docs=set())
    assert [x["anchor"] for x in r["unresolved"]] == ["wevolley#sc-analytics-blind-spot"]
    assert r["unresolved"][0]["targets"] == ["작업완료/scalability-product-infra"]
    assert r["ok"] is False


def test_report_ok_when_resolution_doc_is_in_corpus():
    """종결 문서를 실제로 읽었으면 미해결이 아니다 — 배제를 풀면 초록이 된다."""
    r = archive_reference_report(BODIES, ARCHIVE,
                                 ingested_docs={"작업완료/24-scalability-product-infra"})
    assert r["ok"] is True and r["unresolved"] == []


def test_ingested_match_is_suffix_not_exact():
    """링크는 상대경로(`작업완료/x`)인데 적재 신원은 루트 포함(`planning/작업완료/x`)이다.
    완전일치로 재면 읽고도 '안 읽었다'가 되어 게이트가 영영 안 꺼진다 — 불변식 11과 같은 병."""
    r = archive_reference_report(
        BODIES, ARCHIVE, ingested_docs={"planning/작업완료/24-scalability-product-infra"})
    assert r["ok"] is True


def test_report_ignores_tombstoned_and_superseded_fragments():
    """죽은 조각의 포인터로 살아있는 주장을 흔들지 않는다."""
    bodies = {"A": [{"key": f"planning/x#{D1_HEADING}|content", "text": "t",
                     "removed_at": "abc"}]}
    assert archive_reference_report(bodies, ARCHIVE, ingested_docs=set())["ok"] is True


def test_report_is_deterministic_and_sorted():
    r1 = archive_reference_report(BODIES, ARCHIVE, ingested_docs=set())
    r2 = archive_reference_report(BODIES, ARCHIVE, ingested_docs=set())
    assert r1 == r2


# ── 확신도 축: 종결 문서를 안 읽었으면 frozen/high를 주지 않는다 ────────

def test_unresolved_claim_cannot_be_frozen_high():
    """근인의 마지막 마디 — 반증 문서를 안 읽은 주장이 확정 사실로 앉아 있었다."""
    concepts = [{"anchor": "wevolley#sc-analytics-blind-spot",
                 "commitment": "frozen", "confidence": "high"},
                {"anchor": "wevolley#sc-approval-gate",
                 "commitment": "frozen", "confidence": "high"}]
    out = demote_unresolved_claims(concepts, BODIES, ARCHIVE, ingested_docs=set())
    by = {c["anchor"]: c for c in out}
    a = by["wevolley#sc-analytics-blind-spot"]
    assert a["commitment"] == "working" and a["confidence"] == "medium"
    assert a["unresolved_reference"] == ["작업완료/scalability-product-infra"]
    # 관련 없는 개념은 손대지 않는다
    assert by["wevolley#sc-approval-gate"]["commitment"] == "frozen"
    assert "unresolved_reference" not in by["wevolley#sc-approval-gate"]


def test_demotion_never_raises_commitment():
    """강등만 한다 — 이미 낮은 걸 올리지 않는다(판정은 사람 몫)."""
    concepts = [{"anchor": "wevolley#sc-analytics-blind-spot",
                 "commitment": "hypothesis", "confidence": "low"}]
    out = demote_unresolved_claims(concepts, BODIES, ARCHIVE, ingested_docs=set())
    assert out[0]["commitment"] == "hypothesis" and out[0]["confidence"] == "low"


def test_demotion_is_idempotent():
    concepts = [{"anchor": "wevolley#sc-analytics-blind-spot",
                 "commitment": "frozen", "confidence": "high"}]
    once = demote_unresolved_claims(concepts, BODIES, ARCHIVE, ingested_docs=set())
    twice = demote_unresolved_claims(once, BODIES, ARCHIVE, ingested_docs=set())
    assert once == twice


# ── 불변식 12는 신호지 빌드 브레이커가 아니다 ─────────

def test_unresolved_frozen_is_reported_not_gated():
    """★초판 설계 오류: 이걸 `metrics_gate` 회귀 축에 넣었더니 `regen.sh`가 사람이
    9건을 판정하기 전까지 **영구히 exit 1**이 됐다. 그러면 "regen은 원래 빨간불"이
    되고, 이 프로젝트가 계속 경계해 온 "사람이 게이트를 무시하기 시작"이 재현된다.
    drift·crosscheck와 같은 층 — 보고하되 종료 코드는 안 건드린다."""
    from structure_app import metrics_gate
    g = metrics_gate({"concepts": 10, "unresolved_frozen": 0},
                     {"concepts": 10, "unresolved_frozen": 9})
    assert g["ok"] is True, "미판정 큐가 빌드를 깨면 안 된다"
    assert not [r for r in g["regressions"] if r["metric"] == "unresolved_frozen"]


def test_unresolved_frozen_still_visible_in_metrics():
    """게이트에서 뺐다고 감시를 끄는 게 아니다 — 지표로는 계속 노출된다."""
    from structure_app import canon_metrics
    doc = {"concepts": [{"anchor": "A", "commitment": "frozen", "confidence": "high"}],
           "bodies": {"A": [{"key": f"planning/x#{D1_HEADING}|content", "text": "t"}]}}
    m = canon_metrics(doc, archive_segments=ARCHIVE, ingested_docs=set())
    assert m["unresolved_frozen"] == 1
