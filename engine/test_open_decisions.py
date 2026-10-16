"""T9 OPEN_DECISION 질의 — 계약 §2 T9. deferral gold.
핵심 판별: 같은 '보류' 라벨이지만 결정 확정(D-7802)과 결정 미결(D-8038)은 다르다."""
import unittest

from queries import open_decisions

# D-7802형: 결정 확정, 조항화만 보류(I축) → 현행 있음, open 아님
# D-8038형: 결정 내용 자체 미결 → 현행 없음, open
EVENTS = [
    {"event_id": "e1", "type": "adopt", "target": "NEO.payment_model",
     "option": "o_postpaid", "authority_level": "product", "scope": "neomart/billing",
     "valid_at": "2026-07-24", "recorded_at": "2026-07-24"},
    {"event_id": "e2", "type": "propose", "target": "NEO.overseas_invoice",
     "option": "o_auto", "valid_at": "2026-07-24", "recorded_at": "2026-07-24"},
    {"event_id": "e3", "type": "propose", "target": "NEO.overseas_invoice",
     "option": "o_manual", "valid_at": "2026-07-24", "recorded_at": "2026-07-24"},
    {"event_id": "e4", "type": "defer", "target": "NEO.overseas_invoice",
     "option": "o_auto", "valid_at": "2026-07-24", "recorded_at": "2026-07-24",
     "resume_trigger": "복잡도 평가 후 결정"},
    {"event_id": "e5", "type": "defer", "target": "NEO.overseas_invoice",
     "option": "o_manual", "valid_at": "2026-07-24", "recorded_at": "2026-07-24"},
]


class TestOpenDecisions(unittest.TestCase):
    def test_open_lists_only_genuinely_undecided(self):
        rep = open_decisions(EVENTS, "2026-12-31", "2026-12-31")
        opens = {o["target"] for o in rep["open"]}
        self.assertIn("NEO.overseas_invoice", opens)       # 결정 미결
        self.assertNotIn("NEO.payment_model", opens)       # 결정 확정(조항화만 보류=T11)

    def test_resume_trigger_surfaced(self):
        rep = open_decisions(EVENTS, "2026-12-31", "2026-12-31")
        item = next(o for o in rep["open"] if o["target"] == "NEO.overseas_invoice")
        self.assertIn("복잡도 평가 후 결정", item["resume_triggers"])
        self.assertEqual(sorted(item["deferred_options"]), ["o_auto", "o_manual"])

    def test_decided_target_has_active_current(self):
        # 대조: payment_model은 현행 있음(open 아님을 뒷받침)
        from queries import current_authority
        got = current_authority(EVENTS, "NEO.payment_model", "2026-12-31", "2026-12-31")
        self.assertEqual(got["current_option"], "o_postpaid")

    def test_before_proposal_nothing_open(self):
        rep = open_decisions(EVENTS, "2026-07-01", "2026-07-01")
        self.assertEqual(rep["open"], [])                  # 아직 제안 전


if __name__ == "__main__":
    unittest.main()
