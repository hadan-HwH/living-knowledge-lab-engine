"""회차 아카이브 — S6 drift가 잴 `prev`를 만든다 (불변식 4·6의 미완 절반).

고칠 수 없었던 이유는 단순하다: **현행 포맷의 이전 정본이 저장소에 하나도 없었다.**
그래서 회차 정본을 원장으로 남긴다. 그러면 다음 회차부터 축 2(현행/이력)가 **검증
가능**해진다 — 지금은 `history_fragments 0`이 "변경이 없어서"인지 "못 재서"인지 모른다.

★회차의 정의(설계 결정): **내용이 바뀐 재생만 한 회차다.** 같은 원장으로 재생을 두 번
돌린 건 한 회차다(재현성 검사가 매번 promote를 한 번 더 돌리므로, 실행 횟수로 세면
회차가 뻥튀기된다). 그래서 직전 회차와 내용이 같으면 아카이브하지 않는다."""
import tempfile
import unittest
from pathlib import Path

import yaml

from structure_app import archive_round, previous_round


def _canon(tmp, n=1, extra=None):
    doc = {"meta": {"source_sha": "aaa", **(extra or {})},
           "concepts": [{"anchor": f"inv#sc-{i}", "name": f"C{i}", "scope": "s/inv"}
                        for i in range(n)],
           "relations": [], "bodies": {}, "held": {}}
    p = tmp / "canon.yaml"
    yaml.safe_dump(doc, open(p, "w"), allow_unicode=True, sort_keys=False)
    return p


class TestArchiveRound(unittest.TestCase):
    def test_first_archive_creates_a_round(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            out = archive_round(_canon(tmp), tmp / "rounds")
            self.assertIsNotNone(out)
            self.assertTrue(out.exists())

    def test_unchanged_canon_does_not_create_a_new_round(self):
        """★회차 = 내용이 바뀐 재생. 재현성 검사가 promote를 한 번 더 돌리므로
        실행 횟수로 세면 회차가 뻥튀기된다."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p = _canon(tmp)
            archive_round(p, tmp / "rounds")
            self.assertIsNone(archive_round(p, tmp / "rounds"))
            self.assertEqual(len(list((tmp / "rounds").glob("*.yaml"))), 1)

    def test_changed_canon_creates_the_next_round(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            archive_round(_canon(tmp, n=1), tmp / "rounds")
            out = archive_round(_canon(tmp, n=2), tmp / "rounds")
            self.assertIsNotNone(out)
            self.assertEqual(len(list((tmp / "rounds").glob("*.yaml"))), 2)

    def test_rounds_are_orderable_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            a = archive_round(_canon(tmp, n=1), tmp / "rounds")
            b = archive_round(_canon(tmp, n=2), tmp / "rounds")
            self.assertLess(a.name, b.name)

    def test_volatile_meta_does_not_make_a_new_round(self):
        """실행 순서에만 달린 메타는 회차가 아니다 — 재현성 판정과 같은 기준."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            archive_round(_canon(tmp, extra={"last_promoted_app": "inv"}), tmp / "rounds")
            self.assertIsNone(
                archive_round(_canon(tmp, extra={"last_promoted_app": "alert"}),
                              tmp / "rounds"))


class TestPreviousRound(unittest.TestCase):
    def test_newest_round_is_returned(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            archive_round(_canon(tmp, n=1), tmp / "rounds")
            b = archive_round(_canon(tmp, n=2), tmp / "rounds")
            self.assertEqual(previous_round(tmp / "rounds"), b)

    def test_no_rounds_yet_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(previous_round(Path(td) / "rounds"))


class TestDriftActuallyMeasures(unittest.TestCase):
    """회차가 생기면 drift가 실제로 잰다 — 지금까지 0만 찍던 자리."""

    def test_fragment_change_between_rounds_is_reported(self):
        from structure_app import drift_report
        old = {"bodies": {"inv#a": [{"key": "INV-1|content", "text": "옛 서술"}]}}
        new = {"bodies": {"inv#a": [{"key": "INV-1|content", "text": "새 서술"}]}}
        rep = drift_report(old, new)
        self.assertEqual(rep["stats"]["changed"], 1)
        self.assertEqual(rep["stale"], ["inv#a"])

    def test_comparing_a_canon_with_itself_reports_nothing(self):
        """자기 자신과 비교하면 0 — 종전 기본 동작이 왜 무의미했는지의 증거."""
        from structure_app import drift_report
        doc = {"bodies": {"inv#a": [{"key": "INV-1|content", "text": "t"}]}}
        self.assertEqual(drift_report(doc, doc)["stats"],
                         {"changed": 0, "added": 0, "removed": 0})




class TestDriftReadsTheCurrentPlaneOnly(unittest.TestCase):
    """drift는 **현행 평면**을 비교한다 — 이력까지 같이 보면 변화가 안 보인다.

    drift가 묻는 건 "지금 무엇이 낡았나"이므로 현행 평면만 본다. 축 2와 S6가 같은
    평면 정의를 쓰는 게 맞다."""

    def test_supersede_between_rounds_is_seen_as_a_change(self):
        from structure_app import drift_report
        old = {"bodies": {"inv#a": [{"key": "INV-45|근거", "text": "D-7318 — 옛"}]}}
        new = {"bodies": {"inv#a": [
            {"key": "INV-45|근거", "text": "INV-D-8812 — 새"},
            {"key": "INV-45|근거", "text": "D-7318 — 옛", "superseded_at": "s2"}]}}
        rep = drift_report(old, new)
        self.assertEqual(rep["stats"]["changed"], 1)
        self.assertEqual(rep["stale"], ["inv#a"])

    def test_tombstoned_fragment_reads_as_removed(self):
        from structure_app import drift_report
        old = {"bodies": {"inv#a": [{"key": "k", "text": "t"}]}}
        new = {"bodies": {"inv#a": [{"key": "k", "text": "t", "removed_at": "s2"}]}}
        self.assertEqual(drift_report(old, new)["stats"]["removed"], 1)


if __name__ == "__main__":
    unittest.main()
