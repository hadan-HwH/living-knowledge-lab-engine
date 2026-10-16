"""Tier B(LLM) 탐침 — 결정론 껍데기: transcripts 전처리와 왕복 검증.

설계: docs/4-experiments/tierb-probe-transcripts.md.
의미 판단(무엇이 개념인가·kind 명명)은 전부 서브에이전트(LLM) 몫이고,
이 모듈은 의미 판단이 없는 두 곳만 담당한다:
  prep_transcript    jsonl → 사람·어시스턴트 표시 텍스트 턴 + 제외 통계 + 청크
  verify_candidates  후보 인용의 원문 실재 대조(왕복 게이트)·kind 집계·refs 해소

Usage:
  python3 tier_b.py prep <session.jsonl> <outdir> [chunk_budget]
  python3 tier_b.py verify <outdir> [known-anchors.txt]
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


def prep_transcript(jsonl_path, chunk_budget=40000, include_thinking=False):
    """대화 표면만 남긴다: user는 origin.kind=='human'인 타이핑 발화,
    assistant는 text 블록. 나머지는 전부 제외 통계로 정직하게 센다.
    round 2: include_thinking=True면 thinking 블록을 channel='thinking'으로
    별도 턴 표기(기본값=기존 동작 — 제외 통계)."""
    turns, excluded = [], Counter()
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)                 # 줄 단위 내성 — 깨진 1줄이 파일 전체를 죽이지 않는다
        except (ValueError, json.JSONDecodeError):
            excluded["corrupt_line"] += 1
            continue
        if e.get("isSidechain"):
            excluded["sidechain"] += 1
            continue
        etype = e.get("type")
        if etype not in ("user", "assistant"):
            excluded[etype or "unknown"] += 1
            continue
        content = e.get("message", {}).get("content")
        thinking_texts = []
        if etype == "user":
            if not isinstance(content, str):
                excluded["user_blocks"] += 1
                continue
            if e.get("origin", {}).get("kind") != "human":
                excluded["user_injected"] += 1
                continue
            text = content
        else:
            blocks = [b for b in (content or []) if isinstance(b, dict)]
            for b in blocks:
                if b.get("type") == "thinking" and include_thinking:
                    thinking_texts.append(b.get("thinking", ""))
                elif b.get("type") != "text":
                    excluded[b.get("type") or "unknown"] += 1
            text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        for th in thinking_texts:
            th = th.strip()
            if th:
                turns.append({"i": len(turns), "uuid": f'{e["uuid"]}#thinking',
                              "role": etype, "channel": "thinking", "text": th})
        text = text.strip()
        if not text:
            continue
        if etype == "assistant" and _API_ERROR.match(text):
            excluded["api_error"] += 1        # 서버 에러 메시지는 어시스턴트 추론이 아니다
            continue
        turns.append({"i": len(turns), "uuid": e["uuid"], "role": etype, "text": text})
    return {"turns": turns, "excluded": dict(excluded),
            "chunks": chunk_turns(turns, chunk_budget)}


def chunk_turns(turns, chunk_budget=40000):
    """턴 경계로만 나눈다. 예산 초과 단일 턴은 자르지 않고 단독 청크(한계 명시)."""
    chunks, cur, size = [], [], 0
    for t in turns:
        n = len(t["text"])
        if cur and size + n > chunk_budget:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(t)
        size += n
    if cur:
        chunks.append(cur)
    return chunks


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


_API_ERROR = re.compile(r"^(API Error|Request timed out|Overloaded)", re.I)


def verify_candidates(candidates, turns, known_anchors=None):
    """왕복 게이트: 인용이 해당 턴 원문에 실재하는가(공백 정규화 후 substring).
    실패를 고쳐주지 않는다 — verdict로 기록만 한다(실패율이 1급 지표)."""
    by_uuid = {t["uuid"]: _norm(t["text"]) for t in turns}
    role_of = {t["uuid"]: t["role"] for t in turns}
    known = known_anchors or set()
    out, kinds, seen, dups = [], Counter(), set(), []
    refs_total, refs_resolved, refs_unresolved = 0, 0, []
    totals = Counter()
    violations = {"confidence_vocab": [], "missing_authority_basis": []}
    for seq, c in enumerate(candidates):
        verdict = "ok"
        for q in c.get("quotes", []):
            src = by_uuid.get(q.get("turn"))
            if src is None:
                verdict = "unknown_turn"
                break
            if _norm(q.get("text", "")) not in src:
                verdict = "quote_mismatch"
                break
        if not c.get("quotes"):
            verdict = "quote_mismatch"   # 인용 없는 후보는 계약 위반
        # round 2 — 화자 권위 게이트: human 근거 선언은 human 턴 인용 ≥1 필수
        basis = c.get("authority_basis")
        if verdict == "ok" and basis == "human":
            if not any(role_of.get(q.get("turn")) == "user" for q in c.get("quotes", [])):
                verdict = "authority_mismatch"
        if basis is None:
            violations["missing_authority_basis"].append(c.get("anchor"))
        # round 2 — confidence 어휘 강제(high|medium|low): 왕복과 별개로 계약 위반 기록
        if c.get("confidence") not in ("high", "medium", "low"):
            violations["confidence_vocab"].append(c.get("anchor"))
        totals[verdict] += 1
        kinds[c.get("kind") or "unknown"] += 1
        a = c.get("anchor")
        if a in seen and a not in dups:
            dups.append(a)
        seen.add(a)
        for r in c.get("refs", []):
            refs_total += 1
            if r in known:
                refs_resolved += 1
            else:
                refs_unresolved.append(r)
        out.append({"anchor_seq": seq, "anchor": a, "kind": c.get("kind"),
                    "verdict": verdict, "authority_basis": basis})
    n = len(candidates)
    return {
        "candidates": out,
        "totals": {"candidates": n, "ok": totals["ok"],
                   "quote_mismatch": totals["quote_mismatch"],
                   "unknown_turn": totals["unknown_turn"],
                   "authority_mismatch": totals["authority_mismatch"],
                   "pass_rate": (totals["ok"] / n) if n else None},
        "kinds": dict(kinds),
        "refs": {"total": refs_total, "resolved": refs_resolved,
                 "unresolved": refs_unresolved},
        "duplicate_anchors": dups,
        "contract_violations": violations,
    }


def _write_yaml(path, data):
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def main(argv):
    import hashlib
    cmd = argv[1]
    if cmd == "prep":
        jsonl, outdir = Path(argv[2]), Path(argv[3])
        budget = int(argv[4]) if len(argv) > 4 else 40000
        res = prep_transcript(jsonl, chunk_budget=budget)
        sha = hashlib.sha256(jsonl.read_bytes()).hexdigest()[:12]
        _write_yaml(outdir / "turns.yaml", {
            "meta": {"source": jsonl.name, "source_sha256_12": sha,
                     "chunk_budget": budget, "turns": len(res["turns"]),
                     "chunks": len(res["chunks"]),
                     "excluded": res["excluded"]},
            "chunks": [{"chunk": i + 1, "turns": c}
                       for i, c in enumerate(res["chunks"])],
        })
        print(f"turns={len(res['turns'])} chunks={len(res['chunks'])} "
              f"excluded={res['excluded']}")
    elif cmd == "verify":
        import yaml
        outdir = Path(argv[2])
        known = set()
        if len(argv) > 3:
            known = {l.strip() for l in Path(argv[3]).read_text(encoding="utf-8").splitlines() if l.strip()}
        data = yaml.safe_load((outdir / "turns.yaml").read_text(encoding="utf-8"))
        turns = [t for c in data["chunks"] for t in c["turns"]]
        cands = yaml.safe_load((outdir / "concepts.tierb.yaml").read_text(encoding="utf-8"))["candidates"]
        rep = verify_candidates(cands, turns, known_anchors=known)
        _write_yaml(outdir / "verify.yaml", rep)
        print(f"pass_rate={rep['totals']['pass_rate']} kinds={rep['kinds']}")
    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    import sys
    main(sys.argv)


def cross_chunk_merge(candidates):
    """round 2 — 청크 경계 종적 개념: 같은 anchor가 복수 청크에서 나오면 병합 큐.
    자동 병합 아님(판정/후처리 몫) — 종적 개념의 존재 자체가 관측 데이터."""
    by_anchor = {}
    for c in candidates:
        by_anchor.setdefault(c.get("anchor"), set()).add(c.get("chunk"))
    queue = [{"anchor": a, "chunks": sorted(ch)}
             for a, ch in sorted(by_anchor.items()) if len(ch) > 1]
    return {"merge_queue": queue, "cross_chunk_anchors": len(queue)}
