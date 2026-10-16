"""아카이브 종결 축 — 문서가 가리키는 해결 기록을 따라간다. 결정론·LLM 0.

여기서 하는 일은 배제를 푸는 게 아니다(그러면 86% 홍수가 돌아온다). 문서가 **자기
손으로 적어 둔 포인터**를 읽을 뿐이다:

    ### D1. 제품 분석 … → [24 상세 문서 §D1](../작업완료/24-scalability-product-infra.md)

마크다운 링크라 파싱은 결정론이고, 아카이브 구역 판정은 registry `archive_segments`
선언에서 온다(엔진은 `작업완료`라는 이름을 모른다 — 제네릭 원칙).

판정하지 않는다. "이 주장은 종결 문서를 가리키는데 코퍼스가 그걸 안 읽었다"까지만
말하고, 확신도를 **강등**한다. 반증을 안 읽은 주장이 확정 사실 자리에 앉는 걸 막는
게 목적이지, 반대 결론을 지어내는 게 아니다."""
from __future__ import annotations

import re

from ingest import slug

_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

# 강등표 — 한 칸씩만 내린다(판정이 아니라 보류 표시).
_COMMITMENT_DOWN = {"frozen": "working"}
_CONFIDENCE_DOWN = {"high": "medium"}


def _is_archive_path(path, archive_segments):
    if not archive_segments:
        return False
    segs = {slug(p) for p in str(path).split("/")}
    return bool(segs & {slug(a) for a in archive_segments})


def archive_links_in(text, archive_segments):
    """텍스트 안 마크다운 링크 중 아카이브 구역을 가리키는 것. 순서 보존·중복 제거.

    산문 언급(`작업완료 폴더 참고`)은 안 잡는다 — 링크만이 기계가 따라갈 수 있는
    포인터고, 언급으로 종결을 주장하면 지어냄이 된다."""
    out, seen = [], set()
    for href in _MD_LINK.findall(str(text or "")):
        if href in seen or not _is_archive_path(href, archive_segments):
            continue
        seen.add(href)
        out.append(href)
    return out


def _target_doc(href):
    """링크 경로 → 문서 신원(번호 접두 제거·`.md` 제거·`../` 정리)."""
    parts = [p for p in str(href).split("/") if p not in ("", ".", "..")]
    if parts and parts[-1].endswith(".md"):
        parts[-1] = parts[-1][:-3]
    return "/".join(slug(p) for p in parts)


def _live(frag):
    return not frag.get("removed_at") and not frag.get("superseded_at")


def archive_reference_report(bodies, archive_segments, ingested_docs=None):
    """{ok, unresolved} — 살아있는 조각이 아카이브 문서를 가리키는데 그 문서가
    코퍼스 밖인 개념 목록. 결정론(anchor·target 정렬).

    `ingested_docs`에 그 문서가 있으면 미해결이 아니다 — 배제를 풀면 저절로 초록이 된다.
    """
    from doc_identity import same_document
    ingested = {_target_doc(d) for d in (ingested_docs or ())}
    unresolved = []
    for anchor in sorted(bodies or {}):
        targets = set()
        for f in bodies[anchor] or []:
            if not _live(f):
                continue
            for src in (f.get("key"), f.get("text")):
                for href in archive_links_in(src, archive_segments):
                    t = _target_doc(href)
                    if t and not any(same_document(t, i) for i in ingested):
                        targets.add(t)
        if targets:
            unresolved.append({"anchor": anchor, "targets": sorted(targets)})
    return {"ok": not unresolved, "unresolved": unresolved}


def demote_unresolved_claims(concepts, bodies, archive_segments, ingested_docs=None):
    """반증 문서를 안 읽은 주장의 확신도를 한 칸 내린다. 결정론·멱등.

    ★강등만 한다. 올리지 않는다 — 종결 문서를 못 읽었다는 건 "틀렸다"가 아니라
    "확정할 근거가 없다"이므로, 반대 결론을 지어내는 대신 확정 자리에서 내린다.
    `unresolved_reference`로 무엇을 못 읽었는지 남겨 사람이 판정할 수 있게 한다."""
    flagged = {x["anchor"]: x["targets"]
               for x in archive_reference_report(bodies, archive_segments,
                                                 ingested_docs)["unresolved"]}
    out = []
    for c in concepts or []:
        targets = flagged.get(c.get("anchor"))
        if not targets:
            out.append(c)
            continue
        out.append({**c,
                    "commitment": _COMMITMENT_DOWN.get(c.get("commitment"), c.get("commitment")),
                    "confidence": _CONFIDENCE_DOWN.get(c.get("confidence"), c.get("confidence")),
                    "unresolved_reference": targets})
    return out
