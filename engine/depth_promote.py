"""깊이 스택 promote 접합 — depth-fill probe 층(subconcept+relations-canon)을
판정 원장(disposition)에 따라 정본 깊은층으로 fold. 전부 결정론(LLM 0).

여러 앱의 가벼운 표현(subconcept+align)을 판정 원장에 따라
  승격 → concept/state_enum 노드 + bodies(verbatim quote) + relations(canon-13)
  보류 → candidate/ambiguous/gap 큐 (정본 미편입, 소유자/담당자 확정 대기)
로 가른다. 소유자 판정 정책의 기계 집행.
"""
from __future__ import annotations

#: 앱 → 정본 scope 폴백. **비어 있다** — 매핑은 registry `app_scopes` 선언에서 온다
#: (엔진은 앱 이름을 모른다). 호출자가 `app_scopes`를 넘기지 않으면 앱 슬러그 그대로 쓴다.
APP_SCOPE: dict = {}

# disposition → 승격 시 concept basis (승격 대상만). 보류 3종은 held 큐로.
_PROMOTE_BASIS = {
    "new_code_only": "implemented_without_mandate",
    "new_decision": "decision",
    "align_owner_scope": "cross_app_owned",
    "state_enum_observed": "screen_observed",
    "auto_adopt": "document_stated",
    # 섹션이 문서에서 사라진 개념 — 정본에서 지우지 않고 removed_at으로 표시만 한다.
    # basis는 마지막으로 관측된 근거 그대로(문서가 그렇게 말했었다) — 삭제는 상태 변화지
    # 근거의 소급 부정이 아니다. "예전엔 이런 게 있었다"를 물을 수 있어야 발전 위키다.
    "tombstone": "document_stated",
}
_HELD = {"candidate_hold": "candidate", "ambiguous_hold": "ambiguous", "gap_hold": "gap"}


def load_probes(base, apps):
    """work/<app>/{subconcepts,relations-canon}.yaml 로드."""
    import yaml
    from pathlib import Path
    out = {}
    for app in apps:
        d = Path(base) / app
        sc = yaml.safe_load((d / "subconcepts.yaml").read_text(encoding="utf-8"))["subconcepts"]
        rl = yaml.safe_load((d / "relations-canon.yaml").read_text(encoding="utf-8"))["relations"]
        out[app] = {"subconcepts": sc, "relations": rl}
    return out


def fold_depth(adjudication, probes, app_scopes=None, canon_anchors=None,
               merged_into=None):
    """판정 원장 + probe → 승격 concept/bodies/relations + 보류 큐. 결정론(정렬 안정).
    app_scopes: 앱→정본 scope 매핑(생략 시 APP_SCOPE 폴백 — 비어 있다).
    merged_into: `<앱sid> → <정본 sid>` (원장 `synonym_record`). 병합된 개념을 관계
      끝점으로 풀 때 쓴다 — 없으면 종전 동작(같은 접두만 해소).
    전달 시 그 매핑을 쓴다(S4 promote 다리).
    row에 quote_gate_failed가 실려 있으면(structure_app.build_dispositions가 전파)
    승격 node에도 그대로 찍는다 — 소유자 disposition이 게이트 실패를 override해 승격을
    허용하더라도, 그 override 사실 자체는 감사 흔적으로 스택까지 관통 보존한다."""
    scope_of = app_scopes if app_scopes is not None else APP_SCOPE
    sc_by = {app: {s["anchor"]: s for s in p["subconcepts"]}
             for app, p in probes.items()}
    concepts, bodies = [], {}
    held = {"candidate": [], "ambiguous": [], "gap": []}
    promoted_anchor = {}                          # app -> {sc-anchor: 정본 anchor(sid)}

    for row in sorted(adjudication["dispositions"], key=lambda r: r["sid"]):
        disp = row["disposition"]
        app = row["app"]
        sid = row["sid"]
        anc = sid.split("#", 1)[1]
        if disp in _HELD:
            held[_HELD[disp]].append({"sid": sid, "name": row.get("name"),
                                      "was": row.get("was")})
            continue
        s = sc_by.get(app, {}).get(anc, {})
        scope = row["align_to"] if disp == "align_owner_scope" else scope_of[app]
        node = {"anchor": sid,
                "kind": "state_enum" if disp == "state_enum_observed" else "concept",
                "name": row.get("name") or s.get("name"),
                "scope": scope,
                "basis": _PROMOTE_BASIS[disp],
                "commitment": s.get("commitment"),
                "confidence": s.get("confidence")}
        if disp == "align_owner_scope":
            node["provenance_scope"] = scope_of[app]        # 발견 앱(집은 소유앱)
        if disp == "state_enum_observed":
            node["observed"] = True                        # 관측만 — 화면정의서 편집 아님
        if row.get("quote_gate_failed"):
            node["quote_gate_failed"] = True                # 감사 흔적 관통(override 허용)
        if row.get("needs_review"):
            node["needs_review"] = True                     # 사후 리뷰 대상(자동 편입 ambiguous)
        if row.get("removed_at"):
            node["removed_at"] = row["removed_at"]          # 삭제 표시(노드는 남는다)
        concepts.append(node)
        # tombstone은 probe에 더 이상 없다 — row가 들고 온 quote를 쓴다(증거 소실 금지).
        bodies[sid] = [{"key": "quote", "text": row.get("quote") or s.get("quote", "")}]
        promoted_anchor.setdefault(app, {})[anc] = sid

    # 관계 — relations-canon(앱 내 sc-anchor)을 정본 anchor로 승격, 양끝 승격분만.
    relations = []
    for app, p in sorted(probes.items()):
        pa = dict(promoted_anchor.get(app, {}))
        scope = scope_of.get(app) if isinstance(scope_of, dict) else None
        for anc in {r.get("from") for r in p["relations"]} | {r.get("to") for r in p["relations"]}:
            if anc and anc not in pa:
                sid = f"{app}#{anc}"
                if sid in (canon_anchors or set()):
                    pa[anc] = sid
                    continue
                tgt = (merged_into or {}).get(sid)
                if tgt and tgt in (canon_anchors or set()):
                    pa[anc] = tgt
        for r in p["relations"]:
            f, t = pa.get(r.get("from")), pa.get(r.get("to"))
            if f and t:
                relations.append({"from": f, "to": t,
                                  "canonical": r.get("canonical"),
                                  "quote": r.get("quote")})
    relations.sort(key=lambda r: (r["from"], r["to"], str(r["canonical"])))

    stats = {"promoted": len(concepts), "relations": len(relations),
             "held": {k: len(v) for k, v in held.items()}}
    return {"concepts": concepts, "relations": relations, "bodies": bodies,
            "held": held, "stats": stats}

