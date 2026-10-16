"""S6 낡음 감시 — 정본 두 스냅샷 + 결정층으로 '무엇이 낡았나'를 낸다.
설계: docs/superpowers/specs/2026-08-04-tier-b-normative-redesign.md §2 S6.

★왜 신설이 아니라 배선인가: change_layer(낡음 국소화)·decision_axis(낡은 권위 인용)는
이미 있으나 죽은 snapshot_pipeline 계보에만 물려 있어 라이브 정본에서는 아무도 부르지
않았다. 그래서 '결정이 바뀌면 본문이 낡는다'를 현 정본은 감지하지 못했다 —
이 프로젝트의 핵심 주장(N1′ 권위-구동 현행성)의 구현이 정본 밖에 있던 셈이다."""
import unittest

import structure_app as sa


class TestDriftReport(unittest.TestCase):
    def _canon(self, bodies, concepts=None):
        return {"concepts": concepts or [{"anchor": "a#x", "name": "X", "scope": "s"}],
                "bodies": bodies, "relations": [], "held": {}}

    def test_changed_fragment_marks_its_concept_stale(self):
        old = self._canon({"a#x": [{"key": "A-1|content", "text": "옛 문장"}]})
        new = self._canon({"a#x": [{"key": "A-1|content", "text": "바뀐 문장"}]})
        rep = sa.drift_report(old, new)
        self.assertEqual(rep["stale"], ["a#x"])
        self.assertEqual(rep["stats"]["changed"], 1)

    def test_untouched_concept_is_not_stale(self):
        same = self._canon({"a#x": [{"key": "A-1|content", "text": "같은 문장"}]})
        rep = sa.drift_report(same, same)
        self.assertEqual(rep["stale"], [])

    def test_added_fragment_also_marks_stale(self):
        old = self._canon({"a#x": [{"key": "A-1|content", "text": "t"}]})
        new = self._canon({"a#x": [{"key": "A-1|content", "text": "t"},
                                   {"key": "A-2|content", "text": "새 조각"}]})
        rep = sa.drift_report(old, new)
        self.assertEqual(rep["stale"], ["a#x"])

    def test_stale_authority_citation_is_reported(self):
        """근거로 든 결정이 이미 대체됐으면 낡은 권위 인용이다(침식 유형)."""
        new = self._canon({"a#x": [{"key": "A-1|fields.근거", "text": "INV-D-7318 근거"}]})
        rep = sa.drift_report(new, new, supersedes={"INV-D-7318": "INV-D-8812"})
        self.assertEqual(rep["stale_citations"],
                         [{"anchor": "a#x", "cites": "INV-D-7318", "superseded_by": "INV-D-8812"}])


if __name__ == "__main__":
    unittest.main()
