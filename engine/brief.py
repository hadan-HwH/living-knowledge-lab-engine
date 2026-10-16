"""정본 소비 경로 — 한 앱의 현재 상태를 한 화면으로 조립한다. 결정론·LLM 0·읽기 전용.

★부수 목적이 하나 더 있다 — **층별 관련성 계측기**. 각 블록은 자기가 어느 층에서 왔는지
밝히고, `contribution`이 층별 기여 항목 수를 낸다. 어떤 층이 전 앱에서 0이면 그 층은 지금
값을 못 내고 있다는 **데이터**다(감이 아니라). 이게 P4(덜어내기)의 판단 근거가 된다.

침묵 금지: 빈 블록은 사라지지 않고 **왜 비었는지**를 말한다. "재료가 없다"와 "재료는
있는데 해당 없음"은 다른 진단이고, 그 구별이 층을 자를지 말지를 가른다."""
from __future__ import annotations

#: (블록 이름, 출처 층) — 순서 고정. 조건부로 사라지지 않는다.
_BLOCKS = [("정체성", "tier_a"), ("조항", "tier_a"), ("개념", "tier_b"),
           ("현재 유효 결정", "decision"), ("미결", "decision"), ("갭", "tier_b"),
           ("침식", "integrity"), ("리뷰 대기", "review")]

#: 사람이 반드시 봐야 하는 것 — 자동 편입 계약 이후 new/ambiguous는 여기 안 온다.
_REVIEW_WAS = {"quote_gate_failed", "phantom_target"}


def _in_scope(rows, scope):
    return [r for r in rows if r.get("scope") == scope]


def _block(name, layer, items, empty_reason=None, **extra):
    return {"name": name, "layer": layer, "count": len(items), "items": items,
            "empty_reason": (empty_reason if not items else None), **extra}


def build(scope, tier_a, stack, events, integrity, adjudications,
          valid_at, known_at, why=False):
    """한 scope의 브리핑 — 기본은 '어떻게', why=True면 '왜'까지. 전부 결정론."""
    from queries import project_all, open_decisions

    stack = stack or {}
    concepts = _in_scope(stack.get("concepts") or [], scope)
    live = [c for c in concepts if not c.get("removed_at")]
    removed = len(concepts) - len(live)

    a_in = _in_scope(tier_a or [], scope)
    spec = [c for c in a_in if c.get("kind") == "spec_section"]
    a_gaps = [c for c in a_in if c.get("kind") == "gap"]   # Tier A가 이미 표시한 갭
    arts = [c for c in a_in if c.get("kind") == "article"]

    # 결정층 — 입력이 아예 없는 것과 "있는데 활성 0"은 다른 진단이라 구별해 말한다.
    if events:
        proj = project_all(events, valid_at, known_at, scope)
        active = proj["active"]
        opens = open_decisions(events, valid_at, known_at, scope)["open"]
        dec_reason = open_reason = "이 scope에 활성 결정 없음(결정층은 읽었다)"
    else:
        active, opens = [], []
        dec_reason = open_reason = "결정층 입력이 없다 — 이 코퍼스는 결정 원장 미배선"

    gaps = a_gaps + [c for c in live if c.get("basis") == "implemented_without_mandate"] + \
           [{**h, "anchor": h.get("sid")} for h in (stack.get("held") or {}).get("gap") or []
            if str(h.get("sid", "")).split("#")[0] == scope.split("/")[-1]
            or str(h.get("sid", "")).startswith(scope)]

    review = [{**c, "why": "needs_review"} for c in live if c.get("needs_review")] + \
             [{**a, "anchor": a.get("sid"), "why": a.get("was")}
              for a in (adjudications or []) if a.get("was") in _REVIEW_WAS]

    erosion = [d for d in (integrity or {}).get("dead") or [] if d.get("scope") == scope] + \
              [d for d in (integrity or {}).get("ambiguous") or [] if d.get("scope") == scope]

    # 이력 평면 — 요청할 때만. 지나간 현행(history)과 tombstone이 여기 산다.
    past = [{**c, "why": "history"} for c in concepts if c.get("history")] + \
           [{**c, "why": "tombstone"} for c in concepts if c.get("removed_at")]

    blocks = [
        _block("정체성", "tier_a", spec, "정본 스냅샷에 이 scope의 spec 섹션이 없다"),
        _block("조항", "tier_a", arts, "이 scope에 조항이 0건 — 문서 미착수이거나 규약 없음"),
        _block("개념", "tier_b", live, "Tier B 추출을 아직 안 돌렸다", removed=removed),
        _block("현재 유효 결정", "decision", active, dec_reason),
        _block("미결", "decision", opens, open_reason),
        _block("갭", "tier_b", gaps, "해당 없음 — 코드-문서 갭으로 표시된 개념이 없다"),  # noqa: E501
        _block("침식", "integrity", erosion, "해당 없음 — 죽은 참조·모호 참조 0"),
        _block("리뷰 대기", "review", review, "해당 없음 — 사람이 볼 것이 없다"),
    ] + ([_block("이력", "history", past,
                 "이력 없음 — 마이그레이션 중이거나 아직 바뀐 적이 없다(정상)")]
         if why else [])
    # ★층별 기여도는 **distinct 항목 수**다. 한 항목이 여러 블록에 나오면(예: 갭 개념은
    # '개념'과 '갭' 양쪽) 단순 합산은 그 층을 부풀린다 — 관련성 지표가 부풀면 P4에서
    # 잘라야 할 층을 못 자른다.
    # 이력 평면은 선택 블록이라 _BLOCKS(고정 8종)에 없다 — 층 집계는 실제
    # 블록에서 유도한다(선언과 실물이 갈리면 조용히 KeyError가 난다).
    seen = {b["layer"]: set() for b in blocks}
    for b in blocks:
        for i, it in enumerate(b["items"]):
            seen[b["layer"]].add(it.get("anchor") or it.get("target")
                                 or it.get("from_id") or f"{b['name']}#{i}")
    contribution = {layer: len(v) for layer, v in seen.items()}
    return {"scope": scope, "as_of": {"valid_at": valid_at, "known_at": known_at},
            "blocks": blocks, "contribution": contribution}


def load_and_build(corpus, app, scope, snap, valid_at, known_at, root=None, why=False):
    """I/O 다리 — 기존 층 산출물만 읽는다(신규 저장소 0). 없는 재료는 빈 것으로 두고
    build가 '왜 비었는지'를 말하게 한다(파일 부재로 크래시하지 않는다)."""
    from pathlib import Path
    import yaml
    from corpus import FIXTURES

    root = Path(root) if root is not None else FIXTURES
    fx = root / corpus

    def _y(path, default=None):
        return yaml.safe_load(open(path)) if Path(path).exists() else (default or {})

    from corpus import tier_a_path, canon_path, canon_dir
    tier_a = (_y(tier_a_path(corpus, snap, root=root)).get("concepts") or []) if snap else []
    integrity = _y(canon_dir(corpus, root=root) / "integrity.yaml")
    stack = _y(canon_path(corpus, root=root))
    # 결정층 — auto 원장이 있으면 쓴다(코퍼스마다 배선 여부가 다르다).
    events = []
    for cand in sorted((fx / "ledger" / "decisions").glob("*/events.auto.yaml")):
        events += _y(cand).get("events") or []
    adj = (_y(fx / "work" / app / "adjudication.yaml").get("queue") or [])
    return build(scope=scope, tier_a=tier_a, stack=stack, events=events,
                 integrity=integrity, adjudications=adj,
                 valid_at=valid_at, known_at=known_at, why=why)


def _label(item):
    """사람이 읽을 한 줄 — anchor는 render가 따로 찍으므로 여기선 **설명**만 낸다.
    Tier A 레코드는 name이 없고 section/content를 갖는다(스키마가 층마다 다르다)."""
    for k in ("name", "section"):
        if item.get(k):
            return str(item[k])
    if item.get("ref"):
        return f"→ {item['ref']} (from {item.get('from_id', '?')})"
    if item.get("option"):
        # ★결정은 자기참조 토큰(`o_INV-D-6913`)이 아니라 **문서 표기**로 읽힌다
        src = (item.get("source") or [None])[0]
        return str(src or item["option"]).lstrip("o_")
    body = " ".join(str(item.get("content") or "").split())
    return body[:70] if body else ""


def render(doc, limit=12):
    """마크다운 1장. 빈 블록도 자리를 지키고 이유를 보여준다."""
    out = [f"# 브리핑 — {doc['scope']}",
           f"> as_of valid_at={doc['as_of']['valid_at']} · known_at={doc['as_of']['known_at']}",
           "", "| 블록 | 층 | 수 |", "|---|---|---|"]
    out += [f"| {b['name']} | {b['layer']} | {b['count']}"
            f"{' (삭제 %d)' % b['removed'] if b.get('removed') else ''} |" for b in doc["blocks"]]
    out.append("")
    for b in doc["blocks"]:
        out.append(f"## {b['name']}  ·  {b['layer']}  ·  {b['count']}건")
        if not b["items"]:
            out.append(f"- _{b['empty_reason']}_")
        else:
            for it in b["items"][:limit]:
                extra = f" — {it['why']}" if it.get("why") else ""
                anchor = it.get("anchor") or it.get("target") or it.get("from_id") or ""
                out.append(f"- `{anchor}` {_label(it)}{extra}".rstrip())
            if len(b["items"]) > limit:
                out.append(f"- … 외 {len(b['items']) - limit}건")
        out.append("")
    out.append("층별 기여: " + " · ".join(f"{k}={v}" for k, v in sorted(doc["contribution"].items())))
    return "\n".join(out)
