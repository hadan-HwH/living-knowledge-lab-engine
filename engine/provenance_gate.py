"""날조 게이트 — 전달 문서의 주장을 근거로 역추적한다. 결정론·LLM 0.

두 축을 본다:
  ① **출처** — 백틱 안 식별자(코드 심볼·경로)가 정본에도 코퍼스에도 없으면 차단.
  ② **과잉 주장** — 인용한 개념의 `commitment`/수치보다 센 주장을 하면 차단.

산문은 검사하지 않는다. 자연어 사실 판정은 결정론이 아니고, 오탐이 잦으면 사람이
게이트를 끄기 시작한다(이 프로젝트가 이미 아는 실패 경로). 식별자·수치는 기계가
확실히 아는 것만 골라 잡는다 — **적게, 확실하게.**"""
from __future__ import annotations

import re

_FENCE = re.compile(r"```.*?```", re.S)
_BACKTICK = re.compile(r"`([^`\n]+)`")
# 식별자 꼴: 코드 심볼(snake/camel/dotted) 또는 경로. 한글·공백이 섞이면 대상 아님.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*(?:/[A-Za-z0-9_.\-]+)*$")
_ANCHOR = re.compile(r"\b((?:[a-z0-9\-]+#)?sc-[a-z0-9\-]+)\b")
_NUM = re.compile(r"(\d+)\s*(?:곳|개|중복|군데)")
_CERTAIN = re.compile(r"확정|단정|반드시|틀림없|확실히")

# 정본이 이 아래면 "확정" 어투를 쓸 수 없다.
_CERTAIN_OK = {"frozen"}


def checkable_identifiers(md_text):
    """검사 대상 식별자 — 백틱 안, 식별자 꼴인 것만. 정렬·중복 제거.

    코드 펜스는 뺀다(예시는 주장이 아니다). 한글이 섞인 백틱(`상태: 백로그`)도 뺀다."""
    body = _FENCE.sub(" ", str(md_text or ""))
    out = set()
    for tok in _BACKTICK.findall(body):
        t = tok.strip()
        if _IDENT.match(t) and not t.startswith("sc-"):
            out.add(t)
    return sorted(out)


def _canon_haystack(canon):
    """정본에서 근거로 인정할 문자열 풀 — 조각 키 + 조각 텍스트 + 개념 이름."""
    parts = []
    for c in (canon.get("concepts") or []):
        parts.append(str(c.get("name") or ""))
        parts.append(str(c.get("anchor") or ""))
    for frags in (canon.get("bodies") or {}).values():
        for f in frags or []:
            parts.append(str(f.get("key") or ""))
            parts.append(str(f.get("text") or ""))
    return "\n".join(parts)


_DOC_EXT = (".md", ".markdown")


def _path_variants(tok):
    """인용 표기 ↔ 정본 신원의 표기 차이를 흡수한 후보들."""
    from ingest import slug
    out = {tok}
    base = tok
    for ext in _DOC_EXT:
        if base.endswith(ext):
            base = base[: -len(ext)]
            out.add(base)
            break
    if "/" in base:
        out.add("/".join(slug(p) for p in base.split("/")))
    else:
        out.add(slug(base))
    return out


def provenance_report(md_text, canon, extra_sources=()):
    """① 출처 축 — {ok, unsourced}. 근거 없는 식별자 목록(정렬).

    `extra_sources`는 정본 밖 근거(코퍼스 파일 목록·grep 결과 등). 정본이 세상의
    전부는 아니므로, 코퍼스에 실재하면 통과시킨다 — 다만 **아무 데도 없으면 차단**."""
    hay = _canon_haystack(canon) + "\n" + "\n".join(str(s) for s in (extra_sources or ()))
    return _mk(sorted(t for t in checkable_identifiers(md_text)
                      if not any(v in hay for v in _path_variants(t))))


def _mk(unsourced):
    return {"ok": not unsourced, "unsourced": unsourced}


def overclaim_report(md_text, canon):
    """② 과잉 주장 축 — {ok, conflicts}. 인용한 개념보다 센 주장만 본다.

    인용하지 않은 개념과는 대조하지 않는다 — 없는 연결을 지어내면 오탐이 된다."""
    body = _FENCE.sub(" ", str(md_text or ""))
    by_anchor = {c.get("anchor"): c for c in (canon.get("concepts") or [])}
    suffix = {str(a).split("#")[-1]: a for a in by_anchor}
    conflicts = []
    for raw in sorted(set(_ANCHOR.findall(body))):
        anchor = raw if raw in by_anchor else suffix.get(raw.split("#")[-1])
        if not anchor:
            continue
        c = by_anchor[anchor]
        # ★수치는 **인용한 문장** 안에서만 대조한다(실 문서 오탐 1건).
        # 문서 전체를 훑으면 다른 문단의 숫자가 엉뚱한 개념에 붙어 거짓 충돌이 난다
        # (`sc-fix-at-choke-point`의 8·65에 다른 항목의 "5중복"이 붙었다).
        canon_nums = sorted({int(n) for n in _NUM.findall(str(c.get("name") or ""))})
        doc_nums = sorted({int(n) for s in _sentences_citing(body, raw)
                           for n in _NUM.findall(s)})
        row = {"anchor": anchor}
        if canon_nums and doc_nums and not (set(canon_nums) & set(doc_nums)):
            row.update({"canon_numbers": canon_nums, "doc_numbers": sorted({int(x) for x in doc_nums})})
        if any(_CERTAIN.search(s) for s in _sentences_citing(body, raw)) \
                and c.get("commitment") not in _CERTAIN_OK:
            row["overclaimed_certainty"] = c.get("commitment")
        if len(row) > 1:
            conflicts.append(row)
    return {"ok": not conflicts, "conflicts": conflicts}


_BLOCK_SPLIT = re.compile(r"\n\s*\n")


def _sentences_citing(body, ref):
    """`ref`를 인용한 **문단**들. 주장의 사정거리를 그 블록으로 묶는다.

    ★한계(정직하게): 한 문단에 개념 둘을 인용하고 수치가 하나면, 그 수치가 어느
    개념 것인지는 **기계가 못 가른다**(의미 판정이라 결정론 밖). 그래서 수치 축은
    차단이 아니라 **경고**다 — 식별자 축(정밀)만 막고, 수치는 사람이 본다.
    오탐으로 막기 시작하면 사람이 게이트를 끈다."""
    return [s for s in _BLOCK_SPLIT.split(body) if ref in s]


def gate_document(md_text, canon, extra_sources=()):
    """전달 전 마지막 관문. {ok, unsourced, conflicts, warnings}."""
    p = provenance_report(md_text, canon, extra_sources)
    o = overclaim_report(md_text, canon)
    return {"ok": p["ok"],
            "unsourced": p["unsourced"],
            "conflicts": o["conflicts"],
            "warnings": [] if o["ok"] else ["수치·확신도 대조는 사람이 확인 (귀속 모호 가능)"]}
