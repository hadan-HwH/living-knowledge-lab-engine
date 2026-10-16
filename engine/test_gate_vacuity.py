"""데이터 품질 게이트가 **조용히 통과하지 않는지** — 게이트를 재는 게이트.

규약: **검사 대상 0건 = skip**(통과 아님). 이 파일은 그 규약이 지켜지는지 스스로 잰다."""
import unittest
from unittest import mock

import conftest


class _Probe(unittest.TestCase):
    """skipTest 호출을 잡기 위한 더미 — runTest는 안 쓴다."""

    def runTest(self):     # pragma: no cover - 인스턴스화용
        pass


class TestRequireCorpora(unittest.TestCase):
    def test_empty_corpus_set_skips_rather_than_passes(self):
        probe = _Probe()
        with mock.patch("corpus.discover_corpora", return_value=[]):
            with self.assertRaises(unittest.SkipTest) as cm:
                conftest.require_corpora(probe)
        self.assertIn("통과 아님", str(cm.exception))

    def test_present_corpora_are_returned_sorted(self):
        probe = _Probe()
        with mock.patch("corpus.discover_corpora", return_value=["b", "a"]):
            self.assertEqual(conftest.require_corpora(probe), ["a", "b"])


class TestRequireChecked(unittest.TestCase):
    def test_zero_checked_skips(self):
        probe = _Probe()
        with self.assertRaises(unittest.SkipTest) as cm:
            conftest.require_checked(probe, 0, "정본 개념")
        self.assertIn("정본 개념 0건", str(cm.exception))

    def test_nonzero_passes_through(self):
        self.assertEqual(conftest.require_checked(_Probe(), 7, "x"), 7)


class TestEveryCorpusGateUsesTheGuard(unittest.TestCase):
    """코퍼스를 순회하는 테스트는 전부 가드를 거쳐야 한다 — 새로 쓰는 것도 포함.

    ★이 검사가 없으면 다음에 같은 실수를 또 한다. 실제로 이번에 만든 4개가 전부
    `for corpus in sorted(cp.discover_corpora())`로 시작했다."""

    def test_no_test_iterates_corpora_without_the_guard(self):
        import os
        import re
        offenders = []
        for f in sorted(os.listdir(os.path.dirname(__file__))):
            if not f.startswith("test_") or not f.endswith(".py"):
                continue
            src = open(os.path.join(os.path.dirname(__file__), f), encoding="utf-8").read()
            for m in re.finditer(r"discover_corpora\(\)", src):
                # 가드 자신과 가드를 검사하는 이 파일은 제외
                if f in ("test_gate_vacuity.py",):
                    continue
                line = src[:m.start()].count("\n") + 1
                # 같은 함수 안에서 require_corpora를 부르면 통과
                body = src[max(0, m.start() - 600):m.start()]
                if "require_corpora" not in body:
                    offenders.append(f"{f}:{line}")
        self.assertEqual(offenders, [],
                         "코퍼스 순회 전에 require_corpora를 거치지 않은 곳(vacuous pass 위험)")


if __name__ == "__main__":
    unittest.main()
