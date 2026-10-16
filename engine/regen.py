"""재생 스윕 — 원장에서 정본을 처음부터 다시 만드는 회차 절차.

계획과 실행을 가른다. 계획이 데이터라서 "무엇을 어떤 범위로 도는가"에 게이트를 건다.

  regen_plan(apps) → 계획(순수 함수, I/O 0)   ← 테스트가 잰다
  run_regen(...)   → 계획을 실행하는 얇은 층
"""
import os
import shutil
import tempfile
from pathlib import Path


#: promote까지 갈 수 있는 작업 폴더의 조건. 없으면 건너뛰되 **사유를 남긴다**.
REQUIRED = ("subconcepts.yaml", "relations-canon.yaml")

#: 코퍼스 축 단계 — 앱을 고르지 않는다.
CORPUS_STEPS = ("crosscheck", "metrics", "view")


def regen_plan(apps):
    """작업 폴더 목록 → 실행 계획 {steps, skipped}. 순수 함수·I/O 0.

    apps: [{"name": str, "files": set[str], "consolidation": bool}]
    """
    steps, skipped, live = [], [], []
    # 직전 정본을 원장에 남기고 시작한다 — 재생 **전에** 해야 drift의 prev가 생긴다.
    steps.append({"cmd": "archive_round", "app": None})
    for a in apps:
        missing = [f for f in REQUIRED if f not in a["files"]]
        if missing:
            skipped.append({"app": a["name"], "missing": missing})
            continue
        live.append(a)
        steps.append({"cmd": "fold", "app": a["name"]})
        steps.append({"cmd": "promote", "app": a["name"]})
    # 통합은 전 앱 정본이 다 선 뒤에 — 흡수는 교차앱이라 순서가 결과를 바꾼다.
    for a in live:
        if a.get("consolidation"):
            steps.append({"cmd": "consolidate", "app": a["name"]})
    steps.append({"cmd": "drift", "app": None})
    # 불변식 4 — 사본을 뜨고, **같은 앱 집합으로** 한 번 더 접어 대조한다.
    steps.append({"cmd": "snapshot_ref", "app": None})
    for a in live:
        steps.append({"cmd": "promote", "app": a["name"], "phase": "recheck"})
    steps.append({"cmd": "reproduce", "app": None})
    for cmd in CORPUS_STEPS:
        steps.append({"cmd": cmd, "app": None})
    return {"steps": steps, "skipped": skipped}


class RegenRefused(Exception):
    """재생을 거부한다 — 조용히 짐작하고 도는 것보다 안 도는 게 낫다."""


def resolve_snap(requested, declared):
    """어느 스냅샷으로 재생할지. 명시가 선언을 이기고, 둘 다 없으면 거부한다."""
    snap = requested or declared
    if not snap:
        raise RegenRefused("--snap도 registry canon_snap도 없다 — "
                           "어느 시점을 볼지 모른 채 재생하지 않는다")
    return snap


def argv_for(step, corpus, snap):
    """단계 → `structure_app` 인자(스크립트 이름 제외)."""
    cmd, app = step["cmd"], step.get("app")
    if cmd == "reproduce":
        return ["reproduce", corpus, "--against", step["ref"]]
    argv = [cmd, corpus] + ([app] if app else [])
    if cmd == "promote":
        argv += ["--snap", snap]
    return argv


def work_apps(work_dir):
    """작업 폴더를 훑어 계획의 입력을 만든다. 이름 순(재실행 diff 0의 전제)."""
    apps = []
    for d in sorted(p for p in work_dir.iterdir() if p.is_dir()):
        files = {f.name for f in d.iterdir() if f.is_file()}
        apps.append({
            "name": d.name,
            "files": files,
            "consolidation": any(f.startswith("consolidation-proposals")
                                 and f.endswith(".yaml") for f in files),
        })
    return apps


class StepFailed(Exception):
    """단계가 실패했다 — 스윕은 계속 돌되 종료 코드로 낸다."""


def cli_runner(argv, main=None):
    """`structure_app`을 부르고 **종료 코드를 실패로 번역한다.**

    게이트 위반은 `SystemExit(1)`이라 평범한 `except Exception`을 그냥 통과한다.
    """
    if main is None:
        import structure_app
        main = structure_app.main
    try:
        main(["structure_app.py"] + list(argv))
    except SystemExit as e:
        if e.code:
            raise StepFailed(f"{' '.join(argv)} → exit {e.code}") from None


class CliExecutor:
    """단계를 실제로 돌린다. 대부분은 `structure_app` CLI로 가고, 둘은 아니다 —
    회차 아카이브와 사본 뜨기는 정본을 옮기는 일이라 명령이 아니다."""

    def __init__(self, corpus, snap, run, archive, copy):
        self.corpus, self.snap = corpus, snap
        self._run, self._archive, self._copy = run, archive, copy
        self.ref = None

    def __call__(self, step):
        cmd = step["cmd"]
        if cmd == "archive_round":
            out = self._archive()
            print(f"  회차 아카이브: {out or '변화 없음 — 새 회차 아님'}")
            return
        if cmd == "snapshot_ref":
            self.ref = self._copy()
            return
        if cmd == "reproduce":
            if not self.ref:
                raise RegenRefused("재현성 대조할 사본이 없다 — 게이트를 조용히 넘기지 않는다")
            step = dict(step, ref=self.ref)
        self._run(argv_for(step, self.corpus, self.snap))


def run_plan(steps, execute):
    """계획을 순서대로 실행한다. **실패는 삼키지 않고 계속 돈 뒤 종료 코드로 낸다.**"""
    failures = []
    for step in steps:
        try:
            execute(step)
        except Exception as e:                        # noqa: BLE001 — 사유를 남기는 게 목적
            failures.append({"cmd": step["cmd"], "app": step.get("app"),
                             "error": f"{type(e).__name__}: {e}"})
    return {"ok": not failures, "failures": failures}


def fixtures_root():
    """cwd로 겨냥이 바뀌지 않는다 — 모듈 기준(`structure_app`과 같은 규약)."""
    return Path(os.environ.get("LKL_FIXTURES")
                or Path(__file__).resolve().parent / "fixtures")


def _default_executor(corpus, snap, root):
    import structure_app as sa

    canon = root / corpus / "canon" / "concepts.yaml"

    def archive():
        out = sa.archive_round(canon, root / corpus / "ledger" / "rounds")
        return out.name if out else None

    def copy():
        fd, path = tempfile.mkstemp(prefix=f"regen-{corpus}-", suffix=".yaml")
        os.close(fd)
        shutil.copyfile(canon, path)
        return path

    return CliExecutor(corpus, snap, run=cli_runner, archive=archive, copy=copy)


def run_regen(corpus, snap=None, root=None, execute=None, declared=None):
    """회차 재생 스윕. 원장 → 정본 전량 재생 + 게이트. 결정론·LLM 호출 0."""
    root = Path(root) if root else fixtures_root()
    work = root / corpus / "work"
    if not work.is_dir():
        raise RegenRefused(f"{work} 없음 — 코퍼스 이름을 확인하라")
    if declared is None and snap is None:
        import corpus as _cp
        declared = ((_cp.load_registry().get("corpora") or {})
                    .get(corpus) or {}).get("canon_snap")
    snap = resolve_snap(snap, declared)

    apps = work_apps(work)
    plan = regen_plan(apps)
    print(f"regen {corpus} @ {snap}")
    rep = run_plan(plan["steps"], execute or _default_executor(corpus, snap, root))

    regenerated = sorted({s["app"] for s in plan["steps"]
                          if s["cmd"] == "promote" and s.get("phase") != "recheck"})
    print(f"regen {corpus}: 재생 {len(regenerated)}앱 · 건너뜀 {len(plan['skipped'])}")
    for s in plan["skipped"]:
        print(f"  – {s['app']} (없음: {' '.join(s['missing'])})")
    for f in rep["failures"]:
        print(f"  ✗ {f['cmd']} {f['app'] or ''} — {f['error']}")
    return dict(rep, skipped=plan["skipped"], regenerated=regenerated, snap=snap)


def main(argv):
    """python3 regen.py <corpus> [--snap SHA]"""
    if len(argv) < 2:
        raise SystemExit("usage: regen.py <corpus> [--snap SHA]")
    snap = argv[3] if len(argv) > 3 and argv[2] == "--snap" else None
    rep = run_regen(argv[1], snap=snap)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    import sys

    try:
        raise SystemExit(main(sys.argv))
    except RegenRefused as e:
        raise SystemExit(f"regen: {e}")
