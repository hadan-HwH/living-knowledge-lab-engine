"""변경 축 테스트 — 설계: docs/2-method/change-layer-design.md. 전부 결정론(LLM 0)."""
import unittest

from change_layer import (diff_fragments, stale_nodes, stale_relations,
                          equivalence_check, evolution_log)

OLD = [
    {"concept": "INV-14", "field": "content", "text": "Coupon PIN은 생성 시 1회만 노출"},
    {"concept": "INV-17", "field": "table[5]", "text": "| Status | 가능 | 상호 전환만 |"},
    {"concept": "INV-45", "field": "content", "text": "장기 보류 시 Paused 전환"},
    {"concept": "INV-99", "field": "content", "text": "삭제될 조항"},
]
NEW = [
    {"concept": "INV-14", "field": "content", "text": "Coupon PIN은 생성 시 1회만 노출 `[INV-17]`"},
    {"concept": "INV-17", "field": "table[5]", "text": "| Status | 가능 | 상호 전환만 |"},
    {"concept": "INV-45", "field": "content", "text": "장기 보류 시 Paused 전환"},
    {"concept": "INV-76", "field": "content", "text": "신설 조항"},
]


class TestDiffFragments(unittest.TestCase):
    def test_added_removed_changed_by_key(self):
        d = diff_fragments(OLD, NEW)
        self.assertEqual(d["changed"], [("INV-14", "content")])
        self.assertEqual(d["removed"], [("INV-99", "content")])
        self.assertEqual(d["added"], [("INV-76", "content")])

    def test_whitespace_only_change_is_not_a_change(self):
        new = [dict(OLD[0], text="Coupon PIN은  생성 시 1회만   노출")] + OLD[1:]
        d = diff_fragments(OLD, new)
        self.assertEqual(d["changed"], [])


class TestStaleNodes(unittest.TestCase):
    def test_changed_and_removed_use_old_homes_added_uses_new(self):
        d = diff_fragments(OLD, NEW)
        old_homes = {("INV-14", "content"): "term:Promo Code.Coupon PIN",
                     ("INV-99", "content"): "term:Item.Barcode"}
        new_homes = {("INV-76", "content"): "concept:Item"}
        self.assertEqual(stale_nodes(d, old_homes, new_homes),
                         ["concept:Item", "term:Item.Barcode", "term:Promo Code.Coupon PIN"])

    def test_unmapped_key_does_not_crash(self):
        d = diff_fragments(OLD, NEW)
        self.assertEqual(stale_nodes(d, {}, {}), [])


class TestStaleRelations(unittest.TestCase):
    RELS = [
        {"from": "a", "rel": "affects", "to": "b",
         "evidence": {"concept": "INV-14", "field": "content",
                      "quote": "Coupon PIN은 생성 시 1회만 노출"}},   # changed, quote 생존
        {"from": "c", "rel": "triggers", "to": "d",
         "evidence": {"concept": "INV-99", "field": "content",
                      "quote": "삭제될 조항"}},                        # removed
        {"from": "e", "rel": "affects", "to": "f",
         "evidence": {"concept": "INV-45", "field": "content",
                      "quote": "장기 보류 시 Paused 전환"}},      # untouched
    ]

    def test_classification_auto_ok_requeue_unaffected(self):
        d = diff_fragments(OLD, NEW)
        r = stale_relations(self.RELS, d, NEW)
        self.assertEqual([x["i"] for x in r["auto_ok"]], [0])   # quote가 신 원문에 실재
        self.assertEqual([x["i"] for x in r["requeue"]], [1])   # 조각 제거 → 재판정 큐
        self.assertEqual([x["i"] for x in r["unaffected"]], [2])

    def test_changed_fragment_killing_quote_goes_to_requeue(self):
        new = [dict(NEW[0], text="전면 재작성된 문장")] + NEW[1:]
        d = diff_fragments(OLD, new)
        r = stale_relations(self.RELS, d, new)
        self.assertEqual([x["i"] for x in r["requeue"]], [0, 1])


class TestEquivalenceGate(unittest.TestCase):
    def test_incremental_equals_full_when_stale_is_correct(self):
        old = {"n1": ["f1"], "n2": ["f2"]}
        new = {"n1": ["f1"], "n2": ["f2 변경"], "n3": ["f3"]}
        rep = equivalence_check(old, new, stale=["n2", "n3"])
        self.assertTrue(rep["equal"])
        self.assertEqual(rep["missed_stale"], [])
        self.assertEqual(rep["false_stale"], [])

    def test_missed_stale_breaks_gate(self):
        old = {"n1": ["f1"], "n2": ["f2"]}
        new = {"n1": ["f1 변경"], "n2": ["f2"]}
        rep = equivalence_check(old, new, stale=[])
        self.assertFalse(rep["equal"])
        self.assertEqual(rep["missed_stale"], ["n1"])

    def test_false_stale_reported_but_gate_holds(self):
        old = {"n1": ["f1"]}
        new = {"n1": ["f1"]}
        rep = equivalence_check(old, new, stale=["n1"])
        self.assertTrue(rep["equal"])            # 결과는 동일 — 게이트 통과
        self.assertEqual(rep["false_stale"], ["n1"])   # 낭비는 기록


class TestEvolutionLog(unittest.TestCase):
    def test_concept_level_changelog(self):
        d = diff_fragments(OLD, NEW)
        old_homes = {("INV-14", "content"): "term:Promo Code.Coupon PIN",
                     ("INV-17", "table[5]"): "concept:Promo Code",
                     ("INV-99", "content"): "term:Item.Barcode"}
        new_homes = {("INV-14", "content"): "term:Promo Code.Coupon PIN",
                     ("INV-17", "table[5]"): "concept:Promo Code",
                     ("INV-76", "content"): "concept:Item"}
        log = evolution_log(d, old_homes, new_homes, ("5a0a004", "0a0a001"))
        self.assertEqual(log["sha_pair"], ["5a0a004", "0a0a001"])
        self.assertEqual(log["nodes_added"], ["concept:Item"])
        self.assertEqual(log["nodes_removed"], ["term:Item.Barcode"])
        self.assertEqual(log["fragments"],
                         {"added": 1, "removed": 1, "changed": 1, "unchanged": 2})


if __name__ == "__main__":
    unittest.main()
