"""발견 층 테스트 — `source_globs` · `concept_formats` (설계 §2·§3).

★진짜 블로커는 파서가 아니라 발견이었다: `collect_concepts`가 두 분기 모두
`rglob("*.md")` 하드코딩이라 .py가 파서에 도달조차 못 했다.
가장 중요한 게이트는 **기존 코퍼스가 한 글자도 안 바뀌는 것**이다(재현성).
"""
import unittest
from pathlib import Path
import tempfile

import corpus as C
from l1_snapshot import collect_concepts

REG = {"corpora": {
    "docs-only": {"concept_format": "markdown-sections"},               # 옛 스칼라 선언
    "mixed": {"concept_formats": {"**/*.md": "markdown-sections",
                                  "src/*.py": "code-symbols:python"}},
    "globbed": {"source_globs": ["**/*.md", "src/*.py"],
                "concept_formats": {"**/*.md": "markdown-sections",
                                    "src/*.py": "code-symbols:python"}},
}}


class TestDeclarations(unittest.TestCase):
    def test_scalar_declaration_still_read(self):
        """옛 선언을 못 읽게 만들지 않는다 — 이 프로젝트가 반복해서 당한 사고."""
        self.assertEqual(C.concept_formats_for("docs-only", REG),
                         {"**/*.md": "markdown-sections"})

    def test_plural_declaration(self):
        fmts = C.concept_formats_for("mixed", REG)
        self.assertEqual(fmts["src/*.py"], "code-symbols:python")

    def test_globs_derived_from_formats_when_undeclared(self):
        """글롭을 두 번 적게 하지 않는다 — `concept_formats`의 키가 곧 발견 대상이다."""
        self.assertEqual(set(C.source_globs_for("mixed", REG)),
                         {"**/*.md", "src/*.py"})

    def test_explicit_globs_win(self):
        self.assertEqual(set(C.source_globs_for("globbed", REG)),
                         {"**/*.md", "src/*.py"})

    def test_default_is_markdown_only(self):
        """미선언 코퍼스는 현행 동작 그대로 — 기존 3코퍼스가 여기 걸린다."""
        self.assertEqual(C.source_globs_for("unknown", {"corpora": {}}), ("**/*.md",))


class TestMixedCorpusCollection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        (r / "docs").mkdir()
        (r / "docs" / "guide.md").write_text("# 제목\n본문이다.\n", encoding="utf-8")
        (r / "src").mkdir()
        (r / "src" / "engine.py").write_text(
            '"""엔진 모듈."""\n\n\ndef run(x):\n    """돌린다."""\n', encoding="utf-8")
        (r / "src" / "deep").mkdir()
        (r / "src" / "deep" / "nested.py").write_text("def hidden():\n    pass\n",
                                                      encoding="utf-8")
        self.root = r

    def tearDown(self):
        self.tmp.cleanup()

    def _collect(self):
        return collect_concepts(self.root, corpus="mixed", registry=REG,
                                flat_scope="app")

    def test_both_adapters_run_in_one_corpus(self):
        """한 코퍼스에 어댑터 둘 — registry가 이미 모순으로 들고 있던 요구."""
        by = {c["anchor"] for c in self._collect()["concepts"]}
        self.assertIn("docs/guide#제목", by)          # 마크다운 축
        self.assertIn("src.engine.run", by)           # 코드 축

    def test_module_path_is_dotted_not_slugged(self):
        """doc_slug는 번호 접두를 떼는 마크다운용 변환이다 — 코드 식별자에 쓰면 안 된다."""
        by = {c["anchor"] for c in self._collect()["concepts"]}
        self.assertIn("src.engine", by)

    def test_glob_depth_is_respected(self):
        """`src/*.py`는 재귀가 아니다 — archive/research가 자동으로 빠지는 자리."""
        by = {c["anchor"] for c in self._collect()["concepts"]}
        self.assertNotIn("src.deep.nested.hidden", by)

    def test_kinds_counted_across_adapters(self):
        stats = self._collect()["stats"]["by_kind"]
        self.assertEqual(stats.get("section"), 1)
        self.assertEqual(stats.get("module"), 1)
        self.assertEqual(stats.get("function"), 1)

    def test_file_recorded_for_every_concept(self):
        """`concept_exclude`·drop_excluded_sources가 `file`로 판정한다."""
        for c in self._collect()["concepts"]:
            self.assertTrue(c.get("file"))

    def test_deterministic(self):
        a = [c["anchor"] for c in self._collect()["concepts"]]
        b = [c["anchor"] for c in self._collect()["concepts"]]
        self.assertEqual(a, b)


class TestLegacyPathUnchanged(unittest.TestCase):
    """★최상위 게이트 — 옛 스칼라 선언은 한 글자도 안 바뀌어야 한다.

    교훈: 게이트가 코드를 재면 산출물이 바뀐 걸 못 잡는다. 그래서 **산출물**을 잰다.
    (실 코퍼스 3종 재생성으로도 확인했다 — diff가 `generated_at` 한 줄뿐이었다.)
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        (r / "a").mkdir()
        (r / "a" / "doc.md").write_text("# H\n본문\n\n## H2\n둘째\n", encoding="utf-8")
        (r / "top.md").write_text("# T\n루트\n", encoding="utf-8")
        self.root = r

    def tearDown(self):
        self.tmp.cleanup()

    def test_scalar_declaration_matches_legacy_traversal(self):
        """`concept_format` 스칼라 코퍼스는 선언 경로로 가도 결과가 같아야 한다."""
        reg = {"corpora": {"c": {"concept_format": "markdown-sections"}}}
        legacy = collect_concepts(self.root, concept_format="markdown-sections",
                                  flat_scope="app")
        new = collect_concepts(self.root, corpus="c", registry=reg, flat_scope="app")
        self.assertEqual([c["anchor"] for c in legacy["concepts"]],
                         [c["anchor"] for c in new["concepts"]])
        self.assertEqual(legacy["stats"], new["stats"])

    def test_legacy_layout_branch_untouched_when_nothing_declared(self):
        """선언이 아예 없는 코퍼스는 acme-docs 레이아웃 분기로 간다(레거시 보존)."""
        out = collect_concepts(self.root, corpus="none", registry={"corpora": {}},
                               flat_scope="app")
        self.assertEqual(out["concepts"], [])   # 1-rules/·spec.md 없음 → 0


class TestCodeCorpusArtifact(unittest.TestCase):
    """실 코퍼스 산출물 게이트 — 선언이 의도대로 배선됐나(선언과 배선을 따로 시험한다).

    서 게이트 4개가, 서 `archive_segments`가 "선언은 있고 배선이 없는"
    형태로 조용히 꺼져 있었다. 그래서 실제 트리로 잰다.
    """

    def setUp(self):
        self.reg = C.load_registry()
        # 코퍼스 이름을 코드가 모르게 — 코드 어댑터를 선언한 코퍼스를 데이터에서 찾는다.
        # ★코퍼스 이름을 코드가 모르게 — 코드 어댑터를 선언한 코퍼스를 **데이터에서**
        # 찾는다. 첫 하나만 집으면 선언 순서가 바뀔 때 조용히 다른 코퍼스를 잰다.
        self.names = [n for n in sorted(self.reg["corpora"])
                      if any(str(f).startswith("code-symbols")
                             for f in C.concept_formats_for(n, self.reg).values())]
        if not self.names:
            self.skipTest("코드 어댑터를 선언한 코퍼스가 없다")
        self.name = self.names[0]
        self.cfg = self.reg["corpora"][self.name]
        root = (Path(__file__).parent / self.cfg["source"]).resolve()
        self.out = collect_concepts(root, corpus=self.name, registry=self.reg,
                                    ignore=self.cfg.get("ignore"),
                                    flat_scope=self.cfg.get("flat_app"))

    def test_code_and_docs_both_present(self):
        kinds = self.out["stats"]["by_kind"]
        self.assertGreater(kinds.get("section", 0), 0, "문서 축이 사라졌다")
        self.assertGreater(kinds.get("function", 0), 0, "코드 축이 안 붙었다")
        self.assertGreater(kinds.get("module", 0), 0)

    def test_anchor_uniqueness_invariant_8(self):
        anchors = [c["anchor"] for c in self.out["concepts"]]
        dup = {a for a in anchors if anchors.count(a) > 1}
        self.assertEqual(dup, set(), f"anchor 중복: {sorted(dup)[:5]}")

    def test_pipeline_own_output_not_ingested(self):
        """★자기 산출 먹기 — fixtures 마크다운이 들어오면 결함 ⓑ의 재발이다."""
        files = {c["file"] for c in self.out["concepts"]}
        self.assertFalse([f for f in files if "fixtures" in f.split("/")],
                         "파이프라인 산출물이 코퍼스에 들어왔다")

    def test_tests_excluded_from_tier_b_input(self):
        """Tier A에는 포함, Tier B에서 제외 — `작업완료/`와 같은 층."""
        for name in self.names:
            ex = C.concept_exclude_for(name, self.reg)
            out = self._collect(name)
            kept = C.drop_excluded_sources(out["concepts"], ex)
            leaked = [c for c in kept if C.is_concept_excluded(c["file"], ex)]
            self.assertFalse(leaked, f"{name}: 제외 선언분이 Tier B 입력에 남았다")

    def _collect(self, name):
        cfg = self.reg["corpora"][name]
        root = (Path(__file__).parent / cfg["source"]).resolve()
        return collect_concepts(root, corpus=name, registry=self.reg,
                                ignore=cfg.get("ignore"),
                                flat_scope=cfg.get("flat_app"))

    def test_sealed_code_is_in_tier_a_but_not_tier_b(self):
        """★2-B로 뒤집힌 결정: 봉인분을 **본다.**"""
        for name in self.names:
            seg = C.archive_segments_for(name, self.reg)
            out = self._collect(name)
            sealed = [c for c in out["concepts"]
                      if set(c["file"].split("/")) & set(seg or ())]
            if not sealed:
                continue          # 봉인 구역이 없는 코퍼스도 있다 — 결함이 아니다
            kept = C.drop_excluded_sources(out["concepts"],
                                           C.concept_exclude_for(name, self.reg))
            self.assertFalse([c for c in kept
                              if set(c["file"].split("/")) & set(seg)],
                             f"{name}: 봉인분이 Tier B 입력에 남았다")

    def test_glob_depth_still_bounded(self):
        """선언한 깊이 밖(예: 더 깊은 하위 폴더)은 여전히 안 딸려온다."""
        files = {c["file"] for c in self.out["concepts"] if c["file"].endswith(".py")}
        self.assertFalse([f for f in files if f.count("/") > 2])


if __name__ == "__main__":
    unittest.main()


class TestModulePathStripsAllCodeExtensions(unittest.TestCase):
    """★앵커는 정체성이다 — 확장자가 박히면 `api.landing.ts.handler`가 된다."""

    def test_python(self):
        from l1_snapshot import _module_path
        self.assertEqual(_module_path("engine/l1_snapshot.py"), "engine.l1_snapshot")

    def test_typescript_and_tsx(self):
        from l1_snapshot import _module_path
        self.assertEqual(_module_path("api/landing.ts"), "api.landing")
        self.assertEqual(_module_path("components/Card.tsx"), "components.Card")

    def test_declaration_file(self):
        from l1_snapshot import _module_path
        self.assertEqual(_module_path("types/api.d.ts"), "types.api")

    def test_unknown_extension_left_alone(self):
        """모르는 확장자는 건드리지 않는다 — 지어내지 않는다."""
        from l1_snapshot import _module_path
        self.assertEqual(_module_path("x/y.rs"), "x.y.rs")
