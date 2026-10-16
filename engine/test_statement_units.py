"""서술 단위 일반화 — 개념이 무엇을 모으는지는 코퍼스가 선언한다 (소유자 지시 2026-08-05).

★소유자 지적: "INV은 문서 중 예시일 뿐이고 비정형도 우리는 필요하잖아. 나는 이 프로덕트를
만든다는 것에서의 제너릭을 원하는 거잖아? 혹시 지금 설계가 inv 문서 같은 거로만 되어 있니?"

맞았다. 엔진의 다른 층은 전부 registry 데이터 구동인데(어댑터·경계·공유tier) **본문 층만
`kind == "article"`로 하드코딩**돼 있었다. 그 한 줄이 세 코퍼스를 동시에 막고 있었다:

    acme-docs   article 662 · screen_section 702 · field 194 …  → 조항만 통과
    personal-wevolley  section 1512                                    → 전량 차단
    lab-self           section 716                                     → 전량 차단

★일반화 원리: 개념은 **인용 가능한 서술 단위**의 조각을 모은다. 그 단위가 무엇인지는
코퍼스가 선언한다(유도하지 않는다 — `app_scopes`·`work_scopes`에서 유도했다가 조용히
틀린 전례가 반복됐다)."""
import unittest

import corpus as cp
import structure_app as sa


TIER_A = [
    {"anchor": "INV-09", "kind": "article", "scope": "s/inv", "content": "조항 본문"},
    {"anchor": "INV01§상태", "kind": "screen_section", "scope": "s/inv", "content": "화면 서술"},
    {"anchor": "Item.Status", "kind": "field", "scope": "s/inv", "content": "필드 정의"},
    {"anchor": "spec§개요", "kind": "spec_section", "scope": "s/inv", "content": "개요"},
    {"anchor": "OTHER-1", "kind": "article", "scope": "s/other", "content": "타 앱"},
]


class TestRegistryDeclaresUnits(unittest.TestCase):
    def test_corpdoc_declares_more_than_articles(self):
        kinds = cp.statement_kinds_for("acme-docs")
        self.assertIn("article", kinds)
        self.assertIn("screen_section", kinds)          # ★화면도 서술 단위다

    def test_prose_corpora_declare_section(self):
        for c in ("personal-wevolley", "lab-self"):
            self.assertIn("section", cp.statement_kinds_for(c), c)

    def test_undeclared_corpus_falls_back_to_something_usable(self):
        """선언이 없다고 0건이 되면 안 된다 — 조용히 빈 본문이 되는 게 이 결함의 형태였다."""
        self.assertTrue(cp.statement_kinds_for("nosuch"))


class TestUnitsForScope(unittest.TestCase):
    def test_only_declared_kinds_pass(self):
        got = sa.statement_units(TIER_A, "s/inv", kinds=("article", "screen_section"))
        self.assertEqual([u["anchor"] for u in got], ["INV-09", "INV01§상태"])

    def test_scope_still_bounds_it(self):
        got = sa.statement_units(TIER_A, "s/inv", kinds=("article",))
        self.assertEqual([u["anchor"] for u in got], ["INV-09"])

    def test_prose_corpus_gets_its_sections(self):
        prose = [{"anchor": "doc§a", "kind": "section", "scope": "w", "content": "산문"}]
        self.assertEqual([u["anchor"] for u in sa.statement_units(prose, "w", ("section",))],
                         ["doc§a"])

    def test_units_carry_their_kind(self):
        """소비자가 조항과 화면을 갈라 볼 수 있어야 한다(`how` 렌더링이 쓴다)."""
        got = sa.statement_units(TIER_A, "s/inv", kinds=("article", "field"))
        self.assertEqual({u["anchor"]: u["kind"] for u in got},
                         {"INV-09": "article", "Item.Status": "field"})

    def test_empty_text_unit_is_dropped(self):
        got = sa.statement_units([{"anchor": "x", "kind": "article", "scope": "s"}],
                                 "s", ("article",))
        self.assertEqual(got, [])


class TestMembersAcceptBothKeys(unittest.TestCase):
    """`members`의 키가 `article`에서 `unit`이 됐다 — 기존 원장은 계속 읽힌다."""

    def test_new_key_works(self):
        out = sa.assemble_body_fragments(
            [{"sid": "inv#a", "target": None}], TIER_A,
            members={"inv#a": [{"unit": "INV01§상태", "quote": "화면 서술"}]})
        self.assertEqual([f["key"] for f in out["inv#a"]], ["INV01§상태|content"])

    def test_legacy_article_key_still_works(self):
        out = sa.assemble_body_fragments(
            [{"sid": "inv#a", "target": None}], TIER_A,
            members={"inv#a": [{"article": "INV-09", "quote": "조항 본문"}]})
        self.assertEqual([f["key"] for f in out["inv#a"]], ["INV-09|content"])

    def test_screen_unit_becomes_body(self):
        """★이 회차의 핵심 — 화면 서술이 정본 본문이 된다(종전 편입 0)."""
        out = sa.assemble_body_fragments(
            [{"sid": "inv#a", "target": None}], TIER_A,
            members={"inv#a": [{"unit": "INV01§상태", "quote": "화면"}]})
        self.assertTrue(out["inv#a"])


if __name__ == "__main__":
    unittest.main()


class TestSpecSectionCarriesBody(unittest.TestCase):
    """★spec_section의 본문이 제목뿐이었다."""

    SRC = """## 개요

이 제품은 매장 보관함을 관리한다.
정책은 [CTN-01]을 따른다.

## 리소스 · 데이터 정의

| 리소스/엔티티 | 필드 | 타입 | 필수 | 설명 |
| Locker | name | string | O | 이름 |

## 기본 정책

재고 집계는 일 1회 자동 생성된다.
"""

    def test_prose_lines_become_content(self):
        from parsers import parse_corpdoc_spec
        by = {c["anchor"]: c for c in parse_corpdoc_spec(self.SRC, scope="s")["concepts"]}
        c = by["spec§개요"]
        self.assertIn("매장 보관함을 관리한다", c["content"])
        self.assertIn("CTN-01", str(c["refs"]["articles"]))

    def test_table_rows_not_duplicated_into_section(self):
        """표는 field/state_enum 단위가 따로 진다 — 두 번 담으면 조각이 중복된다."""
        from parsers import parse_corpdoc_spec
        by = {c["anchor"]: c for c in parse_corpdoc_spec(self.SRC, scope="s")["concepts"]}
        self.assertNotIn("Locker", by["spec§리소스 · 데이터 정의"]["content"])

    def test_general_section_table_is_body(self):
        """★일반 절의 본문은 이 코퍼스에서 대부분 **표**다(실측: §범위·§기본 정책).
        field/enum 절이 아니면 표를 담당할 다른 단위가 없다 — 안 담으면 본문이 0이다.
        1차 수리(산문만)가 표를 건너뛰어 중앙값 5→6자에 머물렀다(수리가 헛돌았다)."""
        from parsers import parse_corpdoc_spec
        src = "## 기본 정책\n\n| 항목 | 내용 |\n|---|---|\n| 앱 유형 | 매장 종속 |\n"
        by = {c["anchor"]: c for c in parse_corpdoc_spec(src, scope="s")["concepts"]}
        self.assertIn("매장 종속", by["spec§기본 정책"]["content"])
        self.assertNotIn("|---|", by["spec§기본 정책"]["content"])

    def test_heading_only_section_stays_thin(self):
        """본문이 진짜 없으면 그대로 얇다 — 지어내지 않는다."""
        from parsers import parse_corpdoc_spec
        by = {c["anchor"]: c for c in
              parse_corpdoc_spec("## 빈 절\n\n## 다음 절\n내용\n", scope="s")["concepts"]}
        self.assertEqual(by["spec§빈 절"]["content"], "빈 절")
