"""원장 2단 — 인용을 조각으로 해소하고, 두 축이 같은 항목에 다른 값을 말하는지 본다.

1단(`derivation.py`)은 사람이 한 짝을 구조로 옮긴다. 2단은 그 짝의 **근거를 나란히
놓는다** — 조항과 화면을 나란히 놓았더니 불일치가 저절로 드러난 것과 같은 메커니즘이다.
판정이 아니라 배치가 일을 한다.

★두 축의 근거가 서로 **다른 곳**에 있다(원본 매핑 문서가 스스로 그렇게 말한다):
    조항 인용 `[XXX-NN]` → spec 조항 (Tier A 스냅샷에 이미 있다)
    분책 인용 `NN권 §X-Y` · 화면 `S-NN` → 조사 문서 섹션
  그래서 인덱스가 둘이고, 조립 시점에 **축의 kind를 붙인다**. 범용 어댑터의
  `kind: "section"`을 고치면 다른 코퍼스까지 흔들린다 — "어느 축에서 왔나"는
  파싱 사실이 아니라 경계 선언이므로(registry `derivation.axes`) 여기가 제자리다.

★미해소 인용은 버리지 않고 표시한다. 조용히 버리면 "근거가 있는데 안 붙었다"를
  영영 못 본다.

Usage: python3 derivation_members.py <corpus> [out.yaml]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from crosscheck import crosscheck_concept
from parsers import parse_markdown_sections

_VOL_FILE = re.compile(r"^(\d{2})-")
_SEC_NO = re.compile(r"^([\d\-]+)\.?\s")
_SCREEN_HEAD = re.compile(r"\b(S-\d+[a-z]?)\b")


def index_sections(docs):
    """{파일명: 본문} → {인용키: 조각}. 분책 섹션(`NN권§X-Y`)과 화면(`S-NN`) 둘 다.

    ★`NN권`의 NN은 파일명 접두다 — 조사 규약이 "S-ID는 00권이 전역으로 한 번만
      채번한다"고 선언한 그 번호다. 유도가 아니라 문서 규약을 읽는 것이다."""
    idx = {}
    for name in sorted(docs):
        stem = Path(name).stem
        vm = _VOL_FILE.match(Path(name).name)
        for c in parse_markdown_sections(docs[name], doc_slug=stem)["concepts"]:
            head = (c.get("section") or "").strip()
            frag = {"text": c["content"], "file": name, "section": head}
            sm = _SEC_NO.match(head)
            if vm and sm:
                idx.setdefault(f"{vm.group(1)}권§{sm.group(1).rstrip('.')}", frag)
            for sid in _SCREEN_HEAD.findall(head):   # 화면은 제목에 ID가 있는 섹션
                idx.setdefault(sid, frag)
    return idx


def index_articles(concepts):
    """Tier A 개념 → {anchor: 조각}. 표를 본문에 이어 붙인다.

    ★표가 안 실리면 대조할 게 없다 — crosscheck는 표 행을 비교한다.
      조항 파서가 조항 밑 표를 `table`로 따로 보관하므로 여기서 합친다."""
    idx = {}
    for c in concepts or []:
        a = c.get("anchor")
        if not a or c.get("kind") != "article":
            continue
        body = "\n".join([str(c.get("content") or "")] + list(c.get("table") or []))
        idx.setdefault(a, {"text": body, "file": c.get("file"),
                           "section": c.get("section")})
    return idx


def attach(rows, axes, indexes):
    """원장 행에 근거 조각을 붙인다. `indexes`는 {열 이름: 인덱스}.

    미해소는 `미해소`에 남긴다 — 버리지 않는다."""
    out = []
    for r in rows:
        members, unresolved = [], []
        for ax in axes:
            col, idx = ax["column"], indexes.get(ax["column"]) or {}
            for cite in r.get(f"{col}_근거") or []:
                hit = idx.get(cite)
                if hit is None:
                    unresolved.append(cite)
                    continue
                members.append({"anchor": cite, "kind": ax["kind"],
                                "text": hit["text"], "file": hit.get("file")})
        row = dict(r)
        row["members"] = sorted(members, key=lambda m: (m["kind"], m["anchor"]))
        row["미해소"] = sorted(unresolved)
        out.append(row)
    return out


def conflicts(rows):
    """층간 값 불일치 후보. **기계는 판정하지 않는다** — 원문을 나란히 보여줄 뿐."""
    out = []
    for r in rows:
        if len({m["kind"] for m in r["members"]}) < 2:
            continue                       # 한 층뿐이면 대조할 게 없다
        frags = [{"key": f"{m['anchor']}|0", "text": m["text"]} for m in r["members"]]
        kinds = {m["anchor"]: m["kind"] for m in r["members"]}
        out += crosscheck_concept(r["항목"], frags, kinds)
    return out


def main():
    import yaml
    from collections import Counter
    import corpus as C
    import derivation as D

    name = sys.argv[1]
    reg = C.load_registry()
    rows, cfg = D.load(name, reg)
    src_root = (Path(__file__).parent / reg["corpora"][name]["source"]).resolve()
    snap = sorted(C.canon_dir(name).glob("tier-a/*.yaml"))
    concepts = yaml.safe_load(snap[-1].read_text(encoding="utf-8"))["concepts"] if snap else []

    indexes = {}
    for ax in cfg["axes"]:
        root = ax.get("evidence_root")
        if root:
            docs = {f.name: f.read_text(encoding="utf-8")
                    for f in sorted((src_root / root).glob("*.md"))
                    if f.name != "README.md"}
            indexes[ax["column"]] = index_sections(docs)
        else:
            indexes[ax["column"]] = index_articles(concepts)

    rows = attach(rows, cfg["axes"], indexes)
    cf = conflicts(rows)
    both = [r for r in rows if len({m["kind"] for m in r["members"]}) >= 2]
    unres = sorted({c for r in rows for c in r["미해소"]})
    print(f"원장 {len(rows)}행 · 조각 {sum(len(r['members']) for r in rows)}개")
    print(f"  두 층 다 붙은 행 : {len(both)}  ← 대조 가능")
    print(f"  층별 조각        : {dict(Counter(m['kind'] for r in rows for m in r['members']))}")
    print(f"  미해소 인용      : {len(unres)}  {unres[:8]}")
    print(f"  ★값 불일치 후보  : {len(cf)}")
    for c in cf:
        print(f"\n  ## {c['item']}  ·  {c['anchor']}")
        for layer in sorted(c["by_layer"]):
            for v in c["by_layer"][layer]:
                print(f"     [{layer}] {v[:92]}")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(
            yaml.safe_dump({"rows": rows, "conflicts": cf},
                           allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"\n→ {sys.argv[2]}")


if __name__ == "__main__":
    main()
