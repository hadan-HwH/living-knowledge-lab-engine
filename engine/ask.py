"""질의 3종 — 정본의 소비 경로. 결정론·LLM 0·읽기 전용.

세 질의는 소유자 모델에서 곧장 나온다:
  how     "a5인 현재만 본다"            → 현행 조각만. 이력은 `--why`로만.
  impact  "조항이 정확하면 비교가 된다"   → 이 조항을 바꾸면 어느 개념·관계가 흔들리나
  recent  "결정은 계속 바뀐다"           → 최근 무엇이 이력으로 내려갔나

★공통 규율: **없으면 없다고 말한다.** 빈 결과를 빈 화면으로 내면 "본 적 없다"와
"봤는데 없다"가 구분되지 않는다 — 이 프로젝트가 반복해서 당한 실패 모양이다."""
from __future__ import annotations


def _index(canon):
    return {c["anchor"]: c for c in canon.get("concepts") or []}


def _find(canon, ref):
    """anchor 정확일치 → 이름 정확일치 → 이름 부분일치. 사람이 부르는 대로 받는다."""
    by_anchor = _index(canon)
    if ref in by_anchor:
        return by_anchor[ref]
    for c in canon.get("concepts") or []:
        if c.get("name") == ref:
            return c
    hits = [c for c in canon.get("concepts") or [] if ref and ref in str(c.get("name") or "")]
    return hits[0] if len(hits) == 1 else None


def _articles_of(frags):
    """조각 키(`<조항>|<필드>`)에서 조항 anchor만. 게이트 인용은 조항이 아니다."""
    out = []
    for f in frags or []:
        k = str(f.get("key") or "")
        if k == "quote" or "|" not in k:
            continue
        a = k.split("|", 1)[0]
        if a not in out:
            out.append(a)
    return out


#: 층 표시 순서 — 규범(무엇이어야 하나)에서 표현(어떻게 보이나) 순.
_LAYER_ORDER = ["article", "spec_section", "state_enum", "field", "screen_section",
                "screen", "gap", "section", "(미상)"]
_LAYER_LABEL = {"article": "조항", "spec_section": "정체성·스펙", "state_enum": "상태값",
                "field": "필드", "screen_section": "화면", "screen": "화면(전체)",
                "gap": "GAP", "section": "본문", "(미상)": "(출처 미상)"}


def ask_how(canon, ref, why=False, unit_kinds=None):
    """이 개념은 지금 어떻게 동작하나. 현행 조각 + 현행 결정 + 별칭 + 출처 조항."""
    c = _find(canon, ref)
    if c is None:
        return {"anchor": None, "query": ref,
                "note": f"`{ref}`에 해당하는 개념이 정본에 없다 — 이름·anchor를 확인하라"}
    frags = (canon.get("bodies") or {}).get(c["anchor"]) or []
    live = [f for f in frags if not f.get("removed_at") and not f.get("superseded_at")]
    past = [f for f in frags if f.get("removed_at") or f.get("superseded_at")]
    rel = [r for r in canon.get("relations") or []
           if c["anchor"] in (r.get("from"), r.get("to"))]
    # ★출처 층을 갈라 담는다 — 서술 단위 일반화로 한 개념 아래 조항·화면·필드가
    # 나란히 앉는다. 섞은 목록(`body`)도 그대로 남긴다: 드리프트는 나란히 놓아야 보인다
    by_layer = {}
    for f in live:
        if f["key"] == "quote":
            continue                       # 게이트 인용은 감사 증거지 서술이 아니다
        kind = (unit_kinds or {}).get(str(f["key"]).split("|", 1)[0]) or "(미상)"
        by_layer.setdefault(kind, []).append(f)
    return {"anchor": c["anchor"], "name": c.get("name"), "scope": c.get("scope"),
            "by_layer": by_layer,
            "commitment": c.get("commitment"), "current": c.get("current"),
            "aliases": [a.get("surface") for a in (c.get("aliases") or [])],
            "articles": _articles_of(live), "body": live,
            "history": past if why else [],
            "history_count": len(past), "relations": rel,
            "note": None if live else "본문 조각이 없다 — 조항 귀속(S3a)이 아직 안 붙었다"}


def ask_impact(canon, ref):
    """이걸 바꾸면 무엇이 흔들리나. direct=직접 인용/보유, related=관계로 1홉."""
    bodies = canon.get("bodies") or {}
    by_anchor = _index(canon)
    direct = []
    if ref in by_anchor:
        direct = [by_anchor[ref]]                       # 개념 자신
    else:
        for anchor, frags in sorted(bodies.items()):
            live = [f for f in frags if not f.get("removed_at") and not f.get("superseded_at")]
            if ref in _articles_of(live) and anchor in by_anchor:
                direct.append(by_anchor[anchor])
    seen = {c["anchor"] for c in direct}
    related = []
    for r in canon.get("relations") or []:
        for near, far in ((r.get("from"), r.get("to")), (r.get("to"), r.get("from"))):
            if near in seen and far not in seen and far in by_anchor:
                if far not in {x["anchor"] for x in related}:
                    related.append({**by_anchor[far], "via": r.get("canonical"), "from": near})
    note = None
    if not direct:
        note = f"`{ref}`를 인용하는 개념이 정본에 없다 — 조항 ID나 개념 anchor를 확인하라"
    return {"query": ref, "direct": direct, "related": related, "note": note}


def ask_recent(canon, scope=None, limit=20):
    """최근 무엇이 이력으로 내려갔나. 갱신(superseded)과 소멸(removed)을 가른다."""
    by_anchor = _index(canon)

    def _in(anchor):
        return not scope or str((by_anchor.get(anchor) or {}).get("scope") or "") == scope

    sup, gone = [], []
    for anchor, frags in sorted((canon.get("bodies") or {}).items()):
        if not _in(anchor):
            continue
        for f in frags or []:
            row = {"anchor": anchor, "name": (by_anchor.get(anchor) or {}).get("name"),
                   "key": f.get("key"), "text": f.get("text")}
            if f.get("superseded_at"):
                sup.append({**row, "at": f["superseded_at"],
                            "superseded_by": f.get("superseded_by")})
            elif f.get("removed_at"):
                gone.append({**row, "at": f["removed_at"]})
    sup.sort(key=lambda x: (x["at"] or "", x["anchor"]), reverse=True)
    gone.sort(key=lambda x: (x["at"] or "", x["anchor"]), reverse=True)
    changed = [c for c in canon.get("concepts") or []
               if (c.get("current") or {}).get("superseded") and _in(c["anchor"])]
    note = None
    if not sup and not gone and not changed:
        note = "이 범위에서 최근 이력으로 내려간 것이 없다 — 조용한 회차다(정본은 읽었다)"
    return {"scope": scope, "superseded": sup[:limit], "removed": gone[:limit],
            "decision_changed": changed, "note": note}


# ── 렌더링 — 사람이 읽는 형태 ─────────────────────────────────────────────

def _decision_text(events, target, option):
    """결정을 `o_INV-D-6913` 같은 자기참조 토큰이 아니라 **문서 표기**로 보여준다.

    ★감사 지적: brief가 결정층을 `PRIME-COMMERCE.…T.INV-D-6913 → o_INV-D-6913`로 찍고
    있었다 — 사람이 읽을 수 없는 자기참조다. 원장의 `source`가 문서 표기를 들고 있다."""
    for e in events or []:
        if e.get("option") == option:
            src = (e.get("source") or [None])[0]
            return src or str(option).lstrip("o_")
    return str(option or "").lstrip("o_")


def render_how(r, events=None):
    if not r.get("anchor"):
        return f"# {r['query']}\n\n> {r['note']}"
    out = [f"# {r['name']}", f"> `{r['anchor']}` · {r['scope']} · {r['commitment']}"]
    cur = r.get("current")
    if cur and cur.get("value"):
        line = f"**지금**: {_decision_text(events, None, cur['value'])}"
        if cur.get("superseded"):
            line += " (이력: " + ", ".join(_decision_text(events, None, o)
                                           for o in cur["superseded"]) + ")"
        out.append(line)
    elif cur and cur.get("open"):
        out.append(f"**미결**: 후보 {cur.get('candidates')}")
    if r.get("aliases"):
        out.append("**다른 이름**: " + " · ".join(r["aliases"]))
    if r.get("articles"):
        out.append(f"**출처 조항** {len(r['articles'])}: " + " · ".join(r["articles"]))
    out.append("")
    layers = r.get("by_layer") or {}
    if layers:
        for kind in _LAYER_ORDER + [k for k in sorted(layers) if k not in _LAYER_ORDER]:
            frags = layers.get(kind)
            if not frags:
                continue
            out.append(f"## {_LAYER_LABEL.get(kind, kind)} ({len(frags)})")
            for f in frags:
                out.append(f"- [{f['key']}] {f['text']}")
            out.append("")
    elif r["body"]:
        for f in r["body"]:
            if f["key"] != "quote":
                out.append(f"- [{f['key']}] {f['text']}")
    else:
        out.append(f"_{r['note']}_")
    if r.get("relations"):
        out.append("\n## 관계")
        for rel in r["relations"]:
            arrow = "→" if rel["from"] == r["anchor"] else "←"
            other = rel["to"] if rel["from"] == r["anchor"] else rel["from"]
            out.append(f"- {arrow} {rel.get('canonical')} · {other}")
    if r["history"]:
        out.append("\n## 이력 (--why)")
        for f in r["history"]:
            tag = "갱신됨" if f.get("superseded_at") else "출처 소멸"
            why = f" ← {f['superseded_by']}" if f.get("superseded_by") else ""
            out.append(f"- [{f['key']}] {tag} @{f.get('superseded_at') or f.get('removed_at')}{why}")
            out.append(f"    {f['text'][:100]}")
    elif r.get("history_count"):
        out.append(f"\n_이력 {r['history_count']}건 — `--why`로 본다_")
    return "\n".join(out)


def render_impact(r):
    out = [f"# 영향 — {r['query']}"]
    if r.get("note"):
        return "\n".join(out + ["", f"> {r['note']}"])
    out.append(f"\n## 직접 ({len(r['direct'])}) — 이 조항을 본문으로 들고 있다")
    for c in r["direct"]:
        out.append(f"- `{c['anchor']}` {c.get('name')}")
    out.append(f"\n## 1홉 ({len(r['related'])}) — 관계로 이어져 있다")
    for c in r["related"] or []:
        out.append(f"- `{c['anchor']}` {c.get('name')}  ({c.get('via')} ← {c.get('from')})")
    if not r["related"]:
        out.append("_없다 — 관계가 아직 안 붙었거나 고립 개념이다_")
    return "\n".join(out)


def render_recent(r, events=None):
    out = [f"# 최근 변경{' — ' + r['scope'] if r.get('scope') else ''}"]
    if r.get("note"):
        return "\n".join(out + ["", f"> {r['note']}"])
    if r["decision_changed"]:
        out.append(f"\n## 결정이 바뀐 개념 ({len(r['decision_changed'])})")
        for c in r["decision_changed"]:
            cur = c["current"]
            out.append(f"- {c.get('name')} — {_decision_text(events, None, cur['value'])}"
                       f" (이력: " + ", ".join(_decision_text(events, None, o)
                                              for o in cur["superseded"]) + ")")
    if r["superseded"]:
        out.append(f"\n## 서술이 갱신됨 ({len(r['superseded'])})")
        for f in r["superseded"]:
            why = f" ← {f['superseded_by']}" if f.get("superseded_by") else ""
            out.append(f"- [{f['key']}] {f.get('name')} @{f['at']}{why}")
    if r["removed"]:
        out.append(f"\n## 출처가 사라짐 ({len(r['removed'])})")
        for f in r["removed"]:
            out.append(f"- [{f['key']}] {f.get('name')} @{f['at']}")
    return "\n".join(out)
