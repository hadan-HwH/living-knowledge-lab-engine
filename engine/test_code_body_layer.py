"""코드 추출 깊이 — 정본이 함수 **안**을 볼 수 있어야 한다 (불변식 15).

결과 둘:
  ⓐ `toISOString`이 정본에 3번뿐이고 셋 다 `lib/utils/date.ts:45`의 **경고 주석**이다.
     실제 위반 두 곳(`tournament-create.tsx:39`, `useMyGames.ts:25`)은 컴포넌트 함수
     안의 구문이라 시야 밖 — 두 파일 다 인제스트돼 있는데도.
  ⓑ `EventCalendarGrid.toDateStr`는 **최상위 선언인데 0히트**다. `_TS_EXPORT`가
     `^export`를 요구해서, export 안 된 최상위 선언은 통째로 안 보인다.

정본은 "로컬 날짜 유틸이 **4곳**에 흩어짐 / 각 파일이 따로 UTC를 피한다"고
`confidence: medium`으로 말했다. 거짓말이 아니라 **자기가 볼 수 있는 증거의 정확한
요약**이었고, 반례는 원리적으로 시야 밖이었다. 위험한 건 이 과소집계가 완전한
집계와 겉으로 구분이 안 된다는 것이다."""
from __future__ import annotations

from parsers import parse

SRC = '''
/** 홈 달력 그리드. */
import { memo } from 'react';

function toDateStr(y: number, m: number, d: number) {
  return `${y}-${String(m).padStart(2, '0')}`;
}

export const EventCalendarGrid = memo(function EventCalendarGrid({ year }: Props) {
  const todayStr = new Date().toISOString().split('T')[0];
  const rows = buildCalendarRows(cells);
  return null;
});
'''


def _by_anchor(src, module="components.home.EventCalendarGrid"):
    res = parse("code-symbols:typescript", src, scope="wevolley", module=module)
    return {c["anchor"]: c for c in res["concepts"]}


# ── ⓑ 비-export 최상위 선언 ─────────────────────────────────────────────

def test_non_exported_top_level_declaration_is_captured():
    """실사고: `EventCalendarGrid.toDateStr`가 0히트였다 — lib 밖 로컬 복제라
    중복 실측에서 통째로 빠졌다."""
    by = _by_anchor(SRC)
    assert "components.home.EventCalendarGrid.toDateStr" in by


def test_non_exported_declaration_keeps_signature():
    by = _by_anchor(SRC)
    sig = by["components.home.EventCalendarGrid.toDateStr"]["fields"]["signature"]
    assert sig.startswith("function toDateStr(")


def test_exported_declarations_still_captured():
    by = _by_anchor(SRC)
    assert "components.home.EventCalendarGrid.EventCalendarGrid" in by


def test_export_flag_is_recorded():
    """export 여부는 사실이라 남긴다 — 공개 표면과 내부 구현은 다른 것이다."""
    by = _by_anchor(SRC)
    assert by["components.home.EventCalendarGrid.toDateStr"]["fields"]["exported"] == "false"
    assert by["components.home.EventCalendarGrid.EventCalendarGrid"]["fields"]["exported"] == "true"


# ── ⓐ 본문층: 호출 연쇄 ─────────────────────────────────────────────────

def test_call_chain_inside_function_body_is_captured():
    """근인 재현 — 이 한 줄이 안 보여서 UTC 버그가 정본 밖에 있었다."""
    by = _by_anchor(SRC)
    calls = by["components.home.EventCalendarGrid.EventCalendarGrid"]["fields"]["calls"]
    assert "new Date().toISOString().split('T')" in calls


def test_plain_call_is_captured_as_name_only():
    """단발 호출은 **이름만** 남긴다 — "무엇을 부른다"는 간선 정보라 인자가 필요 없다.
    전량 원문이면 코드층이 +86% 부풀고 Tier B 입력까지 커진다(실측)."""
    by = _by_anchor(SRC)
    calls = by["components.home.EventCalendarGrid.EventCalendarGrid"]["fields"]["calls"].splitlines()
    assert "buildCalendarRows" in calls
    assert "buildCalendarRows(cells)" not in calls


def test_chain_keeps_full_text_because_usage_is_the_diagnosis():
    """연쇄는 원문을 지킨다 — `toISOString` 이름만으론 UTC 오용이 안 보인다."""
    by = _by_anchor(SRC)
    calls = by["components.home.EventCalendarGrid.EventCalendarGrid"]["fields"]["calls"].splitlines()
    assert "new Date().toISOString().split('T')" in calls


def test_calls_are_deduped_and_sorted():
    src = "export function f() {\n  a.b();\n  a.b();\n  z.y();\n}\n"
    by = _by_anchor(src, module="m")
    calls = by["m.f"]["fields"]["calls"].splitlines()
    assert calls == sorted(set(calls))


def test_no_calls_field_when_body_has_none():
    src = "export const X = 1;\n"
    assert "calls" not in _by_anchor(src, module="m")["m.X"]["fields"]


def test_comments_and_signature_still_present():
    """기존 계약을 깨지 않는다 — 앵커·기존 필드는 그대로."""
    src = ("/** doc */\nexport function f() {\n  // 주석\n  g();\n}\n")
    f = _by_anchor(src, module="m")["m.f"]
    assert f["content"] == "doc"
    assert f["fields"]["signature"].startswith("export function f(")
    assert "주석" in f["fields"]["comments"]


def test_strings_and_comments_do_not_produce_calls():
    """주석·문자열 안의 호출 꼴은 실제 호출이 아니다(오탐 억제)."""
    src = ("export function f() {\n"
           "  // 예전엔 old.thing() 을 썼다\n"
           "  const s = 'no.call()';\n"
           "  real.call();\n"
           "}\n")
    calls = _by_anchor(src, module="m")["m.f"]["fields"]["calls"]
    assert "real.call()" in calls
    assert "old.thing()" not in calls and "no.call()" not in calls


def test_deterministic():
    a = _by_anchor(SRC)["components.home.EventCalendarGrid.EventCalendarGrid"]["fields"]
    b = _by_anchor(SRC)["components.home.EventCalendarGrid.EventCalendarGrid"]["fields"]
    assert a == b
