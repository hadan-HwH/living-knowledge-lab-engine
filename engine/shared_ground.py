"""공통 지반 축 — 같은 코드를 말하는 두 확정 주장이 서로를 모르는 자리. 결정론·LLM 0.

`crosscheck_concept`은 **한 개념 안**의 층간 값만 대조한다. 두 진술이 서로 다른
개념에 앉으면 구조적으로 만나지 않는다 — wevolley 정본이

    sc-analytics-blind-spot   "analytics 스텁·호출처 0건"       frozen·high
    sc-posthog-http-capture   "PostHog capture HTTP API 전송"    frozen·high

모순을 **판정하지 않는다**(의미 판정은 결정론 밖). "같은 코드를 말하는데 그래프가
둘을 잇지 않았다"까지만 말한다. 허브 공유는 연결로 안 친다 — 실 정본이 정확히
그 모양이었다(둘 다 `sc-funnel-retention-visibility`에 스포크로 붙었을 뿐 서로는 모름)."""
from __future__ import annotations

import re
from itertools import combinations

_BACKTICK = re.compile(r"`([^`\n]+)`")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*(?:/[A-Za-z0-9_.\-]+)*$")
_CODE_EXT = (".d.ts", ".tsx", ".ts", ".jsx", ".js", ".mjs", ".py")


def _live(frag):
    return not frag.get("removed_at") and not frag.get("superseded_at")


def _to_module(token):
    """인용 표기 → 모듈 표기. `lib/analytics.ts` → `lib.analytics` (l1_snapshot과 같은 규칙)."""
    t = str(token or "")
    for ext in _CODE_EXT:
        if t.endswith(ext):
            t = t[: -len(ext)]
            break
    return t.replace("/", ".")


def fragment_units(frags):
    """개념의 **지반** — 살아있는 코드 조각이 딛고 선 단위(심볼 + 그 모듈).

    문서 축은 일부러 뺀다(위 ★ 참조 — 같은 문서 공유는 신호가 아니라 잡음).
    게이트 인용(`quote`)은 출처 축이 없으니 지반이 아니다."""
    out = set()
    for f in frags or []:
        if not _live(f):
            continue
        key = str(f.get("key") or "")
        if not key or key == "quote" or "#" in key:
            continue
        unit = key.split("|", 1)[0]
        out.add(unit)
        if "." in unit:
            out.add(".".join(unit.split(".")[:2]))     # 모듈 축 (`lib.analytics`)
    return out


def fragment_mentions(frags):
    """개념의 본문이 **지목한** 코드 단위 — 백틱 안 식별자를 모듈 표기로 정규화.

    산문은 안 본다. 백틱은 사람이 "이건 코드다"라고 표시한 자리라 기계가 확실히 아는
    것만 고른다(provenance_gate와 같은 규율 — 적게, 확실하게)."""
    out = set()
    for f in frags or []:
        if not _live(f):
            continue
        for tok in _BACKTICK.findall(str(f.get("text") or "")):
            t = tok.strip()
            if _IDENT.match(t):
                out.add(_to_module(t))
    return out


def _edges(relations):
    return {frozenset((r.get("from"), r.get("to"))) for r in (relations or [])
            if r.get("from") and r.get("to")}


def shared_ground_report(concepts, bodies, relations=None):
    """{ok, ungrounded_pairs} — 같은 코드를 말하는데 안 이어진 확정 주장 쌍. 결정론(정렬).

    **양쪽 다 확정(frozen·high)**일 때만 본다. 가설끼리 겹치는 건 정상이고, 그것까지
    담으면 목록이 수백 줄이 되어 아무도 안 본다."""
    confident = [c for c in (concepts or [])
                 if c.get("commitment") == "frozen" and c.get("confidence") == "high"]
    ground = {c["anchor"]: fragment_units((bodies or {}).get(c["anchor"])) for c in confident}
    said = {c["anchor"]: fragment_mentions((bodies or {}).get(c["anchor"])) for c in confident}
    edges = _edges(relations)
    pairs = []
    for a, b in combinations(sorted(ground), 2):
        shared = (said[a] & ground[b]) | (said[b] & ground[a])
        if not shared or frozenset((a, b)) in edges:
            continue
        pairs.append({"a": a, "b": b, "shared_units": sorted(shared)})
    return {"ok": not pairs, "ungrounded_pairs": pairs}
