"""코퍼스 전체 추출 드라이버 — discover(ingest) → parse(parsers) → map(map_events) 결합.

레지스트리 데이터 구동: 코퍼스 이름·형식·레이아웃을 코드가 모른다 (corpus.py 원칙 동일).
출력은 후보 event 원장 + adjudication flag 목록 = **제안**이지 gold가 아니다.

event_id·target의 유일성은 scope 전체 경로에서 온다 — 앱 폴더 이름은 코퍼스 안에서
겹칠 수 있어(실제: meadow/crate vs atlas/crate) 말단 이름만으로는 부족하다.

Usage: python3 extract.py <corpus> > fixtures/<corpus>/<대상>/events.auto.yaml
"""
from __future__ import annotations

import sys
from pathlib import Path
import yaml

from ingest import discover
from parsers import parse, PARSERS
from map_events import skeleton_to_events


def _prefix(scope):
    """scope 전체 경로 → event_id/target 접두 (유일성 보장). prime-commerce/summit/inv → PRIME-COMMERCE.SUMMIT.INV"""
    return ".".join(s.upper() for s in scope.split("/"))


def extract_corpus(corpus_name, source_root, registry=None):
    """한 코퍼스의 모든 결정 파일 → {"events": [...], "flags": [...], "stats": {...}}."""
    r = discover(corpus_name, Path(source_root), registry)
    fmt = r["config"].get("decision_format")
    events, flags = [], list(r["warnings"])
    n_files = n_decisions = 0
    for item in r["found"]:
        if fmt not in PARSERS:
            flags.append(f"미등록 형식 {fmt!r}: {item['file']} 건너뜀 (Tier B 필요)")
            continue
        text = (Path(source_root) / item["file"]).read_text(encoding="utf-8")
        parsed = parse(fmt, text, scope=item["scope"])
        if not parsed["decisions"]:
            continue
        n_files += 1
        n_decisions += len(parsed["decisions"])
        out = skeleton_to_events(parsed, prefix=_prefix(item["scope"]), corpus=corpus_name)
        events.extend(out["events"])
        flags.extend(f"[{item['scope']}] {f}" for f in out["flags"])
    events.sort(key=lambda e: (str(e.get("valid_at")), e["event_id"]))
    return {"events": events, "flags": flags,
            "stats": {"files": n_files, "decisions": n_decisions, "events": len(events)}}


def ledger_document(name, src, out, sha, dirty):
    """제안 원장 문서 — meta(출처 시점 포함) + flags + events. 순수함수(I/O 없음).

    ★source_sha가 load-bearing이다: 개념층 스냅샷(l1_snapshot meta.source_sha)과 같은
    필드를 결정층도 들고 있어야 두 층의 시점 어긋남을 **기계가** 묻을 수 있다. flags도
    주석이 아니라 필드로 낸다 — 미판정 건수는 원장의 상태지 사람용 메모가 아니다."""
    return {
        "meta": {
            "corpus": name,
            "source": str(src),
            "source_sha": sha,
            "source_dirty": dirty,
            "generator": "extract.py (기계 생성 — 제안 원장이지 gold 아님)",
            "files": out["stats"]["files"],
            "decisions": out["stats"]["decisions"],
            "events": out["stats"]["events"],
            "flags": len(out["flags"]),
        },
        "flags": list(out["flags"]),
        "events": out["events"],
    }


if __name__ == "__main__":
    import subprocess

    name = sys.argv[1] if len(sys.argv) > 1 else "acme-docs"
    here = Path(__file__).parent
    reg = yaml.safe_load((here / "registry.yaml").read_text(encoding="utf-8"))
    src = (here / reg["corpora"][name]["source"]).resolve()
    sha = subprocess.run(["git", "-C", str(src), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "no-git"
    dirty = bool(subprocess.run(["git", "-C", str(src), "status", "--porcelain"],
                                capture_output=True, text=True).stdout.strip())
    out = extract_corpus(name, src, reg)
    doc = ledger_document(name, src, out, sha, dirty)
    print(f"# AUTO-EXTRACTED proposal ledger — corpus={name} @ {sha}"
          f"{' (dirty)' if dirty else ''}")
    print(f"# {doc['meta']['files']} files, {doc['meta']['decisions']} decisions, "
          f"{doc['meta']['events']} events, FLAG {doc['meta']['flags']}건 (gold 아님)")
    print(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
