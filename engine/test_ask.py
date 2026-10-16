"""질의 3종 — 정본의 소비 경로 (소유자 지시 2026-08-04).

★왜 지금인가: 진단 D1이 "소비자 부재 — 질의 인터페이스 **0**"이었고, 
감사에서 그게 여전히 사실임이 확인됐다(`brief`는 목록이고, `impact_of`는 테스트에만 있다).
정본에 볼 게 생긴 지금 소비 경로가 없으면
"이게 쓸모 있나"를 물을 방법 자체가 없다.

세 질의는 소유자 모델에서 곧장 나온다:
  how     "a5인 현재만 본다"           → 현행 조각만, 이력은 --why로만
  impact  "조항이 정확하면 비교가 된다"  → 이 조항을 바꾸면 어느 개념·어느 관계가 흔들리나
  recent  "결정은 계속 바뀐다"          → 최근 무엇이 이력으로 내려갔나

★공통 규율: **없으면 없다고 말한다.** 빈 결과를 빈 화면으로 내면 "본 적 없다"와
"봤는데 없다"가 구분되지 않는다 — 이 프로젝트가 반복해서 당한 실패 모양이다.
"""
import unittest

from ask import ask_how, ask_impact, ask_recent


CANON = {
    "concepts": [
        {"anchor": "inv#sc-hold", "name": "주문 보류", "scope": "s/inv",
         "commitment": "frozen",
         "current": {"value": "o_INV-D-8812", "superseded": ["o_INV-D-7318"]},
         "aliases": [{"surface": "락아웃", "needs_review": True}]},
        {"anchor": "inv#sc-item", "name": "상품", "scope": "s/inv", "commitment": "frozen"},
        {"anchor": "inv#sc-promotion", "name": "Promotion", "scope": "s/inv", "commitment": "working"},
    ],
    "relations": [
        {"from": "inv#sc-hold", "to": "inv#sc-item", "canonical": "triggers"},
        {"from": "inv#sc-promotion", "to": "inv#sc-item", "canonical": "part_of"},
    ],
    "bodies": {
        "inv#sc-hold": [
            {"key": "quote", "text": "보류 유형"},
            {"key": "INV-45|content", "text": "결제 실패에 따른 주문 보류는"},
            {"key": "INV-45|fields.근거", "text": "INV-D-8812 — 보류 해제 시"},
            {"key": "INV-07|content", "text": "옛 서술", "superseded_at": "s2",
             "superseded_by": "INV-D-8812"},
            {"key": "INV-99|content", "text": "사라진 출처", "removed_at": "s2"},
        ],
        "inv#sc-item": [{"key": "INV-45|content", "text": "결제 실패에 따른 주문 보류는"}],
    },
}


class TestHow(unittest.TestCase):
    """지금 어떻게 동작하나 — 현행 평면만."""

    def test_returns_only_current_fragments(self):
        r = ask_how(CANON, "inv#sc-hold")
        keys = [f["key"] for f in r["body"]]
        self.assertEqual(keys, ["quote", "INV-45|content", "INV-45|fields.근거"])

    def test_history_is_hidden_unless_asked(self):
        self.assertEqual(ask_how(CANON, "inv#sc-hold")["history"], [])
        r = ask_how(CANON, "inv#sc-hold", why=True)
        self.assertEqual([f["key"] for f in r["history"]], ["INV-07|content", "INV-99|content"])

    def test_carries_current_decision_and_aliases(self):
        r = ask_how(CANON, "inv#sc-hold")
        self.assertEqual(r["current"]["value"], "o_INV-D-8812")
        self.assertEqual(r["aliases"], ["락아웃"])

    def test_lists_source_articles(self):
        """이 개념이 어느 조항들에서 왔나 — 축 1이 보이는 자리."""
        self.assertEqual(ask_how(CANON, "inv#sc-hold")["articles"], ["INV-45"])

    def test_name_lookup_works_too(self):
        self.assertEqual(ask_how(CANON, "주문 보류")["anchor"], "inv#sc-hold")

    def test_unknown_concept_says_so(self):
        r = ask_how(CANON, "inv#sc-nope")
        self.assertIsNone(r["anchor"])
        self.assertIn("없다", r["note"])


class TestImpact(unittest.TestCase):
    """이 조항을 바꾸면 무엇이 흔들리나."""

    def test_direct_concepts_that_cite_the_article(self):
        r = ask_impact(CANON, "INV-45")
        self.assertEqual(sorted(c["anchor"] for c in r["direct"]),
                         ["inv#sc-hold", "inv#sc-item"])

    def test_related_concepts_are_one_hop_away(self):
        r = ask_impact(CANON, "INV-45")
        self.assertEqual([x["anchor"] for x in r["related"]], ["inv#sc-promotion"])

    def test_a_concept_anchor_also_works(self):
        r = ask_impact(CANON, "inv#sc-hold")
        self.assertEqual([c["anchor"] for c in r["direct"]], ["inv#sc-hold"])
        self.assertEqual([x["anchor"] for x in r["related"]], ["inv#sc-item"])

    def test_unknown_target_says_so(self):
        r = ask_impact(CANON, "INV-999")
        self.assertEqual(r["direct"], [])
        self.assertIn("없다", r["note"])


class TestRecent(unittest.TestCase):
    """최근 무엇이 이력으로 내려갔나."""

    def test_superseded_fragments_are_listed_newest_first(self):
        r = ask_recent(CANON)
        self.assertEqual([x["key"] for x in r["superseded"]], ["INV-07|content"])
        self.assertEqual(r["superseded"][0]["superseded_by"], "INV-D-8812")

    def test_tombstones_are_separate_from_supersedes(self):
        """사라짐과 갱신은 다른 사건이다 — 섞으면 원본이 사라진 것처럼 보인다."""
        r = ask_recent(CANON)
        self.assertEqual([x["key"] for x in r["removed"]], ["INV-99|content"])

    def test_concepts_whose_decision_changed(self):
        r = ask_recent(CANON)
        self.assertEqual([x["anchor"] for x in r["decision_changed"]], ["inv#sc-hold"])

    def test_scope_filter(self):
        self.assertEqual(ask_recent(CANON, scope="s/other")["superseded"], [])

    def test_quiet_period_says_so(self):
        r = ask_recent({"concepts": [], "relations": [], "bodies": {}})
        self.assertIn("없다", r["note"])




class TestHowSplitsLayers(unittest.TestCase):
    """`how`가 출처 층을 갈라 보여준다 (소유자 지시 2026-08-05)."""

    CANON = {
        "concepts": [{"anchor": "inv#sc-x", "name": "X", "scope": "s/inv",
                      "commitment": "frozen"}],
        "relations": [],
        "bodies": {"inv#sc-x": [
            {"key": "quote", "text": "q"},
            {"key": "INV-45|content", "text": "조항 서술"},
            {"key": "INV01§상태|content", "text": "화면 서술"},
            {"key": "Item.Status|content", "text": "필드 정의"}]},
    }
    KINDS = {"INV-45": "article", "INV01§상태": "screen_section", "Item.Status": "field"}

    def test_body_is_grouped_by_source_kind(self):
        r = ask_how(self.CANON, "inv#sc-x", unit_kinds=self.KINDS)
        self.assertEqual(sorted(r["by_layer"]), ["article", "field", "screen_section"])
        self.assertEqual([f["key"] for f in r["by_layer"]["article"]], ["INV-45|content"])

    def test_gate_quote_is_not_a_layer(self):
        """게이트 인용은 감사 증거지 서술이 아니다 — 층에 안 낀다."""
        r = ask_how(self.CANON, "inv#sc-x", unit_kinds=self.KINDS)
        self.assertNotIn("quote", r["by_layer"])

    def test_unknown_kind_lands_in_its_own_bucket(self):
        """kind를 모르는 단위도 사라지지 않는다 — 조용한 누락이 이 프로젝트의 실패 모양."""
        r = ask_how(self.CANON, "inv#sc-x", unit_kinds={})
        self.assertIn("(미상)", r["by_layer"])

    def test_flat_body_is_still_available(self):
        """섞어 보는 경로도 남긴다 — 드리프트는 나란히 놓아야 보인다."""
        r = ask_how(self.CANON, "inv#sc-x", unit_kinds=self.KINDS)
        self.assertEqual(len(r["body"]), 4)


if __name__ == "__main__":
    unittest.main()
