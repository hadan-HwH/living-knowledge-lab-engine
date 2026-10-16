"""귀속은 개념 정체성을 따라간다 — 병합된 하위개념의 본문이 갈 곳을 잃던 결함.

구조는 이렇다. 추출기가 이미 정본인 개념을 다시 관측하면 계약이 두 경로를 허용한다:

ⓑ는 계약 §1b가 **명시적으로 권하는** 경로다("그 자리에서 그 anchor를 align target으로
지정"). 그런데 개념층만 그 매핑을 따랐고 본문층은 안 따랐다 —

  `members.yaml` 키 = 하위개념 sid(`wevolley#sc-broadcast-from-database`)
  정본 개념 anchor  = 병합 대상(`wevolley#sc-realtime-hybrid`)

`assemble_body_fragments`가 sid로 조각을 키잉하니 조각은 sid에 쌓이고, 실제 정본 개념은
**단위 0**으로 남는다. 겉으로는 "그 개념은 아직 근거가 없다"로 보이는데 근거는 있었고
자리를 잘못 찾은 것이다. 화석과 구분이 안 된다."""
import unittest

import structure_app as sa


class TestRekeyMembersToCanon(unittest.TestCase):
    def test_a_merged_subconcept_hands_its_units_to_the_canon_concept(self):
        members = {"w#sc-broadcast-from-database": [{"unit": "u1", "quote": "q"}]}
        auto_fold = [{"sid": "w#sc-broadcast-from-database", "target": "w#sc-realtime-hybrid"}]
        out = sa.rekey_members_to_canon(members, auto_fold)
        self.assertEqual(out, {"w#sc-realtime-hybrid": [{"unit": "u1", "quote": "q"}]})

    def test_reusing_the_same_anchor_changes_nothing(self):
        """실측상 대부분이 이 경로 — 무해해야 한다."""
        members = {"w#sc-a": [{"unit": "u1", "quote": "q"}]}
        auto_fold = [{"sid": "w#sc-a", "target": "w#sc-a"}]
        self.assertEqual(sa.rekey_members_to_canon(members, auto_fold), members)

    def test_a_sid_absent_from_auto_fold_is_untouched(self):
        members = {"w#sc-new": [{"unit": "u1", "quote": "q"}]}
        self.assertEqual(sa.rekey_members_to_canon(members, []), members)

    def test_two_subconcepts_merging_into_one_concept_union_their_units(self):
        members = {"w#sc-x": [{"unit": "u1", "quote": "q1"}],
                   "w#sc-y": [{"unit": "u2", "quote": "q2"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"},
                     {"sid": "w#sc-y", "target": "w#sc-t"}]
        out = sa.rekey_members_to_canon(members, auto_fold)
        self.assertEqual(sorted(m["unit"] for m in out["w#sc-t"]), ["u1", "u2"])

    def test_an_identical_unit_and_quote_is_not_duplicated_on_merge(self):
        members = {"w#sc-x": [{"unit": "u1", "quote": "q"}],
                   "w#sc-y": [{"unit": "u1", "quote": "q"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"},
                     {"sid": "w#sc-y", "target": "w#sc-t"}]
        self.assertEqual(len(sa.rekey_members_to_canon(members, auto_fold)["w#sc-t"]), 1)

    def test_units_already_on_the_target_survive_the_merge(self):
        """병합 대상이 자기 귀속을 이미 갖고 있으면 덮지 않는다 — 잃는 게 없어야 한다."""
        members = {"w#sc-t": [{"unit": "u0", "quote": "q0"}],
                   "w#sc-x": [{"unit": "u1", "quote": "q1"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"}]
        out = sa.rekey_members_to_canon(members, auto_fold)
        self.assertEqual(sorted(m["unit"] for m in out["w#sc-t"]), ["u0", "u1"])

    def test_an_auto_fold_row_without_a_target_is_ignored(self):
        members = {"w#sc-x": [{"unit": "u1", "quote": "q"}]}
        self.assertEqual(sa.rekey_members_to_canon(members, [{"sid": "w#sc-x"}]), members)

    def test_empty_inputs_are_safe(self):
        self.assertEqual(sa.rekey_members_to_canon({}, []), {})
        self.assertEqual(sa.rekey_members_to_canon({}, None), {})


class TestRekeyBodiesToCanon(unittest.TestCase):
    """정본에 **이미 쌓인** 조각도 옮겨야 한다 — 안 그러면 결함이 스스로를 재생산한다.

    그래서 옮기는 지점을 `prev_bodies` 한 곳으로 잡는다 — 거기서 옮기면 뒤따르는
    `members_from_canon`도 자동으로 옳은 키를 낸다(고칠 자리가 둘이 아니라 하나다)."""

    def test_a_stale_orphan_key_is_migrated_to_its_canon_concept(self):
        bodies = {"w#sc-x": [{"key": "u1|content", "text": "지식"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"}]
        out = sa.rekey_bodies_to_canon(bodies, auto_fold)
        self.assertEqual(list(out), ["w#sc-t"])
        self.assertEqual(out["w#sc-t"][0]["text"], "지식")

    def test_fragments_already_on_the_target_are_kept(self):
        bodies = {"w#sc-t": [{"key": "u0|content", "text": "먼저"}],
                  "w#sc-x": [{"key": "u1|content", "text": "나중"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"}]
        out = sa.rekey_bodies_to_canon(bodies, auto_fold)
        self.assertEqual([f["key"] for f in out["w#sc-t"]], ["u0|content", "u1|content"])

    def test_the_same_fragment_key_is_not_duplicated(self):
        bodies = {"w#sc-t": [{"key": "u1|content", "text": "지식"}],
                  "w#sc-x": [{"key": "u1|content", "text": "지식"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"}]
        self.assertEqual(len(sa.rekey_bodies_to_canon(bodies, auto_fold)["w#sc-t"]), 1)

    def test_the_quote_fragment_of_the_merged_concept_does_not_overwrite_the_targets(self):
        """`quote`는 조각 key가 겹치는 유일한 자리다 — 대상의 것이 이긴다(먼저 온 것)."""
        bodies = {"w#sc-t": [{"key": "quote", "text": "정본 인용"}],
                  "w#sc-x": [{"key": "quote", "text": "병합된 쪽 인용"}]}
        auto_fold = [{"sid": "w#sc-x", "target": "w#sc-t"}]
        out = sa.rekey_bodies_to_canon(bodies, auto_fold)
        self.assertEqual([f["text"] for f in out["w#sc-t"]], ["정본 인용"])

    def test_untouched_when_nothing_was_merged(self):
        bodies = {"w#sc-a": [{"key": "u|content", "text": "t"}]}
        self.assertEqual(sa.rekey_bodies_to_canon(bodies, []), bodies)

    def test_a_history_fragment_survives_beside_its_current_version(self):
        """★이력 조각은 현행과 **같은 key**를 쓴다 — 축 2의 설계가 그렇다.

        `fold_fragment_versions`는 같은 key의 텍스트가 바뀌면 옛 조각에 `superseded_at`을
        달아 남기고 새 조각을 현행으로 올린다. 그래서 한 개념 안에 `U|content`가 **둘**
        존재하는 게 정상이다.

        조각의 정체성은 `key`가 아니라 `(key, superseded_at)`이다."""
        bodies = {"w#sc-x": [{"key": "u|content", "text": "새 서술"},
                             {"key": "u|content", "text": "옛 서술",
                              "superseded_at": "abc1234"}]}
        auto_fold = [{"sid": "w#sc-y", "target": "w#sc-t"}]      # remap 활성화(다른 sid)
        out = sa.rekey_bodies_to_canon(bodies, auto_fold)
        self.assertEqual(len(out["w#sc-x"]), 2)
        self.assertEqual({f.get("superseded_at") for f in out["w#sc-x"]}, {None, "abc1234"})

    def test_two_history_versions_of_the_same_unit_both_survive(self):
        """회차가 쌓이면 한 key에 이력이 여럿 붙는다 — 전부 남아야 한다."""
        bodies = {"w#sc-x": [{"key": "u|content", "text": "현행"},
                             {"key": "u|content", "text": "1세대", "superseded_at": "aaa"},
                             {"key": "u|content", "text": "2세대", "superseded_at": "bbb"}]}
        out = sa.rekey_bodies_to_canon(bodies, [{"sid": "w#sc-y", "target": "w#sc-t"}])
        self.assertEqual(len(out["w#sc-x"]), 3)

    def test_merging_still_drops_a_genuinely_identical_fragment(self):
        """중복 제거 자체는 유지된다 — 같은 key·같은 버전이면 하나다."""
        bodies = {"w#sc-t": [{"key": "u|content", "text": "지식"}],
                  "w#sc-x": [{"key": "u|content", "text": "지식"}]}
        out = sa.rekey_bodies_to_canon(bodies, [{"sid": "w#sc-x", "target": "w#sc-t"}])
        self.assertEqual(len(out["w#sc-t"]), 1)


class TestNoBodyIsStrandedAfterPromote(unittest.TestCase):
    """★불변식으로 건다 — **모든 본문 키는 실재하는 개념을 가리킨다.**"""

    def test_stranded_body_keys_are_reported(self):
        concepts = [{"anchor": "w#sc-a"}]
        bodies = {"w#sc-a": [], "w#sc-ghost": [{"key": "u|content", "text": "지식"}]}
        self.assertEqual(sa.stranded_bodies(concepts, bodies), ["w#sc-ghost"])

    def test_no_stranded_keys_reports_empty(self):
        concepts = [{"anchor": "w#sc-a"}]
        self.assertEqual(sa.stranded_bodies(concepts, {"w#sc-a": []}), [])


if __name__ == "__main__":
    unittest.main()
