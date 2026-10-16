"""S1 정본 부분집합 선택 — canon-aware 추출에 주입할 정본만 고른다(결정론).
전체(2000+) 대신: 같은 제품군 scope ∪ 공유 tier ∪ 이름/토큰 매칭. 비용 유한.
설계: docs/2-method/canon-aware-structuring-pipeline-design.md §4."""
from __future__ import annotations
import re


def _product_prefix(scope):
    """'prime-commerce/meadow/meadow-admin' -> 'prime-commerce/meadow' (제품군 = 앞 2세그먼트)."""
    parts = (scope or "").split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else (scope or "")


def _scope_under(scope, prefix):
    """scope가 prefix 세그먼트 하위인지(문자열 부분일치 아닌 '/' 경계 기준)."""
    return bool(prefix) and (scope == prefix or scope.startswith(prefix + "/"))


def _tokens(text):
    return {w.lower() for w in re.findall(r"[\w가-힣]+", str(text)) if len(w) >= 2}


def _name_key(name):
    """이름매칭용 식별자 부분만 — 첫 '(' 또는 '—' 이전(서술형 꼬리 절단)."""
    return re.split(r"[(（—]", str(name))[0]


def _anchor_cited(anchor, sec_texts_lower):
    """anchor 폴백 매칭(핫픽스 8.5 정밀화) — 토큰 교집합이 아니라 "전체 식별자 인용" 기준.
    교차제품 주입의 실제 사용례는 문서가 개념 식별자를 그대로 인용할 때다
    ("StoreType 값을…"·"[INV-59]에 따라"). 토큰 교집합은 "화면"·"inv"·"01" 같은
    짧고 흔한 조각이 우연히 겹쳐 과다선택을 일으켰다(실측) — 그래서 전체
    소문자 문자열이 섹션 텍스트에 부분문자열로 통째로 있을 때만 매칭한다.
    가드: len(anchor)>=4 AND 순수 숫자 아님(우연 substring 차단)."""
    a = str(anchor)
    if len(a) < 4 or a.isdigit():
        return False
    al = a.lower()
    return any(al in t for t in sec_texts_lower)


def _scope_rank(scope, app_scope):
    """anchor 충돌 시 승자 판정용 순위(작을수록 우선) — app_scope 친화도.
    0=정확히 이 앱 · 1=이 앱 하위(source/ 아카이브 등) · 2=그 밖(제품군 타 앱·공유 tier).
    ★왜 필요한가(비공개 코퍼스 실측): anchor는 스코프 간 유일하지 않다(상당수가 충돌).
    기존 `picked[anchor] = c`는 '입력 순서상 마지막 승'이라, 일반 앱 추출인데
    `spec§개요 · 정체성` 자리에 같은 제품의 admin 앱 레코드가 주입됐다
    — canon-aware 정렬이 다른 앱 개념을 겨냥하게 만드는 조용한 오염. 순위+scope 정렬
    tie-break로 입력 순서와 무관하게 결정론적으로 이 앱 것을 고른다."""
    scope = scope or ""
    if app_scope and scope == app_scope:
        return 0
    if _scope_under(scope, app_scope):
        return 1
    return 2


def canon_collisions(app_scope, sections, canon_concepts, shared_tiers=("foundations",),
                     merged_scopes=()):
    """진단 — 선택된 부분집합에서 anchor 충돌로 **버려진** 레코드 보고(동작 불변).
    반환: [{anchor, kept_scope, dropped_scopes}] (anchor 정렬). 침묵 소실 감시용:
    canon-context.yaml은 anchor 1개당 1레코드라(=align target 공간) 충돌분은 필연적으로
    사라지는데, 몇 개가 왜 사라졌는지 기록이 없으면 주입 누락을 아무도 모른다."""
    picked = _select_index(app_scope, sections, canon_concepts, shared_tiers, merged_scopes)
    kept = {c["anchor"]: c for c in picked}
    dropped = {}
    for c in _candidates(app_scope, sections, canon_concepts, shared_tiers, merged_scopes):
        a = c["anchor"]
        if kept.get(a) is not c:
            dropped.setdefault(a, []).append(c.get("scope") or "")
    return [{"anchor": a, "kept_scope": kept[a].get("scope"),
             "dropped_scopes": sorted(dropped[a])} for a in sorted(dropped)]


def _candidates(app_scope, sections, canon_concepts, shared_tiers, merged_scopes=()):
    """선택 조건(앱·선언 병합 scope·공유 tier·이름/anchor 매칭)을 통과한 후보 — 충돌 해소 전."""
    scopes = (app_scope,) + tuple(merged_scopes or ())
    sec_tokens = set()
    sec_texts_lower = []
    for s in sections:
        text = s.get("text", "")
        sec_tokens |= _tokens(text)
        sec_texts_lower.append(str(text).lower())
    out = []
    for c in canon_concepts:
        # ★Tier B(정본 개념)는 **코퍼스 전량** 주입한다 — 좁히지 않는다.
        if c.get("tier") == "B":
            out.append(c)
            continue
        scope = c.get("scope") or ""
        in_product = any(_scope_under(scope, p) for p in scopes)
        in_shared = any(_scope_under(scope, t) for t in shared_tiers)
        name = c.get("name")
        if name:
            # depth-stack 스타일: name에서 서술형 꼬리를 자르고 토큰 교집합(기존 방식 유지 — 문제없었음).
            name_match = bool(_tokens(_name_key(name)) & sec_tokens)
        else:
            # 0a0a001 스냅샷 스타일(name 없음): anchor 전체 식별자 인용 기준(토큰 교집합 아님).
            name_match = _anchor_cited(c.get("anchor", ""), sec_texts_lower)
        if in_product or in_shared or name_match:
            out.append(c)
    return out


def _select_index(app_scope, sections, canon_concepts, shared_tiers, merged_scopes=()):
    """후보 → anchor당 1레코드(승자). 승자 = (scope 친화도, scope 문자열) 최소 —
    입력 순서 무관 결정론."""
    picked = {}
    for c in _candidates(app_scope, sections, canon_concepts, shared_tiers, merged_scopes):
        a = c["anchor"]
        key = (_scope_rank(c.get("scope"), app_scope), c.get("scope") or "")
        cur = picked.get(a)
        if cur is None or key < (_scope_rank(cur.get("scope"), app_scope),
                                 cur.get("scope") or ""):
            picked[a] = c
    return [picked[a] for a in sorted(picked)]


def select_canon(app_scope, sections, canon_concepts, shared_tiers=("foundations",),
                 merged_scopes=()):
    """반환: 주입용 정본 부분집합(anchor 정렬, anchor당 1레코드). 결정론.
    입력: sections=[{text,...}] · canon_concepts=[{anchor,name,scope,...}] · app_scope='platform/product/app'.
    anchor 충돌은 _scope_rank로 이 앱 것을 우선(진단은 canon_collisions)."""
    return _select_index(app_scope, sections, canon_concepts, shared_tiers, merged_scopes)
