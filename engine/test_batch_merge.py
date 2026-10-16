"""배치 추출 산출 병합 — 한 앱을 여러 에이전트가 나눠 추출할 때."""
import unittest

import batch_merge as bm


class TestMergeSubconcepts(unittest.TestCase):
    def test_batches_concatenate_in_anchor_order(self):
        out = bm.merge_subconcepts([[{"anchor": "sc-b", "name": "B"}],
                                    [{"anchor": "sc-a", "name": "A"}]])
        self.assertEqual([s["anchor"] for s in out["subconcepts"]], ["sc-a", "sc-b"])

    def test_the_same_anchor_in_two_batches_is_reported_not_silently_dropped(self):
        out = bm.merge_subconcepts([[{"anchor": "sc-a", "name": "첫판"}],
                                    [{"anchor": "sc-a", "name": "둘째판"}]])
        self.assertEqual(len(out["subconcepts"]), 1)
        self.assertEqual(out["anchor_collisions"], ["sc-a"])

    def test_the_first_batch_wins_a_collision(self):
        """임의 규칙이지만 **결정론**이어야 한다 — 입력 순서가 곧 우선순위다."""
        out = bm.merge_subconcepts([[{"anchor": "sc-a", "name": "첫판"}],
                                    [{"anchor": "sc-a", "name": "둘째판"}]])
        self.assertEqual(out["subconcepts"][0]["name"], "첫판")

    def test_same_name_under_different_anchors_is_reported_never_merged(self):
        """교차배치 중복 — 배치가 갈라져 같은 개념을 다른 anchor로 냈다.

        합치지 **않는다.** "둘은 같은 개념이다"는 의미 판정이고 병합기의 일이 아니다."""
        out = bm.merge_subconcepts([[{"anchor": "sc-x", "name": "봇 페르소나"}],
                                    [{"anchor": "sc-y", "name": "봇 페르소나"}]])
        self.assertEqual(len(out["subconcepts"]), 2)
        self.assertEqual(out["name_duplicates"], [("봇 페르소나", ["sc-x", "sc-y"])])

    def test_distinct_names_produce_no_report(self):
        out = bm.merge_subconcepts([[{"anchor": "sc-x", "name": "가"}],
                                    [{"anchor": "sc-y", "name": "나"}]])
        self.assertEqual(out["name_duplicates"], [])
        self.assertEqual(out["anchor_collisions"], [])


class TestMergeProposals(unittest.TestCase):
    def test_proposals_merge_by_sid_in_order(self):
        out = bm.merge_proposals([[{"sid": "w#sc-b", "target": "NEW"}],
                                  [{"sid": "w#sc-a", "target": "NEW"}]])
        self.assertEqual([p["sid"] for p in out["proposals"]], ["w#sc-a", "w#sc-b"])

    def test_a_duplicate_sid_is_reported(self):
        out = bm.merge_proposals([[{"sid": "w#sc-a", "target": "NEW"}],
                                  [{"sid": "w#sc-a", "target": "w#sc-z"}]])
        self.assertEqual(out["sid_collisions"], ["w#sc-a"])
        self.assertEqual(len(out["proposals"]), 1)


class TestMergeMembers(unittest.TestCase):
    def test_members_union_by_sid(self):
        out = bm.merge_members_files([{"w#a": [{"unit": "u1", "quote": "q1"}]},
                                      {"w#b": [{"unit": "u2", "quote": "q2"}]}])
        self.assertEqual(sorted(out["members"]), ["w#a", "w#b"])

    def test_the_same_sid_from_two_batches_unions_its_units(self):
        out = bm.merge_members_files([{"w#a": [{"unit": "u1", "quote": "q1"}]},
                                      {"w#a": [{"unit": "u2", "quote": "q2"}]}])
        self.assertEqual([m["unit"] for m in out["members"]["w#a"]], ["u1", "u2"])

    def test_an_identical_unit_and_quote_is_not_duplicated(self):
        out = bm.merge_members_files([{"w#a": [{"unit": "u1", "quote": "q1"}]},
                                      {"w#a": [{"unit": "u1", "quote": "q1"}]}])
        self.assertEqual(len(out["members"]["w#a"]), 1)

    def test_the_same_unit_with_a_different_quote_is_kept_as_separate_evidence(self):
        """같은 단위에 인용이 둘이면 둘 다 증거다 — 조각 key가 단위 단위라 손해가 없다."""
        out = bm.merge_members_files([{"w#a": [{"unit": "u1", "quote": "q1"}]},
                                      {"w#a": [{"unit": "u1", "quote": "q2"}]}])
        self.assertEqual(len(out["members"]["w#a"]), 2)


class TestMergeRelationsAndAliases(unittest.TestCase):
    def test_relations_dedupe_on_from_to_canonical(self):
        r = {"from": "a", "to": "b", "canonical": "part_of", "quote": "q"}
        out = bm.merge_relations([[r], [dict(r)]])
        self.assertEqual(len(out["relations"]), 1)

    def test_a_different_canonical_is_a_different_relation(self):
        out = bm.merge_relations([[{"from": "a", "to": "b", "canonical": "part_of"}],
                                  [{"from": "a", "to": "b", "canonical": "depends_on"}]])
        self.assertEqual(len(out["relations"]), 2)

    def test_aliases_dedupe_on_anchor_and_surface(self):
        a = {"anchor": "w#sc-x", "surface": "파티션", "confidence": "high"}
        out = bm.merge_aliases([[a], [dict(a)]])
        self.assertEqual(len(out["aliases"]), 1)

    def test_empty_batches_produce_empty_lists_not_errors(self):
        self.assertEqual(bm.merge_relations([])["relations"], [])
        self.assertEqual(bm.merge_aliases([[], []])["aliases"], [])


class TestEveryConceptKeepsExactlyOneProposal(unittest.TestCase):
    """계약 §5-4(전건 커버)는 병합 **후에도** 성립해야 한다 — 배치별로 통과해도
    합치면서 깨질 수 있는 자리라 병합기가 스스로 잰다."""

    def test_coverage_holds_when_each_batch_covered_itself(self):
        scs = bm.merge_subconcepts([[{"anchor": "sc-a", "name": "A"}],
                                    [{"anchor": "sc-b", "name": "B"}]])
        props = bm.merge_proposals([[{"sid": "w#sc-a", "target": "NEW"}],
                                    [{"sid": "w#sc-b", "target": "NEW"}]])
        rep = bm.check_coverage(scs["subconcepts"], props["proposals"], "w")
        self.assertEqual(rep, {"missing": [], "phantom": []})

    def test_a_concept_without_a_proposal_is_named(self):
        scs = bm.merge_subconcepts([[{"anchor": "sc-a", "name": "A"}]])
        rep = bm.check_coverage(scs["subconcepts"], [], "w")
        self.assertEqual(rep["missing"], ["w#sc-a"])

    def test_a_proposal_without_a_concept_is_named(self):
        rep = bm.check_coverage([], [{"sid": "w#sc-ghost", "target": "NEW"}], "w")
        self.assertEqual(rep["phantom"], ["w#sc-ghost"])


if __name__ == "__main__":
    unittest.main()
