"""Tier B 탐침 — 결정론 껍데기(전처리·왕복 검증) 검증.

Run: python3 -m pytest engine/test_tier_b.py -q  (from repo root)
"""
from __future__ import annotations

import json

from tier_b import chunk_turns, prep_transcript, verify_candidates

EVENTS = [
    {"type": "mode", "mode": "normal"},
    {"type": "user", "uuid": "u1", "isSidechain": False,
     "origin": {"kind": "human"},
     "message": {"role": "user", "content": "결정층은  손저작하지 않는다"}},
    {"type": "assistant", "uuid": "a1", "isSidechain": False,
     "message": {"role": "assistant", "content": [
         {"type": "thinking", "thinking": "고민"},
         {"type": "text", "text": "네, 결정 구조는 추출로 파생합니다"}]}},
    # 스킬/커맨드 주입: user str인데 origin 없음 → 제외
    {"type": "user", "uuid": "u2", "isSidechain": False,
     "message": {"role": "user", "content": "Base directory for this skill: ..."}},
    # tool_result 블록 리스트 → 제외
    {"type": "user", "uuid": "u3", "isSidechain": False,
     "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
    # tool_use만 있는 assistant → 턴 없음
    {"type": "assistant", "uuid": "a2", "isSidechain": False,
     "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]}},
    # 사이드체인 → 통째로 제외
    {"type": "assistant", "uuid": "a3", "isSidechain": True,
     "message": {"role": "assistant", "content": [{"type": "text", "text": "서브에이전트"}]}},
]


def _write_jsonl(tmp_path, events):
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events),
                 encoding="utf-8")
    return p


def test_prep_keeps_human_and_assistant_text_only(tmp_path):
    res = prep_transcript(_write_jsonl(tmp_path, EVENTS))
    turns = res["turns"]
    assert [(t["role"], t["uuid"]) for t in turns] == [("user", "u1"), ("assistant", "a1")]
    assert turns[0]["text"] == "결정층은  손저작하지 않는다"   # 원문 무수정 보존
    assert turns[1]["text"] == "네, 결정 구조는 추출로 파생합니다"
    assert [t["i"] for t in turns] == [0, 1]


def test_prep_excluded_stats(tmp_path):
    res = prep_transcript(_write_jsonl(tmp_path, EVENTS))
    ex = res["excluded"]
    assert ex["mode"] == 1            # 비대화 이벤트
    assert ex["user_injected"] == 1   # origin 없는 user str (스킬 주입)
    assert ex["user_blocks"] == 1     # tool_result 등 블록형 user
    assert ex["thinking"] == 1        # assistant 비-text 블록
    assert ex["tool_use"] == 1
    assert ex["sidechain"] == 1


def test_chunk_turns_respects_budget_and_boundaries():
    turns = [{"i": i, "uuid": f"u{i}", "role": "user", "text": "가" * n}
             for i, n in enumerate([30, 30, 30])]
    chunks = chunk_turns(turns, chunk_budget=60)
    # 30+30=60은 예산 안, 셋째 턴은 넘치므로 다음 청크
    assert [[t["i"] for t in c] for c in chunks] == [[0, 1], [2]]


def test_chunk_turns_oversized_turn_gets_own_chunk():
    turns = [{"i": 0, "uuid": "u0", "role": "user", "text": "가" * 100},
             {"i": 1, "uuid": "u1", "role": "user", "text": "나" * 10}]
    chunks = chunk_turns(turns, chunk_budget=60)
    # 예산 초과 턴도 자르지 않는다(턴 경계 분할만) — 단독 청크
    assert [[t["i"] for t in c] for c in chunks] == [[0], [1]]


TURNS = [{"i": 0, "uuid": "u1", "role": "user", "text": "결정층은  손저작하지\n않는다. D-7318 참조."}]

CANDS = [
    {"anchor": "TB-1-1", "kind": "원칙",
     "quotes": [{"turn": "u1", "text": "결정층은 손저작하지 않는다"}],  # 공백 정규화 후 일치
     "gloss": "결정층 손저작 금지", "refs": ["D-7318"], "confidence": "high",
     "scope": "lab-self/test"},
    {"anchor": "TB-1-2", "kind": "용어",
     "quotes": [{"turn": "u1", "text": "이 문장은 원문에 없다"}],
     "gloss": "환각 인용", "refs": ["INV-99"], "confidence": "high",
     "scope": "lab-self/test"},
    {"anchor": "TB-1-2", "kind": "용어",   # anchor 중복
     "quotes": [{"turn": "uX", "text": "결정층"}],  # 없는 턴
     "gloss": "미상 턴", "refs": [], "confidence": "low",
     "scope": "lab-self/test"},
]


def test_verify_quote_gate_and_aggregates():
    rep = verify_candidates(CANDS, TURNS, known_anchors={"D-7318"})
    verdicts = {c["anchor_seq"]: c["verdict"] for c in rep["candidates"]}
    # anchor_seq = 원장 순번(중복 anchor 구분용)
    assert verdicts == {0: "ok", 1: "quote_mismatch", 2: "unknown_turn"}
    assert rep["totals"] == {"candidates": 3, "ok": 1, "quote_mismatch": 1,
                             "unknown_turn": 1, "authority_mismatch": 0,   # round 2 키 추가
                             "pass_rate": 1 / 3}
    assert rep["kinds"] == {"원칙": 1, "용어": 2}
    assert rep["refs"] == {"total": 2, "resolved": 1, "unresolved": ["INV-99"]}
    assert rep["duplicate_anchors"] == ["TB-1-2"]
