"""fixture 레이아웃 — 폴더는 '역할'을 말한다(정본/작업/원장/벤치).
설계: docs/superpowers/specs/2026-08-04-tier-b-normative-redesign.md §5.

★왜 한 곳에 모으나: 경로 문자열이 6개 모듈에 흩어져 있어 구조를 바꿀 때마다
전수 수정이 필요했고, 그래서 `probes/`(탐침) 안에 정본이 눌러앉는 일이 생겼다.
레이아웃은 경계 지식이므로 경계를 이미 소유한 corpus.py가 갖는다(신규 모듈 0)."""
import unittest
from pathlib import Path

import corpus


class TestLayout(unittest.TestCase):
    def setUp(self):
        self.root = Path("/tmp/fx")

    def test_canon_is_not_under_a_working_folder(self):
        p = corpus.canon_path("c", root=self.root)
        self.assertEqual(p, self.root / "c" / "canon" / "concepts.yaml")

    def test_tier_a_snapshot_is_named_by_role_not_by_old_layer_name(self):
        # 구 `l1-snapshots/<sha>/concepts.yaml` — "L1"은 폐기된 옛 이름이다.
        p = corpus.tier_a_path("c", "abc1234", root=self.root)
        self.assertEqual(p, self.root / "c" / "canon" / "tier-a" / "abc1234.yaml")

    def test_work_dir_is_named_by_app_not_by_stage(self):
        # 구 `probes/subconcept-<app>` — 폴더에 단계 이름(subconcept)이 박혀 있었다.
        p = corpus.work_dir("c", "inv", root=self.root)
        self.assertEqual(p, self.root / "c" / "work" / "inv")

    def test_ledger_and_bench(self):
        self.assertEqual(corpus.ledger_dir("c", root=self.root), self.root / "c" / "ledger")
        self.assertEqual(corpus.bench_dir("c", root=self.root), self.root / "c" / "bench")

    def test_drift_lives_with_the_canon_it_describes(self):
        self.assertEqual(corpus.drift_path("c", root=self.root),
                         self.root / "c" / "canon" / "drift.yaml")


if __name__ == "__main__":
    unittest.main()
