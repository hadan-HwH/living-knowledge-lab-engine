"""Corpus, tier, platform, app boundaries.

Lesson from PPIR: folder separation != isolation (the loader merges everything).
Boundaries must be namespaced + guarded. Full hierarchy (mirrors acme-docs):

    corpus       acme-docs | personal-wevolley | ...      <- HARD boundary, never crosses
      └ tier     foundations | product  (SHARED, citable by any app)  vs  a platform's apps
          └ platform   summit | atlas | meadow | cargo | mango | neomart
              └ app    inv | alert | courier | billing | ...
                  └ feature / target / option

scope convention (corpus is a separate tag from the fixture path):
    "foundations/<area>"   "product/<area>"        -> SHARED tier
    "<platform>/<app>/<feature...>"                 -> a platform's app  (e.g. "summit/inv/items")
    personal corpus: "<app>/<feature...>"           -> single-product corpus, app = 1st segment

Isolation rules:
    - no ref crosses `corpus`
    - a ref into a SHARED (foundations/product) target is legal from any app (acme-docs Key→App citation)
    - a ref into another app's NON-shared target = violation (cross-app / cross-platform leak)
"""
from __future__ import annotations

from pathlib import Path
import yaml
from reducer import load_events

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FILE = Path(__file__).parent / "registry.yaml"

# Fallback only — the real structure lives in registry.yaml (data), discovered per corpus.
# The engine hardcodes NO platform/app/corpus names; this is just a sensible default when a
# corpus has no manifest entry.
DEFAULT_SHARED_TIERS = ("foundations", "product")


def load_registry(path=REGISTRY_FILE):
    """Structure grows in DATA, not code. Adding a corpus/platform/tier edits registry.yaml
    or the folder layout — never corpus.py."""
    if not Path(path).exists():
        return {"corpora": {}}
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {"corpora": {}}


def shared_tiers_for(corpus, registry=None):
    """Per-corpus shared-tier names, from the manifest (default fallback if unlisted)."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus)
    if entry is None:
        return tuple(DEFAULT_SHARED_TIERS)
    return tuple(entry.get("shared_tiers", DEFAULT_SHARED_TIERS))


def app_scopes_for(corpus, registry=None):
    """probe 앱 슬러그 → 정본 scope 선언 (registry `app_scopes`). 미선언 코퍼스는 {}."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    return dict(entry.get("app_scopes") or {})


def work_scopes_for(corpus, registry=None):
    """작업 폴더 슬러그 → **sid 접두** 선언 (registry `work_scopes`). 미선언은 {}."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    return entry.get("work_scopes") or {}


def discover_corpora(root=FIXTURES):
    """Corpora are discovered from the data (folders), not enumerated in code."""
    return sorted({corpus_of(p, root) for p in Path(root).rglob("events.yaml")})


def corpus_of(events_yaml_path, root=FIXTURES):
    """fixtures/<corpus>/.../<case>/events.yaml -> '<corpus>' (깊이 무관 — gold/ 등
    중간 폴더가 있어도 fixtures 바로 아래 첫 조각이 코퍼스)."""
    # ★resolve()를 쓰지 않는다 — 심링크를 실경로로 풀면 코퍼스 이름이 바뀐다.
    p = Path(events_yaml_path)
    p = p if p.is_absolute() else (Path.cwd() / p)
    r = Path(root)
    r = r if r.is_absolute() else (Path.cwd() / r)
    try:
        rel = p.relative_to(r)
    except ValueError:
        rel = Path(os.path.relpath(p, r))
    return rel.parts[0]


def product_of(atom_id):
    """Target id 'INV.status_representation' -> 'INV'. (Options are target-local.)"""
    return atom_id.split(".")[0] if atom_id and "." in atom_id else None


def is_shared(scope, shared_tiers=DEFAULT_SHARED_TIERS):
    """foundations/product tier — citable across apps. Tier names come from the manifest."""
    return bool(scope) and scope.split("/")[0] in tuple(shared_tiers)


def platform_of(scope, shared_tiers=DEFAULT_SHARED_TIERS):
    """'summit/inv/items' -> 'summit'. shared/legacy-app-rooted -> None. Position-based (no name list)."""
    if not scope or is_shared(scope, shared_tiers):
        return None
    parts = scope.split("/")
    return parts[0] if len(parts) >= 2 else None


def app_of(scope, shared_tiers=DEFAULT_SHARED_TIERS):
    """'summit/inv/items' -> 'inv'; personal 'wevolley/chat' -> 'wevolley'; shared -> None."""
    if not scope or is_shared(scope, shared_tiers):
        return None
    parts = scope.split("/")
    return parts[1] if len(parts) >= 2 else parts[0]


def load_all(root=FIXTURES):
    """Load every corpus's events, stamping `corpus` (from path) on each."""
    events = []
    import os
    found = []
    for base, dirs, files in os.walk(root, followlinks=True):
        dirs.sort()
        if "events.yaml" in files:
            found.append(Path(base) / "events.yaml")
    for f in sorted(found):
        corpus = corpus_of(f)
        for e in load_events(f):
            e = dict(e)
            e["corpus"] = corpus
            events.append(e)
    return events


def events_in_corpus(events, corpus):
    """'회사만' 필터 — 다른 corpus는 안 섞인다."""
    return [e for e in events if e.get("corpus") == corpus]


def events_in_platform(events, corpus, platform):
    """'atlas 전체' 같은 플랫폼 단위 선택."""
    return [e for e in events
            if e.get("corpus") == corpus and platform_of(e.get("scope")) == platform]


def check_isolation(events, registry=None):
    """Return boundary violations. Empty = clean. Structure (shared tiers per corpus) comes
    from the registry (data) — this function hardcodes no platform/app/tier names.

    - corpus_collision: a target defined in >1 corpus
    - cross_corpus_ref: a ref points at a target owned by another corpus
    - cross_app_ref: a ref points at another app's NON-shared target (foundations/product refs legal)
    """
    reg = registry if registry is not None else load_registry()

    def _shared(corpus):
        return shared_tiers_for(corpus, reg)

    violations = []
    owner = {}   # target -> (corpus, scope)
    for e in events:
        t, c = e.get("target"), e.get("corpus")
        if c is None:
            violations.append(("no_corpus", e.get("event_id")))
        if t:
            if t in owner and owner[t][0] != c:
                violations.append(("corpus_collision", t, owner[t][0], c))
            owner.setdefault(t, (c, e.get("scope")))

    def _refs(e):
        rs = [r.get("to") for r in (e.get("refs") or []) if isinstance(r, dict)]
        sup = e.get("supersedes")
        if sup and product_of(sup) and sup in owner:
            rs.append(sup)
        return [r for r in rs if r]

    for e in events:
        c = e.get("corpus")
        a = app_of(e.get("scope"), _shared(c))
        for ref in _refs(e):
            if ref not in owner:
                continue
            ref_corpus, ref_scope = owner[ref]
            if ref_corpus != c:
                violations.append(("cross_corpus_ref", e.get("event_id"), c, ref_corpus))
            elif not is_shared(ref_scope, _shared(ref_corpus)) and app_of(ref_scope, _shared(ref_corpus)) != a:
                violations.append(("cross_app_ref", e.get("event_id"), a, app_of(ref_scope, _shared(ref_corpus))))
    return violations


# ── fixture 레이아웃 — 폴더는 '역할'을 말한다 ───────────────────────────────

def canon_dir(corpus, root=FIXTURES):
    return Path(root) / corpus / "canon"


def canon_path(corpus, root=FIXTURES):
    return canon_dir(corpus, root) / "concepts.yaml"


def tier_a_path(corpus, sha, root=FIXTURES):
    return canon_dir(corpus, root) / "tier-a" / f"{sha}.yaml"


def drift_path(corpus, root=FIXTURES):
    return canon_dir(corpus, root) / "drift.yaml"


def work_dir(corpus, app, root=FIXTURES):
    return Path(root) / corpus / "work" / app


def ledger_dir(corpus, root=FIXTURES):
    return Path(root) / corpus / "ledger"


def concept_scope_merges_for(corpus, registry=None):
    """`{정본 scope: [개념 우주를 공유하는 scope, ...]}` (registry `concept_scope_merges`).

    선언 근거(registry 주석): 보통 한 제품은 일반·어드민·시스템을 한 앱 밑에 두는데
    inv만 인위적으로 둘로 갈려 있어 개념은 하나의 우주를 공유해야 한다."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    return entry.get("concept_scope_merges") or {}


#: 선언이 없는 코퍼스의 폴백 — 조용히 0건이 되는 것보다 넓게 잡는 게 낫다.
#: (본문이 비는 게 이 결함의 형태였다: 안 보이고 안 아프고 계속 틀림)
DEFAULT_STATEMENT_KINDS = ("article", "section", "screen_section", "spec_section",
                           "field", "state_enum", "gap")


def concept_exclude_for(corpus, registry=None):
    """개념층 적재에서 뺄 경로 세그먼트·파일명 (registry `concept_exclude`)."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    declared = list(entry.get("concept_exclude") or ())
    decision_file = entry.get("decision_file")
    if decision_file and decision_file not in declared:
        declared.append(decision_file)
    return tuple(declared)


def is_concept_excluded(path, exclude):
    """경로가 제외 대상인가 — **세그먼트 완전일치** 또는 파일명 일치.

    부분 문자열 매칭을 안 쓰는 이유는 `3-research-old` 같은 이름이 우연히 걸리기 때문이다
    (`archive_segments`가 같은 이유로 완전일치를 쓴다)."""
    from ingest import slug
    parts = str(path).split("/")
    seg_slugs = {slug(p) for p in parts}
    for e in exclude or ():
        if e.endswith("*"):
            pre = e[:-1]
            if any(p.startswith(pre) for p in parts):
                return True
        elif e in parts or slug(e) in seg_slugs:
            return True
    return False


def drop_excluded_sources(concepts, exclude):
    """Tier B 입력에서 제외 문서 유래 단위를 뺀다 — "A는 포함, B는 제외"의 나머지 절반.

    Tier A 스냅샷 자체는 건드리지 않는다 — 이 필터는 Tier B 입력 조립 시점에만 걸린다."""
    if not exclude:
        return list(concepts or [])
    return [c for c in (concepts or [])
            if not (c.get("file") and is_concept_excluded(c["file"], exclude))]


def archive_segments_for(corpus, registry=None):
    """보존 구역 세그먼트 (registry `archive_segments`) — 정본은 아니지만 **보존**된 것."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    return tuple(entry.get("archive_segments") or ())


DEFAULT_SOURCE_GLOBS = ("**/*.md",)


def concept_formats_for(corpus, registry=None):
    """경로 글롭 → 개념 파서 (registry `concept_formats`). 스칼라 `concept_format` 호환."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    plural = entry.get("concept_formats")
    if plural:
        return dict(plural)
    scalar = entry.get("concept_format")
    return {"**/*.md": scalar} if scalar else {}


def source_globs_for(corpus, registry=None):
    """스냅샷이 **발견**할 파일 (registry `source_globs`). 미선언이면 포맷 키에서 유도.

    ★진짜 블로커가 여기였다: `collect_concepts`가 두 분기 모두 `rglob("*.md")`로
    하드코딩돼 있어 `.py`가 파서에 **도달조차 못 했다**. 파서(`ast`)는 처음부터 됐다.
    포맷 층과 발견 층이 S1 안에서 겹쳐 있던 것이다.

    글롭을 두 번 적게 하지 않는다 — `concept_formats`의 키가 곧 발견 대상이다.
    (`canon_snap`을 정렬로 **추측**하던 금지 사례와 다르다: 저긴 없는 선언을 지어냈고
    여긴 있는 선언을 읽는다.) 미선언 코퍼스는 `**/*.md` = 현행 동작 그대로."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    declared = entry.get("source_globs")
    if declared:
        return tuple(declared)
    fmts = concept_formats_for(corpus, reg)
    return tuple(fmts) if fmts else DEFAULT_SOURCE_GLOBS


def statement_kinds_for(corpus, registry=None):
    """개념이 조각을 모아오는 **서술 단위**의 kind (registry `statement_kinds`)."""
    reg = registry or load_registry()
    entry = (reg.get("corpora") or {}).get(corpus) or {}
    return tuple(entry.get("statement_kinds") or DEFAULT_STATEMENT_KINDS)


def kind_families(registry=None):
    """kind → 표시용 가족 (registry 최상위 `kind_families`).

    ★코퍼스별이 아니라 전역이다 — 표시 어휘는 코퍼스와 무관하다. kind 집합 자체는
    코퍼스마다 다르므로(acme-docs article 계열 ↔ wevolley function 계열) 접기만 한다.
    선언에 없는 kind는 호출자가 '기타'로 센다 — 삼키면 층 분류가 썩는 걸 못 본다.
    """
    reg = registry if registry is not None else load_registry()
    out = {}
    for family, kinds in (reg.get("kind_families") or {}).items():
        for k in kinds or []:
            out[k] = family
    return out


def canon_extensions_path(corpus, root=FIXTURES):
    """관계 어휘 선언(core_13 + extensions) — **정본 옆**이지 작업 폴더가 아니다."""
    return canon_dir(corpus, root=root) / "canon-extensions.yaml"


def integrity_path(corpus, root=FIXTURES):
    """침식 감시 산출 — brief가 읽는 자리. 종전엔 아무도 이 파일을 쓰지 않아
    brief의 '침식 0'이 측정이 아니라 파일 부재였다."""
    return canon_dir(corpus, root=root) / "integrity.yaml"


def snapshot_index(corpus, root=FIXTURES):
    """Tier A 스냅샷 목록 — **기록된 시각 최신순**. [{sha, generated_at, dirty}].

    meta는 파일 첫 블록이라 `concepts:`가 나오면 읽기를 멈춘다 — 스냅샷 1개가
    1.1MB라 전량 파싱하면 게이트 하나가 초 단위로 느려진다."""
    d = canon_dir(corpus, root=root) / "tier-a"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.yaml")):
        head = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line[:1] not in (" ", "\t", "") and not line.startswith("meta:"):
                    break            # 최상위 다음 키(concepts:/flags:) → meta 끝
                head.append(line)
        meta = ((yaml.safe_load("".join(head)) or {}).get("meta")) or {}
        out.append({"sha": p.stem, "generated_at": meta.get("generated_at"),
                    "dirty": meta.get("source_dirty")})
    out.sort(key=lambda r: (r["generated_at"] is not None, r["generated_at"] or ""),
             reverse=True)
    return out


def bench_dir(corpus, root=FIXTURES):
    return Path(root) / corpus / "bench"
