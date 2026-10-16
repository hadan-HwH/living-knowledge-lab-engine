"""정본 코퍼스에서 뺄 것 — 조사 문서는 개념의 원천이 아니다.

이건 노이즈 문제가 아니라 **피드백 루프**다. 조사 문서는 정본을 읽고 쓴 것인데, 그걸
다시 추출하면 "조사에서 한 말"이 개념이 되고 다음 회차엔 그게 정본으로 보인다.
관측이 관측 대상을 바꾸는 자리라 구조로 막아야 한다.

★`4-source/`(아카이브)는 이미 `archive_segments`로 선언돼 있는데 그건 **침식 감시 분류**용
이지 적재 제외가 아니다. 성격이 다르므로 선언을 따로 둔다:
  `archive_segments` — 정본이 아니지만 **보존**된 옛 문서(죽은 참조를 침식으로 안 셈)
  `concept_exclude`  — 애초에 **개념의 원천이 아닌** 것(조사·회의록·README·결정 로그)"""
import unittest

import corpus as cp


class TestConceptExclude(unittest.TestCase):
    def test_research_is_excluded_from_the_concept_corpus(self):
        ex = cp.concept_exclude_for("acme-docs")
        self.assertIn("3-research", ex)

    def test_decision_log_is_excluded(self):
        """결정 로그는 **결정층**의 원천이지 개념층의 원천이 아니다 — 두 번 먹으면 중복."""
        self.assertIn("decisions-log.md", cp.concept_exclude_for("acme-docs"))

    def test_undeclared_corpus_excludes_nothing(self):
        self.assertEqual(cp.concept_exclude_for("nosuch"), ())

    def test_the_declared_decision_file_excludes_itself(self):
        """★유도한다 — `decision_file`이 곧 결정층의 원천 선언이다."""
        self.assertIn("DECISIONS.md", cp.concept_exclude_for("personal-wevolley"))

    def test_derivation_does_not_drop_hand_declared_entries(self):
        """유도분이 손 선언을 **덮지 않는다** — 합집합이다."""
        ex = cp.concept_exclude_for("acme-docs")
        self.assertIn("3-research", ex)          # 손 선언
        self.assertIn("decisions-log.md", ex)    # 손 선언 겸 decision_file

    def test_a_corpus_without_a_decision_file_derives_nothing(self):
        reg = {"corpora": {"c": {"concept_exclude": ["x"]}}}
        self.assertEqual(cp.concept_exclude_for("c", registry=reg), ("x",))

    def test_the_derived_entry_appears_even_with_no_hand_declaration(self):
        reg = {"corpora": {"c": {"decision_file": "D.md"}}}
        self.assertEqual(cp.concept_exclude_for("c", registry=reg), ("D.md",))

    def test_no_duplicate_when_hand_declaration_already_names_it(self):
        reg = {"corpora": {"c": {"decision_file": "D.md", "concept_exclude": ["D.md"]}}}
        self.assertEqual(cp.concept_exclude_for("c", registry=reg), ("D.md",))

    def test_matching_is_by_path_segment_or_filename(self):
        ex = ("3-research", "decisions-log.md")
        self.assertTrue(cp.is_concept_excluded("a/b/3-research/x.md", ex))
        self.assertTrue(cp.is_concept_excluded("a/b/decisions-log.md", ex))
        self.assertFalse(cp.is_concept_excluded("a/b/1-rules/x.md", ex))

    def test_partial_name_does_not_match(self):
        """세그먼트 완전일치 — `3-research-old`가 우연히 걸리면 안 된다."""
        self.assertFalse(cp.is_concept_excluded("a/3-research-old/x.md", ("3-research",)))

    def test_excluding_nothing_keeps_everything(self):
        self.assertFalse(cp.is_concept_excluded("a/b.md", ()))


class TestIngestHonorsExclusion(unittest.TestCase):
    """선언이 **적재에 실제로 물려 있는가** — 선언만 있고 배선이 없으면 죽은 게이트다.

    이 프로젝트가 반복해서 당한 형태라
    선언 테스트와 배선 테스트를 나눠 둔다."""

    def _tree(self):
        import tempfile, pathlib
        d = pathlib.Path(tempfile.mkdtemp())
        for rel in ["1-rules/a.md", "3-research/found.md", "README.md", "2-screens/s.md"]:
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("## H\n본문\n", encoding="utf-8")
        return d

    def test_excluded_files_never_enter_sections(self):
        import tempfile, pathlib, io, contextlib
        import structure_app as sa
        src = self._tree()
        out = pathlib.Path(tempfile.mkdtemp())
        with contextlib.redirect_stdout(io.StringIO()):
            secs = sa.run_ingest_cli(src, ".", out, "x", exclude=("3-research", "README.md"))
        docs = {s["doc"] for s in secs}
        self.assertEqual(docs, {"1-rules/a.md", "2-screens/s.md"})

    def test_the_skip_is_reported_not_silent(self):
        """무성 누락 금지 — 몇 개를 왜 뺐는지 말한다."""
        import tempfile, pathlib, io, contextlib
        import structure_app as sa
        src = self._tree()
        out = pathlib.Path(tempfile.mkdtemp())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sa.run_ingest_cli(src, ".", out, "x", exclude=("3-research", "README.md"))
        self.assertIn("제외 2", buf.getvalue())

    def test_no_exclusion_keeps_every_document(self):
        import tempfile, pathlib, io, contextlib
        import structure_app as sa
        src = self._tree()
        out = pathlib.Path(tempfile.mkdtemp())
        with contextlib.redirect_stdout(io.StringIO()):
            secs = sa.run_ingest_cli(src, ".", out, "x")
        self.assertEqual(len({s["doc"] for s in secs}), 4)


class TestPrefixPattern(unittest.TestCase):
    """★2026-08-06 — 코드 코퍼스가 요구한 확장. 테스트 파일은 `test_*.py`처럼 **접두**로만
    식별된다(완전일치로는 47개를 일일이 적어야 하고, 새 테스트가 생기면 조용히 새어 든다)."""

    def test_prefix_star_matches_filename(self):
        self.assertTrue(cp.is_concept_excluded("engine/test_ask.py", ["test_*"]))
        self.assertTrue(cp.is_concept_excluded("engine/test_brief.py", ["test_*"]))

    def test_prefix_star_does_not_match_unrelated(self):
        """`test_`로 시작하지 않는 건 안 걸린다 — `latest_run.py` 같은 우연 매치 금지."""
        self.assertFalse(cp.is_concept_excluded("engine/latest_run.py", ["test_*"]))
        self.assertFalse(cp.is_concept_excluded("engine/contest.py", ["test_*"]))

    def test_exact_match_still_works(self):
        """기존 선언(완전일치)이 안 깨진다."""
        self.assertTrue(cp.is_concept_excluded("a/3-research/x.md", ["3-research"]))
        self.assertFalse(cp.is_concept_excluded("a/3-research-old/x.md", ["3-research"]))

    def test_prefix_applies_to_directory_segment_too(self):
        self.assertTrue(cp.is_concept_excluded("engine/test_data/fx.py", ["test_*"]))


class TestSlugNormalizedMatch(unittest.TestCase):
    """★번호 접두 리넘버링 내성.

    registry 선언은 `4-source`인데 실제 폴더는 **`04-source`**(zero-padded 리넘버링).
    완전일치가 놓쳐서 to_extract 664 중 **301(45%)이 아카이브 원본**으로 들어갔다 —
    구 위키 이관 원본의 폐기된 내용까지 개념 원천이 될 뻔했다.

    registry 맨 아래 원칙이 이미 답을 적어뒀다: "폴더 번호(1-·2-·a-)는 순번이라 언제든
    재배정됨 → 정체성은 slug(번호 뗀 이름)". 선언과 세그먼트를 **둘 다 slug 정규화**해
    완전일치한다 — 부분 문자열 매칭 금지 원칙은 그대로다(`3-research-old` 오탐 방지).
    """

    def test_zero_padded_segment_matches_declaration(self):
        self.assertTrue(cp.is_concept_excluded("a/04-source/x.md", ("4-source",)))
        self.assertTrue(cp.is_concept_excluded("a/03-research/x.md", ("3-research",)))

    def test_renumbered_segment_matches(self):
        """번호가 아예 바뀌어도 slug 정체성으로 잡는다."""
        self.assertTrue(cp.is_concept_excluded("a/07-source/x.md", ("4-source",)))

    def test_slugless_declaration_matches_numbered_segment(self):
        self.assertTrue(cp.is_concept_excluded("a/04-source/x.md", ("source",)))

    def test_exact_match_discipline_kept(self):
        """slug 후에도 완전일치다 — `3-research-old`는 여전히 안 걸린다."""
        self.assertFalse(cp.is_concept_excluded("a/3-research-old/x.md", ("3-research",)))

    def test_filename_not_slugged_into_false_match(self):
        """파일명의 번호는 문서 정체성일 수 있다 — 세그먼트(폴더)만 slug한다."""
        self.assertTrue(cp.is_concept_excluded("a/decisions-log.md", ("decisions-log.md",)))
