"""통합 패스 — 배치 경계를 넘는 유일한 경로.

경로: 결정론 후보 좁히기(여기) → Tier B 판정 1회 → 제안 → 사후 리뷰.
전수 비교는 1,344개면 90만 쌍이라 애초에 불가능하고, 좁히지 않으면 LLM 비용이
추출 자체보다 커진다."""
from __future__ import annotations

import re
from collections import defaultdict

#: 신호가 못 되는 낱말 — 조사·수량사 계열. 이름에서 걷어내지 않으면 전부가 이어진다.
_STOP = {"이", "그", "및", "를", "을", "은", "는", "의", "에", "로", "가", "한",
         "와", "과", "수", "것", "때", "더", "안", "밖", "또", "즉"}
_TOKEN = re.compile(r"[가-힣a-zA-Z][가-힣a-zA-Z0-9_]+")

_STRUCTURE = {"사전", "등록", "한계", "다음", "성격", "개요", "요약", "배경", "목적",
              "범위", "결론", "부록", "참고", "정직", "남은", "하지", "않을", "것"}


#: 한국어는 교착어라 같은 말이 조사·어미를 달고 다른 토큰이 된다(`청킹은` vs `청킹`).
#: 형태소 분석기를 들이지 않고(stdlib-only 관례) **꼬리만** 깎는다 — 보수적으로,
#: 남는 줄기가 2자 이상일 때만. 과하게 깎으면 없던 일치가 생겨 후보가 오염된다.
_TAIL = ("으로써", "으로", "로써", "이라", "라고", "에서", "에게", "까지", "부터",
         "만이", "한다", "된다", "이다", "하다", "들이", "들을", "은", "는", "이",
         "가", "을", "를", "의", "에", "로", "와", "과", "도", "만")


def _stem(t):
    for tail in _TAIL:
        if t.endswith(tail) and len(t) - len(tail) >= 2:
            return t[: -len(tail)]
    return t


def _tokens(name):
    return {_stem(t) for t in _TOKEN.findall(str(name or "").lower())
            if len(t) > 1 and t not in _STOP and t not in _STRUCTURE}


def _units(anchor, bodies):
    """개념이 모은 **서로 다른 서술 단위**. `quote` 조각은 왕복 증거지 귀속이 아니다."""
    return {str(f.get("key")).split("|")[0]
            for f in (bodies or {}).get(anchor) or []
            if isinstance(f, dict) and "|" in str(f.get("key") or "")}


def _unit_count(anchor, bodies):
    return len(_units(anchor, bodies))


def merge_candidates(concepts, bodies, min_shared=2, max_docfreq=20,
                     min_jaccard=0.20, max_unit_group=8):
    """통합 후보 쌍. 결정론·LLM 0. 반환 항목에 **판정 필드는 없다.**

    대상은 **아직 모으지 못한 개념**(단위 0~1)이다. 이미 여러 단위를 모은 개념은
    축 1이 제 일을 한 것이라 건드리지 않는다.

    신호는 이름 토큰 공유 `min_shared`개 이상 **그리고** Jaccard `min_jaccard` 이상.
    흔한 낱말(`max_docfreq` 초과 등장)은 신호에서 뺀다 — 안 빼면 "정본"·"게이트" 같은
    말로 전부가 이어진다."""
    pool = [c for c in concepts
            if c.get("name") and _unit_count(c.get("anchor"), bodies) <= 1]
    toks = {c["anchor"]: _tokens(c["name"]) for c in pool}
    inv = defaultdict(list)
    for anchor in sorted(toks):
        for t in toks[anchor]:
            inv[t].append(anchor)
    shared = defaultdict(set)
    for t, anchors in inv.items():
        if len(anchors) > max_docfreq:
            continue                       # 흔한 낱말은 신호가 아니다
        for i in range(len(anchors)):
            for j in range(i + 1, len(anchors)):
                shared[(anchors[i], anchors[j])].add(t)
    out = []
    for (a, b), ts in shared.items():
        if len(ts) < min_shared:
            continue
        union = toks[a] | toks[b]
        if union and len(ts) / len(union) >= min_jaccard:
            out.append({"a": a, "b": b, "shared": sorted(ts), "signal": "name",
                        "jaccard": round(len(ts) / len(union), 3)})
    # ★두 번째 축 — 같은 출처 단위에서 나온 개념들(과분할). 이름 축과 거의 안 겹친다
    seen = {(p["a"], p["b"]) for p in out}
    by_unit = defaultdict(list)
    for c in pool:
        u = _units(c.get("anchor"), bodies)
        if len(u) == 1:
            by_unit[next(iter(u))].append(c["anchor"])
    for unit, anchors in by_unit.items():
        anchors = sorted(anchors)
        if not 1 < len(anchors) <= max_unit_group:
            continue
        for i in range(len(anchors)):
            for j in range(i + 1, len(anchors)):
                if (anchors[i], anchors[j]) not in seen:
                    out.append({"a": anchors[i], "b": anchors[j],
                                "signal": "same_unit", "unit": unit})
    out.sort(key=lambda p: (p["a"], p["b"]))
    return out


def candidate_groups(pairs):
    """쌍을 연결 성분으로 묶는다 — 판정은 **묶음 단위**로 물어야 싸다.

    쌍으로 주면 같은 개념을 여러 번 묻게 되고, 판정자가 쌍마다 다른 답을 낼 수도 있다
    (같은 것을 두 번 묻지 않는다는 규율)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs or []:
        ra, rb = find(p["a"]), find(p["b"])
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups = defaultdict(list)
    for x in parent:
        groups[find(x)].append(x)
    return sorted([sorted(v) for v in groups.values()])


def apply_consolidation(canon, proposals, prefix=""):
    """판정된 통합 제안을 정본에 반영한다. 결정론·LLM 0·멱등.

    ★판정은 이미 났다 — 여기선 **옮기기만** 한다. `merge`가 아닌 판정(`separate`·
    `unsure`)은 아무것도 바꾸지 않는다."""
    by_anchor = {c.get("anchor"): c for c in canon.get("concepts") or []}
    absorbed, unresolved = {}, []
    for p in sorted(proposals or [], key=lambda x: str(x.get("group"))):
        if p.get("verdict") != "merge" or not p.get("keep"):
            continue
        keep = p["keep"] if p["keep"] in by_anchor else prefix + p["keep"]
        if keep not in by_anchor:
            unresolved.append(keep)
            continue
        for a in p.get("absorb") or []:
            src = a if a in by_anchor else prefix + a
            if src not in by_anchor or src == keep:
                if src not in by_anchor:
                    unresolved.append(src)
                continue
            absorbed[src] = keep
    # 사슬 해소 — a→b, b→c 면 a→c (판정이 겹쳐도 끝점이 하나로 모인다)
    def final(x, seen=None):
        seen = seen or set()
        while x in absorbed and x not in seen:
            seen.add(x)
            x = absorbed[x]
        return x

    bodies = {k: list(v) for k, v in (canon.get("bodies") or {}).items()}
    concepts = []
    for c in canon.get("concepts") or []:
        a = c.get("anchor")
        if a in absorbed:
            continue
        concepts.append(dict(c))
    for src, dst in sorted(absorbed.items()):
        dst = final(dst)
        node = next((c for c in concepts if c.get("anchor") == dst), None)
        if node is None:
            continue
        node["absorbed_anchors"] = sorted(
            set(node.get("absorbed_anchors") or []) | {src})
        have = {f.get("key") for f in bodies.get(dst) or []}
        for f in bodies.pop(src, []) or []:
            if f.get("key") not in have:
                bodies.setdefault(dst, []).append(f)
                have.add(f.get("key"))
    rels, seen_rel = [], set()
    for r in canon.get("relations") or []:
        f, t = final(r.get("from")), final(r.get("to"))
        if f == t:
            continue                       # 자기 자신과의 관계는 관계가 아니다
        key = (f, t, r.get("canonical"))
        if key in seen_rel:
            continue
        seen_rel.add(key)
        rels.append({**r, "from": f, "to": t})
    out = {**canon, "concepts": concepts, "bodies": bodies, "relations": rels}
    # ★정당한 감소는 **기록이 있을 때만** 면제된다(불변식 9).
    # 은퇴 기록은 줄어드는 지표를 **전부** 담는다 — 게이트가 지표별로 면제를 계산한다.
    if absorbed:
        def _live(fr):
            return sum(len(str(f.get("text") or "")) for f in fr
                       if not f.get("removed_at") and not f.get("superseded_at"))
        old_bodies = canon.get("bodies") or {}
        meta = dict(canon.get("meta") or {})
        meta["retired"] = list(meta.get("retired") or []) + [{
            "at": (canon.get("meta") or {}).get("source_sha"),
            "reason": "consolidation",
            "concepts": len(absorbed),
            "bodies": len(old_bodies) - len(bodies),
            "body_chars": sum(_live(v) for v in old_bodies.values())
                          - sum(_live(v) for v in bodies.values()),
            "relations": len(canon.get("relations") or []) - len(rels),
        }]
        out["meta"] = meta
    if unresolved:
        out["_unresolved"] = sorted(set(unresolved))
    return out
