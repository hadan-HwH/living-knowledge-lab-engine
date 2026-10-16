"""L1 개념층 스냅샷 — 기계 파생물의 물질화.

"사람은 그래프를 저작하지 않는다" 원칙과 구분: 이 파일들은 **기계 생성·SHA 고정·
언제든 재생성 가능**하다. 손으로 편집하지 않는다(편집할 거면 원본을 고치고 재추출).

Usage: python3 l1_snapshot.py [corpus]   → fixtures/<corpus>/l1-snapshots/<sha>/concepts.yaml"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

from ingest import slug
from parsers import parse

_SKIP_PARTS = {".system", ".git", ".github", ".claude"}


def _scope(root, app_dir):
    parts = app_dir.relative_to(root).parts
    return "/".join(slug(p) for p in parts)


def _module_path(rel):
    """코드 어댑터의 모듈 축 — `engine/l1_snapshot.py` → `engine.l1_snapshot`."""
    s = str(rel)
    for ext in (".d.ts", ".py", ".tsx", ".ts", ".jsx", ".js", ".mjs"):
        if s.endswith(ext):
            s = s[: -len(ext)]
            break
    return s.replace("/", ".")


def collect_concepts(root, concept_format=None, ignore=None, flat_scope=None,
                     corpus=None, registry=None):
    """코퍼스 트리 → 개념 수집. 결정론(정렬 순회) — 같은 원본이면 같은 출력.

    corpus가 주어지면 선언 경로, `concept_format`만 주어지면 옛 스칼라 경로(호환),
    둘 다 없으면 기존 acme-docs 레이아웃 매핑(1-rules/·spec.md·2-screens/·foundations).
    [flag] 기존 레이아웃 매핑이 코드에 잔존 — registry 선언 이전 후보(특수 잔여)."""
    root = Path(root)
    skip = _SKIP_PARTS | set(ignore or [])
    concepts, flags = [], []

    fmt_map = None
    if corpus is not None:
        from corpus import concept_formats_for, source_globs_for
        fmt_map = concept_formats_for(corpus, registry)
        globs = source_globs_for(corpus, registry)
    elif concept_format:
        fmt_map, globs = {"**/*.md": concept_format}, ("**/*.md",)

    if fmt_map:
        from ingest import doc_slug
        seen = set()
        for g in globs:
            fmt = fmt_map.get(g)
            if fmt is None:
                flags.append(f"[{g}] 포맷 미선언 글롭 — 건너뜀 (concept_formats에 추가하라)")
                continue
            for f in sorted(root.glob(g)):
                if not f.is_file():
                    continue
                rel = f.relative_to(root)
                if any(p in skip for p in rel.parts) or rel in seen:
                    continue
                seen.add(rel)
                res = parse(fmt, f.read_text(encoding="utf-8"), scope=flat_scope,
                            doc_slug=doc_slug(str(rel)), module=_module_path(rel))
                for c in res["concepts"]:
                    c["file"] = str(rel)
                    concepts.append(c)
                flags.extend(f"[{rel}] {x}" for x in res.get("flags", []))
        concepts.sort(key=lambda c: (c["file"], c.get("line") or 0))
        kinds = {}
        for c in concepts:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        return {"concepts": concepts, "flags": flags,
                "stats": {"concepts": len(concepts), "by_kind": kinds,
                          "flags": len(flags)}}
    for f in sorted(root.rglob("*.md")):
        rel = f.relative_to(root)
        if any(p in skip for p in rel.parts):
            continue
        parent_slug = slug(f.parent.name)
        slugs = [slug(p) for p in rel.parts]
        if parent_slug == "rules":
            fmt, app_dir = "corpdoc-rules", f.parent.parent
        elif f.name == "spec.md":
            fmt, app_dir = "corpdoc-spec", f.parent
        elif "screens" in slugs[:-1] and f.name != "README.md":
            i = slugs.index("screens")
            fmt, app_dir = "corpdoc-screen", root.joinpath(*rel.parts[:i])
        elif parent_slug == "foundations" and f.name != "README.md":
            fmt, app_dir = "corpdoc-rules", f.parent   # 전사 공통 조항(ARCH·MAIL 등)
        else:
            continue
        res = parse(fmt, f.read_text(encoding="utf-8"), scope=_scope(root, app_dir))
        for c in res["concepts"]:
            c["file"] = str(rel)
            concepts.append(c)
        flags.extend(f"[{rel}] {x}" for x in res.get("flags", []))

    kinds = {}
    for c in concepts:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    return {"concepts": concepts, "flags": flags,
            "stats": {"concepts": len(concepts), "by_kind": kinds, "flags": len(flags)}}


def main():
    corpus = sys.argv[1] if len(sys.argv) > 1 else "acme-docs"
    here = Path(__file__).parent
    reg = yaml.safe_load((here / "registry.yaml").read_text(encoding="utf-8"))
    root = (here / reg["corpora"][corpus]["source"]).resolve()
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "no-git"
    dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                capture_output=True, text=True).stdout.strip())

    cfg = reg["corpora"][corpus]
    out = collect_concepts(root, corpus=corpus, registry=reg,
                           ignore=cfg.get("ignore"), flat_scope=cfg.get("flat_app"))
    from corpus import tier_a_path
    snap_path = tier_a_path(corpus, sha)
    snap_dir = snap_path.parent
    snap_dir.mkdir(parents=True, exist_ok=True)
    doc = {"meta": {"corpus": corpus, "source_sha": sha, "source_dirty": dirty,
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "generator": "l1_snapshot.py (기계 생성 — 손 편집 금지, 재생성 가능)",
                    **out["stats"]},
           "flags": out["flags"], "concepts": out["concepts"]}
    snap_path.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"snapshot {corpus}@{sha}{' (dirty!)' if dirty else ''}: "
          f"{out['stats']['concepts']} concepts {out['stats']['by_kind']}, "
          f"flags {out['stats']['flags']} → {snap_dir.relative_to(here)}/concepts.yaml")


if __name__ == "__main__":
    main()
