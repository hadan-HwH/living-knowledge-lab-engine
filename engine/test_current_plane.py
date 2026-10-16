"""현행 평면 — 개념 하나당 현행 하나, 나머지는 이력.
설계: 2026-08-04 소유자 정의.

  개념이 a→b→c→…→f로 흘러가면 평면에는 **f만** 살고 a~e는 이력이 된다.
  b일지 c일지 아직 모르는 상태라면 **모르는 상태 그대로** 평면에 산다(강등 아님).
  결정되면 그 자리를 갱신하고, 미결이었다는 사실이 이력으로 내려간다.

'왜'(이력)는 **필수가 아니다** — 마이그레이션 중엔 비어 있는 게 정상이고,
큼지막한 것에만 자연히 생긴다. 게이트로 걸지 않는다."""
import unittest

import structure_app as sa

def _e(n, type_, target, option, at, **kw):
    """이벤트 최소 스키마 — bitemporal 두 축과 event_id는 reducer의 필수 입력이다."""
    return {"event_id": f"T.{n}", "type": type_, "target": target, "option": option,
            "valid_at": at, "recorded_at": at, **kw}


SETTLED = [
    _e(1, "adopt", "INV.state", "o_held", "2026-07-01"),
    _e(2, "adopt", "INV.state", "o_paused", "2026-07-24"),
    # supersede는 승계 옵션(option)이 **누구를**(supersedes) 대체하는지로 쓴다.
    _e(3, "supersede", "INV.state", "o_paused", "2026-07-24",
       supersedes="o_held"),
]
OPEN = [
    _e(4, "propose", "NEO.mode", "o_auto", "2026-07-01"),
    _e(5, "propose", "NEO.mode", "o_manual", "2026-07-01"),
    _e(6, "defer", "NEO.mode", "o_auto", "2026-07-02", resume_trigger="복잡도 평가 후"),
    _e(7, "defer", "NEO.mode", "o_manual", "2026-07-02"),
]
AS_OF = ("2030-12-31", "2030-12-31")


class TestResolveCurrent(unittest.TestCase):
    def test_settled_concept_carries_only_the_live_value(self):
        cur = sa.resolve_current("INV.state", SETTLED, *AS_OF)
        self.assertEqual(cur["value"], "o_paused")
        self.assertNotIn("open", cur)
        self.assertEqual(cur["superseded"], ["o_held"])      # a는 이력으로

    def test_undecided_concept_stays_on_the_plane_as_undecided(self):
        """b일지 c일지 모르는 상태 그대로 평면에 산다 — 숨기지도 강등하지도 않는다."""
        cur = sa.resolve_current("NEO.mode", OPEN, *AS_OF)
        self.assertTrue(cur["open"])
        self.assertEqual(cur["candidates"], ["o_auto", "o_manual"])
        self.assertEqual(cur["resume_triggers"], ["복잡도 평가 후"])

    def test_target_without_events_has_no_current(self):
        self.assertIsNone(sa.resolve_current("없는.타겟", SETTLED, *AS_OF))


class TestPlaneMoveIsNotLoss(unittest.TestCase):
    """단조성 정정 — 평면에서 이력으로 내려가는 건 위반이 아니다."""

    def test_previous_value_moves_to_history_not_away(self):
        before = {"anchor": "a#x", "current": {"value": "o_held"}}
        after = sa.update_current(before, {"value": "o_paused"})
        self.assertEqual(after["current"]["value"], "o_paused")
        self.assertEqual([h["value"] for h in after["history"]], ["o_held"])

    def test_unchanged_current_does_not_grow_history(self):
        c = {"anchor": "a#x", "current": {"value": "o_x"}, "history": []}
        self.assertEqual(sa.update_current(c, {"value": "o_x"})["history"], [])

    def test_settling_an_open_concept_records_that_it_was_open(self):
        before = {"anchor": "a#x", "current": {"open": True, "candidates": ["b", "c"]}}
        after = sa.update_current(before, {"value": "c"})
        self.assertEqual(after["current"]["value"], "c")
        self.assertTrue(after["history"][0]["open"])          # 미결이었다는 사실이 남는다


if __name__ == "__main__":
    unittest.main()


class TestPromoteFillsCurrent(unittest.TestCase):
    """개념이 `governed_by`로 결정 target을 가리키면 promote가 현행을 채운다.
    신규 원장 0 — 추출 계약의 선택 필드 하나로 이어붙인다."""

    def _run(self, events, governed_by="INV.state", prev_concepts=None):
        import tempfile, yaml
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td); base = tmp / "probe"; base.mkdir()
            yaml.safe_dump({"subconcepts": [{"anchor": "sc-s", "name": "상태", "quote": "q",
                                             "governed_by": governed_by}]},
                           open(base / "subconcepts.yaml", "w"), allow_unicode=True)
            yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
            yaml.safe_dump({"queue": [{"sid": "inv#sc-s", "was": "new",
                                       "disposition": "new_code_only"}], "carried": []},
                           open(base / "adjudication.yaml", "w"), allow_unicode=True)
            stack = tmp / "canon.yaml"
            yaml.safe_dump({"meta": {}, "concepts": prev_concepts or [], "relations": [],
                            "bodies": {}, "held": {"candidate": [], "ambiguous": [], "gap": []}},
                           open(stack, "w"), allow_unicode=True)
            sa.run_promote(base, "inv", stack, app_scope="x/inv", events=events)
            return yaml.safe_load(open(stack))

    def test_settled_current_is_filled(self):
        c = self._run(SETTLED)["concepts"][0]
        self.assertEqual(c["current"]["value"], "o_paused")

    def test_open_current_is_filled_as_undecided(self):
        c = self._run(OPEN, governed_by="NEO.mode")["concepts"][0]
        self.assertTrue(c["current"]["open"])
        self.assertEqual(c["current"]["candidates"], ["o_auto", "o_manual"])

    def test_previous_current_moves_to_history(self):
        prev = [{"anchor": "inv#sc-s", "kind": "concept", "scope": "x/inv", "name": "상태",
                 "current": {"value": "o_held"}}]
        c = [x for x in self._run(SETTLED, prev_concepts=prev)["concepts"]
             if x["anchor"] == "inv#sc-s"][0]
        self.assertEqual(c["current"]["value"], "o_paused")
        self.assertEqual([h["value"] for h in c["history"]], ["o_held"])


class TestAccumulatedFieldsSurviveRepromote(unittest.TestCase):
    """★재생성이 누적을 지우지 않는다 — 본문 소실과 같은 계열의 결함 방지.
    fold_depth는 probe에서 노드를 새로 짓기 때문에, 막지 않으면 정본이 회차를 거치며
    쌓은 것(현행·이력·별칭)이 재promote 한 번에 전부 사라진다."""

    def test_aliases_and_history_survive(self):
        import tempfile, yaml
        from pathlib import Path
        prev = [{"anchor": "inv#sc-s", "kind": "concept", "scope": "x/inv", "name": "상태",
                 "aliases": [{"surface": "옛이름", "basis": "owner"}],
                 "current": {"value": "o_held"},
                 "history": [{"value": "o_old"}]}]
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td); base = tmp / "probe"; base.mkdir()
            yaml.safe_dump({"subconcepts": [{"anchor": "sc-s", "name": "상태", "quote": "q"}]},
                           open(base / "subconcepts.yaml", "w"), allow_unicode=True)
            yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
            yaml.safe_dump({"queue": [{"sid": "inv#sc-s", "was": "new",
                                       "disposition": "new_code_only"}], "carried": []},
                           open(base / "adjudication.yaml", "w"), allow_unicode=True)
            stack = tmp / "canon.yaml"
            yaml.safe_dump({"meta": {}, "concepts": prev, "relations": [], "bodies": {},
                            "held": {"candidate": [], "ambiguous": [], "gap": []}},
                           open(stack, "w"), allow_unicode=True)
            sa.run_promote(base, "inv", stack, app_scope="x/inv")
            c = yaml.safe_load(open(stack))["concepts"][0]
        self.assertEqual([a["surface"] for a in c["aliases"]], ["옛이름"])
        self.assertEqual(c["current"]["value"], "o_held")
        self.assertEqual([h["value"] for h in c["history"]], ["o_old"])


class TestCurrentHistoryIdempotent(unittest.TestCase):
    """★현행 이력의 멱등.

    한 개념에 두 앱의 결정이 붙으면(교차앱 개념) 앱별 promote가 current를 번갈아
    밀어 직전 값이 이력으로 내려간다 — 그 자체는 정당한 회전이지만, **같은 값의
    재등장은 새 사건이 아니다.** dedup 없이는 재생마다 이력이 핑퐁으로 부푼다
    (reproduce 게이트가 잡았다). 기존 오염도 지나가는 길에 접는다.
    """

    def test_pingpong_does_not_grow_history(self):
        c = {"current": "o_A", "history": []}
        for _ in range(3):
            c = sa.update_current(c, "o_B")
            c = sa.update_current(c, "o_A")
        vals = [h if isinstance(h, str) else h.get("value") for h in c["history"]]
        self.assertEqual(sorted(set(vals)), sorted(vals))   # 값 중복 없음

    def test_existing_duplicates_collapsed_on_update(self):
        c = {"current": "o_A",
             "history": [{"value": "o_B", "superseded": []},
                         {"value": "o_B", "superseded": []}]}
        c = sa.update_current(c, "o_C")
        vals = [h if isinstance(h, str) else h.get("value") for h in c["history"]]
        self.assertEqual(len([v for v in vals if v == "o_B"]), 1)

    def test_distinct_values_all_kept(self):
        c = {"current": "o_A"}
        c = sa.update_current(c, "o_B")
        c = sa.update_current(c, "o_C")
        vals = [h if isinstance(h, str) else h.get("value") for h in c["history"]]
        self.assertEqual(set(vals), {"o_A", "o_B"})
