"""침식 상시 감시 — 스냅샷 정합 리포트 + 스냅샷 diff (L1 설계 §5.5의 활용층).

1회성으로 찾던 죽은 참조를 상설 능력으로: 새 스냅샷마다
  ① dead_ref_report — 모든 참조(결정→조항·개념→조항·개념→결정)를 코퍼스 전체
     anchor에 대조, 죽은 참조 + 역링크(근거 역인용) 재해소 제안. D-7149 교훈:
     역링크 탐색은 앱이 아니라 항상 코퍼스 전체다.
  ② snapshot_diff — 두 스냅샷의 개념 생성·소멸·내용 변경 = 변경 관측 데이터.

출력은 전부 제안/관측이다 — 확정은 각 도메인 담당자의 adjudication 몫.

Usage:
  python3 l1_integrity.py                  # 최신 스냅샷 정합 리포트 (integrity.yaml 저장)
  python3 l1_integrity.py diff SHA1 SHA2   # 두 스냅샷 diff
"""
from __future__ import annotations

import sys
from pathlib import Path
import yaml

from ingest import discover
from parsers import parse


from decision_alias import (FULL as _DEC_FULL, is_decision_ref,
                            canonical, scope_prefix_map)

_RESCUE_KINDS = {"article", "state_enum", "field"}    # 재해소 제안은 조항류만 (화면 섹션 잡음 제거)


def _is_archive_scope(scope, archive_segments):
    """scope가 아카이브인가 — 경로 **세그먼트** 완전일치로만 판정.

    부분 문자열 매칭이면 `resource-manager`·`outsourcing` 같은 실 앱이 아카이브로
    오분류된다(감시가 조용히 꺼지는 최악의 실패). 선언이 없으면 아무것도 제외하지
    않는다 = 기본은 전수 감시(fail-closed)."""
    if not archive_segments or not scope:
        return False
    return bool(set(str(scope).split("/")) & set(archive_segments))


def dead_ref_report(concepts, decisions, archive_segments=None):
    """스냅샷 개념 + 결정 스켈레톤 → 죽은 참조 목록(+재해소 제안).

    결정 참조 대조는 별칭 층(epoch 경계) 경유:
      전체형 `<APP>-D-N` = 전역 고유 → 전역 대조(모호 범주 구조 제외).
      구형 `D-N` = scope 접두사로 승격 후 대조. 접두사 미상(잔존 구 스킴 로그)
      scope만 기존 scope 내 대조 + 타 scope 존재 시 모호 인용 유지.

    archive_segments (registry 데이터 구동, 엔진은 폴더 이름을 모른다):
      아카이브 scope에서 나온 죽은/모호 참조는 **침식이 아니라 보존**이라 별도 분류
      `archived`로 분리한다. 근거는 코퍼스의 자기 선언 — acme-docs `4-source/README.md`
      "**감사 제외(4-source)**. 분리 전 기존 앱 문서를 raw로 보존한 곳",
      `4-source/inv/README.md` "여기 있는 `[MINV-NN]` 조항은 **정본이 아니다**".
      ★분리이지 삭제가 아니다 — 조용한 소멸 금지(집계에서 빠지되 원장에는 남는다).
    """
    anchors = {c["anchor"] for c in concepts}
    pm = scope_prefix_map(decisions)
    all_canon = set()
    dec_by_scope = {}
    for d in decisions:
        dec_by_scope.setdefault(d.get("scope"), set()).add(d["decision_id"])
        all_canon.add(canonical(d["decision_id"], d.get("scope"), pm))
    backref = {}                                  # 결정(정본 표기) -> 역인용하는 조항류 개념들
    for c in concepts:
        if c["kind"] not in _RESCUE_KINDS:
            continue
        for d in c["refs"].get("decisions", []):
            backref.setdefault(canonical(d, c.get("scope"), pm), []).append(c["anchor"])

    dead, ambiguous, checked = [], [], 0

    def _check(from_id, from_kind, scope, ref, rescue_fn):
        nonlocal checked
        checked += 1
        if is_decision_ref(ref):                  # 결정 참조 — 별칭 층 경유 대조
            canon = canonical(ref, scope, pm)
            if _DEC_FULL.match(canon):            # 전체형(승격 포함) = 전역 고유 → 전역 대조
                if canon not in all_canon:        # 미실존 = dead, 모호 범주 없음
                    dead.append({"from_id": from_id, "from_kind": from_kind, "scope": scope,
                                 "ref": ref, "ref_kind": "decision", "rescue": []})
                return
            if ref in dec_by_scope.get(scope, set()):   # 접두사 미상 scope — scope 내 대조
                return
            exists_in = sorted(str(s) for s, ids in dec_by_scope.items() if ref in ids)
            if exists_in:                         # 타 scope에만 존재 = 모호 인용 (어느 앱의 D-N인지 미명시)
                ambiguous.append({"from_id": from_id, "from_kind": from_kind, "scope": scope,
                                  "ref": ref, "ref_kind": "decision", "exists_in": exists_in})
            else:                                 # 어디에도 없음 = 진짜 dead
                dead.append({"from_id": from_id, "from_kind": from_kind, "scope": scope,
                             "ref": ref, "ref_kind": "decision", "rescue": []})
        elif ref not in anchors:                  # 조항 참조 — 코퍼스 전체 anchor 대조
            dead.append({"from_id": from_id, "from_kind": from_kind, "scope": scope,
                         "ref": ref, "ref_kind": "article", "rescue": rescue_fn()})

    for d in decisions:                           # 결정 → 영향 조항
        for a in d.get("articles", []):
            _check(d["decision_id"], "decision", d.get("scope"), a,
                   lambda d=d: sorted(set(backref.get(
                       canonical(d["decision_id"], d.get("scope"), pm), []))))
    for c in concepts:                            # 개념 → 조항
        for a in c["refs"].get("articles", []):
            def _rescue(a=a):
                rel = [canonical(d["decision_id"], d.get("scope"), pm)
                       for d in decisions if a in d.get("articles", [])]
                return sorted({x for dd in rel for x in backref.get(dd, [])})
            _check(c["anchor"], c["kind"], c.get("scope"), a, _rescue)
    for c in concepts:                            # 개념 → 결정 (scope-aware 존재 검사)
        for d0 in c["refs"].get("decisions", []):
            _check(c["anchor"], c["kind"], c.get("scope"), d0, lambda: [])
    # 아카이브 재분류 — 판정 로직은 위 한 곳뿐이고 여기선 **옮기기만** 한다.
    # (해소 규칙을 복제하면 두 경로가 갈라진다 — 실제로 갈라져서 모호 인용이
    #  아카이브로 안 넘어가는 버그를 냈다. 단일 판정 → 사후 재분류가 맞다.)
    archived = []
    if archive_segments:
        for bucket in (dead, ambiguous):
            moved = [x for x in bucket if _is_archive_scope(x.get("scope"), archive_segments)]
            for x in moved:
                bucket.remove(x)
                archived.append({**x, "was": "dead" if bucket is dead else "ambiguous",
                                 "note": "아카이브 scope — 감사 제외(코퍼스 자기 선언)"})
    return {"dead": dead, "ambiguous": ambiguous, "archived": archived,
            "stats": {"refs_checked": checked, "dead": len(dead),
                      "ambiguous": len(ambiguous), "archived": len(archived)}}


def reflected_but_present(decisions, concepts):
    """'반영완료' 결정이 값 폐지를 선언했는데 대상 state_enum에 그 값이 잔존 = 결정↔코드 드리프트.

    dead/ambiguous(죽은 참조·모호 인용)·낡은 권위 인용과 **다른 침식 유형**: 참조 자체는
    살아 있으나, "해결됐다(반영완료)"고 선언된 결정이 실제 코드/스펙(state_enum)에 미반영.
    출력=제안, 확정=담당자 몫.

    최초 발견 사례(StoreType.popup 잔존)의 출처도 정확히 적어 둔다: 그것은 이
    검출기가 코드를 읽어 찾은 것이 **아니라**, 기획팀이 `ai-suite` `prod` `ea33ec1d1`을
    손으로 대조해 acme-docs 문서에 적어 둔 자기 기록을 파이프라인이 인용한 것이다.
    이 함수는 코드베이스를 읽지 않는다.

    입력:
      decisions: 결정 이벤트. 드리프트 후보 = reflected=True + removes:[값] + target(state_enum anchor).
      concepts: 스냅샷 개념. kind=state_enum 항목의 anchor·values·scope로 대조.
    반환: {"drift": [...], "stats": {refs_checked, drift}}  각 drift = 제안 1건(잔존 값 1개)."""
    enums = {}                                      # anchor -> [state_enum 개념들]
    for c in concepts:
        if c.get("kind") == "state_enum":
            enums.setdefault(c["anchor"], []).append(c)
    drift, checked = [], 0
    for d in decisions:
        if not (d.get("reflected") and d.get("removes") and d.get("target")):
            continue                                # 반영 전·폐지의미 없음·대상 미상 = 후보 아님
        cands = enums.get(d["target"], [])
        scope = d.get("scope")
        if scope is not None:                       # scope 일치 enum 우선 (앱 오귀속 방지)
            scoped = [c for c in cands if c.get("scope") == scope]
            cands = scoped                          # scope 명시 시 타 scope enum은 대상 아님
        for value in d["removes"]:
            checked += 1
            if any(value in (c.get("values") or []) for c in cands):
                drift.append({"decision_id": d.get("decision_id"), "target": d["target"],
                              "value": value, "scope": scope,
                              "kind": "reflected_but_present"})
            # 대상 enum 없음 or 값 이미 제거 = abstention(무플래그) — 드리프트 유형 아님
    return {"drift": drift,
            "stats": {"refs_checked": checked, "drift": len(drift)}}


def snapshot_diff(old, new):
    """개념 (kind·scope·anchor) 단위의 생성·소멸·내용 변경. 변경 관측의 최소 단위."""
    key = lambda c: (c["kind"], str(c.get("scope")), c["anchor"])
    om = {key(c): c for c in old}
    nm = {key(c): c for c in new}
    added = [nm[k] for k in sorted(nm.keys() - om.keys())]
    removed = [om[k] for k in sorted(om.keys() - nm.keys())]
    changed, unchanged = [], 0
    for k in sorted(om.keys() & nm.keys()):
        if (om[k].get("content"), om[k].get("values")) != (nm[k].get("content"), nm[k].get("values")):
            changed.append(nm[k])
        else:
            unchanged += 1
    return {"added": added, "removed": removed, "changed": changed,
            "stats": {"added": len(added), "removed": len(removed),
                      "changed": len(changed), "unchanged": unchanged}}


def _leaf(anchor):
    """앵커의 말단 이름 — 코드는 `a.b.foo`의 `foo`, 마크다운은 `doc#헤딩`의 `헤딩`.
    자리(경로)와 정체(이름)를 가르는 축이다."""
    a = str(anchor)
    return a.rsplit("#", 1)[-1] if "#" in a else a.rsplit(".", 1)[-1]


def classify_removed_units(removed, added, archive_segments=()):
    """사라진 단위를 **이동**과 **개명/삭제**로 가른다. 결정론·LLM 0.

    판정 규율 — 지어내지 않는다:
      · 말단 이름이 같고 **내용도 같으면** 이동(`leaf+content`).
      · 말단 이름이 같은 후보가 **유일하면** 이동(`leaf`) — 옮기며 고치는 건 흔하다.
      · 후보가 여럿이면 이동으로 **안 본다**(판정 큐로). 내용이 정확히 하나와 같을 때만 해소.
      · 자리가 그대로인데 이름만 바뀐 건 이동이 아니다 — 재바인딩(`rebind_proposals`) 몫.
    `archived`는 목적지가 봉인 구역인지 — 그러면 **현행 평면에서 내리되 지식은 보존**한다
    (tombstone은 "없어졌다", archived는 "여기 있지만 현행이 아니다")."""
    def _is_archived(u):
        parts = str(u.get("file") or u.get("anchor") or "").replace(".", "/").split("/")
        return any(s in parts for s in archive_segments or ())

    # ── 1단계: **파일이 옮겨졌나.** 심볼은 파일을 따라간다.
    def _base(f):
        return str(f).rsplit("/", 1)[-1]

    old_files = {u.get("file") for u in removed if u.get("file")}
    new_files = {u.get("file") for u in added if u.get("file")}
    gone, born = old_files - new_files, new_files - old_files
    moved_files = {}
    for f in sorted(gone):
        cand = [g for g in sorted(born) if _base(g) == _base(f)]
        if len(cand) == 1:                       # 동명 파일이 여럿이면 지어내지 않는다
            moved_files[f] = cand[0]
    added_by_file = {}
    for a in added:
        added_by_file.setdefault(a.get("file"), []).append(a)

    by_leaf = {}
    for a in added:
        by_leaf.setdefault((a.get("kind"), _leaf(a["anchor"])), []).append(a)

    moved, rest = [], []
    for r in sorted(removed, key=lambda x: x["anchor"]):
        dest = moved_files.get(r.get("file"))
        if dest:
            # 파일이 옮겨졌다 — 그 파일 안에서 같은 이름·같은 종류를 찾는다.
            # 못 찾으면 파일은 옮겨졌지만 **그 심볼은 사라진 것**이라 tombstone이 맞다.
            same = [c for c in added_by_file.get(dest, [])
                    if c.get("kind") == r.get("kind")
                    and _leaf(c["anchor"]) == _leaf(r["anchor"])]
            if len(same) == 1:
                moved.append({"from": r["anchor"], "to": same[0]["anchor"],
                              "kind": r.get("kind"), "basis": "file",
                              "archived": _is_archived(same[0])})
                continue
        cands = [c for c in by_leaf.get((r.get("kind"), _leaf(r["anchor"])), [])
                 if c["anchor"] != r["anchor"]]
        # 자리가 그대로면(같은 부모) 이동이 아니라 개명이다
        parent = lambda a: str(a).rsplit("#", 1)[0] if "#" in str(a) \
            else str(a).rsplit(".", 1)[0]
        cands = [c for c in cands if parent(c["anchor"]) != parent(r["anchor"])]
        hit, basis = None, None
        exact = [c for c in cands if c.get("content") == r.get("content")]
        if len(exact) == 1:
            hit, basis = exact[0], "leaf+content"
        elif len(cands) == 1:
            hit, basis = cands[0], "leaf"
        if hit is None:
            rest.append(r)
            continue
        moved.append({"from": r["anchor"], "to": hit["anchor"], "kind": r.get("kind"),
                      "basis": basis, "archived": _is_archived(hit)})
    moved.sort(key=lambda m: m["from"])
    rest.sort(key=lambda r: r["anchor"])
    return {"moved": moved, "renamed_or_deleted": rest,
            "stats": {"moved": len(moved), "renamed_or_deleted": len(rest),
                      "archived": sum(1 for m in moved if m["archived"])}}


# ── 실행 유틸 ──────────────────────────────────────────────────────────

def _load_decisions(corpus, here):
    reg = yaml.safe_load((here / "registry.yaml").read_text(encoding="utf-8"))
    root = (here / reg["corpora"][corpus]["source"]).resolve()
    fmt = reg["corpora"][corpus].get("decision_format")
    # ★원천이 없으면 대조하지 않는다. 빈 결정 목록으로 돌면 모든 결정 참조가 '죽은 참조'로
    #   읽힌다 — 모르는 것을 통과(또는 실패)라 부르는 셈이고, 산출물이 기계마다 달라진다.
    if not root.is_dir():
        raise FileNotFoundError(f"결정 원천 없음({reg['corpora'][corpus]['source']}) — "
                                "원천을 장착하면 대조한다")
    decisions = []
    r = discover(corpus, root, reg)
    for item in r["found"]:
        parsed = parse(fmt, (root / item["file"]).read_text(encoding="utf-8"),
                       scope=item["scope"])
        decisions.extend(parsed["decisions"])
    return decisions


def _snap_dir(here, corpus):
    from corpus import canon_dir
    return canon_dir(corpus) / "tier-a"


def _load_snapshot(here, corpus, sha):
    p = _snap_dir(here, corpus) / sha / "concepts.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def main():
    here = Path(__file__).parent
    corpus = "acme-docs"
    if len(sys.argv) > 1 and sys.argv[1] == "diff":
        a, b = sys.argv[2], sys.argv[3]
        d = snapshot_diff(_load_snapshot(here, corpus, a)["concepts"],
                          _load_snapshot(here, corpus, b)["concepts"])
        print(f"diff {a} → {b}: {d['stats']}")
        for k in ("added", "removed", "changed"):
            for c in d[k][:20]:
                print(f"  {k}: [{c['kind']}] {c.get('scope')}/{c['anchor']}")
        return

    # 최신 = mtime 기준 (SHA 사전순은 시간순이 아님 — 0a0a001<5a0a004 오선택 실측 교훈)
    shas = sorted((p for p in _snap_dir(here, corpus).iterdir() if p.is_dir()),
                  key=lambda p: p.stat().st_mtime)
    sha = sys.argv[1] if len(sys.argv) > 1 else shas[-1].name
    snap = _load_snapshot(here, corpus, sha)
    decisions = _load_decisions(corpus, here)
    reg = yaml.safe_load((here / "registry.yaml").read_text(encoding="utf-8"))
    archive_segments = reg["corpora"][corpus].get("archive_segments")   # 데이터 구동
    rep = dead_ref_report(snap["concepts"], decisions, archive_segments=archive_segments)

    out = _snap_dir(here, corpus) / sha / "integrity.yaml"
    out.write_text(yaml.safe_dump({"meta": {"snapshot": sha, **rep["stats"]},
                                   "dead": rep["dead"], "ambiguous": rep["ambiguous"],
                                   "archived": rep["archived"]},
                                  allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"integrity {corpus}@{sha}: 참조 {rep['stats']['refs_checked']}개 검사, "
          f"죽은 참조 {rep['stats']['dead']}건 · 모호 인용 {rep['stats']['ambiguous']}건 "
          f"· 아카이브 분리 {rep['stats']['archived']}건 → {out.name}")
    by_scope = {}
    for d in rep["dead"]:
        by_scope.setdefault(d["scope"], []).append(d)
    for sc in sorted(by_scope, key=str):
        print(f"  [{sc}] {len(by_scope[sc])}건")
        for d in by_scope[sc][:6]:
            r = f" → 재해소 제안 {d['rescue']}" if d["rescue"] else ""
            print(f"    {d['from_id']} → {d['ref']} ({d['ref_kind']}){r}")


if __name__ == "__main__":
    main()
