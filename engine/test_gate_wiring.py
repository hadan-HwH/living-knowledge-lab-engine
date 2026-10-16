"""게이트 배선 — 켜져 있나, 그리고 안 켜졌으면 그렇다고 말하나.

★감사에서 나온 것: 게이트 4개가 **조용히 꺼져 있었다.** 셋은 fixture 재편(fb19bac)이
경로를 바꿨는데 따라오지 않은 것이고, 하나는 시간을 SHA 알파벳 정렬로 유도한 것이다.
공통점은 **꺼졌다는 사실이 아무 데도 안 남았다**는 것 — 그래서 몇 세션을 버텼다.

규약을 하나 세운다: **게이트가 조건 불충족으로 안 돌면 `skipped(사유)`를 남긴다.**
`quote_gate`는 처음부터 `skipped(no sections)`를 남기고 있었다 — 그 관례를 전부에 편다."""
import tempfile
import unittest
from pathlib import Path

import yaml

import corpus as cp
from conftest import require_checked, require_corpora, require_corpus
import structure_app as sa


class TestNewestByRecordedTime(unittest.TestCase):
    """최신은 유도하지 않고 **기록된 시각**으로 정한다."""

    RECS = [{"sha": "1a0a008", "generated_at": "2026-08-03T23:35:18+00:00"},
            {"sha": "fa0a009", "generated_at": "2026-08-03T06:28:06+00:00"}]

    def test_newest_is_the_latest_timestamp_not_the_last_string(self):
        self.assertEqual(sa.newest_snapshot(self.RECS)["newest"], "1a0a008")
        self.assertEqual(sorted(r["sha"] for r in self.RECS)[-1], "fa0a009")   # 옛 방식

    def test_undated_snapshot_is_reported_not_silently_ranked(self):
        recs = self.RECS + [{"sha": "abc1234", "generated_at": None}]
        out = sa.newest_snapshot(recs)
        self.assertEqual(out["newest"], "1a0a008")
        self.assertEqual(out["undated"], ["abc1234"])

    def test_all_undated_yields_no_newest_rather_than_a_guess(self):
        out = sa.newest_snapshot([{"sha": "a", "generated_at": None}])
        self.assertIsNone(out["newest"])
        self.assertEqual(out["undated"], ["a"])

    def test_freshness_fails_when_a_snapshot_is_undated(self):
        """날짜 없는 스냅샷이 있으면 '최신인지 모른다' — 모르는 것을 통과라 부르지 않는다."""
        rep = sa.freshness_report("aaa", available=["aaa"], newest="aaa", undated=["bbb"])
        self.assertFalse(rep["fresh"])
        self.assertEqual(rep["undated"], ["bbb"])

    def test_every_real_snapshot_carries_a_timestamp(self):
        """날짜 없는 스냅샷이 생기면 여기서 걸린다. 대상 0건이면 통과가 아니라 skip."""
        checked = 0
        for corpus in require_corpora(self):
            recs = cp.snapshot_index(corpus)
            undated = [r["sha"] for r in recs if not r.get("generated_at")]
            self.assertEqual(undated, [], f"{corpus}: 시각 없는 스냅샷 {undated}")
            checked += len(recs)
        require_checked(self, checked, "Tier A 스냅샷")

    def test_snapshot_index_is_sorted_newest_first(self):
        """★성질을 재지 특정 SHA를 재지 않는다 — 처음엔 SHA를 박았다가 세션 종료 훅이
        새 스냅샷을 뜨자마자 깨졌다. 자기 코퍼스를 스냅샷하는 레포에서
        고정 SHA 단언은 시한폭탄이다."""
        checked = 0
        for corpus in require_corpora(self):
            recs = [r for r in cp.snapshot_index(corpus) if r.get("generated_at")]
            stamps = [r["generated_at"] for r in recs]
            self.assertEqual(stamps, sorted(stamps, reverse=True), corpus)
            checked += len(recs)
        require_checked(self, checked, "시각이 기록된 스냅샷")


class TestVocabGatePath(unittest.TestCase):
    """어휘 게이트는 정본 옆(`canon/`)의 어휘 선언을 본다 — 작업 폴더가 아니라."""

    def test_registry_layout_points_at_canon(self):
        p = cp.canon_extensions_path(require_corpus(self, "acme-docs"))
        self.assertTrue(p.exists(), f"{p} 없음")
        self.assertEqual(p.parent.name, "canon")

    def test_gate_actually_runs_on_a_real_app(self):
        """28/28 미실행이던 게이트가 실제 원장에서 돈다."""
        base = cp.work_dir(require_corpus(self, "personal-wevolley"), "wevolley")
        rels = (yaml.safe_load(open(base / "relations-canon.yaml")) or {}).get("relations") or []
        from relation_canon import validate_vocabulary
        ext = yaml.safe_load(open(cp.canon_extensions_path(
            require_corpus(self, "acme-docs"))))
        rep = validate_vocabulary(rels, ext)
        self.assertGreater(len(rels), 0, "실 원장에 관계가 없다 — 게이트가 공허하게 돈다")
        classified = rep["ok"] + rep["new_proposals"] + len(rep["unregistered"])
        self.assertEqual(classified, len(rels))     # 전건 분류 — 빠뜨린 관계 0

    def test_the_vocabulary_gate_still_catches_an_unregistered_term(self):
        """위 테스트가 실 원장 의존을 버렸으니, 검출력은 합성 입력으로 못 박는다."""
        from relation_canon import validate_vocabulary
        ext = yaml.safe_load(open(cp.canon_extensions_path(
            require_corpus(self, "acme-docs"))))
        rep = validate_vocabulary(
            [{"from": "a", "to": "b", "canonical": "지어낸_어휘"}], ext)
        self.assertEqual(len(rep["unregistered"]), 1)


class TestSkippedIsRecorded(unittest.TestCase):
    """조건 불충족으로 안 돈 게이트는 **그렇다고 말한다.**"""

    def _fold(self, tmp, with_ext):
        base = tmp / "probe"
        base.mkdir()
        yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "name": "A", "quote": "q"}]},
                       open(base / "subconcepts.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"relations": [{"from": "sc-a", "to": "sc-a", "canonical": "made_up_rel"}]},
                       open(base / "relations-canon.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"proposals": [{"sid": "x#sc-a", "target": "NEW", "confidence": "high"}]},
                       open(base / "align-proposals.yaml", "w"), allow_unicode=True)
        ext = None
        if with_ext:
            ext = tmp / "canon-extensions.yaml"
            yaml.safe_dump({"core_13": ["depends_on"], "extensions": [], "not_a_relation": []},
                           open(ext, "w"), allow_unicode=True)
        sa.run_fold(base, "x", ext_path=ext)
        return yaml.safe_load(open(base / "adjudication.yaml"))["stats"]

    def test_missing_vocabulary_declaration_is_recorded_not_omitted(self):
        with tempfile.TemporaryDirectory() as td:
            stats = self._fold(Path(td), with_ext=False)
        self.assertIn("relation_vocab", stats)
        self.assertIn("skipped", str(stats["relation_vocab"]))

    def test_present_declaration_runs_the_gate(self):
        with tempfile.TemporaryDirectory() as td:
            stats = self._fold(Path(td), with_ext=True)
        self.assertEqual(stats["relation_vocab"]["unregistered"], ["made_up_rel"])

    def test_promote_records_why_body_assembly_did_not_run(self):
        """tier_a 없이 promote하면 본문 층이 안 생긴다 — 조용히 넘어가지 않는다."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "probe"
            base.mkdir()
            yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "name": "A", "quote": "q"}]},
                           open(base / "subconcepts.yaml", "w"), allow_unicode=True)
            yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
            yaml.safe_dump({"queue": [{"sid": "x#sc-a", "was": "new",
                                       "disposition": "auto_adopt", "quote": "q"}],
                            "carried": []},
                           open(base / "adjudication.yaml", "w"), allow_unicode=True)
            stack = tmp / "canon.yaml"
            yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                            "held": {"candidate": [], "ambiguous": [], "gap": []}},
                           open(stack, "w"), allow_unicode=True)
            sa.run_promote(base, "x", stack, app_scope="x")
            meta = yaml.safe_load(open(stack))["meta"]
        self.assertIn("skipped", meta)
        self.assertIn("body_assembly", meta["skipped"])


class TestIntegrityIsWired(unittest.TestCase):
    """침식 감시가 정본 옆에 산출을 남기고, brief가 그걸 읽는다."""

    def test_report_writes_where_brief_reads(self):
        concepts = [{"anchor": "INV-02", "kind": "article", "scope": "s/inv", "content": "c",
                     "refs": {"decisions": []}}]
        with tempfile.TemporaryDirectory() as td:
            out = sa.write_integrity(Path(td), concepts, decisions=[], archive_segments=None)
            self.assertEqual(out.name, "integrity.yaml")
            doc = yaml.safe_load(open(out))
        self.assertIn("dead", doc)
        self.assertIn("ambiguous", doc)

    def test_brief_reads_the_same_filename(self):
        import inspect
        import brief
        self.assertIn("integrity.yaml", inspect.getsource(brief.load_and_build))


if __name__ == "__main__":
    unittest.main()
