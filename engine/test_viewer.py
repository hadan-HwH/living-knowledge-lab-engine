"""정본 뷰어 — 뷰 모델 빌더 (설계: docs/superpowers/specs/2026-08-07-canon-viewer-design.md).

★합성 픽스처만 쓴다. 실 코퍼스에 의존하면 코퍼스가 바뀔 때 테스트가 깨지고,
엔진 레포(동료 초청용)에는 fixtures가 없다.
"""
import unittest

from viewer import split_planes


class TestSplitPlanes(unittest.TestCase):
    def test_gars_by_marker_and_removed_wins(self):
        frs = [{"key": "A-1|content", "text": "현행"},
               {"key": "A-2|content", "text": "옛것", "superseded_at": "aaa"},
               {"key": "A-3|content", "text": "지운것", "removed_at": "bbb"},
               {"key": "A-4|content", "text": "둘다", "superseded_at": "aaa",
                "removed_at": "bbb"}]
        p = split_planes(frs)
        self.assertEqual([f["key"] for f in p["current"]], ["A-1|content"])
        self.assertEqual([f["key"] for f in p["history"]], ["A-2|content"])
        self.assertEqual([f["key"] for f in p["removed"]],
                         ["A-3|content", "A-4|content"])

    def test_empty_input_still_has_three_planes(self):
        self.assertEqual(split_planes([]), {"current": [], "history": [], "removed": []})


from corpus import kind_families


class TestKindFamilies(unittest.TestCase):
    def test_flattens_declaration_into_kind_to_family(self):
        fam = kind_families({"kind_families": {"조항": ["article"],
                                               "코드": ["function", "method"]}})
        self.assertEqual(fam, {"article": "조항", "function": "코드", "method": "코드"})

    def test_missing_declaration_is_empty_not_error(self):
        self.assertEqual(kind_families({}), {})

    def test_real_registry_declares_all_fifteen_measured_kinds(self):
        """2026-08-07 실측 3코퍼스 kind 합집합. 새 어댑터가 kind를 늘리면 여기서 깨진다 —
        깨지면 registry에 선언을 추가하는 것이 정답이다(코드 수정 아님)."""
        measured = {"article", "screen", "screen_section", "spec_section", "field",
                    "state_enum", "gap", "section", "module", "function", "method",
                    "class", "const", "interface", "type"}
        self.assertEqual(measured - set(kind_families()), set())


from viewer import anchor_of, resolve_sources


class TestResolveSources(unittest.TestCase):
    TIER_A = {"ALERT-13": {"kind": "article", "file": "a/b.md", "line": 29},
              "mod.fn": {"kind": "function", "file": "engine/x.py", "line": 7},
              "N-1": {"kind": "왠지새로운kind", "file": "n.md", "line": 1}}

    def test_anchor_is_key_before_pipe_and_quote_has_none(self):
        self.assertEqual(anchor_of("ALERT-13|fields.근거"), "ALERT-13")
        self.assertEqual(anchor_of("ALERT-13"), "ALERT-13")
        self.assertIsNone(anchor_of("quote"))

    def test_attaches_kind_family_file_line_for_referenced_anchors_only(self):
        bodies = {"c#1": [{"key": "ALERT-13|content", "text": "t"},
                          {"key": "quote", "text": "q"}]}
        src, cov = resolve_sources(bodies, self.TIER_A, {"article": "조항"})
        self.assertEqual(set(src), {"ALERT-13"})
        self.assertEqual(src["ALERT-13"], {"kind": "article", "family": "조항",
                                           "file": "a/b.md", "line": 29})
        self.assertEqual(cov["families"], {"조항": 1, "인용": 1})

    def test_unknown_kind_falls_to_기타_and_is_counted(self):
        bodies = {"c#1": [{"key": "N-1|content", "text": "t"}]}
        src, cov = resolve_sources(bodies, self.TIER_A, {"article": "조항"})
        self.assertEqual(src["N-1"]["family"], "기타")
        self.assertEqual(cov["other_kinds"], {"왠지새로운kind": 1})

    def test_anchor_absent_from_tier_a_is_counted_not_linked(self):
        bodies = {"c#1": [{"key": "사라진앵커|content", "text": "t"}]}
        src, cov = resolve_sources(bodies, self.TIER_A, {})
        self.assertEqual(src, {})
        self.assertEqual(cov["unresolved_anchors"], 1)

    def test_no_tier_a_at_all_resolves_nothing_without_crashing(self):
        bodies = {"c#1": [{"key": "ALERT-13|content", "text": "t"}]}
        src, cov = resolve_sources(bodies, None, {"article": "조항"})
        self.assertEqual(src, {})
        self.assertEqual(cov["unresolved_anchors"], 1)


import tempfile
from pathlib import Path

import yaml

from viewer import load_tier_a_index, load_optional


class TestLoaders(unittest.TestCase):
    def test_missing_file_is_none_not_empty(self):
        """★부재와 공집합을 가른다 — 이 구분이 커버리지 배너의 전부다."""
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_optional(Path(d) / "없다.yaml"))
            self.assertIsNone(load_tier_a_index(Path(d) / "없다.yaml"))

    def test_present_but_empty_is_empty_not_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "있다.yaml"
            p.write_text("conflicts: []\n", encoding="utf-8")
            self.assertEqual(load_optional(p), {"conflicts": []})

    def test_tier_a_indexes_by_anchor(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sha.yaml"
            p.write_text(yaml.safe_dump({"concepts": [
                {"anchor": "A-1", "kind": "article", "file": "x.md", "line": 3},
                {"kind": "article"},
            ]}, allow_unicode=True), encoding="utf-8")
            idx = load_tier_a_index(p)
            self.assertEqual(idx, {"A-1": {"kind": "article", "file": "x.md", "line": 3}})


from viewer import merge_issues


class TestMergeIssues(unittest.TestCase):
    CROSSCHECK = {"conflicts": [{"anchor": "c#1", "item": "actor",
                                 "by_layer": {"article": ["A"], "screen_section": ["B"]},
                                 "sources": {"article": ["ALERT-06|table[2]"]}}],
                  "checked_concepts": 27}
    DRIFT = {"stale": ["c#2"],
             "stale_citations": [{"anchor": "c#1", "cites": "D-9",
                                  "superseded_by": "D-1093"}]}
    INTEGRITY = {"dead": [{"from_id": "SHOP-D-1062", "from_kind": "decision",
                           "ref": "CB-17", "ref_kind": "article", "rescue": []}],
                 "ambiguous": [{"from_id": "M-11", "from_kind": "article",
                                "ref": "D-2861", "ref_kind": "decision",
                                "exists_in": ["s/x"]}]}
    HELD = {"candidate": [{"sid": "S-1"}], "ambiguous": [], "gap": []}
    OWNER = {"SHOP-D-1062": "c#3"}

    def test_all_four_sources_land_in_one_schema(self):
        issues = merge_issues(self.CROSSCHECK, self.DRIFT, self.INTEGRITY, self.HELD,
                              self.OWNER)
        self.assertEqual([i["kind"] for i in issues],
                         ["conflict", "stale", "stale_citation", "dead", "ambiguous",
                          "held"])
        for i in issues:
            self.assertEqual(set(i), {"id", "kind", "concept", "title", "detail",
                                      "sources", "severity"})
        self.assertEqual(len({i["id"] for i in issues}), 6)

    def test_integrity_items_are_joined_to_concept_via_owner_index(self):
        issues = merge_issues(None, None, self.INTEGRITY, None, self.OWNER)
        by = {i["kind"]: i for i in issues}
        self.assertEqual(by["dead"]["concept"], "c#3")
        self.assertIsNone(by["ambiguous"]["concept"])

    def test_absent_sources_yield_nothing_without_crashing(self):
        self.assertEqual(merge_issues(None, None, None, None, {}), [])

    def test_archived_integrity_items_are_excluded(self):
        """archived는 코퍼스가 스스로 감사 제외를 선언한 것 — 어긋남으로 세지 않는다."""
        issues = merge_issues(None, None, {"dead": [], "ambiguous": [],
                                           "archived": [{"from_id": "X"}]}, None, {})
        self.assertEqual(issues, [])


from viewer import build_coverage, number_gate


class TestCoverage(unittest.TestCase):
    def test_absent_scan_is_none_not_zero(self):
        """★personal-wevolley 실물 — integrity.yaml이 없다. '침식 0'이 아니라 '안 쟀음'."""
        cov = build_coverage(crosscheck=None, integrity=None, drift=None,
                             total_concepts=297,
                             source_stats={"families": {}, "other_kinds": {},
                                           "unresolved_anchors": 40})
        self.assertIsNone(cov["integrity"])
        self.assertIsNone(cov["crosscheck"])
        self.assertEqual(cov["unresolved_anchors"], 40)

    def test_present_scan_reports_numerator_and_denominator(self):
        cov = build_coverage(crosscheck={"checked_concepts": 20, "conflicts": []},
                             integrity={"meta": {"refs_checked": 1500}},
                             drift={"freshness": {"fresh": True, "canon_sha": "ba0a006"}},
                             total_concepts=300,
                             source_stats={"families": {"조항": 3}, "other_kinds": {},
                                           "unresolved_anchors": 0})
        self.assertEqual(cov["crosscheck"], {"checked": 20, "total": 300})
        self.assertEqual(cov["integrity"], {"refs_checked": 1500})
        self.assertEqual(cov["drift"], {"fresh": True, "canon_sha": "ba0a006"})


class TestNumberGate(unittest.TestCase):
    def test_agreement_is_silent(self):
        self.assertEqual(number_gate(counted={"concepts": 3, "relations": 1},
                                     metrics={"concepts": 3, "relations": 1}), [])

    def test_disagreement_names_the_field_and_both_numbers(self):
        """★규약을 코드로 강제한다 — 정본↔뷰가 갈라지면 화면에 뜬다."""
        w = number_gate(counted={"concepts": 4}, metrics={"concepts": 3})
        self.assertEqual(len(w), 1)
        self.assertIn("concepts", w[0])
        self.assertIn("4", w[0])
        self.assertIn("3", w[0])

    def test_missing_metrics_is_its_own_warning(self):
        w = number_gate(counted={"concepts": 4}, metrics=None)
        self.assertEqual(len(w), 1)
        self.assertIn("metrics.yaml", w[0])


from viewer import build_view_model


def _write_canon(d, *, concepts, bodies, relations=(), held=None, meta=None,
                 tier_a=None, metrics=None, crosscheck=None):
    """합성 canon 디렉터리. None을 넘긴 파일은 아예 안 쓴다(부재를 재현)."""
    canon = Path(d) / "canon"
    (canon / "tier-a").mkdir(parents=True)
    (canon / "concepts.yaml").write_text(yaml.safe_dump(
        {"meta": meta or {"source_sha": "sha1"}, "concepts": list(concepts),
         "relations": list(relations), "bodies": bodies,
         "held": held or {"candidate": [], "ambiguous": [], "gap": []}},
        allow_unicode=True), encoding="utf-8")
    if tier_a is not None:
        (canon / "tier-a" / "sha1.yaml").write_text(
            yaml.safe_dump({"concepts": tier_a}, allow_unicode=True), encoding="utf-8")
    if metrics is not None:
        (canon / "metrics.yaml").write_text(
            yaml.safe_dump({"metrics": metrics}, allow_unicode=True), encoding="utf-8")
    if crosscheck is not None:
        (canon / "crosscheck.yaml").write_text(
            yaml.safe_dump(crosscheck, allow_unicode=True), encoding="utf-8")
    return canon


class TestBuildViewModel(unittest.TestCase):
    def _model(self, d, **kw):
        canon = _write_canon(d, **kw)
        return build_view_model(canon, corpus="t", families={"article": "조항"},
                                source_root="/src")

    def test_meta_paths_can_be_relative(self):
        """★산출물에 기계 고유 절대경로가 남지 않게 — 호출자가 상대경로를 넘기면 그대로 싣는다."""
        with tempfile.TemporaryDirectory() as d:
            canon = _write_canon(d, concepts=[{"anchor": "c#1", "name": "가", "scope": "s"}],
                                 bodies={"c#1": []}, relations=[])
            m = build_view_model(canon, corpus="t", families={}, source_root="../../src",
                                 generated_from="fixtures/t/canon")
            self.assertEqual(m["meta"]["source_root"], "../../src")
            self.assertEqual(m["meta"]["generated_from"], "fixtures/t/canon")

    def test_concept_carries_planes_and_neighbors(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._model(
                d,
                concepts=[{"anchor": "c#1", "name": "가", "scope": "s"},
                          {"anchor": "c#2", "name": "나", "scope": "s"}],
                bodies={"c#1": [{"key": "A-1|content", "text": "현행"},
                                {"key": "A-2|content", "text": "옛", "superseded_at": "s0"}],
                        "c#2": []},
                relations=[{"from": "c#1", "to": "c#2", "canonical": "constrains",
                            "quote": "q"}],
                tier_a=[{"anchor": "A-1", "kind": "article", "file": "x.md", "line": 3},
                        {"anchor": "A-2", "kind": "article", "file": "x.md", "line": 9}],
                metrics={"concepts": 2, "relations": 1})
            c1 = [c for c in m["concepts"] if c["anchor"] == "c#1"][0]
            self.assertEqual(len(c1["fragments"]["current"]), 1)
            self.assertEqual(len(c1["fragments"]["history"]), 1)
            self.assertEqual(c1["neighbors"],
                             [{"dir": "out", "other": "c#2", "canonical": "constrains",
                               "quote": "q"}])
            self.assertEqual(m["sources"]["A-1"]["family"], "조항")
            self.assertEqual(m["warnings"], [])

    def test_number_gate_fires_when_metrics_disagree(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._model(d, concepts=[{"anchor": "c#1", "name": "가", "scope": "s"}],
                            bodies={"c#1": []}, tier_a=[], metrics={"concepts": 99})
            self.assertTrue(any("concepts" in w for w in m["warnings"]))

    def test_missing_tier_a_warns_and_still_builds(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._model(d, concepts=[{"anchor": "c#1", "name": "가", "scope": "s"}],
                            bodies={"c#1": [{"key": "A-1|content", "text": "t"}]},
                            tier_a=None, metrics={"concepts": 1})
            self.assertTrue(any("tier-a" in w for w in m["warnings"]))
            self.assertEqual(m["sources"], {})
            self.assertEqual(m["coverage"]["unresolved_anchors"], 1)

    def test_missing_crosscheck_is_none_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._model(d, concepts=[], bodies={}, tier_a=[], metrics={"concepts": 0})
            self.assertIsNone(m["coverage"]["crosscheck"])


import viewer_html
from viewer import attach_map


class TestMapInViewModel(unittest.TestCase):
    """지도는 뷰 모델의 일부다 — 렌더는 얇게 두고 판단은 여기서 한다(설계 §3-1)."""

    MODEL = {"concepts": [{"anchor": "inv#a", "scope": "p/t/inv", "name": "A",
                           "commitment": "frozen",
                           "fragments": {"current": [{"key": "k1"}], "history": [],
                                         "removed": []}},
                          {"anchor": "kms#b", "scope": "p/t/kms", "name": "B",
                           "commitment": "working",
                           "fragments": {"current": [], "history": [], "removed": []}}]}

    def test_the_model_carries_a_map_with_its_axis(self):
        m = attach_map(dict(self.MODEL), relations=[])
        self.assertEqual(m["map"]["axis"], "scope")
        self.assertEqual(m["map"]["stats"]["concepts"], 2)

    def test_the_map_counts_only_current_fragments(self):
        model = {"concepts": [{"anchor": "x#a", "scope": "s", "name": "A",
                               "commitment": None,
                               "fragments": {"current": [{"key": "lib/api/z#s|content"}],
                                             "history": [{"key": "old"}],
                                             "removed": [{"key": "gone"}]}}]}
        m = attach_map(model, relations=[])
        self.assertEqual(m["map"]["stats"]["fragments"], 1)

    def test_an_empty_canon_still_gets_a_map(self):
        m = attach_map({"concepts": []}, relations=[])
        self.assertEqual(m["map"]["groups"], [])


class TestMapPageIsRendered(unittest.TestCase):

    def test_the_nav_offers_the_map_page(self):
        html = viewer_html.render_html({"meta": {"corpus": "c"}, "concepts": [],
                                        "map": {"axis": "none", "axis_note": "", "groups": [],
                                                "links": [], "stats": {}}})
        self.assertIn('data-page="지도"', html)
