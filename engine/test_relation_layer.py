"""관계 축 파일럿 테스트 — 설계: docs/2-method/relation-layer-design.md."""
import unittest

from relation_layer import (build_resource_concepts, structural_relations,
                            rehome_fragments, verify_relations,
                            r1_neighbors, r2_impact, r3_home,
                            designate_concepts, rehome_by_subject,
                            SEMANTIC_VOCAB, R2_PROPAGATE)

TERMS = [
    {"anchor": "term:Item.Active", "surface": "Active", "resource": "Item",
     "members": [{"concept": "Item.Status", "kind": "state_enum", "basis": "machine"}]},
    {"anchor": "term:Item.Paused", "surface": "Paused", "resource": "Item",
     "members": [{"concept": "Item.Status", "kind": "state_enum", "basis": "machine"}]},
    {"anchor": "term:Promo Code.Active", "surface": "Active", "resource": "Promo Code",
     "members": [{"concept": "Promo Code.Status", "kind": "state_enum", "basis": "machine"}]},
    {"anchor": "term:Promo Code.Paused", "surface": "Paused", "resource": "Promo Code",
     "members": [{"concept": "Promo Code.Status", "kind": "state_enum", "basis": "machine"}]},
    {"anchor": "term:Voucher.대상 매장", "surface": "대상 매장", "resource": "Voucher",
     "members": [{"concept": "Voucher.대상 매장", "kind": "field", "basis": "machine"}]},
]

# term별 조각 (rehome 입력): AK 두 term이 같은 조각을 공유
FRAGS = {
    "term:Item.Paused": [
        {"concept": "Item.Status", "field": None, "text": "중지."},
        {"concept": "X-45", "field": "content", "text": "장기 보류 시 Paused 전환"}],
    "term:Promo Code.Active": [
        {"concept": "Promo Code.Status", "field": None, "text": "Paused는 보존·재전환 가능"},
        {"concept": "X-17", "field": "table[5]", "text": "| Status | 가능 | 상호 전환만 |"}],
    "term:Promo Code.Paused": [
        {"concept": "Promo Code.Status", "field": None, "text": "Paused는 보존·재전환 가능"},
        {"concept": "X-17", "field": "table[5]", "text": "| Status | 가능 | 상호 전환만 |"}],
}


class TestResourceConcepts(unittest.TestCase):
    def test_convergence_promotes_machine_concepts(self):
        nodes = build_resource_concepts(TERMS)
        by = {n["anchor"]: n for n in nodes}
        self.assertIn("concept:Item", by)             # term 2개 수렴
        self.assertIn("concept:Promo Code", by)
        self.assertEqual(by["concept:Item"]["basis"], "machine")
        self.assertEqual(by["concept:Item"]["criteria"], "term-convergence")
        self.assertEqual(sorted(by["concept:Item"]["terms"]),
                         ["term:Item.Active", "term:Item.Paused"])

    def test_single_term_resource_stays_candidate(self):
        nodes = build_resource_concepts(TERMS)
        by = {n["anchor"]: n for n in nodes}
        self.assertIn("concept:Voucher", by)
        self.assertEqual(by["concept:Voucher"]["status"], "candidate")   # 수렴 미달
        self.assertEqual(by["concept:Item"]["status"], "promoted")


class TestStructuralRelations(unittest.TestCase):
    def test_value_of_and_belongs_to_machine_only(self):
        nodes = build_resource_concepts(TERMS)
        rels = structural_relations(TERMS, nodes)
        s = {(r["from"], r["rel"], r["to"]) for r in rels}
        self.assertIn(("term:Item.Paused", "value_of", "Item.Status"), s)
        self.assertIn(("term:Item.Paused", "belongs_to", "concept:Item"), s)
        self.assertIn(("term:Voucher.대상 매장", "belongs_to", "concept:Voucher"), s)
        self.assertTrue(all(r["basis"] == "machine" for r in rels))

    def test_field_term_has_no_value_of(self):
        nodes = build_resource_concepts(TERMS)
        rels = structural_relations(TERMS, nodes)
        self.assertFalse([r for r in rels
                          if r["from"] == "term:Voucher.대상 매장" and r["rel"] == "value_of"])


class TestRehome(unittest.TestCase):
    def test_shared_fragment_rehomed_to_resource_concept(self):
        nodes = build_resource_concepts(TERMS)
        res = rehome_fragments(FRAGS, TERMS, nodes)
        # AK 공유 조각 2개 → concept:Promo Code로 재배치
        self.assertEqual(res["homes"][("Promo Code.Status", None)], "concept:Promo Code")
        self.assertEqual(res["homes"][("X-17", "table[5]")], "concept:Promo Code")
        # 단독 조각은 자기 term이 집
        self.assertEqual(res["homes"][("X-45", "content")], "term:Item.Paused")

    def test_duplication_measured_before_after(self):
        nodes = build_resource_concepts(TERMS)
        res = rehome_fragments(FRAGS, TERMS, nodes)
        self.assertEqual(res["duplication"]["before"], 2)   # 2조각이 중복 소유
        self.assertEqual(res["duplication"]["after"], 0)

    def test_cross_resource_share_goes_to_ambiguous(self):
        frags = {**FRAGS, "term:Item.Paused": FRAGS["term:Item.Paused"] + [
            {"concept": "X-17", "field": "table[5]", "text": "| Status | 가능 | 상호 전환만 |"}]}
        nodes = build_resource_concepts(TERMS)
        res = rehome_fragments(frags, TERMS, nodes)
        self.assertIn(("X-17", "table[5]"), res["ambiguous"])   # 리소스 넘는 공유=판정 큐
        self.assertNotIn(("X-17", "table[5]"), res["homes"])


class TestVerifyAndQueries(unittest.TestCase):
    def setUp(self):
        self.frag_pool = [f for fs in FRAGS.values() for f in fs]
        self.rels = [
            {"from": "concept:주문보류", "to": "term:Item.Paused", "rel": "triggers",
             "evidence": {"concept": "X-45", "field": "content", "quote": "장기 보류 시 Paused 전환"}},
            {"from": "term:Item.Paused", "to": "concept:Promo Code", "rel": "affects",
             "evidence": {"concept": "X-45", "field": "content", "quote": "없는 문장"}},
        ]

    def test_verify_relations_roundtrip_gate(self):
        rep = verify_relations(self.rels, self.frag_pool)
        self.assertEqual(rep["relations"][0]["verdict"], "ok")
        self.assertEqual(rep["relations"][1]["verdict"], "quote_mismatch")
        self.assertEqual(rep["totals"]["pass_rate"], 0.5)
        self.assertEqual(rep["vocab"], {"triggers": 1, "affects": 1})

    def test_r1_neighbors_bidirectional(self):
        edges = [{"from": "a", "to": "b", "rel": "affects"},
                 {"from": "c", "to": "a", "rel": "triggers"}]
        self.assertEqual(r1_neighbors("a", edges), ["b", "c"])

    def test_r2_impact_follows_semantic_edges_transitively(self):
        edges = [{"from": "a", "to": "b", "rel": "affects"},
                 {"from": "b", "to": "c", "rel": "affects"},
                 {"from": "a", "to": "x", "rel": "belongs_to"}]   # 구조 관계는 파급 아님
        self.assertEqual(r2_impact("a", edges), ["b", "c"])

    def test_r3_home(self):
        homes = {("X-17", "table[5]"): "concept:Promo Code"}
        self.assertEqual(r3_home(("X-17", "table[5]"), homes), "concept:Promo Code")
        self.assertIsNone(r3_home(("X-99", None), homes))


class TestVocabFreeze(unittest.TestCase):
    """어휘 동결 (소유자 판정 2026-07-31): triggers·affects·transitions_to 3종.
    동결 밖 어휘는 버리지 않고 vocab_status=candidate로 기록."""

    def test_frozen_vocab_is_three(self):
        self.assertEqual(SEMANTIC_VOCAB, ("triggers", "affects", "transitions_to"))

    def test_verify_marks_vocab_status(self):
        frag_pool = [{"concept": "X-45", "field": "content",
                      "text": "장기 보류 시 Paused 전환"}]
        rels = [
            {"from": "a", "to": "b", "rel": "transitions_to",
             "evidence": {"concept": "X-45", "field": "content",
                          "quote": "장기 보류 시 Paused 전환"}},
            {"from": "a", "to": "b", "rel": "paired_with",
             "evidence": {"concept": "X-45", "field": "content",
                          "quote": "장기 보류 시 Paused 전환"}},
        ]
        rep = verify_relations(rels, frag_pool)
        self.assertEqual(rep["relations"][0]["vocab_status"], "frozen")
        self.assertEqual(rep["relations"][1]["vocab_status"], "candidate")


class TestR2Semantics(unittest.TestCase):
    """R2 파급 = affects·triggers만 (소유자 판정 2026-07-31: transitions_to 제외 —
    상태 전이 상대는 변경 파급이 아니라 상태 기계 이웃)."""

    def test_r2_propagate_vocab(self):
        self.assertEqual(R2_PROPAGATE, ("triggers", "affects"))

    def test_r2_excludes_transitions_to(self):
        edges = [{"from": "a", "to": "b", "rel": "affects"},
                 {"from": "a", "to": "c", "rel": "transitions_to"},   # 재전환 상대
                 {"from": "b", "to": "d", "rel": "triggers"}]
        self.assertEqual(r2_impact("a", edges), ["b", "d"])

    def test_r1_still_includes_transitions_to(self):
        edges = [{"from": "a", "to": "c", "rel": "transitions_to"}]
        self.assertEqual(r1_neighbors("a", edges), ["c"])


class TestSubjectRehome(unittest.TestCase):
    """조항 주어 기준 (소유자 판정 2026-07-31 승인): 조항이 서술하는 대상의
    concept이 그 조항 조각들의 집. 소유자 지정 concept(설계 §2 기준 3) 생성 포함."""

    def test_designate_concepts_owner_basis(self):
        nodes = designate_concepts([{"name": "주문보류"}])
        self.assertEqual(nodes[0]["anchor"], "concept:주문보류")
        self.assertEqual(nodes[0]["basis"], "owner")
        self.assertEqual(nodes[0]["criteria"], "owner-designation")
        self.assertEqual(nodes[0]["status"], "promoted")

    def test_designate_concepts_tier_b_basis(self):
        # 완전판 트랙 A — Tier B 승격 concept은 basis로 구분(소유자 배치 검토 큐 표식)
        nodes = designate_concepts([{"name": "결제", "basis": "tier_b",
                                     "criteria": "body-signal"}])
        self.assertEqual(nodes[0]["basis"], "tier_b")
        self.assertEqual(nodes[0]["criteria"], "body-signal")

    def test_subject_map_moves_clause_fragments(self):
        nodes = build_resource_concepts(TERMS) + designate_concepts([{"name": "주문보류"}])
        res = rehome_fragments(FRAGS, TERMS, nodes)
        out = rehome_by_subject(res, {"X-45": "concept:주문보류"}, nodes)
        self.assertEqual(out["homes"][("X-45", "content")], "concept:주문보류")
        self.assertEqual(out["moved"], [("X-45", "content")])
        # 주어 매핑이 없는 조각은 그대로
        self.assertEqual(out["homes"][("Promo Code.Status", None)], "concept:Promo Code")

    def test_subject_map_claims_ambiguous_keys(self):
        # 축 결합 실측(0a0a001): cross-resource 공유로 ambiguous가 된 INV-45 표 행도
        # 소유자 판정(조항 주어 기준)의 적용 대상 — subject_map이 큐에서 회수한다
        frags = {**FRAGS, "term:Voucher.대상 매장": [
            {"concept": "X-45", "field": "content", "text": "장기 보류 시 Paused 전환"}]}
        nodes = build_resource_concepts(TERMS) + designate_concepts([{"name": "주문보류"}])
        res = rehome_fragments(frags, TERMS, nodes)
        self.assertIn(("X-45", "content"), res["ambiguous"])   # Item·Voucher 교차 공유
        out = rehome_by_subject(res, {"X-45": "concept:주문보류"}, nodes)
        self.assertEqual(out["homes"][("X-45", "content")], "concept:주문보류")
        self.assertNotIn(("X-45", "content"), out["ambiguous"])
        self.assertIn(("X-45", "content"), out["moved"])

    def test_subject_map_to_unknown_concept_is_ignored(self):
        nodes = build_resource_concepts(TERMS)   # 주문보류 노드 없음
        res = rehome_fragments(FRAGS, TERMS, nodes)
        out = rehome_by_subject(res, {"X-45": "concept:주문보류"}, nodes)
        self.assertEqual(out["homes"][("X-45", "content")], "term:Item.Paused")
        self.assertEqual(out["moved"], [])


if __name__ == "__main__":
    unittest.main()
