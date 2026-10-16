"""code-symbols 어댑터 테스트 — 설계: docs/2-method/code-symbols-adapter-design.md.

범용(코퍼스 무지) — 테스트에도 특정 코퍼스 이름 하드코딩 없음.
계약은 마크다운 어댑터와 **같은 SourceConcept**다: anchor·kind·content·section·scope·
line·refs·confidence. 다른 건 S1(무엇을 단위로 보나)뿐이다.
"""
import unittest

from parsers import parse, parse_code_symbols

SRC = '''"""모듈 설명이다. 설계는 concept-body-design.md:19를 따른다."""
import os


def collect(root, fmt=None):
    """수집기 docstring. 결정론이다."""
    return []


async def fetch(url):
    """비동기도 함수다."""


def _private(x):
    return x


class Holder:
    """클래스 docstring."""

    def method(self, a, b=1):
        """메서드 docstring."""

    def _hidden(self):
        pass
'''


class TestParseCodeSymbols(unittest.TestCase):
    def setUp(self):
        self.res = parse_code_symbols(SRC, scope="x", module="pkg.mod")
        self.by = {c["anchor"]: c for c in self.res["concepts"]}

    def test_anchor_is_dotted_qualname(self):
        """이름만 쓰면 실측 9종이 충돌한다 — 불변식 8(anchor 유일성)이 즉시 깨진다."""
        self.assertIn("pkg.mod", self.by)
        self.assertIn("pkg.mod.collect", self.by)
        self.assertIn("pkg.mod.Holder", self.by)
        self.assertIn("pkg.mod.Holder.method", self.by)

    def test_module_is_a_unit(self):
        """★초판 §6 표에 module이 없었다. 실측상 최밀도 단위다(보유율 100%·평균 530자)."""
        m = self.by["pkg.mod"]
        self.assertEqual(m["kind"], "module")
        self.assertIn("모듈 설명이다", m["content"])
        self.assertEqual(m["line"], 1)

    def test_kinds_are_distinguished(self):
        self.assertEqual(self.by["pkg.mod.collect"]["kind"], "function")
        self.assertEqual(self.by["pkg.mod.fetch"]["kind"], "function")
        self.assertEqual(self.by["pkg.mod.Holder"]["kind"], "class")
        self.assertEqual(self.by["pkg.mod.Holder.method"]["kind"], "method")

    def test_private_symbols_are_kept(self):
        """`_private`도 지식이다 — 공개 API만 걷으면 엔진 내부가 통째로 사라진다."""
        self.assertIn("pkg.mod._private", self.by)
        self.assertIn("pkg.mod.Holder._hidden", self.by)

    def test_content_is_docstring_verbatim(self):
        """원문 무수정 — 왕복 게이트가 quote를 원문에서 찾아야 한다."""
        c = self.by["pkg.mod.collect"]
        self.assertEqual(c["content"], "수집기 docstring. 결정론이다.")
        self.assertIn(c["content"], SRC)

    def test_signature_is_a_field_not_content(self):
        """조각 키는 `<anchor>|<필드>`다. content와 fields가 겹치면 조각이 중복된다."""
        c = self.by["pkg.mod.collect"]
        self.assertEqual(c["fields"]["signature"], "def collect(root, fmt=None):")
        self.assertIn(c["fields"]["signature"], SRC)   # 원문 슬라이스 — 재구성 금지
        self.assertNotIn("docstring", c["fields"])   # content와 중복 금지

    def test_async_signature_marked(self):
        self.assertEqual(self.by["pkg.mod.fetch"]["fields"]["signature"],
                         "async def fetch(url):")

    def test_docstringless_symbol_has_empty_content(self):
        """본문이 없어도 앵커는 선다 — 조각은 안 만들어진다(지어냄 0)."""
        c = self.by["pkg.mod._private"]
        self.assertEqual(c["content"], "")
        self.assertIn("signature", c["fields"])

    def test_section_is_parent_symbol(self):
        self.assertEqual(self.by["pkg.mod.Holder.method"]["section"], "pkg.mod.Holder")
        self.assertEqual(self.by["pkg.mod.collect"]["section"], "pkg.mod")
        self.assertIsNone(self.by["pkg.mod"]["section"])

    def test_line_preserved_for_roundtrip(self):
        self.assertEqual(self.by["pkg.mod.collect"]["line"], 5)

    def test_scope_and_confidence(self):
        for c in self.res["concepts"]:
            self.assertEqual(c["scope"], "x")
            self.assertEqual(c["confidence"], "high")

    def test_refs_shape_is_compatible(self):
        """하류가 refs.decisions/articles를 읽는다 — 비어도 키는 있어야 한다."""
        c = self.by["pkg.mod"]
        self.assertEqual(c["refs"]["decisions"], [])
        self.assertEqual(c["refs"]["articles"], [])

    def test_doc_citation_collected(self):
        """코드→설계문서 인용은 얇지만(실측 6%) 실재한다 — 부가 신호로 보존."""
        self.assertIn("concept-body-design.md", self.by["pkg.mod"]["refs"]["docs"])

    def test_anchor_unique_within_file(self):
        anchors = [c["anchor"] for c in self.res["concepts"]]
        self.assertEqual(len(anchors), len(set(anchors)))

    def test_syntax_error_is_flagged_not_raised(self):
        """깨진 파일 하나가 스냅샷 전체를 죽이면 안 된다 — 조용히 삼키지도 않는다."""
        res = parse_code_symbols("def (:\n", scope="x", module="pkg.bad")
        self.assertEqual(res["concepts"], [])
        self.assertTrue(any("구문 오류" in f for f in res["flags"]))

    def test_registered_in_dispatch(self):
        res = parse("code-symbols:python", SRC, scope="x", module="pkg.mod")
        self.assertTrue(any(c["anchor"] == "pkg.mod.collect" for c in res["concepts"]))


class TestParseIgnoresUnknownKwargs(unittest.TestCase):
    """포맷별 kwarg가 달라도 dispatch가 안 깨져야 한다 — 새 어댑터가 기존 것을 못 망치게."""

    def test_markdown_parser_survives_code_kwarg(self):
        res = parse("markdown-sections", "# 제목\n본문\n", scope="x",
                    doc_slug="d", module="ignored")
        self.assertTrue(res["concepts"])

    def test_code_parser_survives_doc_slug_kwarg(self):
        res = parse("code-symbols:python", SRC, scope="x",
                    doc_slug="ignored", module="pkg.mod")
        self.assertTrue(res["concepts"])


if __name__ == "__main__":
    unittest.main()


class TestInlineComments(unittest.TestCase):
    """★인라인 주석을 서술 단위에 싣는다.

    귀속의 진실 원천은 `articles.yaml`(= `_texts_of` 산출)이므로, 주석이 거기 실려야
    인용이 성립한다. 조각 키는 `<anchor>|fields.comments`가 된다."""

    SRC = '''"""모듈 docstring."""
# 모듈 수준 주석 — 여기는 모듈 것이다.
import os


def outer(a):
    """바깥 함수."""
    # ★설계 근거: 이 줄이 본문층에 닿아야 한다.
    x = a + 1
    return x


class Holder:
    """클래스."""
    # 클래스 수준 주석

    def method(self):
        """메서드."""
        # 메서드 안 주석
        pass
'''

    def setUp(self):
        self.by = {c["anchor"]: c for c in
                   parse_code_symbols(self.SRC, scope="x", module="m")["concepts"]}

    def test_comment_attaches_to_innermost_symbol(self):
        """가장 안쪽 심볼이 임자다 — 함수 안 주석이 모듈 것이 되면 안 된다."""
        self.assertIn("★설계 근거", self.by["m.outer"]["fields"]["comments"])
        self.assertNotIn("★설계 근거", self.by["m"].get("fields", {}).get("comments", ""))

    def test_module_level_comment_belongs_to_module(self):
        self.assertIn("모듈 수준 주석", self.by["m"]["fields"]["comments"])

    def test_class_comment_not_stolen_by_method(self):
        self.assertIn("클래스 수준 주석", self.by["m.Holder"]["fields"]["comments"])
        self.assertNotIn("클래스 수준 주석",
                         self.by["m.Holder.method"]["fields"]["comments"])

    def test_method_comment_belongs_to_method(self):
        self.assertIn("메서드 안 주석", self.by["m.Holder.method"]["fields"]["comments"])

    def test_no_comments_field_when_none(self):
        """빈 필드를 만들지 않는다 — `_texts_of`가 빈 조각을 거른다지만 원장이 지저분해진다."""
        res = parse_code_symbols("def f():\n    return 1\n", scope="x", module="m")
        self.assertNotIn("comments", res["concepts"][1]["fields"])

    def test_comment_text_is_verbatim_source_slice(self):
        """왕복 게이트가 걸린다 — 가공하면 인용이 원문에서 안 찾아진다."""
        c = self.by["m.outer"]["fields"]["comments"]
        for line in c.splitlines():
            self.assertIn(line, self.SRC)

    def test_docstring_content_unchanged(self):
        """content는 여전히 docstring이다 — 주석이 섞이면 두 층이 뭉개진다."""
        self.assertEqual(self.by["m.outer"]["content"], "바깥 함수.")

    def test_shebang_and_coding_lines_are_not_body(self):
        res = parse_code_symbols("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nx = 1\n",
                                 scope="x", module="m")
        f = res["concepts"][0].get("fields", {}).get("comments", "")
        self.assertNotIn("usr/bin/env", f)
        self.assertNotIn("coding:", f)
