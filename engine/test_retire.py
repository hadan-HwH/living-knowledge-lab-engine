"""앱 슬라이스 은퇴 — 버리되 보존한다 (소유자 지시 2026-08-04).

★소유자: "기존 문서는 다른 폴더에 다 집어넣어. 버리고 하는 거니까. 전체를 한 번에 안 할
거고 INV만 0으로 해보고 점차 늘릴 거임."

정본에서 개념이 빠지는 유일한 경로는 tombstone이라는 게 불변식 1이다. 은퇴는 그 예외라
**조용히 지우면 안 된다.** 슬라이스 전량을 `ledger/legacy/`로 옮기고, 정본 meta에
무엇을 언제 왜 뺐는지 남긴다. 되돌릴 수 있어야 실험이 실험이다.

tombstone과 다른 점: tombstone은 "원본에서 사라졌다"(관측 사실)이고, 은퇴는 "이 슬라이스를
새 파이프라인으로 다시 만들겠다"(운영 결정)다. 섞으면 원본이 사라진 것처럼 보인다.
"""
import tempfile
import unittest
from pathlib import Path

import yaml

import structure_app as sa


def _canon(tmp):
    doc = {
        "meta": {"promoted_total": 3},
        "concepts": [
            {"anchor": "inv#sc-a", "name": "A", "scope": "s/inv"},
            {"anchor": "inv#sc-b", "name": "B", "scope": "s/inv"},
            {"anchor": "alert#sc-c", "name": "C", "scope": "s/alert"},
        ],
        "relations": [{"from": "inv#sc-a", "to": "inv#sc-b", "canonical": "part_of"},
                      {"from": "alert#sc-c", "to": "alert#sc-c", "canonical": "part_of"}],
        "bodies": {"inv#sc-a": [{"key": "quote", "text": "q"}],
                   "alert#sc-c": [{"key": "quote", "text": "r"}]},
        "held": {"candidate": [{"sid": "inv#sc-z"}], "ambiguous": [], "gap": []},
    }
    p = tmp / "canon.yaml"
    yaml.safe_dump(doc, open(p, "w"), allow_unicode=True, sort_keys=False)
    return p


class TestRetireSlice(unittest.TestCase):
    def _run(self, tmp, reason="파일럿 재구축"):
        path = _canon(tmp)
        out = sa.retire_slice(path, "inv", tmp / "legacy", at="aaa", reason=reason)
        return yaml.safe_load(open(path)), yaml.safe_load(open(out)), out

    def test_slice_leaves_the_canon(self):
        with tempfile.TemporaryDirectory() as td:
            canon, _, _ = self._run(Path(td))
        self.assertEqual([c["anchor"] for c in canon["concepts"]], ["alert#sc-c"])
        self.assertEqual(list(canon["bodies"]), ["alert#sc-c"])
        self.assertEqual([r["from"] for r in canon["relations"]], ["alert#sc-c"])
        self.assertEqual(canon["held"]["candidate"], [])

    def test_everything_is_preserved_in_the_archive(self):
        with tempfile.TemporaryDirectory() as td:
            _, arch, _ = self._run(Path(td))
        self.assertEqual([c["anchor"] for c in arch["concepts"]], ["inv#sc-a", "inv#sc-b"])
        self.assertEqual(list(arch["bodies"]), ["inv#sc-a"])
        self.assertEqual(len(arch["relations"]), 1)
        self.assertEqual(arch["held"]["candidate"], [{"sid": "inv#sc-z"}])

    def test_archive_records_why_and_when(self):
        with tempfile.TemporaryDirectory() as td:
            _, arch, out = self._run(Path(td))
        self.assertEqual(arch["meta"]["retired_app"], "inv")
        self.assertEqual(arch["meta"]["retired_at"], "aaa")
        self.assertEqual(arch["meta"]["reason"], "파일럿 재구축")
        self.assertIn("inv", out.name)

    def test_canon_meta_keeps_a_pointer_not_a_silence(self):
        """정본만 봐도 '뭔가 빠졌다'가 보여야 한다 — 조용한 감소는 불변식 9와 충돌한다."""
        with tempfile.TemporaryDirectory() as td:
            canon, _, out = self._run(Path(td))
        rec = canon["meta"]["retired"][0]
        self.assertEqual(rec["app"], "inv")
        self.assertEqual(rec["concepts"], 2)
        self.assertEqual(rec["archive"], out.name)

    def test_retiring_an_absent_app_changes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _canon(tmp)
            before = open(path).read()
            sa.retire_slice(path, "nosuch", tmp / "legacy", at="aaa", reason="x")
            self.assertEqual(open(path).read(), before)

    def test_repeated_retire_does_not_lose_the_first_record(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _canon(tmp)
            sa.retire_slice(path, "inv", tmp / "legacy", at="aaa", reason="1차")
            sa.retire_slice(path, "alert", tmp / "legacy", at="bbb", reason="2차")
            canon = yaml.safe_load(open(path))
        self.assertEqual([r["app"] for r in canon["meta"]["retired"]], ["inv", "alert"])




class TestRetireIsDurable(unittest.TestCase):
    """은퇴는 **원장까지** 버린다 — 아니면 재생이 되살린다.

    소유자 지시는 "예전 건 버려라 — 잘못된 설계에서 잘못 나온 것"이었다. 잘못된
    산출의 출처가 원장이므로 원장도 같이 옮겨야 은퇴가 성립한다(삭제 아님 — 보존)."""

    def test_work_ledger_moves_with_the_slice(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _canon(tmp)
            work = tmp / "work" / "inv"
            work.mkdir(parents=True)
            (work / "subconcepts.yaml").write_text("subconcepts: []", encoding="utf-8")
            sa.retire_slice(path, "inv", tmp / "legacy", at="aaa", reason="x",
                            work_dir=work)
            self.assertFalse(work.exists())
            self.assertTrue((tmp / "legacy" / "retired-inv-aaa" / "subconcepts.yaml").exists())

    def test_absent_work_ledger_is_fine(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _canon(tmp)
            out = sa.retire_slice(path, "inv", tmp / "legacy", at="aaa", reason="x",
                                  work_dir=tmp / "nosuch")
            self.assertIsNotNone(out)


if __name__ == "__main__":
    unittest.main()
