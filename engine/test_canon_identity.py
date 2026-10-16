"""정본 정체성 불변식 — anchor 유일성과 비파괴 병합 (불변식 8, 2026-08-04 소유자 지시)."""
import tempfile
import unittest
from pathlib import Path

import yaml

import corpus as cp
from conftest import require_checked, require_corpora
import structure_app as sa


def _write_probe(base, subconcepts, queue, relations=None):
    yaml.safe_dump({"subconcepts": subconcepts}, open(base / "subconcepts.yaml", "w"),
                   allow_unicode=True)
    yaml.safe_dump({"relations": relations or []}, open(base / "relations-canon.yaml", "w"),
                   allow_unicode=True)
    yaml.safe_dump({"queue": queue, "carried": []}, open(base / "adjudication.yaml", "w"),
                   allow_unicode=True)


def _write_stack(path, concepts=None, bodies=None):
    yaml.safe_dump({"meta": {}, "concepts": concepts or [], "relations": [],
                    "bodies": bodies or {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(path, "w"), allow_unicode=True, sort_keys=False)


class TestAnchorUniqueness(unittest.TestCase):
    """불변식 8 — 정본에 같은 anchor가 두 번 나오지 않는다."""

    def test_report_flags_duplicates(self):
        rep = sa.anchor_uniqueness_report([{"anchor": "a#x"}, {"anchor": "a#y"},
                                           {"anchor": "a#x"}])
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["duplicates"], [{"anchor": "a#x", "count": 2}])

    def test_report_passes_when_unique(self):
        rep = sa.anchor_uniqueness_report([{"anchor": "a#x"}, {"anchor": "a#y"}])
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["duplicates"], [])

    def test_every_committed_canon_holds_the_invariant(self):
        """데이터 품질 게이트 — 정본 전부에 건다. 대상 0건이면 통과가 아니라 skip."""
        checked = 0
        for corpus in require_corpora(self):
            path = cp.canon_path(corpus)
            if not path.exists():
                continue
            doc = yaml.safe_load(open(path)) or {}
            rep = sa.anchor_uniqueness_report(doc.get("concepts") or [])
            self.assertTrue(rep["ok"], f"{corpus}: anchor 중복 {rep['duplicates']}")
            checked += len(doc.get("concepts") or [])
        require_checked(self, checked, "정본 개념")


class TestMergeByLedgerPrefix(unittest.TestCase):
    """병합 접두는 CLI 앱 슬러그가 아니라 원장 sid에서 온다."""

    def test_round_folder_merges_into_the_app_it_belongs_to(self):
        """`mango-pipeline-r2` 폴더의 원장 sid는 `mango#`이다 — 정본의 mango 슬라이스와
        병합돼야 하고, 중복 anchor를 만들면 안 된다."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "mango-pipeline-r2"
            base.mkdir()
            _write_probe(base,
                         subconcepts=[{"anchor": "sc-phase", "name": "Phase", "quote": "q"}],
                         queue=[{"sid": "mango#sc-phase", "was": "merged",
                                 "disposition": "auto_adopt", "quote": "q"}])
            stack = tmp / "canon.yaml"
            _write_stack(stack, concepts=[{"anchor": "mango#sc-phase", "kind": "concept",
                                           "name": "Phase", "scope": "pc/mango/mango",
                                           "basis": "document_stated"}])
            sa.run_promote(base, "mango-pipeline-r2", stack,
                           app_scope="pc/mango/mango")
            saved = yaml.safe_load(open(stack))
        anchors = [c["anchor"] for c in saved["concepts"]]
        self.assertEqual(anchors.count("mango#sc-phase"), 1)
        self.assertTrue(sa.anchor_uniqueness_report(saved["concepts"])["ok"])

    def test_other_apps_are_still_untouched(self):
        """원장 접두로 바꿔도 타 앱 슬라이스는 보존된다(종전 계약 불변)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "probe"
            base.mkdir()
            _write_probe(base,
                         subconcepts=[{"anchor": "sc-a", "name": "A", "quote": "q"}],
                         queue=[{"sid": "mango#sc-a", "was": "new",
                                 "disposition": "auto_adopt", "quote": "q"}])
            stack = tmp / "canon.yaml"
            _write_stack(stack, concepts=[{"anchor": "inv#sc-keep", "kind": "concept",
                                           "name": "Keep", "scope": "pc/summit/inv",
                                           "basis": "document_stated"}])
            sa.run_promote(base, "mango-pipeline-r2", stack, app_scope="pc/mango/mango")
            saved = yaml.safe_load(open(stack))
        self.assertIn("inv#sc-keep", [c["anchor"] for c in saved["concepts"]])


class TestEmptyDoesNotOverwrite(unittest.TestCase):
    """빈 값은 채워진 값을 덮지 않는다 — carried 행이 정본의 이름을 지우던 결함."""

    def test_carried_row_without_name_keeps_the_canon_name(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "probe"
            base.mkdir()
            # 이번 회차 probe에 sc-phase가 없다 → fold_depth가 name=None으로 접는다.
            _write_probe(base,
                         subconcepts=[{"anchor": "sc-other", "name": "Other", "quote": "q"}],
                         queue=[{"sid": "mango#sc-phase", "was": "merged",
                                 "disposition": "auto_adopt", "quote": "q"}])
            stack = tmp / "canon.yaml"
            _write_stack(stack, concepts=[{"anchor": "mango#sc-phase", "kind": "concept",
                                           "name": "벤치마크 단계", "scope": "pc/mango/mango",
                                           "basis": "document_stated"}])
            sa.run_promote(base, "mango-pipeline-r2", stack, app_scope="pc/mango/mango")
            saved = yaml.safe_load(open(stack))
        node = {c["anchor"]: c for c in saved["concepts"]}["mango#sc-phase"]
        self.assertEqual(node["name"], "벤치마크 단계")

    def test_every_committed_canon_concept_has_a_name(self):
        """이름 없는 개념은 별칭·귀속·브리핑에서 전부 걸린다. 대상 0건이면 skip."""
        checked = 0
        for corpus in require_corpora(self):
            path = cp.canon_path(corpus)
            if not path.exists():
                continue
            doc = yaml.safe_load(open(path)) or {}
            concepts = doc.get("concepts") or []
            nameless = [c["anchor"] for c in concepts if not c.get("name")]
            self.assertEqual(nameless, [], f"{corpus}: 무명 개념 {len(nameless)}건")
            checked += len(concepts)
        require_checked(self, checked, "정본 개념")




class TestWorkScopeDeclaration(unittest.TestCase):
    """작업 폴더 이름 ≠ sid 접두 — 회차 폴더는 선언으로 잇는다."""

    def test_registry_declares_the_sid_prefix_for_round_folders(self):
        ws = cp.work_scopes_for("acme-docs")
        self.assertEqual(ws.get("mango-pipeline-r1"), "mango")
        self.assertEqual(ws.get("mango-pipeline-r2"), "mango")

    def test_undeclared_folder_falls_back_to_its_own_name(self):
        self.assertIsNone(cp.work_scopes_for("acme-docs").get("inv"))


if __name__ == "__main__":
    unittest.main()


class TestRelationsSurviveReObservation(unittest.TestCase):
    """관계도 anchor 기준 **병합**이다 — 개념·본문과 같은 규칙."""

    def _promote(self, tmp, queue, relations, stack_relations=None, stack_concepts=None):
        base = tmp / "p"
        base.mkdir(exist_ok=True)
        yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "name": "A", "quote": "q"},
                                        {"anchor": "sc-b", "name": "B", "quote": "q"}]},
                       open(base / "subconcepts.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"relations": relations},
                       open(base / "relations-canon.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"queue": queue, "carried": []},
                       open(base / "adjudication.yaml", "w"), allow_unicode=True)
        stack = tmp / "canon.yaml"
        yaml.safe_dump({"meta": {}, "concepts": stack_concepts or [],
                        "relations": stack_relations or [], "bodies": {},
                        "held": {"candidate": [], "ambiguous": [], "gap": []}},
                       open(stack, "w"), allow_unicode=True)
        sa.run_promote(base, "inv", stack, app_scope="x/inv")
        return yaml.safe_load(open(stack))

    def test_reobserved_round_does_not_wipe_earlier_relations(self):
        rel = {"from": "inv#sc-a", "to": "inv#sc-b", "canonical": "part_of"}
        with tempfile.TemporaryDirectory() as td:
            saved = self._promote(
                Path(td),
                queue=[],                                  # 전건 재관측 = 승격 0
                relations=[{"from": "sc-a", "to": "sc-b", "canonical": "part_of"}],
                stack_relations=[rel],
                stack_concepts=[{"anchor": "inv#sc-a", "name": "A", "scope": "x/inv"},
                                {"anchor": "inv#sc-b", "name": "B", "scope": "x/inv"}])
        self.assertEqual(saved["relations"], [rel])

    def test_relation_between_canon_concepts_is_admitted(self):
        """양끝이 이번에 승격되지 않았어도 **정본에 있으면** 관계는 성립한다."""
        with tempfile.TemporaryDirectory() as td:
            saved = self._promote(
                Path(td), queue=[],
                relations=[{"from": "sc-a", "to": "sc-b", "canonical": "constrains"}],
                stack_relations=[],
                stack_concepts=[{"anchor": "inv#sc-a", "name": "A", "scope": "x/inv"},
                                {"anchor": "inv#sc-b", "name": "B", "scope": "x/inv"}])
        self.assertEqual([(r["from"], r["to"], r["canonical"]) for r in saved["relations"]],
                         [("inv#sc-a", "inv#sc-b", "constrains")])

    def test_dangling_endpoint_is_still_refused(self):
        """정본에도 이번 승격분에도 없는 끝점은 여전히 안 받는다(지어냄 차단 불변)."""
        with tempfile.TemporaryDirectory() as td:
            saved = self._promote(
                Path(td), queue=[],
                relations=[{"from": "sc-a", "to": "sc-nope", "canonical": "part_of"}],
                stack_relations=[],
                stack_concepts=[{"anchor": "inv#sc-a", "name": "A", "scope": "x/inv"}])
        self.assertEqual(saved["relations"], [])


class TestLastSeenOnPromotion(unittest.TestCase):
    """승격도 "이번 회차에 문서에서 봤다"이다 — 재관측만 찍는 건 반쪽이다.

    ★확산 청크 A에서 서브에이전트가 지적: 증분 회차는 새 개념만 내므로
    auto_fold가 0이고, `stamp_last_seen`이 재관측 target만 찍어서 **방금 승격한 개념에
    last_seen이 안 박힌다.** `last_seen`의 뜻이 "마지막으로 문서에서 본 회차"라면
    승격이야말로 가장 확실하게 본 회차다. 안 찍으면 tombstone 후보 판정("몇 회차째
    안 보이는 개념")이 신규 개념을 즉시 후보로 올린다."""

    def test_newly_promoted_concept_carries_the_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "p"
            base.mkdir()
            _write_probe(base, subconcepts=[{"anchor": "sc-new", "name": "N", "quote": "q"}],
                         queue=[{"sid": "inv#sc-new", "was": "new",
                                 "disposition": "auto_adopt", "quote": "q"}])
            stack = tmp / "canon.yaml"
            _write_stack(stack)
            sa.run_promote(base, "inv", stack, app_scope="x/inv", snap="s9")
            saved = yaml.safe_load(open(stack))
        self.assertEqual(saved["concepts"][0]["last_seen"], "s9")

    def test_untouched_other_app_keeps_its_own_stamp(self):
        """이번에 안 본 개념은 그대로 — 노후 신호가 보존돼야 tombstone 후보가 드러난다."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "p"
            base.mkdir()
            _write_probe(base, subconcepts=[{"anchor": "sc-new", "name": "N", "quote": "q"}],
                         queue=[{"sid": "inv#sc-new", "was": "new",
                                 "disposition": "auto_adopt", "quote": "q"}])
            stack = tmp / "canon.yaml"
            _write_stack(stack, concepts=[{"anchor": "alert#sc-old", "name": "O",
                                           "scope": "x/alert", "last_seen": "s1"}])
            sa.run_promote(base, "inv", stack, app_scope="x/inv", snap="s9")
            saved = yaml.safe_load(open(stack))
        old = {c["anchor"]: c for c in saved["concepts"]}["alert#sc-old"]
        self.assertEqual(old["last_seen"], "s1")

    def test_no_snapshot_means_no_stamp(self):
        """모르는 것을 최신이라 부르지 않는다 — snap이 없으면 안 찍는다."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base = tmp / "p"
            base.mkdir()
            _write_probe(base, subconcepts=[{"anchor": "sc-new", "name": "N", "quote": "q"}],
                         queue=[{"sid": "inv#sc-new", "was": "new",
                                 "disposition": "auto_adopt", "quote": "q"}])
            stack = tmp / "canon.yaml"
            _write_stack(stack)
            sa.run_promote(base, "inv", stack, app_scope="x/inv")
            saved = yaml.safe_load(open(stack))
        self.assertNotIn("last_seen", saved["concepts"][0])


class TestResolvedVocabularyAbsorbsNew(unittest.TestCase):
    """같은 쌍에 승격된 어휘가 이미 있으면 `NEW`는 접힌다.

    `NEW`는 어휘가 아니라 **판정 대기 표식**이다 — 같은 쌍에 판정된 어휘가 생기면
    그 표식은 역할이 끝난다. 남겨두면 관계 수가 부풀고 질의가 같은 쌍을 두 번 낸다."""

    def test_new_is_dropped_when_a_named_relation_exists_for_the_pair(self):
        rels = [{"from": "a", "to": "b", "canonical": "NEW"},
                {"from": "a", "to": "b", "canonical": "realizes"}]
        out = sa.absorb_resolved_new(rels)
        self.assertEqual([r["canonical"] for r in out], ["realizes"])

    def test_new_survives_when_the_pair_has_no_verdict(self):
        rels = [{"from": "a", "to": "b", "canonical": "NEW"}]
        self.assertEqual(sa.absorb_resolved_new(rels), rels)

    def test_other_pairs_are_untouched(self):
        rels = [{"from": "a", "to": "b", "canonical": "NEW"},
                {"from": "c", "to": "d", "canonical": "part_of"}]
        self.assertEqual(len(sa.absorb_resolved_new(rels)), 2)

    def test_canon_has_no_pair_carrying_both_new_and_a_verdict(self):
        """제네릭 게이트 — 다음에 어휘를 승격해도 같은 중복이 안 생긴다."""
        import collections
        checked = 0
        for corpus in require_corpora(self):
            path = cp.canon_path(corpus)
            if not path.exists():
                continue
            rels = (yaml.safe_load(open(path)) or {}).get("relations") or []
            pairs = collections.defaultdict(set)
            for r in rels:
                pairs[(r.get("from"), r.get("to"))].add(r.get("canonical"))
            bad = {k: v for k, v in pairs.items() if "NEW" in v and len(v) > 1}
            self.assertEqual(bad, {}, f"{corpus}: NEW와 판정 어휘가 공존하는 쌍 {len(bad)}")
            checked += len(rels)
        require_checked(self, checked, "정본 관계")
