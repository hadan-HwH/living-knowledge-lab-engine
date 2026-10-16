"""최신성 게이트 + 조각 tombstone.
설계 §4-5·§4-6 (2026-08-04 소유자 정정: 시금석은 본문 총량 게이트가 아니라 조각 삭제 표시).

★왜 총량 게이트가 아니라 tombstone인가: 정당한 편집으로도 글자 수는 준다. 총량으로
재면 진짜 소실과 정상 편집을 못 가른다. 조각이 사라졌다는 사실 자체를 표시하면
본문은 줄지 않으면서(단조성 유지) 무엇이 죽었는지 보인다."""
import unittest

import structure_app as sa


class TestFreshness(unittest.TestCase):
    def test_canon_older_than_available_snapshot_is_reported(self):
        rep = sa.freshness_report(canon_sha="aaa", available=["aaa", "bbb"], newest="bbb")
        self.assertFalse(rep["fresh"])
        self.assertEqual(rep["canon_sha"], "aaa")
        self.assertEqual(rep["newest"], "bbb")

    def test_canon_at_newest_is_fresh(self):
        rep = sa.freshness_report(canon_sha="bbb", available=["aaa", "bbb"], newest="bbb")
        self.assertTrue(rep["fresh"])

    def test_layer_sha_mismatch_is_reported(self):
        """층마다 다른 시점을 보면 그 자체가 경고다(결정층 78커밋 stale의 재발 방지)."""
        rep = sa.freshness_report(canon_sha="bbb", available=["bbb"], newest="bbb",
                                  layers={"decisions": "aaa"})
        self.assertFalse(rep["fresh"])
        self.assertIn("decisions", rep["stale_layers"])

    def test_unknown_canon_sha_is_not_silently_fresh(self):
        rep = sa.freshness_report(canon_sha=None, available=["aaa"], newest="aaa")
        self.assertFalse(rep["fresh"])


class TestFragmentTombstone(unittest.TestCase):
    def test_fragment_whose_source_vanished_is_marked_not_dropped(self):
        prev = {"a#x": [{"key": "A-1|content", "text": "살아있음"},
                        {"key": "A-9|content", "text": "출처가 사라짐"}]}
        fresh = {"a#x": [{"key": "A-1|content", "text": "살아있음"}]}
        out = sa.tombstone_lost_fragments(prev, fresh, at="2026-08-04")
        keys = [f["key"] for f in out["a#x"]]
        self.assertEqual(keys, ["A-1|content", "A-9|content"])      # 줄지 않는다
        gone = [f for f in out["a#x"] if f["key"] == "A-9|content"][0]
        self.assertEqual(gone["removed_at"], "2026-08-04")
        self.assertEqual(gone["text"], "출처가 사라짐")               # 증거 보존

    def test_already_tombstoned_fragment_keeps_its_original_date(self):
        prev = {"a#x": [{"key": "A-9|content", "text": "t", "removed_at": "2026-07-01"}]}
        out = sa.tombstone_lost_fragments(prev, {"a#x": []}, at="2026-08-04")
        self.assertEqual(out["a#x"][0]["removed_at"], "2026-07-01")

    def test_returning_fragment_loses_its_tombstone(self):
        """출처가 되살아나면 삭제 표시를 뗀다 — 재관측은 갱신이다."""
        prev = {"a#x": [{"key": "A-9|content", "text": "t", "removed_at": "2026-07-01"}]}
        fresh = {"a#x": [{"key": "A-9|content", "text": "t"}]}
        out = sa.tombstone_lost_fragments(prev, fresh, at="2026-08-04")
        self.assertNotIn("removed_at", out["a#x"][0])


    def test_gate_quote_stays_first(self):
        """정렬은 한 곳에서만 정한다 — 갈리면 같은 내용에도 diff가 떠 멱등이 깨진다."""
        prev = {"a#x": [{"key": "A-1|content", "text": "t"}, {"key": "quote", "text": "q"}]}
        out = sa.tombstone_lost_fragments(prev, prev, at="x")
        self.assertEqual([f["key"] for f in out["a#x"]], ["quote", "A-1|content"])


class TestPromoteWiring(unittest.TestCase):
    def _run(self, tmp, tier_a, prev_bodies=None):
        import yaml
        base = tmp / "probe"; base.mkdir()
        yaml.safe_dump({"subconcepts": [{"anchor": "sc-p", "name": "P", "quote": "q"}]},
                       open(base / "subconcepts.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
        yaml.safe_dump({"queue": [{"sid": "inv#sc-p", "was": "new", "target": "A-1",
                                   "disposition": "new_code_only"}], "carried": []},
                       open(base / "adjudication.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"snap": "bbb"}, open(base / "extract-manifest.yaml", "w"))
        stack = tmp / "canon.yaml"
        yaml.safe_dump({"meta": {}, "concepts": [], "relations": [],
                        "bodies": prev_bodies or {},
                        "held": {"candidate": [], "ambiguous": [], "gap": []}},
                       open(stack, "w"), allow_unicode=True)
        sa.run_promote(base, "inv", stack, app_scope="x/inv", tier_a=tier_a)
        return yaml.safe_load(open(stack))

    def test_promote_records_source_sha(self):
        import tempfile, yaml
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            saved = self._run(Path(td), [{"anchor": "A-1", "kind": "article",
                                          "scope": "x/inv", "content": "c"}])
        self.assertEqual(saved["meta"]["source_sha"], "bbb")

    def test_promote_tombstones_fragment_whose_article_vanished(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            saved = self._run(
                Path(td),
                tier_a=[{"anchor": "A-1", "kind": "article", "scope": "x/inv", "content": "c"}],
                prev_bodies={"inv#sc-p": [{"key": "A-9|content", "text": "사라진 출처"}]})
        keys = {f["key"]: f for f in saved["bodies"]["inv#sc-p"]}
        self.assertIn("A-9|content", keys)                 # 줄지 않는다
        self.assertIn("removed_at", keys["A-9|content"])   # 삭제 표시

    def test_cli_snap_is_recorded_when_manifest_absent(self):
        """--snap으로 준 시점이 정본에 남아야 최신성 게이트의 입력이 생긴다.
        manifest가 없는 수기 probe에서도 '어느 시점을 봤나'를 잃지 않는다."""
        import tempfile, yaml
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td); base = tmp / "probe"; base.mkdir()
            yaml.safe_dump({"subconcepts": [{"anchor": "sc-p", "name": "P", "quote": "q"}]},
                           open(base / "subconcepts.yaml", "w"), allow_unicode=True)
            yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
            yaml.safe_dump({"queue": [{"sid": "inv#sc-p", "was": "new",
                                       "disposition": "new_code_only"}], "carried": []},
                           open(base / "adjudication.yaml", "w"), allow_unicode=True)
            stack = tmp / "canon.yaml"
            yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                            "held": {"candidate": [], "ambiguous": [], "gap": []}},
                           open(stack, "w"), allow_unicode=True)
            sa.run_promote(base, "inv", stack, app_scope="x/inv", snap="ccc")
            saved = yaml.safe_load(open(stack))
        self.assertEqual(saved["meta"]["source_sha"], "ccc")


if __name__ == "__main__":
    unittest.main()


class TestForeignSidBodiesAreAdditive(unittest.TestCase):
    """★비소유 sid의 본문은 **더하기만** 한다.

    교차앱 귀속에서 한 개념(system 소유)에 세 앱이 단위를 붙이면, 각 앱의 promote가
    그 sid를 조립한다. 그런데 stack 병합이 sid 통째 교체라 **뒤에 도는 비소유 앱의
    얇은 슬라이스가 소유 앱의 조립 22조각을 1조각으로 덮었다.**
    소유 앱은 완전한 뷰라 교체가 맞고, 비소유 앱은 부분 기여라 합집합이 맞다 —
    partial 보호(축 2)와 같은 원칙이 stack 병합 층에는 안 펴져 있던 것.
    """

    def _run(self, tmp, prev_bodies, members):
        import yaml
        base = tmp / "probe"; base.mkdir()
        yaml.safe_dump({"subconcepts": []}, open(base / "subconcepts.yaml", "w"))
        yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
        yaml.safe_dump({"queue": [], "carried": []},
                       open(base / "adjudication.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"snap": "bbb"}, open(base / "extract-manifest.yaml", "w"))
        yaml.safe_dump({"members": members}, open(base / "members.yaml", "w"),
                       allow_unicode=True)
        stack = tmp / "canon.yaml"
        yaml.safe_dump({"meta": {}, "concepts": [{"anchor": "sys#sc-f", "name": "F",
                                                  "scope": "x/sys"}],
                        "relations": [], "bodies": prev_bodies,
                        "held": {"candidate": [], "ambiguous": [], "gap": []}},
                       open(stack, "w"), allow_unicode=True)
        tier_a = [{"anchor": "A-1", "kind": "article", "scope": "x/courier", "content": "본문A"},
                  {"anchor": "S-1", "kind": "article", "scope": "x/sys", "content": "본문S"}]
        sa.run_promote(base, "courier", stack, app_scope="x/courier", tier_a=tier_a)
        return yaml.safe_load(open(stack))

    def test_foreign_contribution_does_not_clobber(self):
        import tempfile
        from pathlib import Path
        prev = {"sys#sc-f": [{"key": "S-1|content", "text": "본문S"},
                             {"key": "quote", "text": "q0"}]}
        members = {"sys#sc-f": [{"unit": "A-1", "quote": "본문A"}]}
        with tempfile.TemporaryDirectory() as td:
            saved = self._run(Path(td), prev, members)
        keys = {f["key"] for f in saved["bodies"]["sys#sc-f"]}
        self.assertIn("S-1|content", keys)   # ★소유 앱 조각이 살아남는다
        self.assertIn("A-1|content", keys)   # 비소유 기여도 더해진다
