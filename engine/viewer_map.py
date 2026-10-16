"""지도 모델 — 정본이 어떤 구조로 되어 있나. 결정론·LLM 0.

묶는 축은 데이터가 정한다: scope가 여러 갈래면 scope 계층, 하나뿐이면 `part_of` 관계,
그것도 없으면 무리 없이 낸다. 코퍼스마다 다른 축을 코드에 박지 않는다.
"""
import collections
import re

#: 평평한 코퍼스에서 무리를 만들 때 쓰는 관계. 부모-자식 의미가 있는 것만.
NEST = "part_of"

#: 출처를 못 따라가는 조각(`quote`)만 든 개념의 자리. 숨기면 지도가 정본보다 작아진다.
NO_ORIGIN = "(출처 미상)"

#: 조각 키에서 무리 이름을 몇 마디까지 딸까. 1은 너무 굵고 3은 개념당 하나가 된다(실측).
ORIGIN_DEPTH = 2


def _app_of(concepts):
    """anchor → 무리 이름. **scope 말단이 정본**이다 — anchor 접두와 다를 수 있다."""
    home = {}
    for c in concepts:
        parts = [p for p in (c.get("scope") or "").split("/") if p]
        home[c["anchor"]] = parts[-1] if parts else "(scope 없음)"
    return lambda a: home.get(a, (a or "").split("#")[0])


def _current(frags):
    """현행 조각만 — 이력·삭제를 세면 두께가 거짓말을 한다(불변식 6)."""
    return [f for f in (frags or [])
            if not f.get("superseded_at") and not f.get("removed_at")]


def _leaf(concept, bodies):
    return {"anchor": concept["anchor"],
            "name": concept.get("name") or concept["anchor"],
            "fragments": len(_current(bodies.get(concept["anchor"]))),
            "commitment": concept.get("commitment")}


def _weigh(groups):
    """무게 = **코퍼스 전체** 최대 칸 대비 비율. 무리마다 따로 재면 작은 무리의 칸이
    큰 무리의 칸보다 커 보인다. 0인 칸도 바닥값을 받는다 — 비었다는 사실이
    지도에서 사라지면 안 된다."""
    cells = [c for g in groups for c in (g.get("children") or [])]
    top = max([c["fragments"] for c in cells] or [0])
    for c in cells:
        c["weight"] = round(max(c["fragments"] / top, 0.12), 3) if top else 1.0
    return groups


def _roll_up(name, leaves):
    counts = collections.Counter(l["commitment"] for l in leaves if l["commitment"])
    return {"name": name,
            "concepts": len(leaves),
            "fragments": sum(l["fragments"] for l in leaves),
            "commitment": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
            "children": sorted(leaves, key=lambda l: (-l["fragments"], l["anchor"]))}


def _by_scope(concepts, bodies):
    """scope 경로로 묶는다 — 끝에서 둘째가 무리(platform), 마지막이 갈래(app)."""
    tree = collections.defaultdict(lambda: collections.defaultdict(list))
    for c in concepts:
        parts = [p for p in (c.get("scope") or "").split("/") if p]
        app = parts[-1] if parts else "(scope 없음)"
        group = parts[-2] if len(parts) >= 2 else "(무리 없음)"
        tree[group][app].append(_leaf(c, bodies))
    groups = []
    for gname in sorted(tree):
        apps = [_roll_up(a, tree[gname][a]) for a in sorted(tree[gname])]
        groups.append({"name": gname,
                       "concepts": sum(a["concepts"] for a in apps),
                       "fragments": sum(a["fragments"] for a in apps),
                       "children": sorted(apps, key=lambda a: (-a["fragments"], a["name"]))})
    return sorted(groups, key=lambda g: (-g["concepts"], -g["fragments"], g["name"]))


def _origin_of(key):
    """조각 키 → 출처 무리. `a/b/c#s|content`도 `a.b.c|signature`도 `a/b`로 접힌다."""
    head = (key or "").split("#")[0].split("|")[0]
    if not head or head == "quote":
        return None
    parts = [p for p in re.split(r"[/.]", head) if p]
    return "/".join(parts[:ORIGIN_DEPTH]) or None


def _home_by_origin(anchor, bodies):
    """조각이 가장 많이 온 곳이 그 개념의 집이다."""
    counts = collections.Counter()
    for f in _current(bodies.get(anchor)):
        o = _origin_of(f.get("key"))
        if o:
            counts[o] += 1
    return counts.most_common(1)[0][0] if counts else NO_ORIGIN


def _by_origin(concepts, bodies):
    buckets = collections.defaultdict(list)
    for c in concepts:
        buckets[_home_by_origin(c["anchor"], bodies)].append(_leaf(c, bodies))
    groups = [_roll_up(name, leaves) for name, leaves in buckets.items()]
    return sorted(groups, key=lambda g: (g["name"] == NO_ORIGIN, -g["concepts"],
                                         -g["fragments"], g["name"]))


def _by_nesting(concepts, rels, bodies):
    """`part_of`의 부모를 무리로 삼는다. 부모가 없으면 자기가 무리다."""
    parent = {}
    for r in rels:
        if r.get("canonical") == NEST and r.get("from") and r.get("to"):
            parent.setdefault(r["from"], r["to"])
    known = {c["anchor"] for c in concepts}
    buckets = collections.defaultdict(list)
    for c in concepts:
        home = parent.get(c["anchor"])
        buckets[home if home in known else c["anchor"]].append(_leaf(c, bodies))
    names = {c["anchor"]: c.get("name") or c["anchor"] for c in concepts}
    groups = [dict(_roll_up(head, leaves), label=names.get(head, head))
              for head, leaves in buckets.items()]
    return sorted(groups, key=lambda g: (-g["concepts"], -g["fragments"], g["name"]))


def _links(concepts, rels, key_of):
    """무리를 관통하는 관계만 그린다. 무리 안 관계는 세기만 한다."""
    known = {c["anchor"] for c in concepts}
    seen, within, dangling = collections.Counter(), 0, 0
    for r in rels:
        a, b = r.get("from"), r.get("to")
        if a not in known or b not in known:
            dangling += 1
            continue
        ka, kb = key_of(a), key_of(b)
        if ka == kb:
            within += 1
            continue
        seen[(ka, kb, r.get("canonical"))] += 1
    links = [{"from": a, "to": b, "canonical": k, "count": n}
             for (a, b, k), n in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))]
    return links, within, dangling


def build_map_model(concepts, relations, bodies):
    """정본 → 지도 모델 {axis, axis_note, groups, links, stats}."""
    concepts = list(concepts or [])
    relations = list(relations or [])
    bodies = bodies or {}
    scopes = {c.get("scope") for c in concepts}

    if len(scopes) > 1:
        axis = "scope"
        note = "scope 경로로 묶었다 — 코퍼스가 갈래를 스스로 말한다."
        groups = _by_scope(concepts, bodies)
        key_of = _app_of(concepts)
    elif any(_origin_of(f.get("key"))
             for frs in bodies.values() for f in _current(frs)):
        axis = "origin"
        note = "scope가 하나뿐이라 **조각이 어디서 왔나**로 묶었다 — 문서·모듈이 갈래다."
        groups = _by_origin(concepts, bodies)
        home = {c["anchor"]: g["name"] for g in groups for c in g["children"]}
        key_of = lambda a: home.get(a, NO_ORIGIN)               # noqa: E731
    elif any(r.get("canonical") == NEST for r in relations):
        axis = NEST
        note = f"scope가 하나뿐이라 `{NEST}` 관계로 묶었다 — 이 코퍼스의 유일한 구조 신호다."
        groups = _by_nesting(concepts, relations, bodies)
        home = {c["anchor"]: g["name"] for g in groups for c in g["children"]}
        key_of = lambda a: home.get(a, a)                       # noqa: E731
    else:
        axis = "none"
        note = "묶을 축이 없다 — scope도 하나고 `part_of` 관계도 없다. 크기순으로만 낸다."
        groups = [_roll_up("(전체)", [_leaf(c, bodies) for c in concepts])] if concepts else []
        key_of = lambda a: "(전체)"                              # noqa: E731

    _weigh(groups)
    links, within, dangling = _links(concepts, relations, key_of)
    return {"axis": axis, "axis_note": note, "groups": groups, "links": links,
            "stats": {"concepts": len(concepts),
                      "fragments": sum(len(_current(v)) for v in bodies.values()),
                      "groups": len(groups),
                      "relations_within": within,
                      "relations_across": sum(l["count"] for l in links),
                      "relations_dangling": dangling}}
