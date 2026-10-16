#!/usr/bin/env python3
"""배치 추출 산출 → 앱 원장 하나. 결정론·LLM 0.

usage: scripts/merge_batches.py <corpus> <app> <batch> [<batch> …]
       예) scripts/merge_batches.py personal-wevolley wevolley batchA batchB batchC

★왜 있나: 원장은 앱당 하나인데(fold·promote가 그렇게 읽는다) 큰 앱은 한 에이전트
컨텍스트에 안 들어간다. wevolley 재생성 183섹션을 문서별 3배치로 나눠 병렬 추출했고,
큰 문서 코퍼스의 앱 단위 확산도 같은 형태를 만난다.

★의미 판정은 하지 않는다 — 교차배치 중복(같은 개념, 다른 anchor)은 **보고만** 한다.
합치는 쪽이 "둘은 같다"고 정하면 그건 병합이 아니라 추출이다.

★실패와 건너뜀을 삼키지 않는다(regen.sh와 같은 규약). 없는 배치 파일은 이유와 함께
인쇄하고, 전건 커버가 깨지면 종료 코드로 낸다 — 깨진 원장을 fold에 넘기지 않는다.
"""
import sys
from pathlib import Path

import yaml

ENGINE = Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(ENGINE))

import batch_merge as bm  # noqa: E402


def _load(path, key):
    """없으면 (None, 사유). 조용히 빈 값으로 때우지 않는다 — 그게 무성 누락이다."""
    if not path.exists():
        return None, f"{path.name} 없음"
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    if key not in doc:
        return None, f"{path.name}에 `{key}:` 키 없음"
    return doc[key] or [], None


def main(argv):
    if len(argv) < 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    corpus, app, batches = argv[1], argv[2], argv[3:]
    base = ENGINE / "fixtures" / corpus / "work" / app
    if not base.is_dir():
        print(f"merge: {base} 없음", file=sys.stderr)
        return 1

    spec = [("subconcepts", "subconcepts"), ("align-proposals", "proposals"),
            ("relations-canon", "relations"), ("aliases", "aliases")]
    loaded, skipped = {}, []
    for stem, key in spec:
        per_batch = []
        for b in batches:
            items, why = _load(base / f"{stem}.{b}.yaml", key)
            if why:
                skipped.append(f"{b}/{stem}: {why}")
            else:
                per_batch.append(items)
        loaded[stem] = per_batch

    members_batches = []
    for b in batches:
        p = base / f"members.{b}.yaml"
        if not p.exists():
            skipped.append(f"{b}/members: {p.name} 없음")
            continue
        members_batches.append((yaml.safe_load(open(p, encoding="utf-8")) or {}).get("members") or {})

    sc = bm.merge_subconcepts(loaded["subconcepts"])
    pr = bm.merge_proposals(loaded["align-proposals"])
    me = bm.merge_members_files(members_batches)
    re_ = bm.merge_relations(loaded["relations-canon"])
    al = bm.merge_aliases(loaded["aliases"])

    def dump(name, payload):
        with open(base / name, "w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)

    dump("subconcepts.yaml", {"subconcepts": sc["subconcepts"]})
    dump("align-proposals.yaml", {"proposals": pr["proposals"]})
    dump("members.yaml", {"members": me["members"]})
    dump("relations-canon.yaml", {"relations": re_["relations"]})
    dump("aliases.yaml", {"aliases": al["aliases"]})

    n_units = sum(len(v) for v in me["members"].values())
    n_c = len(sc["subconcepts"])
    print(f"merge {corpus}/{app} ← {len(batches)}배치: "
          f"개념 {n_c} · 제안 {len(pr['proposals'])} · 귀속 {n_units}"
          f"(개념당 {n_units / n_c:.2f}) · 관계 {len(re_['relations'])} · 별칭 {len(al['aliases'])}")

    fail = 0
    if skipped:
        print(f"  건너뜀 {len(skipped)}:")
        for s in skipped:
            print(f"    – {s}")
    if sc["anchor_collisions"]:
        print(f"  ⚠ anchor 충돌 {len(sc['anchor_collisions'])}(첫 배치가 이김): "
              f"{', '.join(sc['anchor_collisions'][:10])}")
    if pr["sid_collisions"]:
        print(f"  ⚠ sid 충돌 {len(pr['sid_collisions'])}: {', '.join(pr['sid_collisions'][:10])}")
    if sc["name_duplicates"]:
        # 판정하지 않는다 — 같은 개념일 수도, 정말 다른 개념에 같은 이름일 수도 있다.
        print(f"  ⚠ 교차배치 이름 중복 {len(sc['name_duplicates'])}(병합 안 함 — 판정 대상):")
        for n, anchors in sc["name_duplicates"][:10]:
            print(f"    – {n!r}: {', '.join(anchors)}")

    cov = bm.check_coverage(sc["subconcepts"], pr["proposals"], app)
    if cov["missing"] or cov["phantom"]:
        print(f"  ✗ 전건 커버 깨짐 — 제안 없는 개념 {len(cov['missing'])} · "
              f"개념 없는 제안 {len(cov['phantom'])}")
        for x in (cov["missing"] + cov["phantom"])[:10]:
            print(f"    – {x}")
        fail = 1
    else:
        print("  전건 커버 OK")
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv))
