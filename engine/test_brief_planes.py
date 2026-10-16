"""brief 두 평면 — 평소엔 '어떻게', 물을 때만 '왜'.
소유자 정의(2026-08-04): 평소에는 어떻게인지만 보면 된다. 가장 최근의 확정된 지식이다.
하지만 가끔 꼭 한 번씩 묻는다 — 왜 이렇게 흘러왔냐고.

읽어야 할 양이 **전체 개념 수가 아니라 현행 개념 수**에 비례해야 한다(탐색 비용)."""
import unittest

import brief

CONCEPTS = [
    {"anchor": "a#settled", "kind": "concept", "scope": "s", "name": "확정된 것",
     "current": {"value": "o_b"}, "history": [{"value": "o_a"}]},
    {"anchor": "a#open", "kind": "concept", "scope": "s", "name": "미결인 것",
     "current": {"open": True, "candidates": ["o_b", "o_c"]}},
    {"anchor": "a#plain", "kind": "concept", "scope": "s", "name": "결정과 무관한 것"},
    {"anchor": "a#dead", "kind": "concept", "scope": "s", "name": "죽은 것",
     "removed_at": "2026-08-01"},
]
STACK = {"concepts": CONCEPTS, "bodies": {}, "relations": [], "held": {}}
KW = dict(scope="s", tier_a=[], events=[], integrity={}, adjudications=[],
          valid_at="2030-12-31", known_at="2030-12-31")


def _block(doc, name):
    return next((b for b in doc["blocks"] if b["name"] == name), None)


class TestDefaultPlaneIsHow(unittest.TestCase):
    def test_history_is_absent_by_default(self):
        doc = brief.build(stack=STACK, **KW)
        self.assertIsNone(_block(doc, "이력"))

    def test_undecided_concept_is_shown_not_demoted(self):
        """미결도 현행 지식이다 — 평면에 살아 있어야 한다."""
        doc = brief.build(stack=STACK, **KW)
        names = [i["name"] for i in _block(doc, "개념")["items"]]
        self.assertIn("미결인 것", names)

    def test_undecided_is_labelled_so_it_can_be_asked_about(self):
        doc = brief.build(stack=STACK, **KW)
        item = [i for i in _block(doc, "개념")["items"] if i["name"] == "미결인 것"][0]
        self.assertTrue(item["current"]["open"])

    def test_tombstoned_concept_stays_off_the_plane(self):
        doc = brief.build(stack=STACK, **KW)
        names = [i["name"] for i in _block(doc, "개념")["items"]]
        self.assertNotIn("죽은 것", names)


class TestWhyPlaneOnRequest(unittest.TestCase):
    def test_history_block_appears_only_when_asked(self):
        doc = brief.build(stack=STACK, why=True, **KW)
        blk = _block(doc, "이력")
        self.assertIsNotNone(blk)
        self.assertEqual([i["anchor"] for i in blk["items"]], ["a#settled", "a#dead"])

    def test_empty_history_is_normal_not_a_failure(self):
        """'왜'는 필수가 아니다 — 마이그레이션 중엔 비어 있는 게 정상이다."""
        bare = {"concepts": [{"anchor": "a#x", "kind": "concept", "scope": "s", "name": "X"}],
                "bodies": {}, "relations": [], "held": {}}
        doc = brief.build(stack=bare, why=True, **KW)
        blk = _block(doc, "이력")
        self.assertEqual(blk["count"], 0)
        self.assertIsNotNone(blk["empty_reason"])


if __name__ == "__main__":
    unittest.main()
