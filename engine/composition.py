"""구성 평면 — 파생 **제품 하나**를 lab이 실제로 "들고 있는" 형태로 접는다.

★원칙은 파생 평면(derivation.py)과 같다:
  - 엔진은 제품 이름을 모른다 — registry `composition` 선언이 소스·화면 접두·결정
    namespace를 준다. 새 파생 제품은 블록 하나, 코드 변경 0.
  - 결정론·LLM 0·재생성 가능(기계 생성 — 손 편집 금지).
  - 판정하지 않는다 — 사람이 쓴 초안·결정을 접고, 인용은 원문 그대로 싣는다.

Usage: python3 composition.py <corpus> [out.yaml]"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from parsers import parse_markdown_sections, parse_corpdoc_decisions

_HEAD = re.compile(r"^(#{2,6})\s+(.+)$", re.M)


def _screen_pat(prefix):
    """정의 헤딩만 — 제목이 ID로 **시작**해야 한다. 중간에 나오는 건 참조다
    (`진열 매트릭스 (NEO-S-62 종속)`이 화면으로 오인되면 인벤토리와 정의 수가
    어긋난다 — 실측)."""
    return re.compile(rf"^({re.escape(prefix)}\d+[a-z]?)\b")


def compose(cfg, source_texts, decision_texts=(), derivation=None):
    """선언(cfg) + 소스 원문 → 구성 평면 dict. 결정론 — 같은 입력이면 같은 출력."""
    sections, screens, flags = [], [], []
    spat = _screen_pat(cfg["screen_id_prefix"])

    for src in cfg["sources"]:
        path, role = src["path"], src["role"]
        text = source_texts.get(path)
        if text is None:
            flags.append(f"[{path}] 소스 없음 — 구성에서 빠졌다(공백 아님, 부재)")
            continue
        for c in parse_markdown_sections(text, scope=cfg["product"],
                                         doc_slug=Path(path).stem)["concepts"]:
            m = spat.search(c.get("section") or "")
            if m:
                screens.append({"id": m.group(1), "section": c["section"],
                                "content": c["content"], "role": role})
            else:
                sections.append({"anchor": c["anchor"], "section": c.get("section"),
                                 "content": c["content"], "role": role})

    ns = tuple(f"{n}-D-" for n in cfg.get("decision_ns") or ())
    decisions, open_items = [], []
    for text in decision_texts:
        for d in parse_corpdoc_decisions(text)["decisions"]:
            if d["decision_id"].startswith(ns):
                decisions.append({k: d[k] for k in
                                  ("decision_id", "date", "content", "status")})
        open_items += _open_items(text, cfg.get("open_items_marker", "미확정"))

    rows = (derivation or {}).get("rows") or []
    # ★미결 축 — {TBD}·❓·검토 목록이 안 세지면 "완성처럼 보이는" 평면이 된다
    #.
    body = "\n".join(s["content"] for s in sections + screens)
    have = {d["decision_id"] for d in decisions}
    ns_pat = re.compile(r"\b(?:" + "|".join(map(re.escape, cfg.get("decision_ns") or []))
                        + r")-D-\d+\b") if cfg.get("decision_ns") else None
    unresolved = sorted({m for m in (ns_pat.findall(body) if ns_pat else [])
                         if m not in have})
    out = {
        "meta": {
            "product": cfg["product"],
            "generator": "composition.py (기계 생성 — 손 편집 금지, 재생성 가능)",
            "sections": len(sections), "screens": len(screens),
            "decisions": len(decisions), "derivation_rows": len(rows),
            "chars": sum(len(s["content"]) for s in sections)
                     + sum(len(s["content"]) for s in screens),
            "tbd": body.count("{TBD}"), "unverified": body.count("❓"),
            "open_items": sum(1 for o in open_items if o["status"] == "open"),
        },
        "flags": flags,
        "sections": sections,
        "screens": screens,
        "decisions": decisions,
        # 인용됐는데 미보유(결번 포함) — 무성이면 결번인지 누락인지 구분이 안 된다.
        "미해소_결정인용": unresolved,
        "open_items": open_items,
        "derivation": {"rows": len(rows),
                       "관계": _count(rows, "관계"), "상태": _count(rows, "상태")},
    }
    return out


_OPEN_ITEM = re.compile(r"^- (~~)?\*\*(.+?)\*\*[:：]?\s*(.*)$")


def _open_items(text, marker):
    """결정 로그의 검토 목록(`- **이름**: 내용` 불릿) — 제품 지식의 미결 절반.

    취소선(~~)은 원문이 스스로 닫은 항목이다 — 버리지 않고 closed로 옮긴다
    (판정이 아니라 전달)."""
    items, keep = [], False
    for raw in text.splitlines():
        if raw.startswith("#"):
            keep = marker in raw
            continue
        if not keep:
            continue
        m = _OPEN_ITEM.match(raw.strip())
        if m:
            struck, name, body = m.groups()
            name = re.sub(r"[~*]", "", name).split(":")[0].strip()
            items.append({"name": name, "status": "closed" if struck else "open",
                          "content": body.strip()})
    return items


def _count(rows, key):
    c = {}
    for r in rows:
        k = str(r.get(key) or "(미정)")
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))


def main():
    import yaml
    import corpus as CO
    from ingest import discover

    name = sys.argv[1]
    reg = CO.load_registry()
    entry = reg["corpora"][name]
    cfg = entry.get("composition")
    if not cfg:
        raise SystemExit(f"{name}: registry에 composition 선언이 없다")
    root = (Path(__file__).parent / entry["source"]).resolve()

    texts = {}
    for src in cfg["sources"]:
        p = root / src["path"]
        if p.exists():
            texts[src["path"]] = p.read_text(encoding="utf-8")

    # 결정 로그는 코퍼스 발견 규칙 그대로 — 경로를 또 선언하지 않는다(무중복).
    dec_texts = [(root / d["file"]).read_text(encoding="utf-8")
                 for d in discover(name, root, reg)["found"]]

    deriv_p = CO.canon_dir(name) / "derivation.yaml"
    deriv = yaml.safe_load(deriv_p.read_text(encoding="utf-8")) if deriv_p.exists() else None

    out = compose(cfg, texts, decision_texts=dec_texts, derivation=deriv)
    m = out["meta"]
    print(f"구성 {m['product']}: 섹션 {m['sections']} · 화면 {m['screens']} · "
          f"결정 {m['decisions']} · 파생 {m['derivation_rows']}행 · 본문 {m['chars']:,}자")
    for f in out["flags"]:
        print("  ⚠", f)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(
            yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"→ {sys.argv[2]}")


if __name__ == "__main__":
    main()
