"""배치 추출 산출 병합 — 한 앱을 여러 에이전트가 나눠 추출했을 때 원장 하나로.

★무성 누락 금지 — 충돌은 전부 이름을 붙여 돌려준다. 개수만 세면 못 고친다."""
from __future__ import annotations


def _first_wins(batches, key):
    """배치 순서가 곧 우선순위 — 임의 규칙이지만 **결정론**이어야 한다."""
    seen, out, collisions = {}, [], []
    for batch in batches or []:
        for item in batch or []:
            k = key(item)
            if k in seen:
                collisions.append(k)
                continue
            seen[k] = item
            out.append(item)
    out.sort(key=key)
    return out, sorted(set(collisions))


def merge_subconcepts(batches):
    """anchor로 합친다. 같은 anchor는 첫 배치가 이기고, 같은 `name`에 다른 anchor는 보고만."""
    subs, collisions = _first_wins(batches, lambda s: s["anchor"])
    by_name = {}
    for s in subs:
        by_name.setdefault(s.get("name"), []).append(s["anchor"])
    dups = sorted((n, sorted(a)) for n, a in by_name.items() if n and len(a) > 1)
    return {"subconcepts": subs, "anchor_collisions": collisions, "name_duplicates": dups}


def merge_proposals(batches):
    props, collisions = _first_wins(batches, lambda p: p["sid"])
    return {"proposals": props, "sid_collisions": collisions}


def merge_members_files(dicts):
    """sid별 단위 목록의 합집합. `(unit, quote)`가 같으면 중복이고, 인용만 다르면 둘 다
    증거로 남긴다 — 조각 key가 단위 단위라(`<unit>|<field>`) 인용이 늘어도 손해가 없다."""
    out = {}
    for d in dicts or []:
        for sid, members in (d or {}).items():
            bucket = out.setdefault(sid, [])
            have = {(m.get("unit") or m.get("article"), m.get("quote")) for m in bucket}
            for m in members or []:
                k = (m.get("unit") or m.get("article"), m.get("quote"))
                if k not in have:
                    have.add(k)
                    bucket.append(m)
    return {"members": {sid: out[sid] for sid in sorted(out)}}


def merge_relations(batches):
    rels, _ = _first_wins(
        batches, lambda r: (r["from"], r["to"], str(r.get("canonical"))))
    return {"relations": rels}


def merge_aliases(batches):
    al, _ = _first_wins(batches, lambda a: (a["anchor"], a.get("surface") or ""))
    return {"aliases": al}


def check_coverage(subconcepts, proposals, slug):
    """계약 §5-4(전건 커버)를 **병합 후에** 다시 잰다 — 배치별로 통과해도 합치면서
    깨질 수 있는 자리다(배치 경계에서 제안만 살고 개념이 죽는 경우 등)."""
    want = {f"{slug}#" + s["anchor"] for s in subconcepts or []}
    have = {p["sid"] for p in proposals or []}
    return {"missing": sorted(want - have), "phantom": sorted(have - want)}
