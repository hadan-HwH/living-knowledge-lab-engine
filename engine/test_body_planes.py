"""축 2 — 본문의 현행 평면과 이력 평면 (소유자 설계 2026-08-04).

★소유자 모델: "개념 a는 버전이 5번 바뀔 수 있는데, a1~a4를 다 볼 필요가 없다. a5인
현재만 보고 안 바뀐 b만 보면 된다. 나머지는 이력으로 내려서 개념들의 층고를 맞춘다."

`current`/`history`는 **결정 옵션 ID**의 이력이지 본문의 이력이 아니다. a5는 옵션
`o_INV-D-8812`이 아니라 **a의 지금 서술**이다. 그 축이 없었다.

★그리고 없기만 한 게 아니라 **거꾸로 돼 있었다**: `tombstone_lost_fragments`가
양쪽에 다 있는 key에 대해 **옛 조각을 남기고 새 조각을 버렸다.**

    merged[f["key"]] = {k: v for k, v in f.items() if k != "removed_at"}   # prev를 채택
    ...
    for k, f in now.items(): merged.setdefault(k, f)                        # 새 것은 빈자리만

즉 정본 본문은 **첫 회차 텍스트에 영구 고정**된다 — 문서가 갱신돼도 정본은 안 따라간다.
게이트는 전부 통과한다: 존재 단조 ✓(조각 안 사라짐)·key 유지 ✓·재실행 diff 0 ✓.
"살아있는 위키"를 표방하면서 실제로는 화석이었다.

판정 기준(소유자 확정): **(ㄴ) 스냅샷 diff가 기본**(모든 개념에 적용, 값싸다),
**(¬) 결정 계보는 그 위에 '왜'를 붙이는 층**(`governed_by`가 있는 개념에만).
"""
import unittest

import structure_app as sa
from structure_app import current_fragments, fold_fragment_versions


def frag(key, text, **kw):
    return {"key": key, "text": text, **kw}


class TestUnchangedFragment(unittest.TestCase):
    def test_same_text_stays_current_and_does_not_duplicate(self):
        out = fold_fragment_versions({"a": [frag("INV-02|content", "그대로")]},
                                     {"a": [frag("INV-02|content", "그대로")]}, at="s2")
        self.assertEqual(out["a"], [frag("INV-02|content", "그대로")])

    def test_returning_fragment_loses_its_tombstone(self):
        out = fold_fragment_versions({"a": [frag("k", "t", removed_at="s1")]},
                                     {"a": [frag("k", "t")]}, at="s2")
        self.assertNotIn("removed_at", out["a"][0])


class TestChangedFragment(unittest.TestCase):
    PREV = {"a": [frag("INV-02|content", "옛 서술 — 즉시 삭제된다")]}
    NEW = {"a": [frag("INV-02|content", "새 서술 — 30일 뒤 삭제된다")]}

    def test_new_text_becomes_current(self):
        """★종전엔 새 텍스트가 조용히 버려졌다 — 정본이 화석이 되던 자리."""
        out = fold_fragment_versions(self.PREV, self.NEW, at="s2")
        cur = current_fragments(out["a"])
        self.assertEqual([f["text"] for f in cur], ["새 서술 — 30일 뒤 삭제된다"])

    def test_old_text_is_kept_as_history_not_deleted(self):
        out = fold_fragment_versions(self.PREV, self.NEW, at="s2")
        old = [f for f in out["a"] if f.get("superseded_at")]
        self.assertEqual([f["text"] for f in old], ["옛 서술 — 즉시 삭제된다"])
        self.assertEqual(old[0]["superseded_at"], "s2")

    def test_history_does_not_pile_up_on_re_run(self):
        """멱등 — 같은 입력을 다시 접어도 이력이 두 번 쌓이지 않는다."""
        once = fold_fragment_versions(self.PREV, self.NEW, at="s2")
        twice = fold_fragment_versions(once, self.NEW, at="s2")
        self.assertEqual(once, twice)

    def test_three_versions_keep_only_the_last_on_the_plane(self):
        v1 = {"a": [frag("k", "a1")]}
        v2 = fold_fragment_versions(v1, {"a": [frag("k", "a2")]}, at="s2")
        v3 = fold_fragment_versions(v2, {"a": [frag("k", "a3")]}, at="s3")
        self.assertEqual([f["text"] for f in current_fragments(v3["a"])], ["a3"])
        self.assertEqual(sorted(f["text"] for f in v3["a"] if f.get("superseded_at")),
                         ["a1", "a2"])


class TestGateQuoteIsNotBody(unittest.TestCase):
    """게이트 인용은 본문이 아니라 **감사 증거**다 — 버전 축에 태우지 않는다."""

    def test_quote_is_replaced_not_versioned(self):
        out = fold_fragment_versions({"a": [{"key": "quote", "text": "1회차 인용"}]},
                                     {"a": [{"key": "quote", "text": "2회차 인용"}]}, at="s2")
        self.assertEqual(out["a"], [{"key": "quote", "text": "2회차 인용"}])

    def test_empty_quote_does_not_overwrite_evidence(self):
        """빈 값은 채워진 값을 덮지 않는다 — `_merge_node`에 세운 원칙을 조각에도 적용.
        회차마다 게이트 인용 유무가 갈리는데, 빈 회차가 마지막이라고 증거를 지우면
        감사 흔적이 사라진다(실측: 회차 폴더 여럿인 앱에서 quote가 ''로 덮였다)."""
        out = fold_fragment_versions({"a": [{"key": "quote", "text": "실제 인용"}]},
                                     {"a": [{"key": "quote", "text": ""}]}, at="s2")
        self.assertEqual(out["a"], [{"key": "quote", "text": "실제 인용"}])

    def test_article_fragment_next_to_it_still_versions(self):
        out = fold_fragment_versions(
            {"a": [{"key": "quote", "text": "q1"}, {"key": "INV-02|content", "text": "옛"}]},
            {"a": [{"key": "quote", "text": "q2"}, {"key": "INV-02|content", "text": "새"}]},
            at="s2")
        self.assertEqual([f["text"] for f in current_fragments(out["a"])], ["q2", "새"])
        self.assertEqual([f["text"] for f in out["a"] if f.get("superseded_at")], ["옛"])


class TestWhyLayer(unittest.TestCase):
    """(¬) 결정 계보 — 있으면 '왜 내려갔나'를 붙인다. 없으면 비운다(필수가 아니다)."""

    def test_supersede_reason_is_attached_when_known(self):
        out = fold_fragment_versions({"a": [frag("INV-04|content", "옛")]},
                                     {"a": [frag("INV-04|content", "새")]},
                                     at="s2", why={"INV-04": "INV-D-8812"})
        old = [f for f in out["a"] if f.get("superseded_at")][0]
        self.assertEqual(old["superseded_by"], "INV-D-8812")

    def test_absent_reason_is_normal(self):
        out = fold_fragment_versions({"a": [frag("INV-04|content", "옛")]},
                                     {"a": [frag("INV-04|content", "새")]}, at="s2")
        old = [f for f in out["a"] if f.get("superseded_at")][0]
        self.assertNotIn("superseded_by", old)


class TestVanishedFragment(unittest.TestCase):
    """출처가 사라진 조각은 종전대로 tombstone — 갱신과 소멸은 다른 사건이다."""

    def test_missing_key_gets_removed_at(self):
        out = fold_fragment_versions({"a": [frag("gone|content", "t")]}, {"a": []}, at="s2")
        self.assertEqual(out["a"][0]["removed_at"], "s2")

    def test_tombstoned_and_superseded_are_both_off_the_plane(self):
        bodies = [frag("k1", "산다"),
                  frag("k2", "죽었다", removed_at="s2"),
                  frag("k3", "낡았다", superseded_at="s2")]
        self.assertEqual([f["text"] for f in current_fragments(bodies)], ["산다"])


class TestDeterminism(unittest.TestCase):
    def test_output_order_is_stable(self):
        prev = {"a": [frag("B|x", "1"), frag("A|y", "2")]}
        new = {"a": [frag("A|y", "2"), frag("B|x", "9")]}
        self.assertEqual(fold_fragment_versions(prev, new, at="s"),
                         fold_fragment_versions(prev, new, at="s"))

    def test_gate_quote_stays_first(self):
        out = fold_fragment_versions({"a": [frag("Z|c", "z"), frag("quote", "q")]},
                                     {"a": [frag("quote", "q"), frag("Z|c", "z")]}, at="s")
        self.assertEqual(out["a"][0]["key"], "quote")


if __name__ == "__main__":
    unittest.main()


class TestMembersReachReobservedConcepts(unittest.TestCase):
    """이미 정본인 개념에 붙인 조항 귀속도 본문이 된다.

    이게 치명적인 이유: 축 1(흩어진 서술을 개념 하나로 모으기)의 값은 **증분 회차에서**
    나온다. 1회차엔 개념도 조항도 같이 새로 생기지만, 2회차부터는 "이미 있는 개념에
    다른 문서의 서술을 더한다"가 전부다. 그 경로가 no-op이면 확산해도 개념만 늘고
    본문은 안 모인다 — 위키가 아니라 목록이 된다."""

    def _promote(self, tmp, queue, auto_fold, members):
        import yaml as _y
        base = tmp / "p"
        base.mkdir(exist_ok=True)
        _y.safe_dump({"subconcepts": [{"anchor": "sc-x", "name": "X", "quote": "q"}]},
                     open(base / "subconcepts.yaml", "w"), allow_unicode=True)
        _y.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
        _y.safe_dump({"queue": queue, "carried": [], "auto_fold": auto_fold},
                     open(base / "adjudication.yaml", "w"), allow_unicode=True)
        _y.safe_dump({"members": members}, open(base / "members.yaml", "w"),
                     allow_unicode=True)
        stack = tmp / "canon.yaml"
        _y.safe_dump({"meta": {}, "concepts": [{"anchor": "inv#sc-x", "name": "X",
                                                "scope": "x/inv"}],
                      "relations": [], "bodies": {"inv#sc-x": [{"key": "quote", "text": "q"}]},
                      "held": {"candidate": [], "ambiguous": [], "gap": []}},
                     open(stack, "w"), allow_unicode=True)
        sa.run_promote(base, "inv", stack, app_scope="x/inv",
                       tier_a=[{"anchor": "INV-41", "kind": "article", "scope": "x/inv",
                                "content": "첫 주문 시 단가를 확정해야 한다"}],
                       snap="s2")
        return _y.safe_load(open(stack))

    def test_article_attached_to_a_reobserved_concept_becomes_body(self):
        import tempfile as _t
        from pathlib import Path as _P
        with _t.TemporaryDirectory() as td:
            saved = self._promote(
                _P(td),
                queue=[],                                     # 승격 0
                auto_fold=[{"sid": "inv#sc-x", "target": "inv#sc-x"}],   # 재관측
                members={"inv#sc-x": [{"article": "INV-41",
                                       "quote": "첫 주문 시 단가를"}]})
        keys = [f["key"] for f in saved["bodies"]["inv#sc-x"]]
        self.assertIn("INV-41|content", keys)

    def test_roundtrip_gate_still_applies_to_reobserved_members(self):
        """지어낸 인용은 재관측 경로로도 못 들어온다."""
        import tempfile as _t
        from pathlib import Path as _P
        with _t.TemporaryDirectory() as td:
            saved = self._promote(
                _P(td), queue=[],
                auto_fold=[{"sid": "inv#sc-x", "target": "inv#sc-x"}],
                members={"inv#sc-x": [{"article": "INV-41", "quote": "원문에 없는 말"}]})
        self.assertEqual([f["key"] for f in saved["bodies"]["inv#sc-x"]], ["quote"])


class TestPartialContributionDoesNotTombstone(unittest.TestCase):
    """부분 기여는 완전한 뷰가 아니다 — 안 실린 조각을 죽었다고 하면 안 된다.

    이건 직전 수정(members가 재관측 개념에 도달하게 한 것)이 만든 부작용이다.
    갱신/소멸 판정은 **완전한 뷰일 때만** 성립한다 — 부분 기여는 더하기만 한다."""

    def test_partial_bodies_add_without_tombstoning(self):
        prev = {"a": [{"key": "quote", "text": "게이트 인용"},
                      {"key": "INV-32|content", "text": "기존 조항"}]}
        fresh = {"a": [{"key": "INV-41|content", "text": "새 조항"}]}
        out = fold_fragment_versions(prev, fresh, at="s2", partial={"a"})
        keys = {f["key"]: f for f in out["a"]}
        self.assertEqual(sorted(keys), ["INV-32|content", "INV-41|content", "quote"])
        self.assertNotIn("removed_at", keys["quote"])
        self.assertNotIn("removed_at", keys["INV-32|content"])

    def test_partial_still_versions_a_changed_fragment(self):
        """부분 기여여도 **같은 key의 내용이 바뀌면** 갱신은 갱신이다."""
        out = fold_fragment_versions({"a": [{"key": "INV-32|content", "text": "옛"}]},
                                     {"a": [{"key": "INV-32|content", "text": "새"}]},
                                     at="s2", partial={"a"})
        self.assertEqual([f["text"] for f in current_fragments(out["a"])], ["새"])
        self.assertEqual([f["text"] for f in out["a"] if f.get("superseded_at")], ["옛"])

    def test_gate_quote_is_never_tombstoned(self):
        """게이트 인용은 **조항 파생이 아니라 감사 증거**다 — 조항이 사라져서 죽는 게 아니다."""
        out = fold_fragment_versions({"a": [{"key": "quote", "text": "q"}]},
                                     {"a": [{"key": "INV-1|content", "text": "새"}]}, at="s2")
        keys = {f["key"]: f for f in out["a"]}
        self.assertNotIn("removed_at", keys["quote"])

    def test_stale_false_tombstone_on_a_quote_is_cleared(self):
        """이미 찍힌 거짓 표시도 다음 접기에서 풀린다 — 결함이 남긴 흔적을 물려주지 않는다."""
        out = fold_fragment_versions({"a": [{"key": "quote", "text": "q", "removed_at": "s1"}]},
                                     {"a": []}, at="s2")
        self.assertNotIn("removed_at", out["a"][0])

    def test_complete_view_still_tombstones(self):
        """완전한 뷰(승격분)에서는 종전대로 사라진 조각을 표시한다 — 기능 축소 아님."""
        out = fold_fragment_versions({"a": [{"key": "gone|content", "text": "t"}]},
                                     {"a": []}, at="s2")
        self.assertEqual(out["a"][0]["removed_at"], "s2")


class TestCrossAppFragmentNotTombstoned(unittest.TestCase):
    """★교차앱 조각의 거짓 삭제."""

    def _prev(self):
        return {"inv#sc-x": [
            {"key": "INV-02|content", "text": "조항"},
            {"key": "screen:재고탐색기§구성|content", "text": "타 앱 화면"}]}

    def test_unit_alive_elsewhere_in_snapshot_survives(self):
        """단위가 스냅샷에 실재하면(교차앱) 조립만 안 된 것 — 판정 유보."""
        out = fold_fragment_versions(
            self._prev(), {"inv#sc-x": [{"key": "INV-02|content", "text": "조항"}]},
            at="r2", visible_units={"INV-02", "screen:재고탐색기§구성"})
        frags = {f["key"]: f for f in out["inv#sc-x"]}
        self.assertNotIn("removed_at", frags["screen:재고탐색기§구성|content"])

    def test_unit_gone_from_snapshot_still_tombstones(self):
        """스냅샷 전체에서 사라졌으면 진짜 삭제다 — 삭제 축을 끄지 않는다."""
        out = fold_fragment_versions(
            self._prev(), {"inv#sc-x": [{"key": "INV-02|content", "text": "조항"}]},
            at="r2", visible_units={"INV-02"})
        frags = {f["key"]: f for f in out["inv#sc-x"]}
        self.assertEqual(frags["screen:재고탐색기§구성|content"].get("removed_at"), "r2")

    def test_no_visible_units_keeps_old_behavior(self):
        out = fold_fragment_versions(
            self._prev(), {"inv#sc-x": [{"key": "INV-02|content", "text": "조항"}]},
            at="r2")
        frags = {f["key"]: f for f in out["inv#sc-x"]}
        self.assertEqual(frags["screen:재고탐색기§구성|content"].get("removed_at"), "r2")


class TestHistoryAppendIdempotent(unittest.TestCase):
    """★이력 누적의 멱등.

    이미 이력에 있는 것과 **같은 (key, text, superseded_at)** 조각을 또 내리면
    이력이 재생 횟수만큼 부푼다 — reproduce 게이트(byte_identical)가 이걸 잡았다.
    갱신은 사건이고 사건은 한 번이다 — 같은 사건을 두 번 기록하지 않는다.
    """

    def test_replaying_same_supersede_does_not_duplicate_history(self):
        prev = {"a#x": [
            {"key": "U|content", "text": "새 판"},
            {"key": "U|content", "text": "옛 판", "superseded_at": "r1"}]}
        fresh = {"a#x": [{"key": "U|content", "text": "더 새 판"}]}
        once = fold_fragment_versions(prev, fresh, at="r2")
        twice = fold_fragment_versions(once, fresh, at="r2")
        self.assertEqual(len(once["a#x"]), len(twice["a#x"]))

    def test_preexisting_duplicate_history_is_collapsed(self):
        """이미 오염된 이력(같은 사건 8중복 실측)도 지나가는 길에 정화한다 —
        결함의 흔적을 물려주지 않는다(quote removed_at 해제와 같은 원칙)."""
        prev = {"a#x": [
            {"key": "U|content", "text": "현행"},
            {"key": "U|content", "text": "옛 판", "superseded_at": "r1"},
            {"key": "U|content", "text": "옛 판", "superseded_at": "r1"},
            {"key": "U|content", "text": "옛 판", "superseded_at": "r1"}]}
        out = fold_fragment_versions(prev, {"a#x": [{"key": "U|content", "text": "현행"}]},
                                     at="r2")
        hist = [f for f in out["a#x"] if f.get("superseded_at")]
        self.assertEqual(len(hist), 1)

    def test_distinct_supersedes_both_kept(self):
        """다른 시점의 갱신은 다른 사건 — 둘 다 남는다."""
        prev = {"a#x": [
            {"key": "U|content", "text": "판2"},
            {"key": "U|content", "text": "판1", "superseded_at": "r1"}]}
        out = fold_fragment_versions(prev, {"a#x": [{"key": "U|content", "text": "판3"}]},
                                     at="r2")
        hist = [f for f in out["a#x"] if f.get("superseded_at")]
        self.assertEqual({(f["text"], f["superseded_at"]) for f in hist},
                         {("판1", "r1"), ("판2", "r2")})
