"""의미 층(용어 통합) 파일럿 — 결정론 부분.

설계: docs/4-experiments/term-layer-pilot-inv.md.
어휘는 spec 계열(state_enum 값·field 필드명)이 이미 anchor로 가진 표면형의
유한 집합만 쓴다(원자화 금지 — 조항 자유 텍스트에서 임의 용어를 만들지 않는다).
동일성 판단 중 기계 신호로 안 풀리는 것(복수 리소스 표면형의 조항 등장)만
LLM 판정 → adjudication으로 넘긴다(제안이지 확정이 아님).

Usage:
  python3 term_layer.py build <concepts.yaml> <outdir> [scope]
  python3 term_layer.py finalize <outdir> <concepts.yaml> [judgments.yaml] [scope]
"""
from __future__ import annotations

import re
from pathlib import Path

SOURCE_KINDS = ("state_enum", "field")   # 어휘 출처 — 화면·article 제외 (설계 §1·§3)


def _resource(anchor):
    return anchor.split(".")[0] if "." in anchor else anchor


def build_vocab(concepts):
    """spec 계열 개념에서 (surface, resource) 어휘를 만든다. dedup."""
    vocab, seen = [], set()
    for c in concepts:
        kind = c.get("kind")
        if kind not in SOURCE_KINDS:
            continue
        anchor = c["anchor"]
        if kind == "state_enum":
            surfaces = list(c.get("values") or [])
            notes = c.get("value_notes") or {}
        else:  # field — anchor "Item.ItemCode" 의 필드명
            surfaces = [anchor.split(".", 1)[1]] if "." in anchor else []
            notes = {}
        for s in surfaces:
            key = (s, _resource(anchor))
            if s and key not in seen:
                seen.add(key)
                entry = {"surface": s, "resource": _resource(anchor),
                         "source_anchor": anchor, "source_kind": kind}
                if notes.get(s):
                    entry["note"] = notes[s]   # 자기 값의 행 note만 (round 2 ①)
                vocab.append(entry)
    return vocab


def _texts_of(article):
    yield "content", article.get("content") or ""
    for k, v in (article.get("fields") or {}).items():
        yield f"fields.{k}", v or ""
    for idx, row in enumerate(article.get("table") or []):   # round 2 ② — 표 행 단위
        yield f"table[{idx}]", row or ""


def find_occurrences(vocab, concepts, kinds=("article",)):
    """대상 kind 개념의 content·fields에서 어휘 표면형의 전체 단어 등장을 찾는다.
    kinds는 코퍼스별 선언 가능(범용) — 기본값은 기존 동작(article)."""
    surfaces = sorted({v["surface"] for v in vocab}, key=len, reverse=True)
    pats = {s: re.compile(r"(?<![A-Za-z])" + re.escape(s) + r"(?![A-Za-z])") for s in surfaces}
    occ = []
    for c in concepts:
        if c.get("kind") not in kinds:
            continue
        for field, text in _texts_of(c):
            for s in surfaces:
                if pats[s].search(text):
                    occ.append({"surface": s, "concept": c["anchor"],
                                "field": field, "text": text})
    return occ


def make_terms(vocab, occurrences, judgments=None):
    """(resource, surface)별 term 노드 + 2단 지위. 모호 등장은 판정 전까지 큐."""
    by_surface = {}
    for v in vocab:
        by_surface.setdefault(v["surface"], []).append(v)
    judged = {(j["surface"], j["concept"], j["field"]): j for j in (judgments or [])}

    terms = {}
    for v in vocab:
        a = f'term:{v["resource"]}.{v["surface"]}'
        t = terms.setdefault(a, {"anchor": a, "kind": "term", "surface": v["surface"],
                                 "resource": v["resource"], "members": [], "status": "promoted",
                                 "basis": "machine"})
        t["members"].append({"concept": v["source_anchor"], "kind": v["source_kind"],
                             "basis": "machine",
                             **({"note": v["note"]} if v.get("note") else {})})

    ambiguous = []
    for o in occurrences:
        entries = by_surface[o["surface"]]
        resources = sorted({e["resource"] for e in entries})
        j = judged.get((o["surface"], o["concept"], o["field"]))
        if len(resources) == 1:
            res_name, basis = resources[0], "machine"
        elif j:
            res_name, basis = j["resource"], "llm"
        else:
            ambiguous.append({"surface": o["surface"], "concept": o["concept"],
                              "field": o["field"], "text": o["text"],
                              "resource_options": resources})
            continue
        t = terms[f'term:{res_name}.{o["surface"]}']
        t["members"].append({"concept": o["concept"], "kind": "article",
                             "field": o["field"], "basis": basis,
                             **({"quote": j["quote"]} if j else {})})
        if basis == "llm":
            t["status"], t["basis"] = "candidate", "llm"
    return {"terms": sorted(terms.values(), key=lambda t: t["anchor"]),
            "ambiguous": ambiguous}


def bridge(term, concepts, events, valid_at, known_at):
    """term 멤버 조항의 refs.decisions → 그 D-N을 언급하는 이벤트의 target →
    현행 권위(queries.current_authority)와 전이 이력. N1′ 검증용 리포트."""
    from queries import current_authority
    by_anchor = {c["anchor"]: c for c in concepts}
    decisions = sorted({d for m in term["members"]
                        for d in (by_anchor.get(m["concept"], {}).get("refs", {}) or {}).get("decisions", [])})
    def mentions(e):
        from decision_alias import variants
        blob = " ".join(list(e.get("source") or []) + [e.get("title") or ""])
        # epoch 경계: 신 스킴 참조(INV-D-7318)도 구 스킴 원장(D-7318 언급 gold)과 매칭
        forms = {f for d in decisions for f in variants(d, None, {})}
        return any(re.search(r"\b" + re.escape(f) + r"\b", blob) for f in forms)
    targets = sorted({e["target"] for e in events if mentions(e)})
    currency = {}
    for tgt in targets:
        got = current_authority(events, tgt, valid_at, known_at, None)
        trans = [(e["event_id"], e["type"], e.get("actor"))
                 for e in sorted((e for e in events if e["target"] == tgt),
                                 key=lambda e: e["valid_at"])
                 if e["type"] in ("adopt", "supersede", "revoke", "re_adopt")]
        cur_opt = got.get("current_option")
        currency[tgt] = {"current_option": cur_opt,
                         "surface_match": bool(cur_opt) and term["surface"].lower() in cur_opt.lower(),
                         "transitions": trans,
                         "all_transitions_are_decision_acts": all(a for _, _, a in trans)}
    return {"term": term["anchor"], "decisions": decisions, "targets": targets,
            "currency": currency}


def _load_concepts(path):
    import yaml
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data["concepts"], data.get("meta", {})


def _dump(path, data):
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def main(argv):
    import yaml
    cmd = argv[1]
    if cmd == "build":
        concepts, meta = _load_concepts(argv[2])
        outdir = Path(argv[3])
        scope_prefix = argv[4] if len(argv) > 4 else "prime-commerce/summit/inv"
        pool = [c for c in concepts if c.get("scope") == scope_prefix]
        vocab = build_vocab(pool)
        occ = find_occurrences(vocab, pool)
        res = make_terms(vocab, occ)
        prov = {"snapshot_sha": meta.get("source_sha"), "generator": "term_layer.py",
                "scope": scope_prefix,
                "vocab": len(vocab), "occurrences": len(occ)}
        _dump(outdir / "terms.draft.yaml", {"meta": prov, "terms": res["terms"]})
        _dump(outdir / "ambiguous.yaml", {"meta": prov, "queue": res["ambiguous"]})
        promoted = sum(1 for t in res["terms"] if t["status"] == "promoted")
        print(f"vocab={len(vocab)} occ={len(occ)} terms={len(res['terms'])} "
              f"promoted={promoted} ambiguous={len(res['ambiguous'])}")
    elif cmd == "finalize":
        outdir = Path(argv[2])
        concepts, meta = _load_concepts(argv[3])
        scope_prefix = argv[5] if len(argv) > 5 else "prime-commerce/summit/inv"
        pool = [c for c in concepts if c.get("scope") == scope_prefix]
        judgments = []
        if len(argv) > 4:
            judgments = yaml.safe_load(Path(argv[4]).read_text(encoding="utf-8"))["judgments"]
        judgments = [j for j in judgments if j.get("resource") and j["resource"] != "?"]
        vocab = build_vocab(pool)
        occ = find_occurrences(vocab, pool)
        res = make_terms(vocab, occ, judgments=judgments)
        draft_meta = yaml.safe_load((outdir / "terms.draft.yaml").read_text(encoding="utf-8"))["meta"]
        draft_meta["judgments"] = len(judgments)
        _dump(outdir / "terms.yaml", {"meta": draft_meta, "terms": res["terms"],
                                      "unresolved": res["ambiguous"]})
        print(f"terms={len(res['terms'])} unresolved={len(res['ambiguous'])}")
    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    import sys
    main(sys.argv)
