"""변경 축 — 결정론 국소화 (설계: docs/2-method/change-layer-design.md).

원리: 변경은 원본(acme-docs) 스냅샷 SHA 간 diff로 관측한다. 본문=A 조립층이라
조각→본문 매핑이 exact — 낡음 국소화·증분 등가성 검사는 전부 결정론(LLM 0).
LLM 원장(의미 관계)은 재생성하지 않고 실효 검사로 auto_ok/재판정 큐만 분류한다."""
from __future__ import annotations

import re


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def _key(f):
    return (f["concept"], f.get("field"))


def diff_fragments(old_frags, new_frags):
    """key(concept, field) 단위 diff. 텍스트는 공백 정규화 후 비교 — key가 concept ID
    기반이라 폴더 재번호 같은 경로 변경은 diff에 잡히지 않는다(변경 내성)."""
    old = {_key(f): _norm(f["text"]) for f in old_frags}
    new = {_key(f): _norm(f["text"]) for f in new_frags}
    return {"added": sorted(k for k in new if k not in old),
            "removed": sorted(k for k in old if k not in new),
            "changed": sorted(k for k in old if k in new and old[k] != new[k]),
            "unchanged": sorted(k for k in old if k in new and old[k] == new[k])}


def stale_nodes(diff, old_homes, new_homes):
    """낡은 노드 = changed·removed 조각의 (구) 집 ∪ added·changed 조각의 (신) 집.
    homes에 없는 key는 무시(그 조각은 어떤 노드 본문에도 없음)."""
    out = set()
    for k in diff["changed"] + diff["removed"]:
        if k in old_homes:
            out.add(old_homes[k])
    for k in diff["added"] + diff["changed"]:
        if k in new_homes:
            out.add(new_homes[k])
    return sorted(out)


def stale_relations(relations, diff, new_pool):
    """의미 관계 실효 검사 — 원장 보존, LLM 재호출은 requeue만.
    evidence 조각이 removed → requeue / changed → quote가 신 원문에 실재하면
    auto_ok, 아니면 requeue / diff 밖 → unaffected."""
    new_text = {_key(f): _norm(f["text"]) for f in new_pool}
    changed, removed = set(diff["changed"]), set(diff["removed"])
    out = {"auto_ok": [], "requeue": [], "unaffected": []}
    for i, r in enumerate(relations):
        ev = r.get("evidence") or {}
        key = (ev.get("concept"), ev.get("field"))
        entry = {"i": i, "from": r.get("from"), "rel": r.get("rel"),
                 "to": r.get("to"), "evidence_key": f"{key[0]}|{key[1]}"}
        if key in removed:
            out["requeue"].append(entry)
        elif key in changed:
            if ev.get("quote") and _norm(ev["quote"]) in new_text.get(key, ""):
                out["auto_ok"].append(entry)
            else:
                out["requeue"].append(entry)
        else:
            out["unaffected"].append(entry)
    return out


def equivalence_check(old_bodies, new_bodies, stale):
    """증분 재조립(낡은 노드만 새로, 나머지는 구 본문 승계) == 전체 재조립 게이트.
    missed_stale = 변했는데 stale로 안 잡힌 노드(게이트 실패 원인),
    false_stale = stale로 잡혔지만 본문이 같은 노드(낭비 — 게이트는 통과)."""
    stale = set(stale)
    missed, false = [], []
    for node, body in new_bodies.items():
        carried = body if (node in stale or node not in old_bodies) else old_bodies[node]
        if carried != body:
            missed.append(node)
    for node in stale:
        if node in old_bodies and node in new_bodies \
                and old_bodies[node] == new_bodies[node]:
            false.append(node)
    return {"equal": not missed, "missed_stale": sorted(missed),
            "false_stale": sorted(false)}


def evolution_log(diff, old_homes, new_homes, sha_pair):
    """개념 수준 changelog — 스냅샷 쌍의 개념 진화 관측(침식 감시의 개념층 확장)."""
    old_nodes, new_nodes = set(old_homes.values()), set(new_homes.values())
    return {"sha_pair": list(sha_pair),
            "nodes_added": sorted(new_nodes - old_nodes),
            "nodes_removed": sorted(old_nodes - new_nodes),
            "fragments": {"added": len(diff["added"]), "removed": len(diff["removed"]),
                          "changed": len(diff["changed"]),
                          "unchanged": len(diff["unchanged"])}}


# ── 파일럿 배선 (결정론 — LLM 재호출 0) ──────────────────────────────


def _load(path):
    import yaml
    from pathlib import Path
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _parse_key(s):
    concept, _, field = s.partition("|")
    return (concept, None if field == "None" else field)


def _bodies(pool, homes):
    """A 조립층 등가 프록시 — 노드별 (key, text) 정렬 목록. assemble_a가 이 입력의
    순수 함수라 입력 등가 ⇒ 본문 등가."""
    out = {}
    for f in pool:
        key = (f["concept"], f.get("field"))
        node = homes.get(key)
        if node:
            out.setdefault(node, []).append([f"{key[0]}|{key[1]}", _norm(f["text"])])
    return {n: sorted(v) for n, v in out.items()}


def main(argv):
    from pathlib import Path
    import yaml
    from body_probe import collect_fragments
    from term_layer import build_vocab, find_occurrences, make_terms
    from relation_layer import (build_resource_concepts, designate_concepts,
                                rehome_fragments, rehome_by_subject)
    cmd = argv[1]
    if cmd != "pilot":
        raise SystemExit(f"unknown command: {cmd}")
    old_dir, new_dir = Path(argv[2]), Path(argv[3])
    scope = argv[4] if len(argv) > 4 else "prime-commerce/summit/inv"
    resources = (argv[5] if len(argv) > 5 else "Item,Promo Code").split(",")

    old_snap, new_snap = _load(old_dir / "concepts.yaml"), _load(new_dir / "concepts.yaml")
    old_concepts, new_concepts = old_snap["concepts"], new_snap["concepts"]
    old_terms = [t for t in _load(old_dir / "terms.yaml")["terms"]
                 if t["resource"] in resources]
    judgments = [j for j in _load(old_dir / "judgments-merged.yaml")["judgments"]
                 if j.get("resource") and j["resource"] != "?"]

    # term 정체성 승계: 어휘·판정 원장은 구 스냅샷, 등장·조각만 신 원문 재검색
    new_pool_c = [c for c in new_concepts if c.get("scope") == scope]
    vocab = build_vocab(new_pool_c)
    occ = find_occurrences(vocab, new_pool_c)
    res = make_terms(vocab, occ, judgments=judgments)
    new_terms = [t for t in res["terms"] if t["resource"] in resources]

    adj = _load(old_dir / "relations" / "adjudication.yaml") or {}
    old_frags = [f for t in old_terms for f in collect_fragments(t, old_concepts)]
    new_frags = [f for t in new_terms for f in collect_fragments(t, new_concepts)]
    new_nodes = (build_resource_concepts(new_terms)
                 + designate_concepts(adj.get("designated_concepts", [])))
    rh = rehome_fragments({t["anchor"]: collect_fragments(t, new_concepts)
                           for t in new_terms}, new_terms, new_nodes)
    if adj.get("subject_map"):
        rh = rehome_by_subject(rh, adj["subject_map"], new_nodes)
    new_homes = rh["homes"]
    old_homes = {_parse_key(k): v for k, v in
                 _load(old_dir / "relations" / "relations.structural.yaml")
                 ["rehome"]["homes"].items()}

    diff = diff_fragments(old_frags, new_frags)
    stale = stale_nodes(diff, old_homes, new_homes)
    rels = stale_relations(_load(old_dir / "relations" / "candidates.tierb.yaml")
                           ["candidates"], diff, new_frags)
    eq = equivalence_check(_bodies(old_frags, old_homes),
                           _bodies(new_frags, new_homes), stale)
    log = evolution_log(diff, old_homes, new_homes, (old_dir.name, new_dir.name))

    out = new_dir / "change" / "change-report.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    dump = {"meta": {"generator": "change_layer.py", "scope": scope,
                     "resources": resources, "sha_pair": log["sha_pair"]},
            "diff": {k: [f"{a}|{b}" for a, b in v] for k, v in diff.items()},
            "stale_nodes": stale,
            "relations": {k: v for k, v in rels.items()},
            "equivalence": eq, "evolution": log,
            "new_ambiguous_queue": len(res["ambiguous"])}
    out.write_text(yaml.safe_dump(dump, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    print(f"frags old={len({(f['concept'], f.get('field')) for f in old_frags})} "
          f"new={len({(f['concept'], f.get('field')) for f in new_frags})} | "
          f"added={len(diff['added'])} removed={len(diff['removed'])} "
          f"changed={len(diff['changed'])} unchanged={len(diff['unchanged'])} | "
          f"stale_nodes={len(stale)} | rel auto_ok={len(rels['auto_ok'])} "
          f"requeue={len(rels['requeue'])} unaffected={len(rels['unaffected'])} | "
          f"equal={eq['equal']} missed={len(eq['missed_stale'])} "
          f"false={len(eq['false_stale'])} | new_ambiguous={len(res['ambiguous'])}")


if __name__ == "__main__":
    import sys
    main(sys.argv)


def rebind_proposals(removed, added, threshold=0.5):
    """anchor 드리프트 재바인딩 제안 — 소멸/생성 조각의 내용 유사도 최적 매칭.
    제안이지 확정 아님(판정 큐). threshold 미달은 to=None으로 정직 보고."""
    from difflib import SequenceMatcher
    out = []
    for r in removed:
        best, score = None, 0.0
        for a in added:
            s = SequenceMatcher(None, _norm(r["text"]), _norm(a["text"])).ratio()
            if s > score:
                best, score = a["anchor"], s
        out.append({"from": r["anchor"], "to": best if score >= threshold else None,
                    "similarity": round(score, 3)})
    return out
