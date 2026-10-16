"""단위 드리프트 분류 — 이동 vs 개명/삭제 (설계 §4-B, 2-B 단계).

원 측정은 생존율 61.2%로 **빨간불**이었다. 갈라 보니 결함이 아니었다."""
import unittest

from l1_integrity import classify_removed_units


def U(anchor, content="본문", kind="function", scope="app", file=None):
    return {"anchor": anchor, "kind": kind, "scope": scope, "content": content,
            "file": file or (anchor.replace(".", "/") + ".py")}


class TestClassify(unittest.TestCase):
    def test_file_move_carries_its_symbols(self):
        """★1단계 — 옮겨지는 단위는 심볼이 아니라 **파일**이다."""
        removed = [U("engine.pilot", "모듈 설명", kind="module", file="engine/pilot.py"),
                   U("engine.pilot.main", "돈다", file="engine/pilot.py")]
        added = [U("engine.archive.pilot", "모듈 설명", kind="module",
                   file="engine/archive/pilot.py"),
                 U("engine.archive.pilot.main", "돈다", file="engine/archive/pilot.py"),
                 U("engine.other.main", "무관한 동명", file="engine/other.py")]
        out = classify_removed_units(removed, added)
        self.assertEqual(out["stats"]["renamed_or_deleted"], 0)
        self.assertEqual({m["from"]: m["to"] for m in out["moved"]},
                         {"engine.pilot": "engine.archive.pilot",
                          "engine.pilot.main": "engine.archive.pilot.main"})
        self.assertEqual(out["moved"][0]["basis"], "file")

    def test_symbol_deleted_during_file_move_is_not_a_move(self):
        """파일은 옮겨졌지만 그 심볼이 사라졌으면 tombstone이 맞다."""
        out = classify_removed_units(
            [U("a.mod.gone", "x", file="a/mod.py")],
            [U("b.mod.other", "y", file="b/mod.py")])
        self.assertEqual(out["moved"], [])
        self.assertEqual(out["renamed_or_deleted"][0]["anchor"], "a.mod.gone")

    def test_ambiguous_file_basename_is_not_a_move(self):
        """동명 파일이 여럿이면 지어내지 않는다."""
        out = classify_removed_units(
            [U("a.mod.f", "x", file="a/mod.py")],
            [U("b.mod.f", "x", file="b/mod.py"), U("c.mod.f", "x", file="c/mod.py")])
        self.assertEqual(out["moved"], [])

    def test_move_detected_by_leaf_and_content_without_file_info(self):
        """★2단계 — 파일 정보가 없는 원장에도 견딘다(마크다운 계열 원장 호환)."""
        removed = [U("engine.baseline", "기준선을 잰다", file=None)]
        added = [U("engine.research.baseline", "기준선을 잰다", file=None)]
        for u in removed + added:
            u.pop("file")
        out = classify_removed_units(removed, added)
        self.assertEqual(out["moved"][0]["to"], "engine.research.baseline")
        self.assertEqual(out["moved"][0]["basis"], "leaf+content")

    def test_move_detected_by_leaf_when_content_edited(self):
        """같은 커밋에서 옮기며 고치는 일은 흔하다 — 말단 이름이 유일하면 이동으로 본다."""
        removed, added = [U("a.foo", "옛 설명")], [U("b.foo", "새 설명")]
        for u in removed + added:
            u.pop("file")
        out = classify_removed_units(removed, added)
        self.assertEqual(out["moved"][0]["to"], "b.foo")
        self.assertEqual(out["moved"][0]["basis"], "leaf")

    def test_ambiguous_leaf_is_not_a_move(self):
        """말단 이름이 여럿이면 지어내지 않는다 — 판정 큐로 보낸다."""
        out = classify_removed_units([U("a.main", "x")],
                                     [U("b.main", "y"), U("c.main", "z")])
        self.assertEqual(out["moved"], [])
        self.assertEqual(out["renamed_or_deleted"][0]["anchor"], "a.main")

    def test_ambiguous_resolved_when_content_matches_exactly_one(self):
        """내용이 정확히 하나와 같으면 모호하지 않다."""
        out = classify_removed_units([U("a.main", "고유한 본문")],
                                     [U("b.main", "고유한 본문"), U("c.main", "다른 것")])
        self.assertEqual(out["moved"][0]["to"], "b.main")

    def test_deletion_stays_deletion(self):
        """진짜 삭제는 tombstone으로 가야 한다 — 이동으로 봐주면 유령이 남는다."""
        out = classify_removed_units([U("a.gone", "사라짐")], [U("b.other", "무관")])
        self.assertEqual(out["moved"], [])
        self.assertEqual([r["anchor"] for r in out["renamed_or_deleted"]], ["a.gone"])

    def test_rename_in_place_is_not_a_move(self):
        """같은 자리에서 이름만 바뀐 건 재바인딩 제안 대상이지 이동이 아니다."""
        out = classify_removed_units([U("a.old_name", "같은 본문")],
                                     [U("a.new_name", "같은 본문")])
        self.assertEqual(out["moved"], [])
        self.assertEqual(out["renamed_or_deleted"][0]["anchor"], "a.old_name")

    def test_archived_destination_flagged(self):
        """봉인으로의 이동은 **현행 평면에서 내리되 지식은 보존**한다 — 삭제와 다르다."""
        out = classify_removed_units(
            [U("engine.bench", "벤치")],
            [U("engine.research.bench", "벤치", file="engine/research/bench.py")],
            archive_segments=("research",))
        self.assertTrue(out["moved"][0]["archived"])

    def test_live_destination_not_archived(self):
        out = classify_removed_units([U("a.foo", "x")], [U("b.foo", "x")],
                                     archive_segments=("research",))
        self.assertFalse(out["moved"][0]["archived"])

    def test_kind_must_match(self):
        """function이 사라지고 section이 생긴 건 이동이 아니다(축이 다르다)."""
        out = classify_removed_units([U("a.foo", "x", kind="function")],
                                     [U("b.foo", "x", kind="section")])
        self.assertEqual(out["moved"], [])

    def test_deterministic_and_sorted(self):
        removed = [U("z.a", "1"), U("y.b", "2")]
        added = [U("q.b", "2"), U("p.a", "1")]
        a = classify_removed_units(removed, added)
        b = classify_removed_units(list(reversed(removed)), list(reversed(added)))
        self.assertEqual(a, b)
        self.assertEqual([m["from"] for m in a["moved"]], ["y.b", "z.a"])

    def test_empty_inputs(self):
        out = classify_removed_units([], [])
        self.assertEqual(out, {"moved": [], "renamed_or_deleted": [],
                               "stats": {"moved": 0, "renamed_or_deleted": 0,
                                         "archived": 0}})

    def test_stats_counted(self):
        out = classify_removed_units(
            [U("a.x", "1"), U("a.y", "2"), U("a.z", "3")],
            [U("b.x", "1", file="engine/research/b.py")],
            archive_segments=("research",))
        self.assertEqual(out["stats"], {"moved": 1, "renamed_or_deleted": 2,
                                        "archived": 1})


class TestNoLeafForFlatAnchors(unittest.TestCase):
    """마크다운 anchor(`docs/x#헤딩`)에도 안전해야 한다 — 코드 전용 기계가 아니다."""

    def test_markdown_anchor_move_across_documents(self):
        out = classify_removed_units(
            [U("docs/a#원리", "본문", kind="section")],
            [U("docs/b#원리", "본문", kind="section")])
        self.assertEqual(out["moved"][0]["to"], "docs/b#원리")

    def test_markdown_heading_rename_is_not_a_move(self):
        out = classify_removed_units(
            [U("docs/a#원리", "본문", kind="section")],
            [U("docs/a#원칙", "본문", kind="section")])
        self.assertEqual(out["moved"], [])


class TestPrepPlanSplitsMoves(unittest.TestCase):
    """★배선 — 분류기가 있어도 prep이 안 부르면 아무 일도 안 일어난다.

    이 프로젝트가 반복해서 당한 형태가 정확히 "선언은 있고 배선이 없는" 것이다
. 그래서 선언과 배선을 따로 시험한다.
    """

    def setUp(self):
        from structure_app import prep_plan
        self.prep_plan = prep_plan

    def _sec(self, anchor, text, file):
        return {"anchor": anchor, "text": text, "file": file, "kind": "function"}

    def test_moved_unit_is_not_reported_as_removed(self):
        """이동을 removed로 흘리면 tombstone이 찍힌다 — 정당한 봉인이 묘비가 된다."""
        prev = [self._sec("engine.pilot.main", "돈다", "engine/pilot.py")]
        new = [self._sec("engine.archive.pilot.main", "돈다", "engine/archive/pilot.py")]
        plan = self.prep_plan("app", new, [], prev_sections=prev)
        self.assertEqual(plan["removed"], [], "이동이 removed로 샜다")
        self.assertEqual([m["from"] for m in plan["moved"]], ["engine.pilot.main"])
        self.assertEqual(plan["moved"][0]["to"], "engine.archive.pilot.main")

    def test_true_deletion_still_reported_as_removed(self):
        """반대 방향 — 진짜 삭제까지 살려주면 유령이 남는다."""
        prev = [self._sec("a.mod.gone", "사라짐", "a/mod.py")]
        new = [self._sec("b.other.x", "무관", "b/other.py")]
        plan = self.prep_plan("app", new, [], prev_sections=prev)
        self.assertEqual([s["anchor"] for s in plan["removed"]], ["a.mod.gone"])
        self.assertEqual(plan["moved"], [])

    def test_pure_move_is_not_re_extracted(self):
        """내용이 같은 순수 이동은 재추출 대상이 아니다 — LLM을 다시 부를 이유가 없다."""
        prev = [self._sec("engine.pilot.main", "돈다", "engine/pilot.py")]
        new = [self._sec("engine.archive.pilot.main", "돈다", "engine/archive/pilot.py")]
        plan = self.prep_plan("app", new, [], prev_sections=prev)
        self.assertEqual(plan["to_extract"], [], "순수 이동이 추출 대상으로 잡혔다")
        self.assertEqual([s["anchor"] for s in plan["carried"]],
                         ["engine.archive.pilot.main"])

    def test_move_with_edit_is_re_extracted(self):
        """옮기며 고쳤으면 내용이 바뀐 것이니 재추출한다."""
        prev = [self._sec("engine.pilot.main", "옛 설명", "engine/pilot.py")]
        new = [self._sec("engine.archive.pilot.main", "새 설명",
                         "engine/archive/pilot.py")]
        plan = self.prep_plan("app", new, [], prev_sections=prev)
        self.assertEqual([s["anchor"] for s in plan["to_extract"]],
                         ["engine.archive.pilot.main"])
        self.assertEqual([m["from"] for m in plan["moved"]], ["engine.pilot.main"])

    def test_first_run_has_no_moves(self):
        plan = self.prep_plan("app", [self._sec("a.b", "x", "a.py")], [])
        self.assertEqual(plan["moved"], [])


if __name__ == "__main__":
    unittest.main()


class TestFileAxisWiredToLedgerSchema(unittest.TestCase):
    """★배선 2 — 원장 스키마와 분류기 입력이 어긋나 있었다.

    분류기의 1단계(파일 축)는 `file`을 읽는데 실 원장(sections.yaml)은 `doc`을 쓴다.
    합성 테스트는 `file`을 직접 넣어서 통과했고, 실 파이프라인에선 1단계가 통째로
    죽어 있었다 — "선언은 있고 배선이 없는" 형태의 또 다른 판이다.
    """

    def test_doc_field_feeds_the_file_axis(self):
        from structure_app import prep_plan
        prev = [{"anchor": "engine.pilot.main", "text": "돈다", "doc": "engine/pilot.py"}]
        new = [{"anchor": "engine.archive.pilot.main", "text": "돈다",
                "doc": "engine/archive/pilot.py"}]
        plan = prep_plan("app", new, [], prev_sections=prev)
        self.assertEqual(plan["removed"], [], "doc을 못 읽어 이동이 삭제로 샜다")
        self.assertEqual([m["basis"] for m in plan["moved"]], ["file"])

    def test_archived_flag_uses_doc_path(self):
        from structure_app import prep_plan
        prev = [{"anchor": "engine.bench.run", "text": "돈다", "doc": "engine/bench.py"}]
        new = [{"anchor": "engine.research.bench.run", "text": "돈다",
                "doc": "engine/research/bench.py"}]
        plan = prep_plan("app", new, [], prev_sections=prev,
                         archive_segments=("research",))
        self.assertTrue(plan["moved"][0]["archived"])
