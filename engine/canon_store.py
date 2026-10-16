"""통합 정본 뷰 — Tier A(결정론 스냅샷) ∪ Tier B(정본 깊은층)를 한 canon 목록으로.

이 모듈이 그 루프를 닫는다. 소비자(canon_select·_slim_canon)는 canon 레코드 모양만
알면 되므로, 두 층의 스키마 차이를 여기 투영 계층에서 흡수하고 소비자는 무수정으로 둔다.
결정론(anchor 정렬)·LLM 0."""
from __future__ import annotations


def depth_to_canon(stack):
    """depth-stack(Tier B) → canon 레코드 목록. 결정론(anchor 정렬).

    투영 규칙:
      anchor/kind/scope/name  그대로 (anchor는 `<app>#<sc-anchor>` sid 형태)
      content                 bodies의 quote 원문 (canon-context의 head 유도원)
      tier                    "B"
    tombstone(`removed_at`)은 **주입하지 않는다** — 죽은 개념을 다시 겨냥하게 만들면
    삭제 표시가 무의미해진다. 이력 조회에는 스택에 그대로 남는다.
    """
    if not stack:
        return []
    bodies = stack.get("bodies") or {}

    def _quote(anchor):
        for entry in bodies.get(anchor) or []:
            if entry.get("key") == "quote":
                return entry.get("text") or ""
        return ""

    out = [{"anchor": c["anchor"], "kind": c.get("kind"), "scope": c.get("scope"),
            "name": c.get("name"), "content": _quote(c["anchor"]), "tier": "B"}
           for c in (stack.get("concepts") or []) if not c.get("removed_at")]
    out.sort(key=lambda c: c["anchor"])
    return out


def merge_canon(tier_a, stack):
    """Tier A 레코드 + depth-stack → 통합 canon. 각 레코드에 `tier` 표시.

    A-vs-B 충돌은 **Tier A가 이긴다**(원문 정본이 파생물보다 권위가 높다)."""
    tier_a = list(tier_a or [])
    taken = {c["anchor"] for c in tier_a}
    depth = [c for c in depth_to_canon(stack) if c["anchor"] not in taken]
    return [{**c, "tier": "A"} for c in tier_a] + depth
