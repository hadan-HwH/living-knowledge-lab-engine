"""개념 본체 비교 탐침(body_probe) 테스트 — 설계: docs/2-method/concept-body-design.md §3-③."""
import unittest

from body_probe import (collect_fragments, assemble_a, verify_body,
                        coverage, impact_of)

CONCEPTS = [
    {"anchor": "U.Status", "kind": "state_enum", "scope": "s",
     "values": ["Active", "Paused"],
     "value_notes": {"Paused": "중지. 규칙 `[X-04]`"}},
    {"anchor": "X-04", "kind": "article", "scope": "s",
     "content": "Paused 상품은 주문할 수 없다",
     "fields": {"참조": "Promo Code 차단은 `[X-19]`"},
     "table": ["| Status | 가능 | Active ↔ Paused 전환만 |"]},
    {"anchor": "X-19", "kind": "article", "scope": "s",
     "content": "Paused인 경우 모든 Promo Code 적용을 차단해야 한다"},
]

TERM = {"anchor": "term:Item.Paused", "surface": "Paused", "resource": "Item",
        "members": [
            {"concept": "U.Status", "kind": "state_enum", "basis": "machine",
             "note": "중지. 규칙 `[X-04]`"},
            {"concept": "X-04", "kind": "article", "field": "content", "basis": "llm",
             "quote": "주문할 수 없다"},
            {"concept": "X-04", "kind": "article", "field": "table[0]", "basis": "llm",
             "quote": "Active ↔ Paused 전환만"},
            {"concept": "X-04", "kind": "article", "field": "fields.참조", "basis": "machine"},
            {"concept": "X-19", "kind": "article", "field": "content", "basis": "llm",
             "quote": "적용을 차단"},
        ]}


class TestCollectFragments(unittest.TestCase):
    def setUp(self):
        self.frags = collect_fragments(TERM, CONCEPTS)

    def test_all_members_resolved_with_provenance(self):
        # 멤버 5 → (concept, field) 단위 조각 5 (dedup 대상 없음)
        self.assertEqual(len(self.frags), 5)
        for f in self.frags:
            self.assertIn("fid", f)
            self.assertIn("concept", f)
            self.assertTrue(f["text"])          # 원문 해소 실패는 조각이 아님

    def test_texts_are_source_verbatim(self):
        by_field = {(f["concept"], f.get("field")): f["text"] for f in self.frags}
        self.assertEqual(by_field[("X-04", "content")], "Paused 상품은 주문할 수 없다")
        self.assertEqual(by_field[("X-04", "table[0]")], "| Status | 가능 | Active ↔ Paused 전환만 |")
        self.assertEqual(by_field[("U.Status", None)], "중지. 규칙 `[X-04]`")

    def test_fids_deterministic(self):
        again = collect_fragments(TERM, CONCEPTS)
        self.assertEqual([f["fid"] for f in self.frags], [f["fid"] for f in again])

    def test_unresolvable_member_is_flagged_not_invented(self):
        term = {**TERM, "members": TERM["members"] + [
            {"concept": "X-99", "kind": "article", "field": "content", "basis": "llm"}]}
        frags = collect_fragments(term, CONCEPTS)
        self.assertEqual(len(frags), 5)          # 지어내지 않음
        # 미해소는 별도 표기로 반환
        unresolved = collect_fragments(term, CONCEPTS, return_unresolved=True)[1]
        self.assertEqual(unresolved, [{"concept": "X-99", "field": "content"}])


class TestAssembleA(unittest.TestCase):
    def test_every_fragment_verbatim_once_with_citation(self):
        frags = collect_fragments(TERM, CONCEPTS)
        body = assemble_a(TERM, frags)
        cited = [c for s in body["sections"] for item in s["items"] for c in [item["fid"]]]
        self.assertEqual(sorted(cited), sorted(f["fid"] for f in frags))
        texts = {i["text"] for s in body["sections"] for i in s["items"]}
        self.assertIn("Paused 상품은 주문할 수 없다", texts)  # 원문 그대로

    def test_grouping_is_structural_not_semantic(self):
        # 그룹은 출처 field 유형(구조 신호)만 사용 — 의미 판단 없음 (Q1-a 미결 유지)
        frags = collect_fragments(TERM, CONCEPTS)
        body = assemble_a(TERM, frags)
        self.assertEqual([s["group"] for s in body["sections"]],
                         [g for g in ("spec", "본문", "표", "부연")
                          if any(f["group"] == g for f in frags)])


class TestVerifyBody(unittest.TestCase):
    def setUp(self):
        self.frags = collect_fragments(TERM, CONCEPTS)
        self.fid = {(f["concept"], f.get("field")): f["fid"] for f in self.frags}

    def test_grounded_sentence_passes(self):
        s = [{"text": "Paused 상태에서는 주문할 수 없다.",
              "cites": [{"fid": self.fid[("X-04", "content")], "quote": "주문할 수 없다"}]}]
        rep = verify_body(s, self.frags)
        self.assertEqual(rep["totals"]["ok"], 1)
        self.assertEqual(rep["totals"]["pass_rate"], 1.0)

    def test_quote_mismatch_fails(self):
        s = [{"text": "임시 단가가 부여된다.",
              "cites": [{"fid": self.fid[("X-04", "content")], "quote": "임시 단가"}]}]
        rep = verify_body(s, self.frags)
        self.assertEqual(rep["totals"]["quote_mismatch"], 1)
        self.assertTrue(rep["hallucination_gate_failed"])   # 환각 1건 = 방식 탈락 게이트

    def test_uncited_or_unknown_fid_fails(self):
        s = [{"text": "인용 없는 주장.", "cites": []},
             {"text": "모르는 조각.", "cites": [{"fid": "F99", "quote": "x"}]}]
        rep = verify_body(s, self.frags)
        self.assertEqual(rep["totals"]["ok"], 0)

    def test_whitespace_normalized_like_tier_b(self):
        s = [{"text": "전환 규정.",
              "cites": [{"fid": self.fid[("X-04", "table[0]")],
                         "quote": "Active  ↔ Paused   전환만"}]}]
        self.assertEqual(verify_body(s, self.frags)["totals"]["ok"], 1)


class TestCoverageAndImpact(unittest.TestCase):
    def setUp(self):
        self.frags = collect_fragments(TERM, CONCEPTS)
        f = {(x["concept"], x.get("field")): x["fid"] for x in self.frags}
        self.sent = [
            {"text": "a", "cites": [{"fid": f[("X-04", "content")], "quote": "주문할 수 없다"}]},
            {"text": "b", "cites": [{"fid": f[("X-04", "content")], "quote": "주문할"},
                                    {"fid": f[("X-19", "content")], "quote": "적용을 차단"}]},
        ]
        self.f = f

    def test_coverage_counts_cited_fragments(self):
        cov = coverage(self.sent, self.frags)
        self.assertEqual(cov["cited"], 2)
        self.assertEqual(cov["total"], 5)
        self.assertEqual(sorted(cov["uncited"]),
                         sorted([self.f[("U.Status", None)], self.f[("X-04", "table[0]")],
                                 self.f[("X-04", "fields.참조")]]))

    def test_impact_localizes_changed_fragment(self):
        hit = impact_of(self.f[("X-04", "content")], self.sent)
        self.assertEqual(hit, [0, 1])            # 문장 인덱스로 국소화
        self.assertEqual(impact_of(self.f[("X-19", "content")], self.sent), [1])
        self.assertEqual(impact_of("F99", self.sent), [])


if __name__ == "__main__":
    unittest.main()
