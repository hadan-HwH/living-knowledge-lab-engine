"""단위 귀속의 루프 닫기 — 정본 조각이 자기 출처 단위를 스스로 말한다.

★처방은 이미 정본 안에 있다 — **조각의 key가 곧 귀속 기록이다.** `INV-41|fields.근거`는
"이 개념이 단위 INV-41을 소유한다"를 이미 담고 있다. 조립 대상 members를
**원장 ∪ 정본 유래**로 잡으면 루프가 닫힌다(개념층에 쓴 것과 같은 처방)."""
import unittest

import structure_app as sa


class TestMembersFromCanon(unittest.TestCase):
    """조각 key에서 귀속을 복원한다 — 정본이 자기 출처를 스스로 말한다."""

    BODIES = {
        "inv#sc-a": [{"key": "INV-41|content", "text": "t"},
                     {"key": "INV-41|fields.근거", "text": "t"},
                     {"key": "screen:X§1|content", "text": "t"},
                     {"key": "quote", "text": "감사 증거"}],
        "inv#sc-b": [{"key": "INV-43|content", "text": "t"}],
    }

    def test_units_are_recovered_from_fragment_keys(self):
        got = sa.members_from_canon(self.BODIES)
        self.assertEqual([m["unit"] for m in got["inv#sc-a"]], ["INV-41", "screen:X§1"])

    def test_quote_is_not_a_unit(self):
        """게이트 인용은 조항 파생이 아니라 감사 증거다 — 단위가 아니다."""
        units = [m["unit"] for m in sa.members_from_canon(self.BODIES)["inv#sc-a"]]
        self.assertNotIn("quote", units)

    def test_history_fragments_still_declare_ownership(self):
        """이력 조각도 귀속의 증거다 — 그 단위를 다시 조립해야 현행이 갱신된다."""
        b = {"inv#sc-a": [{"key": "INV-9|content", "text": "t", "superseded_at": "s1"}]}
        self.assertEqual([m["unit"] for m in sa.members_from_canon(b)["inv#sc-a"]], ["INV-9"])

    def test_removed_fragments_do_not_resurrect_ownership(self):
        """삭제 표시된 조각까지 다시 조립하면 지운 것이 되살아난다."""
        b = {"inv#sc-a": [{"key": "INV-9|content", "text": "t", "removed_at": "s1"}]}
        self.assertEqual(sa.members_from_canon(b).get("inv#sc-a", []), [])

    def test_ownership_filter_restricts_to_this_app(self):
        """타 앱 본문은 이번 조립의 판단 범위가 아니다."""
        got = sa.members_from_canon(self.BODIES, owned=lambda s: s == "inv#sc-b")
        self.assertEqual(sorted(got), ["inv#sc-b"])

    def test_merge_with_ledger_keeps_both_and_dedupes(self):
        """원장 ∪ 정본 — 새 회차가 실은 단위도, 정본이 이미 아는 단위도 둘 다 조립한다."""
        ledger = {"inv#sc-a": [{"unit": "INV-41", "quote": "q"}, {"unit": "INV-99"}]}
        got = sa.merge_members(ledger, sa.members_from_canon(self.BODIES))
        self.assertEqual(sorted(m["unit"] for m in got["inv#sc-a"]),
                         ["INV-41", "INV-99", "screen:X§1"])

    def test_ledger_entry_wins_so_the_gate_quote_survives(self):
        """원장 항목은 인용을 달고 온다 — 정본 유래로 덮어써서 왕복 게이트를 죽이면 안 된다."""
        ledger = {"inv#sc-a": [{"unit": "INV-41", "quote": "q"}]}
        got = sa.merge_members(ledger, sa.members_from_canon(self.BODIES))
        self.assertEqual([m for m in got["inv#sc-a"] if m["unit"] == "INV-41"][0]["quote"], "q")


class TestPartialIsJudgedPerUnit(unittest.TestCase):
    """부분 기여 보호를 **단위 단위**로 — 증분 회차에서 삭제 축이 통째로 꺼지지 않게."""

    PREV = {"inv#sc-a": [{"key": "INV-41|fields.예외", "text": "옛 예외"},
                         {"key": "INV-41|content", "text": "본문"},
                         {"key": "INV-93|content", "text": "다른 단위"}]}

    def test_deletion_within_an_observed_unit_is_real(self):
        """이번에 INV-41을 조립했는데 `fields.예외`가 없다 = 문서에서 지운 것이다."""
        fresh = {"inv#sc-a": [{"key": "INV-41|content", "text": "본문"}]}
        out = sa.fold_fragment_versions(self.PREV, fresh, at="s2",
                                        partial={"inv#sc-a"},
                                        observed_units={"inv#sc-a": {"INV-41"}})
        gone = [f for f in out["inv#sc-a"] if f["key"] == "INV-41|fields.예외"]
        self.assertEqual(gone[0].get("removed_at"), "s2")

    def test_unobserved_units_are_untouched(self):
        """조립 안 한 단위의 조각은 이번에 안 실렸을 뿐 — 거짓 삭제 금지(실측)."""
        fresh = {"inv#sc-a": [{"key": "INV-41|content", "text": "본문"}]}
        out = sa.fold_fragment_versions(self.PREV, fresh, at="s2",
                                        partial={"inv#sc-a"},
                                        observed_units={"inv#sc-a": {"INV-41"}})
        kept = [f for f in out["inv#sc-a"] if f["key"] == "INV-93|content"]
        self.assertIsNone(kept[0].get("removed_at"))

    def test_without_unit_info_the_old_whole_concept_protection_stands(self):
        """단위를 모르면 종전대로 통째 보호 — 모르는 채로 지우지 않는다."""
        fresh = {"inv#sc-a": [{"key": "INV-41|content", "text": "본문"}]}
        out = sa.fold_fragment_versions(self.PREV, fresh, at="s2", partial={"inv#sc-a"})
        self.assertTrue(all(f.get("removed_at") is None for f in out["inv#sc-a"]))

    def test_full_view_still_deletes_everything_missing(self):
        """승격분(완전한 뷰)은 종전 그대로 — 단위 정보와 무관하게 없어진 건 없어진 것."""
        fresh = {"inv#sc-a": [{"key": "INV-41|content", "text": "본문"}]}
        out = sa.fold_fragment_versions(self.PREV, fresh, at="s2")
        gone = {f["key"] for f in out["inv#sc-a"] if f.get("removed_at")}
        self.assertEqual(gone, {"INV-41|fields.예외", "INV-93|content"})

    def test_new_field_in_an_observed_unit_becomes_current(self):
        """삭제만이 아니라 **신설**도 따라와야 한다(`- 사례:` 절 신설이 실제 사례다)."""
        fresh = {"inv#sc-a": [{"key": "INV-41|content", "text": "본문"},
                              {"key": "INV-41|fields.사례", "text": "새 사례"}]}
        out = sa.fold_fragment_versions(self.PREV, fresh, at="s2",
                                        partial={"inv#sc-a"},
                                        observed_units={"inv#sc-a": {"INV-41"}})
        new = [f for f in out["inv#sc-a"] if f["key"] == "INV-41|fields.사례"]
        self.assertEqual(new[0]["text"], "새 사례")

    def test_idempotent(self):
        """같은 입력 두 번 = 같은 결과(회차 재실행 안전)."""
        fresh = {"inv#sc-a": [{"key": "INV-41|content", "text": "본문"}]}
        kw = dict(at="s2", partial={"inv#sc-a"}, observed_units={"inv#sc-a": {"INV-41"}})
        once = sa.fold_fragment_versions(self.PREV, fresh, **kw)
        twice = sa.fold_fragment_versions(once, fresh, **kw)
        self.assertEqual(once, twice)


class TestCanonDerivedAttributionIsNotARegatedClaim(unittest.TestCase):
    """정본 유래 귀속은 **새 주장이 아니라 기록된 사실**이다.

    ★여기서 다시 게이트를 걸면 **확립된 지식이 조용히 사라진다** — 그게 지금 고치고 있는
    화석화의 정확한 형태다. 게다가 문서가 정당하게 수정되면 옛 quote는 원문에서 없어지므로,
    재게이트는 **정상 편집을 침식으로 오인**한다.

    ★그래도 지어냄은 0으로 유지된다 — `_expand`는 tier_a에 **실재하는 단위**만 펼친다.
    단위가 통째로 사라졌으면 조각을 만들지 않는다(아래 시험)."""

    TIER_A = [{"anchor": "INV-41", "content": "쿨다운 60초", "fields": {"근거": "구 위키"}}]

    def test_canon_derived_unit_is_assembled_without_a_quote(self):
        rows = [{"sid": "inv#sc-a", "target": None}]
        members = {"inv#sc-a": [{"unit": "INV-41", "from_canon": True}]}
        got = sa.assemble_body_fragments(rows, self.TIER_A, members=members)
        self.assertEqual(sorted(f["key"] for f in got["inv#sc-a"]),
                         ["INV-41|content", "INV-41|fields.근거"])

    def test_a_new_ledger_claim_without_a_quote_is_still_refused(self):
        """새 주장은 종전대로 막는다 — 게이트를 없애는 게 아니다."""
        rows = [{"sid": "inv#sc-a", "target": None}]
        members = {"inv#sc-a": [{"unit": "INV-41"}]}
        self.assertEqual(sa.assemble_body_fragments(rows, self.TIER_A, members=members), {})

    def test_a_vanished_unit_fabricates_nothing(self):
        """단위가 사라졌으면 조각을 안 만든다 — 지어냄 0은 그대로."""
        rows = [{"sid": "inv#sc-a", "target": None}]
        members = {"inv#sc-a": [{"unit": "INV-999", "from_canon": True}]}
        self.assertEqual(sa.assemble_body_fragments(rows, self.TIER_A, members=members), {})

    def test_members_from_canon_marks_its_entries(self):
        """면제가 **보이게** 남는다 — 암묵적 우회는 다음 사람이 못 읽는다."""
        b = {"inv#sc-a": [{"key": "INV-41|content", "text": "t"}]}
        self.assertTrue(sa.members_from_canon(b)["inv#sc-a"][0]["from_canon"])


if __name__ == "__main__":
    unittest.main()
