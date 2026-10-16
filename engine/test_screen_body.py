"""화면 섹션이 본문을 들고 있게 한다 — 증거력 (소유자 지시 2026-08-05).

★진단: `parse_corpdoc_screen`이 `## 헤딩`을 만나면 `content: heading`으로 노드를 만들고
그 아래 줄을 **모으지 않는다.** 그래서 Tier A의 `screen_section` content 중앙값이 제목 길이
(제목뿐)이고, 실제 본문은 `sections.yaml`에만 남는다.

결과: 화면을 개념에 귀속시켜도 **인용(증거)이 표제어뿐**이라 그것만 읽어서는 아무것도
모른다. 조항은 "관리자는 보관 중인 상품을 …즉시 회수할 수 있다"인데 화면은
"Storage policies (INV07)"이다. 둘 다 왕복 게이트는 통과한다 — 게이트는 "원문에
실재하는가"만 묻지 "읽어서 알 수 있는가"는 안 묻기 때문이다."""
import unittest

from parsers import parse_corpdoc_screen


MD = """---
title: "테스트 화면 정의서"
version: "1.0.0"
---

화면ID: **INV99**

## 1. 개요

이 화면은 상품 목록을 보여준다.
목록은 상태별로 필터링할 수 있다.

## 2. 보관 정책 `[INV-55]`

| 항목 | 기본값 | 범위 |
|---|---|---|
| Hold Period | 10일 | 5–180일 |

**GAP(불일치):** 설계 5일 vs 배포 15일

## 변경 이력

| 날짜 | 내용 |
"""


def _sections(md):
    return {c["anchor"]: c for c in parse_corpdoc_screen(md, scope="s/inv")["concepts"]
            if c["kind"] == "screen_section"}


class TestScreenSectionCarriesBody(unittest.TestCase):
    def test_prose_under_the_heading_is_captured(self):
        s = _sections(MD)["INV99§1. 개요"]
        self.assertIn("상품 목록을 보여준다", s["content"])
        self.assertIn("상태별로 필터링", s["content"])

    def test_table_rows_are_captured(self):
        s = _sections(MD)["INV99§2. 보관 정책 `[INV-55]`"]
        self.assertIn("Hold Period", s["content"])
        self.assertIn("5–180일", s["content"])

    def test_heading_still_starts_the_content(self):
        """제목을 잃지 않는다 — 종전 동작이 제목이었고 그건 유용하다."""
        s = _sections(MD)["INV99§1. 개요"]
        self.assertTrue(s["content"].startswith("1. 개요"))
        self.assertEqual(s["section"], "1. 개요")

    def test_body_is_long_enough_to_be_evidence(self):
        """★증거력 — 인용만 읽어도 내용을 알 수 있어야 한다(종전 중앙값 14자)."""
        for s in _sections(MD).values():
            self.assertGreater(len(s["content"]), 20, s["anchor"])

    def test_change_log_section_is_still_skipped(self):
        self.assertNotIn("INV99§변경 이력", _sections(MD))

    def test_next_heading_ends_the_section(self):
        s = _sections(MD)["INV99§1. 개요"]
        self.assertNotIn("Hold Period", s["content"])       # 다음 섹션 내용이 안 샌다

    def test_gap_marker_stays_its_own_concept(self):
        """GAP은 별도 개념이다 — 화면 본문에 섞여도 자기 노드를 잃지 않는다."""
        kinds = [c["kind"] for c in parse_corpdoc_screen(MD, scope="s")["concepts"]]
        self.assertIn("gap", kinds)

    def test_refs_still_collected(self):
        s = _sections(MD)["INV99§2. 보관 정책 `[INV-55]`"]
        self.assertIn("INV-55", s["refs"]["articles"])


if __name__ == "__main__":
    unittest.main()
