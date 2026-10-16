"""Tier B round 2 테스트 — 사전 등록(보고서 §5.5): speaker 권위·confidence 어휘 강제·
청크 경계 종적 개념·thinking 포함. round 1 실패 4건이 전부 기계 게이트 아래였던 것에 대한 응답."""
import json
import unittest

from tier_b import prep_transcript, verify_candidates, cross_chunk_merge

TURNS = [
    {"i": 0, "uuid": "u1", "role": "user", "text": "결정층 손저작은 하지 말자. 확정이야."},
    {"i": 1, "uuid": "a1", "role": "assistant", "text": "제안: DECISIONS.md를 만들면 어떨까요."},
]


class TestSpeakerAuthorityGate(unittest.TestCase):
    """round 1 잡음 4건 중 2건=화자 권위 미구분(어시스턴트 제안→결정 승격).
    후보가 authority_basis를 선언하고, 기계가 인용 발화자와 대조한다."""

    def _cand(self, **kw):
        return {"anchor": "TB-2-1", "kind": "결정",
                "quotes": [{"turn": kw.pop("turn", "u1"),
                            "text": kw.pop("qtext", "결정층 손저작은 하지 말자")}],
                "confidence": "high", "authority_basis": kw.pop("basis", "human"), **kw}

    def test_human_authority_with_human_quote_ok(self):
        rep = verify_candidates([self._cand()], TURNS)
        self.assertEqual(rep["candidates"][0]["verdict"], "ok")

    def test_human_authority_with_only_assistant_quotes_fails(self):
        c = self._cand(turn="a1", qtext="제안: DECISIONS.md를 만들면 어떨까요.", basis="human")
        rep = verify_candidates([c], TURNS)
        self.assertEqual(rep["candidates"][0]["verdict"], "authority_mismatch")

    def test_assistant_basis_is_visible_not_failed(self):
        c = self._cand(turn="a1", qtext="제안: DECISIONS.md를 만들면 어떨까요.", basis="assistant")
        rep = verify_candidates([c], TURNS)
        self.assertEqual(rep["candidates"][0]["verdict"], "ok")
        self.assertEqual(rep["candidates"][0]["authority_basis"], "assistant")  # 판정에 보이게

    def test_missing_authority_basis_is_contract_violation(self):
        c = self._cand()
        del c["authority_basis"]
        rep = verify_candidates([c], TURNS)
        self.assertIn("TB-2-1", rep["contract_violations"]["missing_authority_basis"])


class TestConfidenceVocab(unittest.TestCase):
    def test_vocab_enforced_high_medium_low(self):
        c = {"anchor": "TB-2-2", "kind": "원칙", "confidence": "확실",
             "authority_basis": "human",
             "quotes": [{"turn": "u1", "text": "결정층 손저작은 하지 말자"}]}
        rep = verify_candidates([c], TURNS)
        self.assertEqual(rep["candidates"][0]["verdict"], "ok")   # 왕복과 별개
        self.assertIn("TB-2-2", rep["contract_violations"]["confidence_vocab"])


class TestThinkingChannel(unittest.TestCase):
    JSONL = "\n".join(json.dumps(e) for e in [
        {"type": "assistant", "uuid": "a1", "message": {"content": [
            {"type": "thinking", "thinking": "내부 추론이다"},
            {"type": "text", "text": "표시 답변이다"}]}},
    ])

    def test_default_excludes_thinking(self):
        import tempfile, pathlib
        p = pathlib.Path(tempfile.mkdtemp()) / "s.jsonl"
        p.write_text(self.JSONL)
        out = prep_transcript(p)
        self.assertEqual(len(out["turns"]), 1)
        self.assertEqual(out["excluded"].get("thinking"), 1)      # 기존 동작 유지

    def test_include_thinking_as_marked_channel(self):
        import tempfile, pathlib
        p = pathlib.Path(tempfile.mkdtemp()) / "s.jsonl"
        p.write_text(self.JSONL)
        out = prep_transcript(p, include_thinking=True)
        ch = {t.get("channel", "text") for t in out["turns"]}
        self.assertIn("thinking", ch)
        th = [t for t in out["turns"] if t.get("channel") == "thinking"][0]
        self.assertEqual(th["role"], "assistant")
        self.assertIn("내부 추론이다", th["text"])


class TestCrossChunkMerge(unittest.TestCase):
    def test_same_anchor_across_chunks_queued(self):
        cands = [{"anchor": "TB-2-goal", "chunk": 0}, {"anchor": "TB-2-goal", "chunk": 2},
                 {"anchor": "TB-2-other", "chunk": 1}]
        out = cross_chunk_merge(cands)
        self.assertEqual(out["merge_queue"], [{"anchor": "TB-2-goal", "chunks": [0, 2]}])
        self.assertEqual(out["cross_chunk_anchors"], 1)


if __name__ == "__main__":
    unittest.main()


class TestResilience(unittest.TestCase):
    """줄 단위 내성 + API 에러 제외 (소유자 지적 2026-08-01: 2줄 때문에 세션 통째 버리지 마라)."""

    def _write(self, lines):
        import tempfile, pathlib
        p = pathlib.Path(tempfile.mkdtemp()) / "s.jsonl"
        p.write_text("\n".join(lines), encoding="utf-8")
        return p

    def test_corrupt_line_skipped_not_whole_file(self):
        good = json.dumps({"type": "user", "uuid": "u1",
                           "message": {"content": "실제 발화"}, "origin": {"kind": "human"}})
        p = self._write([good, '{"broken": unterminated', good.replace("u1", "u2")])
        out = prep_transcript(p)
        self.assertEqual(len(out["turns"]), 2)            # 2 good 살고
        self.assertEqual(out["excluded"].get("corrupt_line"), 1)   # 1 깨진 줄만 제외

    def test_api_error_turn_excluded(self):
        err = json.dumps({"type": "assistant", "uuid": "a1",
                          "message": {"content": [{"type": "text",
                          "text": "API Error: 529 Overloaded. This is a server-side issue"}]}})
        p = self._write([err])
        out = prep_transcript(p)
        self.assertEqual(out["turns"], [])
        self.assertEqual(out["excluded"].get("api_error"), 1)
