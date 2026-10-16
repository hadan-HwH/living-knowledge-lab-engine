"""관계 축 — 결정론 껍데기 (설계: docs/2-method/relation-layer-design.md).

원리: 관계=개념↔개념 의미(인용은 provenance), 조각의 집은 하나, 원자화 금지.
이 모듈은 의미 판단이 없는 부분만 담당한다:
  build_resource_concepts  term.resource 수렴 → concept 노드(≥2 term = promoted)
  structural_relations     value_of·belongs_to 전수 기계 생성
  rehome_fragments         공유 조각의 집 재배치(같은 리소스면 concept로, 넘으면 판정 큐)
  verify_relations         의미 관계 후보의 왕복 게이트(tier_b 규율)
  r1_neighbors / r2_impact / r3_home   사전 고정 질의 3종
의미 관계 후보 생성(triggers·affects·자유 명명)은 Tier B(LLM) 몫.

Usage:
  python3 relation_layer.py pilot <concepts.yaml> <terms.yaml> <probe_dir> <outdir> \
      [scope] [adjudication.yaml]
  python3 relation_layer.py verify <candidates.yaml> <fragment-pool.yaml> <out.yaml> \
      [r1_nodes_csv] [r2_nodes_csv]
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

SEMANTIC_EXCLUDE = ("value_of", "belongs_to")   # 구조 관계 — R2 파급 전파에서 제외
# 어휘 동결 (소유자 판정 2026-07-31): 동결 밖 어휘는 vocab_status=candidate로 보존.
SEMANTIC_VOCAB = ("triggers", "affects", "transitions_to")
# R2 파급 전파 어휘 (같은 판정): transitions_to 제외 — 전이 상대는 파급이 아니라 상태 기계 이웃.
R2_PROPAGATE = ("triggers", "affects")


def designate_concepts(designations):
    """지정 concept 노드 — 기본은 소유자 지정(설계 §2 기준 3), basis/criteria를
    명시하면 Tier B 승격(기준 2: 본체 신호)도 같은 경로로 들어온다(원장 구분 유지)."""
    return [{"anchor": f'concept:{d["name"]}', "kind": "concept", "name": d["name"],
             "basis": d.get("basis", "owner"),
             "criteria": d.get("criteria", "owner-designation"),
             "status": "promoted"}
            for d in designations]


def rehome_by_subject(rehome_result, subject_map, concept_nodes):
    """조항 주어 기준 재배치 (소유자 판정 2026-07-31 승인) — 조항이 서술하는 대상의
    concept이 그 조항 조각들의 집. subject_map: {조항 concept id: concept anchor}.
    지정 concept 노드가 실재할 때만 이동(없으면 원래 집 유지).
    ambiguous 큐의 키도 판정 적용 대상이면 회수한다(축 결합 실측 교훈 — cross-resource
    공유가 된 조각도 '조항 주어' 판정이 이미 집을 정해준 상태)."""
    existing = {n["anchor"] for n in concept_nodes}
    homes, moved = dict(rehome_result["homes"]), []
    ambiguous = list(rehome_result.get("ambiguous", []))
    for key in sorted(homes, key=str):
        target = subject_map.get(key[0])
        if target and target in existing and homes[key] != target:
            homes[key] = target
            moved.append(key)
    for key in sorted(ambiguous, key=str):
        target = subject_map.get(key[0])
        if target and target in existing:
            homes[key] = target
            ambiguous.remove(key)
            moved.append(key)
    return {**rehome_result, "homes": homes, "ambiguous": ambiguous, "moved": moved}


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def build_resource_concepts(terms):
    """term.resource 집계 → concept 노드. 복수 term 수렴 = promoted(기계), 1개 = candidate."""
    by_res = {}
    for t in terms:
        by_res.setdefault(t["resource"], []).append(t["anchor"])
    nodes = []
    for res, anchors in sorted(by_res.items()):
        nodes.append({"anchor": f"concept:{res}", "kind": "concept", "name": res,
                      "basis": "machine", "criteria": "term-convergence",
                      "status": "promoted" if len(anchors) >= 2 else "candidate",
                      "terms": sorted(anchors)})
    return nodes


def structural_relations(terms, concept_nodes):
    """구조 관계 전수 기계 생성 — value_of(상태값→enum 필드)·belongs_to(term→리소스 concept)."""
    existing = {n["anchor"] for n in concept_nodes}
    rels = []
    for t in terms:
        for m in t["members"]:
            if m.get("kind") == "state_enum":
                rels.append({"from": t["anchor"], "rel": "value_of",
                             "to": m["concept"], "basis": "machine"})
                break
        target = f'concept:{t["resource"]}'
        if target in existing:
            rels.append({"from": t["anchor"], "rel": "belongs_to",
                         "to": target, "basis": "machine"})
    return rels


def rehome_fragments(frags_by_term, terms, concept_nodes):
    """공유 조각의 집 재배치. (concept, field) 키가 복수 term에 있으면:
    전원이 같은 리소스 → 그 리소스 concept 노드가 집 / 리소스를 넘으면 ambiguous 큐.
    단독 조각은 자기 term이 집. 중복 소유 수(before/after)를 실측한다."""
    res_of = {t["anchor"]: t["resource"] for t in terms}
    existing = {n["anchor"] for n in concept_nodes}
    owners = {}
    for anchor, frags in frags_by_term.items():
        for f in frags:
            owners.setdefault((f["concept"], f.get("field")), set()).add(anchor)
    homes, ambiguous = {}, []
    dup_before = sum(1 for o in owners.values() if len(o) > 1)
    for key, terms_sharing in owners.items():
        if len(terms_sharing) == 1:
            homes[key] = next(iter(terms_sharing))
            continue
        resources = {res_of[a] for a in terms_sharing}
        target = f"concept:{next(iter(resources))}"
        if len(resources) == 1 and target in existing:
            homes[key] = target
        else:
            ambiguous.append(key)
    dup_after = sum(1 for key, o in owners.items()
                    if len(o) > 1 and key not in homes and key not in ambiguous)
    return {"homes": homes, "ambiguous": ambiguous,
            "duplication": {"before": dup_before, "after": dup_after}}


def verify_relations(candidates, fragment_pool):
    """의미 관계 왕복 게이트 — evidence 인용이 해당 조각 원문에 실재해야 ok.
    실패는 고치지 않고 기록만(실패율=1급 지표). 어휘 집계 포함."""
    by_key = {}
    for f in fragment_pool:
        by_key.setdefault((f["concept"], f.get("field")), _norm(f["text"]))
    out, totals, vocab = [], Counter(), Counter()
    for i, c in enumerate(candidates):
        ev = c.get("evidence") or {}
        src = by_key.get((ev.get("concept"), ev.get("field")))
        if src is None:
            verdict = "unknown_fragment"
        elif not ev.get("quote") or _norm(ev["quote"]) not in src:
            verdict = "quote_mismatch"
        else:
            verdict = "ok"
        totals[verdict] += 1
        vocab[c.get("rel") or "unknown"] += 1
        out.append({"i": i, "from": c.get("from"), "rel": c.get("rel"),
                    "to": c.get("to"), "verdict": verdict,
                    "vocab_status": "frozen" if c.get("rel") in SEMANTIC_VOCAB
                    else "candidate"})
    n = len(candidates)
    return {"relations": out,
            "totals": {**{k: totals[k] for k in ("ok", "quote_mismatch", "unknown_fragment")},
                       "n": n, "pass_rate": (totals["ok"] / n) if n else None},
            "vocab": dict(vocab)}


def r1_neighbors(node, edges):
    """R1 탐색 — 1-hop 이웃(양방향, 관계 종류 무관)."""
    out = {e["to"] for e in edges if e["from"] == node}
    out |= {e["from"] for e in edges if e["to"] == node}
    return sorted(out)


def r2_impact(node, edges, propagate=R2_PROPAGATE):
    """R2 파급 — 파급 어휘(triggers·affects)만 따라 전이적 도달.
    구조 관계·transitions_to는 파급이 아님(어휘 동결 판정)."""
    sem = [(e["from"], e["to"]) for e in edges if e["rel"] in propagate]
    seen, queue = [], [node]
    while queue:
        cur = queue.pop(0)
        for a, b in sem:
            if a == cur and b not in seen and b != node:
                seen.append(b)
                queue.append(b)
    return seen


def r3_home(fragment_key, homes):
    """R3 귀속 — 이 조각의 집은 어느 노드인가."""
    return homes.get(fragment_key)


def _load(path):
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _dump(path, data):
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def main(argv):
    from body_probe import collect_fragments
    cmd = argv[1]
    if cmd == "pilot":
        concepts = _load(argv[2])["concepts"]
        all_terms = _load(argv[3])["terms"]
        probe_dir, outdir = Path(argv[4]), Path(argv[5])
        prefixes = tuple((argv[6] if len(argv) > 6 else "Item,Promo Code").split(","))
        adj = _load(argv[7]) if len(argv) > 7 else {}
        terms = [t for t in all_terms if t["resource"] in prefixes]
        nodes = (build_resource_concepts(terms)
                 + designate_concepts(adj.get("designated_concepts", [])))
        rels = structural_relations(terms, nodes)
        frags_by_term = {t["anchor"]: collect_fragments(t, concepts) for t in terms}
        rh = rehome_fragments(frags_by_term, terms, nodes)
        if adj.get("subject_map"):
            rh = rehome_by_subject(rh, adj["subject_map"], nodes)
        _dump(outdir / "relations.structural.yaml",
              {"concept_nodes": nodes, "relations": rels,
               "rehome": {"homes": {f"{k[0]}|{k[1]}": v for k, v in rh["homes"].items()},
                          "ambiguous": [f"{k[0]}|{k[1]}" for k in rh["ambiguous"]],
                          "moved": [f"{k[0]}|{k[1]}" for k in rh.get("moved", [])],
                          "duplication": rh["duplication"]}})
        print(f"terms={len(terms)} concepts={len(nodes)} structural={len(rels)} "
              f"dup_before={rh['duplication']['before']} "
              f"dup_after={rh['duplication']['after']} ambiguous={len(rh['ambiguous'])} "
              f"moved={len(rh.get('moved', []))}")
    elif cmd == "verify":
        cands = _load(argv[2])["candidates"]
        pool = _load(argv[3])["fragments"]
        rep = verify_relations(cands, pool)
        edges = [r for r in rep["relations"] if r["verdict"] == "ok"]
        queries = {}
        for node in (argv[5].split(",") if len(argv) > 5 else []):
            queries[f"r1:{node}"] = r1_neighbors(node, edges)
        for node in (argv[6].split(",") if len(argv) > 6 else []):
            queries[f"r2:{node}"] = r2_impact(node, edges)
        _dump(Path(argv[4]), {"verify": rep, "queries": queries})
        t = rep["totals"]
        print(f"n={t['n']} ok={t['ok']} pass_rate={t['pass_rate']} "
              f"vocab={rep['vocab']}")
    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    import sys
    main(sys.argv)
