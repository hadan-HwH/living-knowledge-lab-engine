"""층간 대조 — 같은 개념 아래 조항과 화면이 다른 값을 말하는가. 결정론·LLM 0.

★검출 원리는 축 1이 만들어준 구조를 그대로 쓴다. 개념 하나 아래 **서로 다른 층**의
조각이 모였고, 각 층이 **같은 항목에 다른 값**을 말하면 후보다.

    [article]        | Cart Hold Timeout | 45분 | 20분–2시간 | …
    [screen_section] | **Cart hold timeout** * | 분 | 25 | 10–120분 (설계) |

★**기계는 판정하지 않는다.** 어느 쪽이 맞는지는 정책·화면 두 담당자의 몫이다
(`parsers.parse_corpdoc_screen` 주석이 처음부터 그렇게 말한다). 검출기는 "같은 항목인데
값이 다르다"까지만 말하고 원문을 나란히 보여준다. 단위 환산(2시간 vs 120분)도 맞추지
않는다 — 맞추려 들면 지어내는 셈이고, 사람이 보면 3초면 판정한다."""
from __future__ import annotations

import re

_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_SEP = re.compile(r"^[\s|:\-–—]+$")
#: 표 머리글로 흔히 쓰이는 항목명 — 대조 대상이 아니다(모든 표에 나와서 전건 충돌이 된다).
_HEADER_ITEMS = {"항목", "필드", "구분", "이름", "name", "field", "item", "설정 항목",
                 "속성", "컬럼", "key", "값", "상태"}


def table_rows(text):
    """마크다운 표 텍스트 → [(항목명, [값들])]. 구분선·머리글은 버린다."""
    out = []
    for line in str(text or "").split("\n"):
        m = _ROW.match(line)
        if not m or _SEP.match(m.group(1)):
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 2 or not cells[0]:
            continue
        if normalize_item(cells[0]) in _HEADER_ITEMS:
            continue
        out.append((cells[0], cells[1:]))
    return out


def normalize_item(s):
    """항목명 정규화 — 강조·백틱·필수 표시·공백 차이를 지운다.

    `**Cart hold timeout** *`와 `Cart Hold Timeout`이 같은 항목이어야 대조가 된다.
    의미까지 맞추지는 않는다(동의어 판정은 사람 몫)."""
    s = re.sub(r"[*`]", "", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _value_key(values):
    """값 비교 키 — **숫자 집합**이 있으면 그걸, 없으면 텍스트를 쓴다."""
    # 숫자 순으로 정렬한다 — 문자열 정렬이면 15 < 3이 되어 사람이 읽을 때 헷갈린다.
    nums = sorted({n for v in values for n in _NUM.findall(str(v))},
                  key=lambda x: (float(str(x).replace(",", ".")), x))
    if nums:
        return tuple(nums), nums
    txt = " | ".join(str(v).strip() for v in values)
    return (txt,), []


def crosscheck_concept(anchor, fragments, unit_kinds):
    """한 개념의 조각들 → 층간 값 불일치 후보. 결정론(항목명 정렬).

    현행 조각만 본다 — 이력은 낡은 게 정상이라 불일치가 아니다(축 2와 같은 평면 정의).
    같은 층 안의 차이는 이 검출기의 일이 아니다(조항끼리는 조항 검토 몫)."""
    by_item = {}
    for f in fragments or []:
        if f.get("superseded_at") or f.get("removed_at"):
            continue
        key = str(f.get("key") or "")
        if key == "quote":
            continue
        kind = (unit_kinds or {}).get(key.split("|", 1)[0]) or "(미상)"
        for item, values in table_rows(f.get("text")):
            slot = by_item.setdefault(normalize_item(item), {})
            vk, nums = _value_key(values)
            slot.setdefault(kind, []).append((item, values, key, vk, nums))

    out = []
    for item in sorted(by_item):
        layers = by_item[item]
        if len(layers) < 2:
            continue                       # 한 층만 있으면 대조할 게 없다
        keys = {k: {vk for _, _, _, vk, _ in rows} for k, rows in layers.items()}
        if len({frozenset(v) for v in keys.values()}) < 2:
            continue                       # 층마다 같은 값을 말하면 정상
        out.append({"anchor": anchor, "item": item,
                    "by_layer": {k: sorted(" | ".join(v) for _, v, _, _, _ in rows)
                                 for k, rows in layers.items()},
                    "numbers": {k: sorted({n for _, _, _, _, ns in rows for n in ns},
                                          key=lambda x: (float(str(x).replace(",", ".")), x))
                                for k, rows in layers.items()},
                    "sources": {k: sorted({src for _, _, src, _, _ in rows})
                                for k, rows in layers.items()}})
    return out


def crosscheck_canon(canon, unit_kinds, scope=None):
    """정본 전체 대조. 반환 {conflicts, checked_concepts, note}."""
    by_anchor = {c["anchor"]: c for c in canon.get("concepts") or []}
    conflicts, checked = [], 0
    for anchor, frags in sorted((canon.get("bodies") or {}).items()):
        c = by_anchor.get(anchor)
        if c is None or (scope and c.get("scope") != scope):
            continue
        checked += 1
        conflicts += crosscheck_concept(anchor, frags, unit_kinds)
    note = None
    if not checked:
        note = "대조할 개념이 없다 — scope를 확인하라(통과 아님)"
    elif not conflicts:
        note = f"개념 {checked}개를 대조했고 층간 값 불일치가 없다"
    return {"conflicts": conflicts, "checked_concepts": checked, "note": note}


def render(rep, names=None):
    out = [f"# 층간 대조 — 불일치 후보 {len(rep['conflicts'])}건"
           f" (개념 {rep['checked_concepts']}개 대조)"]
    if rep.get("note"):
        out += ["", f"> {rep['note']}"]
    for cf in rep["conflicts"]:
        nm = (names or {}).get(cf["anchor"]) or cf["anchor"]
        out.append(f"\n## {cf['item']}  ·  {nm}")
        for layer in sorted(cf["by_layer"]):
            for v in cf["by_layer"][layer]:
                out.append(f"  [{layer}] {v}")
        out.append(f"  출처: {cf['sources']}")
    if rep["conflicts"]:
        out.append("\n_어느 쪽이 맞는지는 기계가 판정하지 않는다 — 정책·화면 담당자의 몫._")
    return "\n".join(out)
