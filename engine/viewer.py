"""정본 뷰어 — 정본 YAML을 자기 완결 HTML 한 파일로 만드는 뷰 모델 빌더.

★로직은 전부 여기 있고 렌더(viewer_html.py)에는 없다. 렌더로 새면 테스트가 못 잡고,
그게 이 프로젝트가 반복해서 맞은 실패(게이트가 코드를 재고 산출물을 안 재는 것)의
같은 계열이다.
"""
from pathlib import Path

import yaml


def load_optional(path):
    """파일이 없으면 None, 있으면 파싱 결과(빈 파일은 {})."""
    p = Path(path)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_tier_a_index(path):
    """tier-a 스냅샷 → {anchor: {kind, file, line}}. 파일이 없으면 None."""
    doc = load_optional(path)
    if doc is None:
        return None
    return {c["anchor"]: {"kind": c.get("kind"), "file": c.get("file"),
                          "line": c.get("line")}
            for c in (doc.get("concepts") or []) if c.get("anchor")}


def anchor_of(key):
    """조각 key는 <앵커>|<필드>. 'quote'는 개념 자체의 근거 인용이라 앵커가 없다."""
    if not key or key == "quote":
        return None
    return key.split("|", 1)[0]


def resolve_sources(bodies, tier_a, families):
    """참조된 앵커에만 층·원문 위치를 붙인다."""
    sources, other_kinds, fam_counts, unresolved = {}, {}, {}, 0
    for frs in (bodies or {}).values():
        for fr in frs or []:
            a = anchor_of(fr.get("key", ""))
            if a is None:
                fam_counts["인용"] = fam_counts.get("인용", 0) + 1
                continue
            rec = (tier_a or {}).get(a)
            if rec is None:
                unresolved += 1
                continue
            kind = rec.get("kind")
            family = (families or {}).get(kind, "기타")
            if family == "기타":
                other_kinds[kind] = other_kinds.get(kind, 0) + 1
            fam_counts[family] = fam_counts.get(family, 0) + 1
            sources[a] = {"kind": kind, "family": family,
                          "file": rec.get("file"), "line": rec.get("line")}
    return sources, {"families": fam_counts, "other_kinds": other_kinds,
                     "unresolved_anchors": unresolved}


def build_coverage(crosscheck, integrity, drift, total_concepts, source_stats):
    """무엇을 쟀고 무엇을 안 쟀는지. None은 '안 쟀음', 숫자는 '쟀고 이만큼'."""
    return {
        "crosscheck": ({"checked": crosscheck.get("checked_concepts"),
                        "total": total_concepts} if crosscheck is not None else None),
        "integrity": ({"refs_checked": (integrity.get("meta") or {}).get("refs_checked")}
                      if integrity is not None else None),
        "drift": ({"fresh": (drift.get("freshness") or {}).get("fresh"),
                   "canon_sha": (drift.get("freshness") or {}).get("canon_sha")}
                  if drift is not None else None),
        "families": source_stats.get("families") or {},
        "other_kinds": source_stats.get("other_kinds") or {},
        "unresolved_anchors": source_stats.get("unresolved_anchors", 0),
    }


def number_gate(counted, metrics):
    """뷰어가 센 값과 metrics.yaml을 대조한다."""
    if metrics is None:
        return ["metrics.yaml을 읽지 못했다 — 숫자 대조를 건너뛴다"]
    out = []
    for field, mine in sorted(counted.items()):
        theirs = metrics.get(field)
        if theirs is not None and theirs != mine:
            out.append(f"{field}: 뷰어가 센 값 {mine} ≠ metrics.yaml {theirs}")
    return out


def owner_index(bodies):
    """조각앵커 → 개념앵커. integrity가 조각 축(from_id)이라 개념으로 잇는 데 쓴다."""
    out = {}
    for concept, frs in (bodies or {}).items():
        for fr in frs or []:
            a = anchor_of(fr.get("key", ""))
            if a is not None:
                out.setdefault(a, concept)
    return out


def merge_issues(crosscheck, drift, integrity, held, owner):
    """네 소스를 한 스키마로 접는다: {id, kind, concept, title, detail, sources, severity}.

    ★개념으로 못 잇는 항목도 버리지 않는다(concept=None으로 남긴다).
    ★integrity.archived는 코퍼스가 스스로 감사 제외를 선언한 것이라 세지 않는다.
    """
    issues = []

    def add(kind, concept, title, detail, sources, severity):
        issues.append({"id": f"{kind}-{len(issues)}", "kind": kind, "concept": concept,
                       "title": title, "detail": detail, "sources": sources,
                       "severity": severity})

    for c in ((crosscheck or {}).get("conflicts") or []):
        add("conflict", c.get("anchor"), f"{c.get('item')} — 층마다 다른 값",
            c.get("by_layer") or {}, c.get("sources") or {}, "high")
    for a in ((drift or {}).get("stale") or []):
        add("stale", a, "조각이 바뀌었다 — 본문을 다시 읽어야 한다", {}, {}, "mid")
    for s in ((drift or {}).get("stale_citations") or []):
        add("stale_citation", s.get("anchor"),
            f"{s.get('cites')}를 근거로 드는데 {s.get('superseded_by')}로 대체됐다",
            {"cites": s.get("cites"), "superseded_by": s.get("superseded_by")},
            {}, "high")
    for d in ((integrity or {}).get("dead") or []):
        add("dead", owner.get(d.get("from_id")),
            f"{d.get('from_id')} → {d.get('ref')} — 가리키는 곳이 없다",
            {"from_kind": d.get("from_kind"), "ref_kind": d.get("ref_kind"),
             "rescue": d.get("rescue") or []},
            {"from_id": d.get("from_id")}, "mid")
    for m in ((integrity or {}).get("ambiguous") or []):
        add("ambiguous", owner.get(m.get("from_id")),
            f"{m.get('from_id')} → {m.get('ref')} — 후보가 여럿이다",
            {"exists_in": m.get("exists_in") or []},
            {"from_id": m.get("from_id")}, "low")
    for bucket in ("candidate", "ambiguous", "gap"):
        for h in ((held or {}).get(bucket) or []):
            add("held", h.get("anchor"), f"판정 대기({bucket}) — {h.get('sid')}",
                {k: v for k, v in h.items() if k != "sid"}, {"sid": h.get("sid")}, "mid")
    return issues


def split_planes(fragments):
    """조각을 현행/이력/삭제 평면으로 가른다.

    removed_at이 superseded_at보다 우선한다 — 지워진 것은 이력이 아니라 무덤이다.
    """
    planes = {"current": [], "history": [], "removed": []}
    for fr in fragments or []:
        if fr.get("removed_at"):
            planes["removed"].append(fr)
        elif fr.get("superseded_at"):
            planes["history"].append(fr)
        else:
            planes["current"].append(fr)
    return planes


def attach_map(model, relations):
    """뷰 모델에 지도를 붙인다 — 현행 조각만 세고, 축은 `viewer_map`이 데이터로 고른다."""
    import viewer_map
    concepts = model.get("concepts") or []
    bodies = {c["anchor"]: ((c.get("fragments") or {}).get("current") or [])
              for c in concepts}
    model["map"] = viewer_map.build_map_model(concepts, relations, bodies)
    return model


def build_view_model(canon_dir, corpus, families, source_root, generated_from=None):
    """정본 디렉터리 → 뷰 모델. 결정론·부작용 0.

    읽는 파일: concepts.yaml(필수) · tier-a/<sha>.yaml · metrics.yaml ·
    crosscheck.yaml · integrity.yaml · drift.yaml (뒤 다섯은 없어도 된다).
    """
    canon_dir = Path(canon_dir)
    doc = load_optional(canon_dir / "concepts.yaml")
    if doc is None:
        raise FileNotFoundError(f"정본이 없다: {canon_dir / 'concepts.yaml'}")
    bodies = doc.get("bodies") or {}
    sha = (doc.get("meta") or {}).get("source_sha")

    warnings = []
    tier_a = load_tier_a_index(canon_dir / "tier-a" / f"{sha}.yaml")
    if tier_a is None:
        warnings.append(f"tier-a 스냅샷 없음({sha}) — 층 뱃지·출처 링크 없이 렌더한다")
    sources, source_stats = resolve_sources(bodies, tier_a, families)

    neighbors = {}
    for r in (doc.get("relations") or []):
        neighbors.setdefault(r.get("from"), []).append(
            {"dir": "out", "other": r.get("to"), "canonical": r.get("canonical"),
             "quote": r.get("quote")})
        neighbors.setdefault(r.get("to"), []).append(
            {"dir": "in", "other": r.get("from"), "canonical": r.get("canonical"),
             "quote": r.get("quote")})

    crosscheck = load_optional(canon_dir / "crosscheck.yaml")
    integrity = load_optional(canon_dir / "integrity.yaml")
    drift = load_optional(canon_dir / "drift.yaml")
    issues = merge_issues(crosscheck, drift, integrity, doc.get("held"),
                          owner_index(bodies))
    by_concept = {}
    for i in issues:
        if i["concept"]:
            by_concept.setdefault(i["concept"], []).append(i["id"])

    concepts = []
    for c in (doc.get("concepts") or []):
        a = c.get("anchor")
        concepts.append({**{k: c.get(k) for k in
                            ("anchor", "name", "scope", "commitment", "confidence",
                             "basis", "current", "last_seen")},
                         "fragments": split_planes(bodies.get(a) or []),
                         "neighbors": neighbors.get(a) or [],
                         "issues": by_concept.get(a) or []})

    metrics_doc = load_optional(canon_dir / "metrics.yaml")
    metrics = (metrics_doc or {}).get("metrics") if metrics_doc is not None else None
    warnings += number_gate({"concepts": len(concepts),
                             "relations": len(doc.get("relations") or []),
                             "bodies": len(bodies)}, metrics)

    return attach_map({"meta": {"corpus": corpus, "source_sha": sha,
                                "source_root": source_root,
                                "generated_from": (generated_from if generated_from is not None
                                                   else str(canon_dir))},
                       "concepts": concepts, "sources": sources, "issues": issues,
                       "coverage": build_coverage(crosscheck, integrity, drift,
                                                  len(concepts), source_stats),
                       "metrics": metrics, "warnings": warnings},
                      relations=doc.get("relations") or [])
