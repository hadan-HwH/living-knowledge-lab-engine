"""화면 분배기의 깊이 가정 — `2-screens/` 아래 한 단계 더 있는 앱이 통째로 빠졌다.

acme-docs이 3단을 쓴 건 정당하다(대상별 분리). 깊이 1을 가정한 lab이 틀렸다."""
import tempfile
import unittest
from pathlib import Path

import corpus as C
from l1_snapshot import collect_concepts

SCREEN = """---
title: "대시보드"
version: "1.0.0"
author: "화면 담당"
---

# 대시보드

화면ID: **{sid}**

## 1. 레이아웃

카드 4종을 상단에 둔다.
"""


class TestNestedScreenDirs(unittest.TestCase):
    """합성 트리 — 같은 앱에 평면 화면과 중첩 화면이 함께 있어도 둘 다 걷힌다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        flat = r / "3-prime-commerce" / "1-summit" / "2-inv" / "2-screens"
        flat.mkdir(parents=True)
        (flat / "1-login-v1.0.0.md").write_text(SCREEN.format(sid="S-01"),
                                                encoding="utf-8")
        nested = r / "3-prime-commerce" / "2-atlas" / "3-stock" / "2-screens" / "1-user"
        nested.mkdir(parents=True)
        (nested / "1-dashboard-v1.0.0.md").write_text(SCREEN.format(sid="S-42"),
                                                      encoding="utf-8")
        deeper = (r / "3-prime-commerce" / "2-atlas" / "3-stock" / "2-screens"
                  / "3-engineering" / "2-detail")
        deeper.mkdir(parents=True)
        (deeper / "1-cluster-v1.0.0.md").write_text(SCREEN.format(sid="S-99"),
                                                    encoding="utf-8")
        meta = r / "0-corpdoc" / "2-screens" / "1-dashboard"
        meta.mkdir(parents=True)
        (meta / "README.md").write_text("# 안내\n이 폴더는 화면 초안을 모은다.\n",
                                        encoding="utf-8")
        self.root = r

    def tearDown(self):
        self.tmp.cleanup()

    def _out(self):
        return collect_concepts(self.root, corpus="none", registry={"corpora": {}})

    def test_flat_screen_still_collected(self):
        """회귀 가드 — 135파일이 걸린 기존 경로는 한 글자도 안 바뀐다."""
        self.assertIn("S-01", {c["anchor"] for c in self._out()["concepts"]})

    def test_nested_screen_collected(self):
        """★결함 본체 — `2-screens/1-user/`가 걷혀야 한다."""
        self.assertIn("S-42", {c["anchor"] for c in self._out()["concepts"]})

    def test_depth_is_not_capped_at_one(self):
        """깊이 1만 더 허용하는 건 같은 가정을 한 칸 미루는 것일 뿐이다."""
        self.assertIn("S-99", {c["anchor"] for c in self._out()["concepts"]})

    def test_readme_is_not_a_screen(self):
        """★깊이를 열면 README가 딸려온다 — 폴더 안내는 화면 정의서가 아니다."""
        got = {c.get("file") for c in self._out()["concepts"]}
        self.assertFalse([f for f in got if f and f.endswith("README.md")],
                         "README가 화면으로 파싱됐다")

    def test_scope_is_the_app_not_the_audience_folder(self):
        """★scope가 어긋나면 회수해도 정본이 엉뚱한 앱에 붙는다.

        `app_dir = f.parent.parent`는 평면 전제다 — 중첩이면 `2-screens`를 앱으로
        잡아 scope가 `prime-commerce/atlas/stock/screens`가 된다.
        앱은 `2-screens`를 **가진** 폴더다, 깊이와 무관하게.
        """
        got = {c["anchor"]: c["scope"] for c in self._out()["concepts"]}
        self.assertEqual(got["S-42"], "prime-commerce/atlas/stock")
        self.assertEqual(got["S-99"], "prime-commerce/atlas/stock")
        self.assertEqual(got["S-01"], "prime-commerce/summit/inv")


class TestRealCorpusRecovery(unittest.TestCase):
    """실 코퍼스 산출물 게이트 — 선언과 배선을 따로 시험한다.

    합성 트리는 "고쳤다"만 말한다. 실제로 본문이 돌아왔는지는 원본이 답한다.
    """

    @classmethod
    def setUpClass(cls):
        cls.reg = C.load_registry()
        cfg = cls.reg["corpora"]["acme-docs"]
        root = (Path(__file__).parent / cfg["source"]).resolve()
        if not root.exists():
            raise unittest.SkipTest("acme-docs 클론 없음")
        cls.out = collect_concepts(root, corpus="acme-docs", registry=cls.reg,
                                   ignore=cfg.get("ignore"))

    @staticmethod
    def _is_screens(part):
        # ★리터럴 "2-screens" 금지 — 번호 접두는 순번이라 재배정된다(실측: 2026-08-06
        #   코퍼스 전면 재편 2-screens→02-screens에서 이 테스트만 깨졌다. 엔진은 slug라 멀쩡).
        from ingest import slug
        return slug(part) == "screens"

    def _screen_files(self):
        return {c["file"] for c in self.out["concepts"]
                if any(self._is_screens(p) for p in c["file"].split("/"))}

    def test_nested_screen_files_present(self):
        """stock 화면 파일 — 대상별 3폴더가 전부 들어와야 한다."""
        nested = {f for f in self._screen_files()
                  if not self._is_screens(f.split("/")[-2])}
        self.assertEqual(len(nested), 14, f"중첩 화면 회수 실패: {len(nested)}/14")

    def test_recovered_screens_belong_to_storage_scope(self):
        got = {c["scope"] for c in self.out["concepts"]
               if any(self._is_screens(p) for p in c["file"].split("/"))
               and not self._is_screens(c["file"].split("/")[-2])}
        self.assertEqual(got, {"prime-commerce/atlas/stock"})

    def test_no_screen_scope_leaks_the_screens_folder(self):
        """어떤 화면도 scope 말단이 `screens`이면 안 된다(앱이 아니다)."""
        bad = [c["anchor"] for c in self.out["concepts"]
               if (c.get("scope") or "").endswith("/screens")]
        self.assertEqual(bad, [])

    def test_recovery_adds_no_new_anchor_collision(self):
        """★회수분이 **새** 충돌을 만들면 안 된다 (불변식 8)."""
        def nested(c):
            from ingest import slug
            p = c["file"].split("/")
            return any(slug(x) == "screens" for x in p[:-1]) \
                and slug(p[-2]) != "screens"

        rec = [c for c in self.out["concepts"] if c["kind"] == "screen" and nested(c)]
        self.assertTrue(rec, "회수분이 없다 — 앞 테스트가 먼저 잡아야 한다")
        others = [c["anchor"] for c in self.out["concepts"]
                  if c["kind"] == "screen" and not nested(c)]
        clash = sorted({c["anchor"] for c in rec if c["anchor"] in others})
        self.assertEqual(clash, [], f"회수분이 기존 화면과 anchor 충돌: {clash}")


if __name__ == "__main__":
    unittest.main()
