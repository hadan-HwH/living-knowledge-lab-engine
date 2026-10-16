"""파생 평면 — 제품 하나가 **다른 둘에서 유도**될 때의 원장.

기존 코퍼스는 전부 `문서 → 개념 → 정본`인데 여기선 지식의 원자가 **짝**이다 —
(가진 쪽 근거, 베낄 쪽 근거, 관계, 결정) 하나가 한 행.

★왜 상태를 사람이 안 매기나: **관계 종류가 곧 완결 조건**이다.
  adopts는 근거 양쪽이면 끝나지만 hides는 고정값(=결정)이 있어야 끝난다.
  손으로 매기면 다음 회차에 낡는다.

★엔진은 제품 이름을 모른다. 어느 열이 어느 축인지는 registry `derivation.axes`가
  선언한다 — 인용 형식(article·volume·screen·canon·decision)만이 코드의 어휘다.

Usage: python3 derivation.py <corpus> [out.yaml]"""
from __future__ import annotations

import re
import sys

#: 통 마커 → 관계. 섹션 제목이 마커를 갖고 있어 추측이 없다(분류·메타 절은 마커가 없다).
_BUCKETS = ((("①-B",), "remaps"), (("①",), "adopts"), (("②",), None),
            (("③",), "builds"), (("④",), "excludes"))
_BUCKET2 = "②"

_SEP = re.compile(r"^\|[\s:|\-–—]+\|$")
_HEADING = re.compile(r"^(#{2,6})\s+(.+)$")
_ID_CELL = re.compile(r"^(?:#|[①②③④]?-?\d+)$")
_EMPTY = {"", "-", "—", "–", "없음", "n/a"}

#: 인용 **형식**의 어휘 — 제품 이름이 아니다. 축이 어느 형식을 쓰는지는 registry가 말한다.
CITES = {
    "article": re.compile(r"\[([A-Z][A-Z0-9]*-\d+)\]"),          # [XXX-NN] 조항
    "volume": re.compile(r"(\d{2})권\s*§([\d\-]+)"),              # NN권 §X-Y 분책 섹션
    "screen": re.compile(r"\b(S-\d+[a-z]?)\b"),                   # S-NN 화면
    "canon": re.compile(r"`([a-z][a-z\-]*#sc-[a-z0-9\-]+)`"),     # lab 정본 개념
    "decision": re.compile(r"\b([A-Z][A-Z0-9]*-D-\d+)\b"),
}

_HEADER_WORDS = {"항목", "구분", "필드", "이름", "통", "#", "결정할 것"}
_FM_PLATFORM = re.compile(r'^platform:\s*"?([A-Za-z0-9_\-]+)"?', re.M)


def _clean(s):
    return re.sub(r"[*`]", "", str(s or "")).strip()


def _find(kind, text):
    m = CITES[kind].findall(text)
    return [f"{a}권§{b}" for a, b in m] if kind == "volume" else list(m)


def _tables(md_text):
    """(섹션 제목, 머리글 셀, [행 셀]) — 머리글을 **버리지 않는다**.

    열 이름이 표마다 다르다(`… 근거`·`… 축`·`출처`). 위치를 가정하면 조용히
    어긋나므로 머리글에서 열을 찾는다."""
    section, head, rows, out = None, None, [], []

    def flush():
        if head and rows:
            out.append((section, head, list(rows)))

    lines = md_text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip()
        m = _HEADING.match(raw)
        if m:
            flush()
            head, rows = None, []
            section = m.group(2).strip()
            continue
        if _SEP.match(line):
            prev = lines[i - 1].strip() if i else ""
            if prev.startswith("|"):
                flush()
                head, rows = [_clean(c) for c in prev.strip("|").split("|")], []
            continue
        if line.startswith("|") and head is not None:
            rows.append([c.strip() for c in line.strip("|").split("|")])
            continue
        if head is not None and not line:
            flush()
            head, rows = None, []
    flush()
    return out


def _col(head, *words):
    for i, h in enumerate(head):
        if any(w.lower() in h.lower() for w in words):
            return i
    return None


def _bucket(section):
    for markers, rel in _BUCKETS:
        if any(m in (section or "") for m in markers):
            return markers[0], rel
    return None, None


def parse_ledger(md_text, axes, decision_ns=None):
    """매핑 문서 → 원장 행. `axes`는 registry 선언 [{column, kind, cite:[...]}].

    행 키는 축 이름이 아니라 **열 이름**을 쓴다(`<column>_셀`·`<column>_근거`) —
    엔진이 제품을 모르면서도 축을 구분할 수 있는 유일한 방법이다."""
    out = []
    # ★자기 결정층 namespace — 지어내지 않고 **선언을 읽는다**(registry, 없으면
    #   문서 프론트매터). 남의 결정을 인용하는 건 근거지 이 행을 끝내는 결정이 아니다.
    ns = decision_ns
    if ns is None:
        pf = _FM_PLATFORM.search(md_text)
        ns = pf.group(1).upper() if pf else None
    own = re.compile(rf"{ns}-D-\d+") if ns else None

    for section, head, rows in _tables(md_text):
        marker, rel = _bucket(section)
        if marker is None:
            continue                     # 분류 기준·결정 대기·GAP 절 = 메타, 원장 아님
        i_named = _col(head, "항목")
        # ★한 행이 한 항목인 표와, 한 행이 **한 항목의 속성**인 표가 섞여 있다.
        #   기계가 못 가르므로 판정하지 않고 표시한다 — 항목 열이 명시 안 된
        #   비교표(첫 칸이 빈 머리글)가 그 신호다.
        coarse = i_named is None and not _clean(head[0] if head else "")
        i_item = i_named or 0
        cols = [(a, _col(head, a["column"])) for a in axes]
        i_advice = _col(head, "권고")
        i_src = _col(head, "출처", "근거") if all(i is None for _, i in cols) else None

        for cells in rows:
            item = _clean(cells[i_item]) if i_item < len(cells) else ""
            if _ID_CELL.match(item):     # 첫 열이 ID 열이면 항목은 다음 열
                item = _clean(cells[i_item + 1]) if i_item + 1 < len(cells) else ""
            if not item or item in _HEADER_WORDS:
                continue
            get = lambda idx: (cells[idx].strip()
                               if idx is not None and idx < len(cells) else "")
            advice, whole = get(i_advice), " | ".join(cells)

            relation, why = rel, None
            if marker == _BUCKET2:       # 이 통만 갈래가 둘 — 권고 셀이 말한 것을 옮긴다
                why = advice
                relation = (None if "결정 필요" in advice
                            else "translates" if "번역" in advice else "hides")

            all_dec = set(_find("decision", whole))
            mine = {d for d in all_dec if own and own.fullmatch(d)}
            row = {"항목": item, "관계": relation, "관계_근거": why,
                   "결정": sorted(mine),                   # 자기 결정층 — 완결을 판정한다
                   "인용_결정": sorted(all_dec - mine),     # 남의 결정 — 근거일 뿐이다
                   "입도주의": coarse, "통": marker, "섹션": section, "출처_셀": get(i_src)}
            for ax, idx in cols:
                col = ax["column"]
                row[f"{col}_셀"] = get(idx)
                cited = []
                for k in ax["cite"]:
                    cited += [c for c in _find(k, whole) if not own or not own.fullmatch(c)]
                row[f"{col}_근거"] = sorted(set(cited))
            row["상태"] = _state(row, axes)
            out.append(row)
    return out


def _has(cell):
    return _clean(cell).lower() not in _EMPTY


def _state(row, axes):
    """★관계가 완결 조건을 정하고, 조건이 상태를 계산한다.

    근거부족이 판정대기보다 앞선다 — 근거 없이 결정할 수는 없다.
    adopts만 결정을 요구하지 않는다(양쪽에 자리가 있으면 그대로 쓴다는 뜻이므로).
    나머지는 전부 **값이 정해져야** 끝나고, 값을 정하는 것이 곧 결정이다:
      remaps=대응표 · hides=고정값 · translates=노출 어휘 · builds=조항 · excludes=재도입 조건
    """
    cols = [a["column"] for a in axes]
    cited = (any(row[f"{c}_근거"] for c in cols) or row["결정"] or row["인용_결정"])
    cells = [row[f"{c}_셀"] for c in cols] + [row["출처_셀"]]
    if not cited and not any(_has(x) for x in cells):
        return "근거부족"
    if row["관계"] is None:
        return "판정대기"
    if row["관계"] == "adopts":
        return "확정" if all(_has(row[f"{c}_셀"]) for c in cols) else "판정대기"
    return "확정" if row["결정"] else "판정대기"


def load(corpus, registry=None):
    """registry 선언 → (원장 행, 선언). 코퍼스 이름은 인자다 — 코드가 모른다."""
    from pathlib import Path
    import corpus as C
    reg = registry or C.load_registry()
    cfg = (reg["corpora"][corpus].get("derivation") or {})
    root = (Path(__file__).parent / reg["corpora"][corpus]["source"]).resolve()
    text = (root / cfg["source"]).read_text(encoding="utf-8")
    return parse_ledger(text, cfg["axes"], cfg.get("decision_ns")), cfg


def main():
    import yaml
    from collections import Counter
    from pathlib import Path
    rows, _ = load(sys.argv[1])
    doc = {"meta": {"corpus": sys.argv[1], "rows": len(rows),
                    "generator": "derivation.py (기계 생성 — 손 편집 금지, 재생성 가능)",
                    "관계": dict(Counter(r["관계"] or "(미정)" for r in rows)),
                    "상태": dict(Counter(r["상태"] for r in rows))},
           "rows": rows}
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
        print(f"원장 {len(rows)}행 → {sys.argv[2]}")
        print(f"  관계 {doc['meta']['관계']}\n  상태 {doc['meta']['상태']}")
    else:
        print(text)


if __name__ == "__main__":
    main()
