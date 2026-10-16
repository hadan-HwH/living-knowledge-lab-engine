"""날조 게이트 — 전달 문서의 모든 주장은 근거로 역추적돼야 한다 (불변식 13).

  | 내가 쓴 것        | 정본 히트 | 실제                                    |
  |-------------------|-----------|-----------------------------------------|
  | `wizard_complete` | 0         | EventName union에 없음(signup·profile_update) |
  | `lib/date`        | 0         | 실재는 `lib/utils/date.ts`               |
  | 5중복             | 0         | 정본은 **4곳**, `working`·`medium`       |

이 게이트는 사람이 기억으로 지키던 규율을 기계로 옮긴다. 잡는 것은 두 축이다:
  ① 출처 없는 식별자 — 백틱 안 코드 심볼·경로가 정본에도 코퍼스에도 없으면 차단
  ② 인용한 개념보다 센 주장 — 정본이 `working`·`medium`이라 한 걸 확정으로 쓰거나,
     정본이 말한 수와 다른 수를 쓰면 차단"""
from __future__ import annotations

from provenance_gate import (checkable_identifiers, provenance_report,
                             overclaim_report, gate_document)

# 정본 축약 — 실제 wevolley 정본에서 뽑은 형태
CANON = {
    "concepts": [
        {"anchor": "wevolley#sc-local-date-string-scattered",
         "name": "로컬 날짜 문자열 유틸이 4곳에 흩어짐 — toISOString UTC 함정을 각 파일이 따로 피한다",
         "commitment": "working", "confidence": "medium"},
        {"anchor": "wevolley#sc-posthog-http-capture",
         "name": "PostHog은 RN SDK 대신 capture HTTP API",
         "commitment": "frozen", "confidence": "high"},
    ],
    "bodies": {
        "wevolley#sc-local-date-string-scattered": [
            {"key": "lib.utils.date.toLocalDateStr|fields.signature",
             "text": "export function toLocalDateStr(date: Date): string {"},
            {"key": "lib.utils.calendar.toDateStr|fields.signature",
             "text": "export function toDateStr(y: number, m: number, d: number) {"},
        ],
        "wevolley#sc-posthog-http-capture": [
            {"key": "lib.analytics|content", "text": "PostHog capture HTTP API로 직접 전송한다."},
            # 실 정본에 있는 것 — 이게 없으면 게이트가 `profile-wizard`도 날조로 잡는다(정당)
            {"key": "app.profile-wizard.ProfileWizard|fields.signature",
             "text": "export default function ProfileWizard() {"},
        ],
    },
}


# ── ① 식별자 축 ──────────────────────────────────────────────────────────

def test_extracts_backticked_identifiers_only():
    """산문은 안 본다 — 백틱 안 코드 심볼·경로만 검사 대상이다(오탐 최소)."""
    md = "이건 `lib/utils/date.ts`의 `toLocalDateStr`를 쓰고, 나머지는 그냥 문장이다."
    assert checkable_identifiers(md) == ["lib/utils/date.ts", "toLocalDateStr"]


def test_ignores_prose_and_korean_in_backticks():
    """백틱 안이어도 식별자 꼴이 아니면 대상이 아니다."""
    assert checkable_identifiers("`상태: 백로그` 로 표시") == []


def test_ignores_code_fences():
    """예시 블록은 주장이 아니다."""
    md = "설명\n\n```ts\nconst wizard_complete = 1\n```\n\n끝"
    assert checkable_identifiers(md) == []


def test_real_fabrication_is_caught():
    """실사고 재현 — 이 둘이 잡혔어야 했다."""
    md = "`profile-wizard`(signup·`wizard_complete`), `lib/date` 한 곳으로 통합"
    r = provenance_report(md, CANON)
    assert r["ok"] is False
    assert set(r["unsourced"]) == {"wizard_complete", "lib/date"}


def test_identifier_present_in_canon_passes():
    r = provenance_report("`toLocalDateStr`로 통합한다", CANON)
    assert r["ok"] is True and r["unsourced"] == []


def test_identifier_found_in_body_text_passes():
    """조각 텍스트 안에 있으면 근거가 있는 것이다(키만 보지 않는다)."""
    assert provenance_report("`capture HTTP API` 채택", CANON)["ok"] is True


def test_extra_sources_widen_the_evidence_base():
    """정본 밖이지만 코퍼스에 실재하는 식별자는 통과 — 정본이 세상의 전부는 아니다."""
    md = "`useMyGames`가 UTC를 쓴다"
    assert provenance_report(md, CANON)["ok"] is False
    assert provenance_report(md, CANON, extra_sources=["lib/hooks/home/useMyGames.ts"])["ok"] is True


def test_report_is_deterministic_and_sorted():
    md = "`zzz_missing` `aaa_missing`"
    assert provenance_report(md, CANON)["unsourced"] == ["aaa_missing", "zzz_missing"]


# ── ② 과잉 주장 축 ───────────────────────────────────────────────────────

def test_number_disagreeing_with_cited_concept_is_caught():
    """정본은 4곳이라 했는데 5중복이라 썼다 — 실사고 그대로."""
    md = ("`toDateStr`/`todayStr` 5중복 통합 "
          "(정본 `sc-local-date-string-scattered` 참조)")
    r = overclaim_report(md, CANON)
    assert r["ok"] is False
    assert r["conflicts"] == [{"anchor": "wevolley#sc-local-date-string-scattered",
                               "canon_numbers": [4], "doc_numbers": [5]}]


def test_matching_number_passes():
    md = "날짜 유틸이 `sc-local-date-string-scattered` 기준 4곳에 흩어져 있다"
    assert overclaim_report(md, CANON)["ok"] is True


def test_certainty_beyond_canon_commitment_is_caught():
    """정본이 `working`·`medium`이라 한 걸 확정으로 전달하면 안 된다."""
    md = "`sc-local-date-string-scattered` — **확정**: 4곳 중복이다"
    r = overclaim_report(md, CANON)
    assert r["ok"] is False
    assert any(c.get("overclaimed_certainty") for c in r["conflicts"])


def test_certainty_ok_when_canon_is_frozen():
    md = "`sc-posthog-http-capture` — **확정**: capture HTTP API를 쓴다"
    assert overclaim_report(md, CANON)["ok"] is True


def test_uncited_concepts_are_not_checked():
    """인용하지 않은 개념의 수치와는 대조하지 않는다(지어낸 연결 금지)."""
    assert overclaim_report("아무 숫자 7개", CANON)["ok"] is True


def test_numbers_are_scoped_to_the_citing_sentence():
    """실 문서 오탐: `sc-fix-at-choke-point`(정본 8·65)를 인용한 문장과 무관한
    다른 문단의 '5중복'이 붙어 거짓 충돌이 났다. 수치 대조는 **인용한 문장** 안에서만."""
    canon = {"concepts": [{"anchor": "wevolley#sc-fix-at-choke-point",
                           "name": "길목 수정 — 65곳이 아니라 공통 훅 ~8곳으로 8할 해결",
                           "commitment": "working", "confidence": "medium"}],
             "bodies": {}}
    md = ("날짜 유틸이 5곳에 흩어져 있다.\n\n"
          "별개 문단: 길목 수정 원칙(`sc-fix-at-choke-point`)을 따른다.")
    assert overclaim_report(md, canon)["ok"] is True


def test_number_conflict_still_caught_within_one_sentence():
    canon = {"concepts": [{"anchor": "wevolley#sc-fix-at-choke-point",
                           "name": "길목 수정 — 65곳이 아니라 공통 훅 ~8곳으로 8할 해결",
                           "commitment": "working", "confidence": "medium"}],
             "bodies": {}}
    md = "`sc-fix-at-choke-point` 기준 3곳만 고치면 된다"
    assert overclaim_report(md, canon)["ok"] is False


def test_document_path_with_extension_is_not_a_fabrication():
    """실 문서 오탐: 정본은 문서 신원을 확장자 없이 저장한다
    (`planning/reference/perf-loading-realtime-history`). `.md`를 붙여 인용했다고
    날조로 잡으면 **올바른 인용까지 전부** 빨간불이 된다."""
    canon = {"concepts": [], "bodies": {"A": [
        {"key": "planning/reference/perf-loading-realtime-history#H|content", "text": "x"}]}}
    assert provenance_report("`planning/reference/perf-loading-realtime-history.md` 참조",
                             canon)["ok"] is True


def test_numeric_prefix_in_cited_path_is_tolerated():
    """정본 신원은 번호 접두를 뗀다 — 원본 파일명대로 인용해도 날조가 아니다."""
    canon = {"concepts": [], "bodies": {"A": [
        {"key": "planning/reference/improvement-catalog#H|content", "text": "x"}]}}
    assert provenance_report("`planning/reference/08-improvement-catalog.md`", canon)["ok"] is True


def test_genuinely_absent_path_still_caught():
    """오탐을 줄이되 진짜 날조는 놓치지 않는다."""
    canon = {"concepts": [], "bodies": {"A": [
        {"key": "planning/reference/perf-loading-realtime-history#H|content", "text": "x"}]}}
    assert provenance_report("`planning/reference/no-such-doc.md`", canon)["ok"] is False


# ── 통합 게이트 ──────────────────────────────────────────────────────────

def test_gate_blocks_and_explains():
    md = "`wizard_complete`를 쏜다. `sc-local-date-string-scattered` 5중복."
    g = gate_document(md, CANON)
    assert g["ok"] is False
    assert "wizard_complete" in g["unsourced"]
    assert g["conflicts"]


def test_gate_passes_clean_document():
    md = "`toLocalDateStr` 한 곳으로 통합한다. `sc-local-date-string-scattered` 4곳."
    assert gate_document(md, CANON)["ok"] is True


def test_gate_on_empty_document():
    assert gate_document("", CANON)["ok"] is True
