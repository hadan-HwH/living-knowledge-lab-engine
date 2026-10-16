"""정본 주입 좁히기 — 조항은 앱 단위, 개념은 코퍼스 전량 (소유자 결정 2026-08-04).

    Tier A — 대상 앱 자신의 조항            필요
    Tier A — 같은 제품군 타 앱 조항         ← 대상 앱 섹션이 실제로 인용한 건 **극소수**
    Tier B — 정본 개념 전량                 어휘 재사용엔 필요하나 head가 크다

타 앱 조항의 절반 이상이 **다른 앱의 화면 섹션·필드**다. 한 앱의 개념을 뽑는 데
다른 앱 화면정의서 조각이 필요할 리가 없다. 주입량이 원본 문서 전체보다 컸던 게
그 자체로 신호였다(비공개 코퍼스 실측).

★두 축을 다르게 좁힌다:
  **조항(Tier A)은 앱 단위** — 제품군(2세그먼트)은 너무 넓다. 다른 앱 조항이 정말
    필요한 경우는 문서가 식별자를 통째로 인용할 때이고, 그건 `_anchor_cited`가 이미 잡는다.
  **개념(Tier B)은 코퍼스 전량 유지** — 코퍼스 안에서 앱은 정체성 경계가 아니다(3단계
    결정 불변). 대신 `head`를 뺀다. Tier B의 `name`은 계약상 "개념명+짧은 설명"이라
    head가 중복이다."""
import unittest

import corpus as cp
from canon_select import select_canon


SECTIONS = [{"text": "이 화면은 묶음 배송을 붙인다"}]
INV = "prime-commerce/summit/inv"


def _a(anchor, scope, name=None):
    return {"anchor": anchor, "scope": scope, "name": name, "tier": "A"}


def _b(anchor, scope, name):
    return {"anchor": anchor, "scope": scope, "name": name, "tier": "B", "content": "설명"}


class TestArticlesNarrowToTheApp(unittest.TestCase):
    def test_same_app_article_is_injected(self):
        picked = select_canon(INV, SECTIONS, [_a("INV-09", INV)])
        self.assertEqual([c["anchor"] for c in picked], ["INV-09"])

    def test_sibling_app_in_the_same_family_is_not(self):
        """종전엔 같은 플랫폼의 모든 앱 조항이 전부 들어왔다."""
        picked = select_canon(INV, SECTIONS, [_a("ALERT-01", "prime-commerce/summit/alert")])
        self.assertEqual(picked, [])

    def test_cited_article_from_anywhere_still_comes_in(self):
        """문서가 식별자를 통째로 인용하면 들어온다 — 좁혀도 이 길은 막지 않는다."""
        picked = select_canon(INV, [{"text": "STORAGE-01에 따라 처리한다"}],
                              [_a("STORAGE-01", "prime-commerce/atlas/stock")])
        self.assertEqual([c["anchor"] for c in picked], ["STORAGE-01"])

    def test_sub_scope_of_the_app_is_still_injected(self):
        picked = select_canon(INV, SECTIONS, [_a("X-1", INV + "/users")])
        self.assertEqual([c["anchor"] for c in picked], ["X-1"])

    def test_shared_tier_is_untouched(self):
        picked = select_canon(INV, SECTIONS, [_a("F-1", "foundations/naming")],
                              shared_tiers=("foundations",))
        self.assertEqual([c["anchor"] for c in picked], ["F-1"])


class TestDeclaredScopeMergeIsHonoured(unittest.TestCase):
    """registry `concept_scope_merges` — 선언만 있고 아무도 안 읽던 것을 실제로 쓴다."""

    def test_registry_declares_the_inv_pair(self):
        merges = cp.concept_scope_merges_for("acme-docs")
        self.assertIn("prime-commerce/summit/inv-system", merges.get(INV, []))

    def test_merged_scope_survives_app_narrowing(self):
        picked = select_canon(INV, SECTIONS,
                              [_a("INVSYS-01", "prime-commerce/summit/inv-system")],
                              merged_scopes=("prime-commerce/summit/inv-system",))
        self.assertEqual([c["anchor"] for c in picked], ["INVSYS-01"])

    def test_without_the_declaration_it_would_be_dropped(self):
        picked = select_canon(INV, SECTIONS,
                              [_a("INVSYS-01", "prime-commerce/summit/inv-system")])
        self.assertEqual(picked, [])


class TestConceptsStayCorpusWide(unittest.TestCase):
    """3단계 결정 불변 — 코퍼스 안에서 앱은 정체성 경계가 아니다."""

    def test_other_app_concept_is_still_injected(self):
        picked = select_canon(INV, SECTIONS,
                              [_b("courier#sc-parcel", "prime-commerce/atlas/courier", "Parcel")])
        self.assertEqual([c["anchor"] for c in picked], ["courier#sc-parcel"])


class TestSlimProjection(unittest.TestCase):
    def test_concept_drops_head_but_keeps_name(self):
        """Tier B의 `name`은 계약상 '개념명+짧은 설명'이라 head가 중복이다."""
        import structure_app as sa
        out = sa._slim_canon({"anchor": "inv#sc-x", "kind": "concept", "scope": "s",
                              "name": "X (짧은 설명)", "content": "긴 본문", "tier": "B"})
        self.assertNotIn("head", out)
        self.assertEqual(out["name"], "X (짧은 설명)")

    def test_article_keeps_head(self):
        import structure_app as sa
        out = sa._slim_canon({"anchor": "INV-09", "kind": "article", "scope": "s",
                              "content": "조항 본문", "tier": "A"})
        self.assertEqual(out["head"], "조항 본문")


if __name__ == "__main__":
    unittest.main()
