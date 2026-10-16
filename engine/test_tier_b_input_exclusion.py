"""Tier B 입력도 `concept_exclude`를 지킨다 — "A는 포함, B는 제외"의 나머지 절반.

    # Tier A(결정론 스냅샷)에는 **포함**하되 침식 감시에서 archived로 분리하고,
    # Tier B(LLM 추출)는 현행 정본만

`concept_exclude`를 적재(run_ingest_cli)에 물린 것이 그 절반이었고, 이 파일은 나머지
절반이다. 적재만 막으면 추출 **대상**은 좁아지지만 추출 **입력**은 그대로다:

★Tier A 스냅샷은 건드리지 않는다 — 이 필터는 Tier B 입력을 만들 때만 걸린다.
그래서 선언의 "A는 포함"이 그대로 성립한다(불변식: 스냅샷 단위 수 불변)."""
import unittest

import corpus as cp


class TestDropExcludedSources(unittest.TestCase):
    def test_a_unit_from_an_excluded_folder_is_dropped(self):
        units = [{"anchor": "a", "file": "작업완료/12-map-review.md"},
                 {"anchor": "b", "file": "reference/49-runbook.md"}]
        kept = cp.drop_excluded_sources(units, ("작업완료",))
        self.assertEqual([u["anchor"] for u in kept], ["b"])

    def test_a_unit_from_an_excluded_filename_is_dropped(self):
        units = [{"anchor": "a", "file": "DECISIONS.md"},
                 {"anchor": "b", "file": "reference/x.md"}]
        self.assertEqual([u["anchor"] for u in cp.drop_excluded_sources(units, ("DECISIONS.md",))],
                         ["b"])

    def test_tier_b_canon_has_no_file_and_is_never_dropped(self):
        """정본 개념(Tier B)에는 `file`이 없다 — 출처를 모른다고 버리면 루프가 다시 열린다.

        `canon_store`로 닫은 그 루프다: 정본 개념이 주입에서 빠지면 추출기가
        지난 회차에 정본화한 개념을 매번 NEW로 다시 낸다."""
        units = [{"anchor": "c:Promotion", "scope": "wevolley"}]
        self.assertEqual(cp.drop_excluded_sources(units, ("작업완료",)), units)

    def test_no_exclusion_keeps_everything(self):
        units = [{"anchor": "a", "file": "작업완료/x.md"}]
        self.assertEqual(cp.drop_excluded_sources(units, ()), units)

    def test_partial_segment_name_does_not_match(self):
        units = [{"anchor": "a", "file": "작업완료-보관/x.md"}]
        self.assertEqual(len(cp.drop_excluded_sources(units, ("작업완료",))), 1)


class TestPrepHonorsExclusionInTierBInputs(unittest.TestCase):
    """선언 테스트와 **배선 테스트**를 나눈다 — 이 프로젝트가 반복해서 당한 형태라서.

    (test_corpus_exclusion.TestIngestHonorsExclusion과 같은 이유·같은 구조)"""

    def _run_prep(self, exclude_archive):
        import tempfile, pathlib, io, contextlib, yaml
        import structure_app as sa
        base = pathlib.Path(tempfile.mkdtemp())
        secs = [{"anchor": "s1", "doc": "reference/a.md", "text": "현행 서술"}]
        yaml.safe_dump({"sections": secs}, open(base / "sections.yaml", "w"),
                       allow_unicode=True)
        snap = [
            {"anchor": "u-cur", "kind": "section", "scope": "wv",
             "file": "reference/a.md", "content": "현행 단위 본문"},
            {"anchor": "u-arc", "kind": "section", "scope": "wv",
             "file": "작업완료/old.md", "content": "이력 단위 본문"},
        ]
        reg = {"corpora": {"wv": {"statement_kinds": ["section"],
                                  "concept_exclude": (["작업완료"] if exclude_archive else [])}}}
        with contextlib.redirect_stdout(io.StringIO()):
            sa.run_prep(base, "wv", snap, corpus="wv", registry=reg)
        return (yaml.safe_load(open(base / "articles.yaml"))["articles"],
                yaml.safe_load(open(base / "canon-context.yaml"))["canon"])

    def test_archived_units_do_not_reach_the_s3a_input(self):
        arts, _ = self._run_prep(exclude_archive=True)
        self.assertEqual([a["anchor"] for a in arts], ["u-cur"])

    def test_archived_units_do_not_reach_the_canon_injection(self):
        _, canon = self._run_prep(exclude_archive=True)
        self.assertNotIn("u-arc", [c.get("anchor") for c in canon])

    def test_without_the_declaration_nothing_is_dropped(self):
        arts, _ = self._run_prep(exclude_archive=False)
        self.assertEqual(sorted(a["anchor"] for a in arts), ["u-arc", "u-cur"])


if __name__ == "__main__":
    unittest.main()
