"""재생 스윕의 **계획**을 잰다 — 무엇을 어떤 범위로 도는가.

엔진 함수는 테스트가 지키는데 그것들을 어떤 범위로 부를지 정하는 층은 안 쟀다.
`crosscheck`가 작업 폴더 하나만 받아 전체 개념 중 일부만 대조하던 결함이 거기 살았다.

계획이 `regen_plan`의 반환값이고, 아래 테스트가 그 반환값을 잰다.
"""
import tempfile
import unittest
from pathlib import Path

import regen


def _apps(*names, **kw):
    """작업 폴더 목록. 기본은 promote까지 갈 수 있는 정상 폴더."""
    files = kw.get("files", {"subconcepts.yaml", "relations-canon.yaml"})
    return [{"name": n, "files": set(files), "consolidation": False} for n in names]


class TestCorpusWideSteps(unittest.TestCase):
    """코퍼스 축 단계는 앱을 고르지 않는다 — 하나를 골랐다는 게 결함이었다."""

    def test_crosscheck_covers_the_corpus_not_the_first_app(self):
        plan = regen.regen_plan(_apps("alert", "courier", "inv"))
        cc = [s for s in plan["steps"] if s["cmd"] == "crosscheck"]
        self.assertEqual(len(cc), 1)
        self.assertIsNone(cc[0]["app"],
                          "crosscheck에 앱을 넘기면 그 앱 scope로 좁는다 — 성공 측정 0/3의 원인")

    def test_each_corpus_step_runs_once_with_no_app(self):
        plan = regen.regen_plan(_apps("alert", "courier"))
        for cmd in ("drift", "crosscheck", "metrics", "view"):
            got = [s for s in plan["steps"] if s["cmd"] == cmd]
            self.assertEqual(len(got), 1, f"{cmd}는 코퍼스 축 단계다")
            self.assertIsNone(got[0]["app"], f"{cmd}에 앱을 넘기지 않는다")


class TestSkipping(unittest.TestCase):
    """조용한 건너뛰기 금지 — 왜 건너뛰었는지 계획에 남는다."""

    def test_an_app_missing_a_required_file_is_skipped_with_the_reason(self):
        apps = _apps("half", files={"subconcepts.yaml"})
        plan = regen.regen_plan(apps)
        self.assertEqual([s["app"] for s in plan["skipped"]], ["half"])
        self.assertEqual(plan["skipped"][0]["missing"], ["relations-canon.yaml"])

    def test_a_skipped_app_gets_no_steps(self):
        plan = regen.regen_plan(_apps("half", files={"subconcepts.yaml"}))
        self.assertEqual([s for s in plan["steps"] if s.get("app") == "half"], [])


class TestRoundArchive(unittest.TestCase):

    def test_the_round_is_archived_before_anything_is_regenerated(self):
        """직전 정본을 원장에 남기고 시작한다 — 이게 S6 drift의 prev다."""
        plan = regen.regen_plan(_apps("alert"))
        self.assertEqual(plan["steps"][0]["cmd"], "archive_round")


class TestConsolidation(unittest.TestCase):
    """통합 판정도 원장이다 — 재생하면 흡수된 개념이 무명으로 부활한다(실측)."""

    def test_consolidate_runs_only_for_apps_that_have_proposals(self):
        apps = _apps("alert", "lab")
        apps[1]["consolidation"] = True
        plan = regen.regen_plan(apps)
        self.assertEqual([s["app"] for s in plan["steps"] if s["cmd"] == "consolidate"],
                         ["lab"])

    def test_every_promote_precedes_any_consolidate(self):
        """통합은 전 앱 정본이 다 선 뒤에 돈다 — 교차앱 흡수라 순서가 결과를 바꾼다."""
        apps = _apps("alert", "lab")
        apps[0]["consolidation"] = True
        cmds = [s["cmd"] for s in regen.regen_plan(apps)["steps"]]
        self.assertLess(max(i for i, c in enumerate(cmds) if c == "promote"
                            and i < cmds.index("consolidate")),
                        cmds.index("consolidate"))
        first_cons = cmds.index("consolidate")
        self.assertNotIn("fold", cmds[first_cons:])


class TestReproducibilityPass(unittest.TestCase):
    """불변식 4 — 같은 원장으로 한 번 더 접어 같은 산출인지 기계가 확인한다."""

    def test_the_recheck_promotes_exactly_the_apps_the_first_pass_did(self):
        """★종전 bash는 1차엔 두 파일을 요구하고 2차엔 `subconcepts.yaml`만 봤다."""
        apps = _apps("alert", "courier") + _apps("half", files={"subconcepts.yaml"})
        plan = regen.regen_plan(apps)
        first = [s["app"] for s in plan["steps"]
                 if s["cmd"] == "promote" and s.get("phase") != "recheck"]
        recheck = [s["app"] for s in plan["steps"]
                   if s["cmd"] == "promote" and s.get("phase") == "recheck"]
        self.assertEqual(first, recheck)
        self.assertNotIn("half", recheck)

    def test_the_reference_copy_is_taken_before_the_recheck_and_compared_after(self):
        cmds = [s["cmd"] for s in regen.regen_plan(_apps("alert"))["steps"]]
        self.assertLess(cmds.index("snapshot_ref"), cmds.index("reproduce"))
        recheck = [i for i, c in enumerate(cmds) if c == "promote"][-1]
        self.assertLess(cmds.index("snapshot_ref"), recheck)
        self.assertLess(recheck, cmds.index("reproduce"))


class TestPerAppOrder(unittest.TestCase):

    def test_an_app_is_folded_before_it_is_promoted(self):
        plan = regen.regen_plan(_apps("alert", "courier"))
        for app in ("alert", "courier"):
            seq = [s["cmd"] for s in plan["steps"]
                   if s.get("app") == app and s.get("phase") != "recheck"]
            self.assertEqual(seq, ["fold", "promote"])


class TestRunner(unittest.TestCase):
    """실패를 삼키지 않는다 — 종전 `|| exit 0` 패턴을 반복하지 않는다."""

    def test_every_step_runs_in_plan_order(self):
        seen = []
        rep = regen.run_plan([{"cmd": "fold", "app": "a"}, {"cmd": "metrics", "app": None}],
                             lambda s: seen.append((s["cmd"], s["app"])))
        self.assertEqual(seen, [("fold", "a"), ("metrics", None)])
        self.assertTrue(rep["ok"])

    def test_a_failing_step_is_recorded_and_the_sweep_continues(self):
        seen = []

        def run(step):
            seen.append(step["cmd"])
            if step["cmd"] == "promote":
                raise RuntimeError("정본 못 씀")

        rep = regen.run_plan([{"cmd": "fold", "app": "a"},
                              {"cmd": "promote", "app": "a"},
                              {"cmd": "metrics", "app": None}], run)
        self.assertEqual(seen, ["fold", "promote", "metrics"], "뒤 단계까지 돈다")
        self.assertFalse(rep["ok"])
        self.assertEqual(len(rep["failures"]), 1)
        self.assertEqual(rep["failures"][0]["cmd"], "promote")
        self.assertIn("정본 못 씀", rep["failures"][0]["error"])


class TestDiscovery(unittest.TestCase):

    def _work(self, tree):
        d = Path(tempfile.mkdtemp())
        for app, files in tree.items():
            (d / app).mkdir()
            for f in files:
                (d / app / f).write_text("{}\n")
        return d

    def test_apps_come_back_sorted_with_the_files_they_have(self):
        w = self._work({"courier": ["subconcepts.yaml"],
                        "alert": ["subconcepts.yaml", "relations-canon.yaml"]})
        apps = regen.work_apps(w)
        self.assertEqual([a["name"] for a in apps], ["alert", "courier"])
        self.assertEqual(apps[1]["files"], {"subconcepts.yaml"})

    def test_a_consolidation_proposal_is_flagged(self):
        w = self._work({"lab": ["subconcepts.yaml", "consolidation-proposals-r1.yaml"],
                        "pipeline": ["subconcepts.yaml"]})
        apps = {a["name"]: a for a in regen.work_apps(w)}
        self.assertTrue(apps["lab"]["consolidation"])
        self.assertFalse(apps["pipeline"]["consolidation"])


class TestSnapshotResolution(unittest.TestCase):
    """어느 시점을 보는지 모른 채 재생하지 않는다."""

    def test_an_explicit_snapshot_wins_over_the_declaration(self):
        self.assertEqual(regen.resolve_snap("4a0a003", "aa0a005"), "4a0a003")

    def test_the_registry_declaration_is_used_when_none_is_given(self):
        self.assertEqual(regen.resolve_snap(None, "aa0a005"), "aa0a005")

    def test_regenerating_with_no_snapshot_at_all_is_refused(self):
        with self.assertRaises(regen.RegenRefused):
            regen.resolve_snap(None, None)


class TestArgv(unittest.TestCase):
    """단계 → CLI 인자. crosscheck 결함이 실제로 고쳐지는 자리."""

    def test_crosscheck_is_called_without_an_app(self):
        argv = regen.argv_for({"cmd": "crosscheck", "app": None}, "acme-docs", "ba0a006")
        self.assertEqual(argv, ["crosscheck", "acme-docs"])

    def test_promote_carries_the_app_and_the_snapshot(self):
        argv = regen.argv_for({"cmd": "promote", "app": "inv"}, "acme-docs", "ba0a006")
        self.assertEqual(argv, ["promote", "acme-docs", "inv", "--snap", "ba0a006"])

    def test_fold_takes_the_app_but_not_the_snapshot(self):
        argv = regen.argv_for({"cmd": "fold", "app": "inv"}, "acme-docs", "ba0a006")
        self.assertEqual(argv, ["fold", "acme-docs", "inv"])

    def test_reproduce_compares_against_the_reference_copy(self):
        argv = regen.argv_for({"cmd": "reproduce", "app": None, "ref": "/tmp/ref.yaml"},
                              "lab-self", "661dc97")
        self.assertEqual(argv, ["reproduce", "lab-self", "--against", "/tmp/ref.yaml"])


class TestCorpusLevelArity(unittest.TestCase):
    """앱 없이 부를 수 있어야 코퍼스 전체를 본다 — 결함이 실제로 닫히는 자리."""

    def test_the_corpus_axis_commands_do_not_require_an_app(self):
        import structure_app as sa
        for cmd in ("metrics", "view", "crosscheck", "drift"):
            self.assertFalse(sa.needs_app(cmd), f"{cmd}는 코퍼스 축이다")

    def test_the_per_app_commands_still_require_one(self):
        import structure_app as sa
        for cmd in ("ingest", "prep", "fold", "promote", "brief"):
            self.assertTrue(sa.needs_app(cmd), f"{cmd}는 앱 축이다")


class TestCliExecutor(unittest.TestCase):
    """실행 층 — CLI로 가는 단계와 안 가는 단계를 가른다."""

    def _ex(self, calls):
        return regen.CliExecutor("lab-self", "661dc97",
                                 run=lambda argv: calls.append(argv),
                                 archive=lambda: "r3.yaml",
                                 copy=lambda: "/tmp/ref.yaml")

    def test_the_round_archive_does_not_go_through_the_cli(self):
        calls = []
        self._ex(calls)({"cmd": "archive_round", "app": None})
        self.assertEqual(calls, [])

    def test_reproduce_compares_against_the_copy_this_sweep_took(self):
        calls = []
        ex = self._ex(calls)
        ex({"cmd": "snapshot_ref", "app": None})
        ex({"cmd": "reproduce", "app": None})
        self.assertEqual(calls, [["reproduce", "lab-self", "--against", "/tmp/ref.yaml"]])

    def test_reproducing_without_a_copy_is_an_error_not_a_silent_pass(self):
        """사본이 없으면 대조할 게 없다 — 조용히 통과시키면 게이트가 꺼진 줄 모른다."""
        with self.assertRaises(regen.RegenRefused):
            self._ex([])({"cmd": "reproduce", "app": None})

    def test_an_app_step_goes_to_the_cli_with_its_argv(self):
        calls = []
        self._ex(calls)({"cmd": "fold", "app": "lab"})
        self.assertEqual(calls, [["fold", "lab-self", "lab"]])


class TestGateExitCodes(unittest.TestCase):
    """★게이트 실패는 `SystemExit(1)`로 나온다 — `except Exception`이 안 잡는다.

    불변식 9(정본 단조)와 4(재현성)는 위반 시 종료 코드 1을 낸다. 이걸 그냥 두면
    스윕이 **게이트가 빨간불인데 초록으로 끝난다** — 이 프로젝트가 계속 경계해 온 형태다.
    """

    def test_a_gate_that_exits_nonzero_is_a_failure(self):
        def gate_fails(argv):
            raise SystemExit(1)

        with self.assertRaises(regen.StepFailed):
            regen.cli_runner(["metrics", "lab-self"], main=gate_fails)

    def test_a_usage_error_is_a_failure_too(self):
        def usage(argv):
            raise SystemExit("usage: ...")

        with self.assertRaises(regen.StepFailed):
            regen.cli_runner(["metrics", "lab-self"], main=usage)

    def test_a_clean_run_is_not(self):
        regen.cli_runner(["metrics", "lab-self"], main=lambda argv: None)

    def test_the_sweep_records_a_failed_gate_and_keeps_going(self):
        def run(step):
            if step["cmd"] == "metrics":
                regen.cli_runner(["metrics", "c"], main=lambda a: (_ for _ in ()).throw(SystemExit(1)))

        rep = regen.run_plan([{"cmd": "metrics", "app": None}, {"cmd": "view", "app": None}], run)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["failures"][0]["cmd"], "metrics")


class TestRunRegen(unittest.TestCase):
    """스윕 전체 — 발견 → 계획 → 실행을 잇는다(실행 층만 주입)."""

    def _fixtures(self, tree):
        root = Path(tempfile.mkdtemp())
        for app, files in tree.items():
            d = root / "c" / "work" / app
            d.mkdir(parents=True)
            for f in files:
                (d / f).write_text("{}\n")
        return root

    def test_a_corpus_with_no_work_folder_is_refused(self):
        root = self._fixtures({"alert": ["subconcepts.yaml"]})
        with self.assertRaises(regen.RegenRefused):
            regen.run_regen("없는코퍼스", snap="x", root=root, execute=lambda s: None)

    def test_the_report_names_the_skipped_folders_and_why(self):
        root = self._fixtures({"alert": ["subconcepts.yaml", "relations-canon.yaml"],
                               "half": ["subconcepts.yaml"]})
        rep = regen.run_regen("c", snap="x", root=root, execute=lambda s: None)
        self.assertEqual(rep["skipped"], [{"app": "half",
                                           "missing": ["relations-canon.yaml"]}])
        self.assertEqual(rep["regenerated"], ["alert"])

    def test_the_whole_corpus_is_crosschecked_once_at_the_end(self):
        root = self._fixtures({"alert": ["subconcepts.yaml", "relations-canon.yaml"],
                               "courier": ["subconcepts.yaml", "relations-canon.yaml"]})
        seen = []
        regen.run_regen("c", snap="x", root=root, execute=lambda s: seen.append(s))
        cc = [s for s in seen if s["cmd"] == "crosscheck"]
        self.assertEqual(len(cc), 1)
        self.assertIsNone(cc[0]["app"])
