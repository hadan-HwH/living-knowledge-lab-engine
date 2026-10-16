"""개념 본체 비교 탐침 — 결정론 껍데기 (설계: docs/2-method/concept-body-design.md §3-③).

같은 조각 입력에서 A(기계 조립)/B(LLM 재서술)/C(2층)를 만들고 사전 등록 지표로 잰다.
이 모듈은 의미 판단이 없는 부분만 담당한다:
  collect_fragments  term members → 원문 조각(provenance 보존, 미해소는 지어내지 않고 표기)
  assemble_a         A안 — 출처 field 유형별 구조 그룹핑(의미 판단 없음, Q1-a 미결 유지)
  verify_body        B/C 산출물의 문장 단위 왕복 게이트(tier_b 규율: 인용 실재 substring)
  coverage           완전성 — 조각 인용 커버리지
  impact_of          변경 내성 — 조각 fid → 영향 문장 국소화
B/C 생성(LLM)은 서브에이전트 몫이며 산출 계약은 sentences[{text, cites[{fid, quote}]}].

Usage:
  python3 body_probe.py prep <concepts.yaml> <terms.yaml> <outdir> <term_anchor> [...]
  python3 body_probe.py verify <outdir>/<slug> <body_file.yaml>
"""
from __future__ import annotations

import re
from pathlib import Path

GROUP_OF = (("spec", lambda f: f.get("field") is None),
            ("본문", lambda f: f.get("field") == "content"),
            ("표", lambda f: (f.get("field") or "").startswith("table[")),
            ("부연", lambda f: (f.get("field") or "").startswith("fields.")))
GROUP_ORDER = [g for g, _ in GROUP_OF]


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def _group(frag):
    for name, pred in GROUP_OF:
        if pred(frag):
            return name
    return "부연"


def _texts_of(article):
    yield "content", article.get("content") or ""
    for k, v in (article.get("fields") or {}).items():
        yield f"fields.{k}", v or ""
    for idx, row in enumerate(article.get("table") or []):
        yield f"table[{idx}]", row or ""


def collect_fragments(term, concepts, return_unresolved=False):
    """term 멤버를 원문 조각으로 해소한다. (concept, field) 단위 dedup.
    원문에서 해소 안 되는 멤버는 조각으로 만들지 않는다(지어내지 않기) — 표기만."""
    by_anchor = {c["anchor"]: c for c in concepts}
    frags, unresolved, seen = [], [], set()
    for m in term["members"]:
        key = (m["concept"], m.get("field"))
        if key in seen:
            continue
        seen.add(key)
        text = None
        c = by_anchor.get(m["concept"])
        if m["kind"] in ("state_enum", "field"):
            text = m.get("note") or (c or {}).get("content") or \
                   ("values: " + ", ".join(c.get("values") or []) if c and c.get("values") else None)
        elif c is not None:
            texts = dict(_texts_of(c))
            text = texts.get(m.get("field"))
        if not text:
            unresolved.append({"concept": m["concept"], "field": m.get("field")})
            continue
        frags.append({"concept": m["concept"], "field": m.get("field"),
                      "kind": m["kind"], "basis": m.get("basis"), "text": text})
    frags.sort(key=lambda f: (GROUP_ORDER.index(_group(f)), f["concept"], f.get("field") or ""))
    for i, f in enumerate(frags):
        f["fid"] = f"F{i+1:02d}"
        f["group"] = _group(f)
    return (frags, unresolved) if return_unresolved else frags


def assemble_a(term, fragments):
    """A안 — 조각을 출처 field 유형별로 묶어 원문 그대로 배치. 의미 판단 0."""
    sections = []
    for name in GROUP_ORDER:
        items = [{"fid": f["fid"], "concept": f["concept"], "field": f.get("field"),
                  "text": f["text"]} for f in fragments if f["group"] == name]
        if items:
            sections.append({"group": name, "items": items})
    return {"term": term["anchor"], "approach": "A", "sections": sections}


def verify_body(sentences, fragments):
    """문장 단위 왕복 게이트 — 각 문장의 모든 인용이 해당 조각 원문에 실재해야 ok.
    인용 없는 문장·모르는 fid·불일치 인용 = 실패. 실패는 고치지 않고 기록만."""
    by_fid = {f["fid"]: _norm(f["text"]) for f in fragments}
    out, totals = [], {"ok": 0, "quote_mismatch": 0, "unknown_fid": 0, "uncited": 0}
    for i, s in enumerate(sentences):
        verdict = "ok"
        if not s.get("cites"):
            verdict = "uncited"
        for c in s.get("cites", []):
            src = by_fid.get(c.get("fid"))
            if src is None:
                verdict = "unknown_fid"
                break
            if _norm(c.get("quote", "")) not in src:
                verdict = "quote_mismatch"
                break
        totals[verdict] += 1
        out.append({"i": i, "verdict": verdict})
    n = len(sentences)
    return {"sentences": out,
            "totals": {**totals, "n": n, "pass_rate": (totals["ok"] / n) if n else None},
            "hallucination_gate_failed": (totals["ok"] < n)}


def coverage(sentences, fragments):
    """완전성 — 어느 조각이 본문에 한 번이라도 인용됐나."""
    cited = {c["fid"] for s in sentences for c in s.get("cites", [])}
    fids = [f["fid"] for f in fragments]
    return {"cited": len([f for f in fids if f in cited]), "total": len(fids),
            "uncited": [f for f in fids if f not in cited]}


def impact_of(fid, sentences):
    """변경 내성 — 조각 하나가 바뀌면 어느 문장이 낡나(인덱스)."""
    return [i for i, s in enumerate(sentences)
            if any(c.get("fid") == fid for c in s.get("cites", []))]


def _load(path):
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _dump(path, data):
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def _slug(anchor):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", anchor.split(":", 1)[-1])


def main(argv):
    cmd = argv[1]
    if cmd == "prep":
        concepts = _load(argv[2])["concepts"]
        terms = {t["anchor"]: t for t in _load(argv[3])["terms"]}
        outdir = Path(argv[4])
        for anchor in argv[5:]:
            term = terms[anchor]
            frags, unresolved = collect_fragments(term, concepts, return_unresolved=True)
            d = outdir / _slug(anchor)
            _dump(d / "fragments.yaml", {"term": anchor, "fragments": frags,
                                         "unresolved_members": unresolved})
            _dump(d / "body_a.yaml", assemble_a(term, frags))
            print(f"{anchor}: fragments={len(frags)} unresolved={len(unresolved)}")
    elif cmd == "verify":
        d = Path(argv[2])
        frags = _load(d / "fragments.yaml")["fragments"]
        body = _load(argv[3])
        rep = verify_body(body["sentences"], frags)
        rep["coverage"] = coverage(body["sentences"], frags)
        _dump(Path(argv[3]).with_suffix(".verify.yaml"), rep)
        print(f"{d.name}/{Path(argv[3]).name}: pass={rep['totals']['pass_rate']} "
              f"cov={rep['coverage']['cited']}/{rep['coverage']['total']} "
              f"gate_failed={rep['hallucination_gate_failed']}")
    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    import sys
    main(sys.argv)
