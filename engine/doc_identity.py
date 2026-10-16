"""문서 정체성 층 — 경로 깊이에서 독립한 문서 신원 (읽기 시점 정규화).

`ingest.doc_slug`는 전체 상대경로를 정체성으로 쓴다. 그 docstring이 이미 옳은 원칙을
말한다 — "폴더 번호는 순번이라 재배정된다 → 정체성은 slug". 그런데 **경로 깊이도
순번과 같다**: 코퍼스 루트는 언제든 옮겨진다.

층위는 `decision_alias`와 같다: **원장·앵커는 무수정**, 매칭 시점에만 정규화한다.
앵커는 정본에 들어간 뒤엔 못 고친다(바꾸면 계보가 끊긴다)."""
from __future__ import annotations


def _segments(doc_slug):
    return [p for p in str(doc_slug or "").split("/") if p]


def _suffixes(segs):
    """짧은 것부터 — basename → … → 전체 경로."""
    return ["/".join(segs[i:]) for i in range(len(segs) - 1, -1, -1)]


def is_suffix_of(short, long):
    """`short`가 `long`의 **경로 조각** 접미인가. 문자열 접미가 아니다 —
    `my-notes`는 `notes`로 끝나지만 다른 문서다."""
    a, b = _segments(short), _segments(long)
    return bool(a) and len(a) <= len(b) and b[len(b) - len(a):] == a


def same_document(a, b):
    """두 doc_slug이 같은 문서인가 — 한쪽이 다른 쪽의 경로 접미면 같다.

    스냅샷 문맥 없이 쓰는 짝 비교다(정본 병합·별칭 조회용). 스냅샷 안에서
    basename이 충돌할 수 있는 상황이면 `doc_identity_map`을 써라 — 그쪽이
    공존 여부를 보고 안 합친다."""
    if not _segments(a) or not _segments(b):
        return False
    return is_suffix_of(a, b) or is_suffix_of(b, a)


def canonical_doc(doc_slug):
    """문맥 없는 최소형 = basename. 충돌 판정이 필요하면 `doc_identity_map`."""
    segs = _segments(doc_slug)
    return segs[-1] if segs else ""


def split_fragment_key(key):
    """조각 key → (doc_slug, 나머지). 문서 축이 없는 키는 `(None, None)`.

    마크다운 조각 키는 `<doc_slug>#<heading_slug>|<field>`다. 코드 조각은
    `lib.analytics.identifyUser|fields.signature`처럼 점 표기 모듈 경로라 `#`이 없고,
    게이트 인용은 그냥 `quote`다 — 둘 다 문서 축이 없으니 건드리지 않는다."""
    s = str(key or "")
    if "#" not in s:
        return (None, None)
    doc, rest = s.split("#", 1)
    return (doc, "#" + rest) if doc else (None, None)


def key_alias_map(prev_keys, now_keys):
    """{옛 조각 key: 현행 조각 key} — 루트 이동으로 갈린 신원을 잇는다.

    공존 판정의 진실 원천은 **현행 스냅샷(now)**이다. prev까지 넣어 지도를 만들면
    옛 사본 자신이 형제로 잡혀 충돌 처리돼 병합이 무산된다(자기 그림자에 걸림).

    규율(원장과 동일): 현행 문서에 **정확히 하나** 걸릴 때만 잇는다.
      - 0개 → 진짜 삭제. 별칭을 만들지 않는다(삭제는 삭제로 남아야 한다).
      - 2개 이상 → 모호. 지어내지 않는다.
    섹션·필드(`#heading|field`)는 완전일치를 요구한다 — 문서만 같고 섹션이 다르면
    다른 조각이다."""
    now_docs, now_by_ident = set(), {}
    for k in now_keys or ():
        doc, rest = split_fragment_key(k)
        if doc is None:
            continue
        now_docs.add(doc)
        now_by_ident.setdefault((doc, rest), k)

    out = {}
    for k in sorted(set(prev_keys or ())):
        doc, rest = split_fragment_key(k)
        if doc is None or doc in now_docs:
            continue                              # 코드/인용 키거나 이미 정렬됨
        cands = sorted(d for d in now_docs if same_document(doc, d))
        if len(cands) != 1:
            continue                              # 삭제이거나 모호 — 지어내지 않는다
        target = now_by_ident.get((cands[0], rest))
        if target and target != k:
            out[k] = target
    return out


def realign_bodies(prev_bodies, fresh_bodies, visible_units=None):
    """옛 네임스페이스 조각 key를 현행으로 정렬한다. 결정론·내용 무수정.

    변경/삭제 판정(`fold_fragment_versions`·`tombstone_lost_fragments`) **직전**에
    한 번만 건다. 판정 자체는 손대지 않는다 — 비교 대상을 같은 좌표로 옮길 뿐이라
    진짜 삭제는 그대로 삭제로 남는다(별칭이 안 생기므로).

    스냅샷은 소스에서 결정론적으로 나온 것이라 옛 좌표가 섞일 수 없다."""
    if visible_units is not None:
        now_docs = {d for u in visible_units
                    for d in (split_fragment_key(u)[0],) if d}
    else:
        now_docs = {d for fs in (fresh_bodies or {}).values() for f in (fs or [])
                    for d in (split_fragment_key(f.get("key"))[0],) if d}
    if not now_docs:
        return dict(prev_bodies or {})

    prev_docs = {d for fs in (prev_bodies or {}).values() for f in (fs or [])
                 for d in (split_fragment_key(f.get("key"))[0],) if d}
    fallback = {}
    for d in prev_docs:
        if d in now_docs or any(same_document(d, n) for n in now_docs):
            continue
        kin = sorted((k for k in prev_docs if same_document(d, k)),
                     key=lambda x: (-len(x.split("/")), x))
        if len(kin) > 1 and len(kin[0].split("/")) > len(d.split("/")):
            fallback[d] = kin[0]

    cache = {}

    def _canon_key(key):
        doc, rest = split_fragment_key(key)
        if doc is None or doc in now_docs:
            return key
        if doc not in cache:
            cands = sorted(d for d in now_docs if same_document(doc, d))
            cache[doc] = cands[0] if len(cands) == 1 else fallback.get(doc)
        target = cache[doc]
        return f"{target}{rest}" if target else key

    return {a: [({**f, "key": nk} if (nk := _canon_key(f.get("key"))) != f.get("key") else f)
                for f in (fs or [])]
            for a, fs in (prev_bodies or {}).items()}


def doc_identity_map(doc_slugs):
    """{doc_slug: 정체성} — 각 문서를 그 집합 안에서 유일해지는 최소 접미로 줄인다.

    결정론: 입력이 같으면 출력이 같다(집합 연산만, 순회 순서 무관).
    고정점: 정체성을 다시 넣으면 자기 자신이 나온다.
    """
    slugs = sorted({s for s in (doc_slugs or ()) if _segments(s)})
    seg_map = {s: _segments(s) for s in slugs}
    out = {}
    for s in slugs:
        others = [seg_map[o] for o in slugs if o != s]
        chosen = None
        for suf in _suffixes(seg_map[s]):
            suf_segs = _segments(suf)
            n = len(suf_segs)
            # 이 접미가 **다른 문서**의 접미이기도 하면 구분이 안 된다
            if any(len(o) >= n and o[len(o) - n:] == suf_segs for o in others):
                continue
            chosen = suf
            break
        out[s] = chosen if chosen is not None else s
    return out
