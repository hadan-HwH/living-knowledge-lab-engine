"""Generic, layout-tolerant structure discovery for any corpus.

원칙(사용자):
  1. 제네릭 우선 — 엔진은 acme-docs을 모른다. 레이아웃·포맷은 registry.yaml(데이터)에서 온다.
  2. 변경 내성 — 폴더 번호(1-·2-·a-)는 순번이라 재배정된다. 정체성은 **slug(번호 뗀 이름)**과
     결정 ID에 둔다. acme-docs이 디렉토리 번호를 바꿔도 scope가 안 깨진다.

이 모듈은 **구조 발견**(어떤 corpus의 폴더 → corpus/platform/app/scope)만 담당한다. 결정 내용
추출(표/번호 형식 파싱)은 corpus의 `decision_format`별 파서가 담당(pluggable) — 여기서 dispatch만.
"""
from __future__ import annotations

import re
from pathlib import Path

from corpus import load_registry, shared_tiers_for

_INDEX = re.compile(r"^(?:[0-9]+|[a-z])-")   # 순번 접두사: 1- · 2- · a- · b-


def slug(folder_name):
    """'1-summit'->'summit', '2-inv'->'inv', 'a-console-builder'->'console-builder'. 번호 없으면 그대로.
    정체성은 slug — acme-docs이 번호를 바꿔도 안 변한다."""
    return _INDEX.sub("", folder_name, count=1)


def derive_scope(rel_parts, corpus_cfg):
    """corpus source 기준 상대 경로 조각들 → (scope, platform, app). 전부 slug 기반.

    깊이-무관 규칙 (구조가 계속 바뀌므로 위치 하드코딩 안 함):
      - 첫 slug이 shared_tiers   -> 공유(foundations/business). scope=전체 경로, app=None
      - 첫 slug이 meta_tiers     -> 메타(corpdoc). scope=slug, app=slug
      - 그 외 = 제품 경로        -> scope=전체 slug 경로, **app=말단 slug**, platform=말단 직전
    말단(=decisions-log가 있는 폴더)이 app이므로, 제품 라인/플랫폼이 몇 겹이든 app을 정확히 집는다.
    """
    slugs = [slug(p) for p in rel_parts if p]
    if not slugs:                                    # flat corpus: 루트 결정 파일 = 프로덕트 자체
        fa = corpus_cfg.get("flat_app")
        return (fa, None, fa) if fa else (None, None, None)
    shared = tuple(corpus_cfg.get("shared_tiers", ()))
    meta = tuple(corpus_cfg.get("meta_tiers", ()))

    if slugs[0] in shared:                           # 공유 tier — 앱 없음
        return "/".join(slugs), None, None
    if slugs[0] in meta:                             # 메타 (corpdoc)
        return "/".join(slugs), None, slugs[0]
    # 제품 경로: 깊이 무관. app=말단, platform=말단 직전(있으면), scope=전체 경로
    scope = "/".join(slugs)
    app = slugs[-1]
    platform = slugs[-2] if len(slugs) >= 2 else None
    return scope, platform, app


def discover(corpus_name, source_root, registry=None):
    """source 폴더를 걸어 decision 파일을 찾고 각각의 scope/platform/app을 도출.
    매치 안 되는 것은 버리지 않고 warnings에 남긴다(무성 누락 금지)."""
    reg = registry or load_registry()
    cfg = (reg.get("corpora") or {}).get(corpus_name, {})
    cfg = {**cfg, "shared_tiers": shared_tiers_for(corpus_name, reg)}
    dfile = cfg.get("decision_file", "DECISIONS.md")
    ignore = set(cfg.get("ignore", []))
    root = Path(source_root)
    found, warnings = [], []
    if not root.exists():
        return {"corpus": corpus_name, "found": [], "warnings": [f"source 없음: {root}"], "config": cfg}
    for f in sorted(root.rglob(dfile)):
        rel = f.parent.relative_to(root).parts
        if any(part in ignore for part in f.relative_to(root).parts):   # 감사 제외 인프라 스킵
            continue
        scope, platform, app = derive_scope(rel, cfg)
        if scope is None:
            warnings.append(f"scope 미도출: {rel}")
            continue
        found.append({"file": str(f.relative_to(root)), "scope": scope,
                      "platform": platform, "app": app, "format": cfg.get("decision_format")})
    return {"corpus": corpus_name, "found": found, "warnings": warnings, "config": cfg}


if __name__ == "__main__":
    reg = load_registry()
    for name, cfg in (reg.get("corpora") or {}).items():
        src = (Path(__file__).parent / cfg["source"]).resolve() if cfg.get("source") else None
        if not src or not src.exists():
            print(f"[{name}] source 미연결({cfg.get('source')}) — 스킵 (dry-run)")
            continue
        res = discover(name, src, reg)
        print(f"[{name}] {len(res['found'])} decision-file, warnings {len(res['warnings'])}")
        for r in res["found"][:12]:
            print(f"    {r['scope'] or '(root)':40s} <- {r['file']}")


def doc_slug(rel_path):
    """문서 정체성 slug — 경로 각 조각의 번호 순번 제거 + .md 확장자 제거.
    (doc-heading anchor 스킴의 문서 축 — markdown-corpus-adapter §2)"""
    parts = str(rel_path).split("/")
    if parts[-1].endswith(".md"):
        parts[-1] = parts[-1][:-3]
    return "/".join(slug(x) for x in parts)
