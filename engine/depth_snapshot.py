"""한 SHA 통합 — 본체(넓이) + 깊은층을 하나의 스냅샷으로 묶고 침식 감시를 관통시킨다."""
from __future__ import annotations

import re


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def unify(breadth_concepts, depth, sha):
    """본체 개념 + 깊은층(concepts·relations·bodies) → 한 SHA 통합 스냅샷 문서.

    각 개념에 `layer`(breadth|depth)를 박아 출처를 잃지 않는다. 충돌은 **합치지 않고
    보고**한다 — 조용히 합치면 한쪽이 사라진다(이 리포 상시 규율).

    ★충돌 키는 `(scope, kind, anchor)`다. 좁히는 과정에서 오보를 두 번 걸렀다:
      · anchor 단독 → 130여 건 오보. 아카이브 사본 ↔ 현행 사본이 같은 anchor를 쓴다
        (MSHELF-01·MCART-01·screen:… 계열). anchor는 전역 고유가 아니다.
      · (scope, anchor) → 3건 오보. field(존재)와 state_enum(값)이 같은 anchor를
        공유하는 것은 **설계된 교차**다(존재↔값 자동 연결). Item.Status·
        Promo Code.Status·Staff.Role이 전부 이 패턴이었다.
    남은 정의: 같은 scope·같은 kind에서 같은 anchor = 한쪽이 조용히 사라지는 진짜 충돌.
    """
    out = []
    for c in breadth_concepts:
        out.append({**c, "layer": "breadth"})
    for c in (depth.get("concepts") or []):
        out.append({**c, "layer": "depth"})
    seen, collisions = set(), []
    for c in out:
        key = (str(c.get("scope")), str(c.get("kind")), c["anchor"])
        if key in seen and key not in collisions:
            collisions.append(key)
        seen.add(key)
    out.sort(key=lambda c: (c["layer"], str(c.get("scope")), c["anchor"]))
    return {"meta": {"source_sha": sha,
                     "breadth": sum(1 for c in out if c["layer"] == "breadth"),
                     "depth": sum(1 for c in out if c["layer"] == "depth"),
                     "generator": "depth_snapshot.py (기계 생성 — 손 편집 금지)"},
            "concepts": out,
            "relations": list(depth.get("relations") or []),
            "bodies": dict(depth.get("bodies") or {}),
            "collisions": [{"scope": s, "kind": k, "anchor": a}
                           for s, k, a in sorted(collisions)]}


def depth_integrity(unified, source_texts):
    """통합 스냅샷의 깊은층 침식 — 관계 끝점 미실존 + 조각 근거(quote) 소실.

    source_texts: 현재 원문 텍스트 조각들(정규화 전 원본 그대로 넘겨도 된다).
                  비어 있으면 전건 실효 = fail-closed(못 잰 것을 통과로 세지 않는다).
    """
    anchors = {c["anchor"] for c in unified["concepts"]}
    depth_anchors = {c["anchor"] for c in unified["concepts"] if c["layer"] == "depth"}
    corpus = [_norm(t) for t in (source_texts or [])]

    dangling = []
    for r in unified["relations"]:
        missing = [e for e in (r.get("from"), r.get("to")) if e and e not in anchors]
        if missing:
            dangling.append({**r, "missing": missing})

    stale = []
    for anchor, body in sorted(unified["bodies"].items()):
        for frag in (body or []):
            q = _norm(frag.get("text"))
            if q and not any(q in c for c in corpus):
                stale.append({"anchor": anchor, "key": frag.get("key"), "quote": q})
    return {"dangling": dangling, "stale_quotes": stale,
            "stats": {"concepts": len(depth_anchors),
                      "relations": len(unified["relations"]),
                      "dangling": len(dangling), "stale_quotes": len(stale)}}


def main(argv=None):
    """usage: depth_snapshot.py <sha> [corpus]  — 한 SHA 통합 + 깊은층 침식 리포트."""
    import sys
    import yaml
    from pathlib import Path

    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        raise SystemExit(main.__doc__)
    sha = argv[1]
    corpus = argv[2] if len(argv) > 2 else "acme-docs"
    here = Path(__file__).parent
    ld = lambda p: yaml.safe_load(Path(p).read_text(encoding="utf-8"))

    from corpus import tier_a_path, canon_path, canon_dir
    snap_dir = canon_dir(corpus)
    breadth = ld(tier_a_path(corpus, sha))["concepts"]
    depth = ld(canon_path(corpus))
    u = unify(breadth, depth, sha=sha)

    reg = ld(here / "registry.yaml")
    root = (here / reg["corpora"][corpus]["source"]).resolve()
    texts = [p.read_text(encoding="utf-8", errors="ignore")
             for p in sorted(root.rglob("*.md")) if ".git" not in p.parts]
    rep = depth_integrity(u, texts)

    (snap_dir / "unified.yaml").write_text(
        yaml.safe_dump({"meta": {**u["meta"], "depth_source": "canon/concepts.yaml",
                                 "collisions": len(u["collisions"])},
                        "collisions": u["collisions"], "concepts": u["concepts"],
                        "relations": u["relations"], "bodies": u["bodies"]},
                       allow_unicode=True, sort_keys=False), encoding="utf-8")
    (snap_dir / "depth-integrity.yaml").write_text(
        yaml.safe_dump({"meta": {"snapshot": sha, "source_files": len(texts),
                                 **rep["stats"]},
                        "dangling": rep["dangling"], "stale_quotes": rep["stale_quotes"]},
                       allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"통합 {corpus}@{sha}: 본체 {u['meta']['breadth']} + 깊은층 {u['meta']['depth']} "
          f"· 충돌 {len(u['collisions'])} → unified.yaml")
    print(f"깊은층 침식: 관계 {rep['stats']['relations']} 중 dangling {rep['stats']['dangling']} "
          f"· 조각 근거 소실 {rep['stats']['stale_quotes']} (원문 {len(texts)}파일 대조) "
          f"→ depth-integrity.yaml")
    if rep["stats"]["stale_quotes"] == 0:
        print("  ※ quote 실재는 최신성의 증거가 아니다 — 낡은 이월 개념도 quote가 "
              "원문에 살아남으면 이 게이트를 통과한다.")


if __name__ == "__main__":
    main()
