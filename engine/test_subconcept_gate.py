"""하위개념 분해 게이트 — 불확실성 가져가기(소유자 방법론). quote 왕복 + commitment 어휘 강제."""
import unittest
from subconcept import verify_subconcepts

SECS = [{"heading":"1. 원죄","text":"PPIR 원죄는 균일 표현이다. 리서치 한 줄도 확정 결정도 같은 타입."},
        {"heading":"2. 깔때기","text":"지식은 깔때기다. 100 벤치마크 중 1 결정."}]

class TestGate(unittest.TestCase):
    def test_real_quote_and_commitment(self):
        sc=[{"anchor":"subc-funnel","name":"깔때기","confidence":"high",
             "commitment":"hypothesis","quote":"지식은 깔때기다","sections":["2. 깔때기"]}]
        rep=verify_subconcepts(sc, SECS)
        self.assertEqual(rep["ok"][0]["anchor"],"subc-funnel")
        self.assertEqual(rep["totals"]["pass_rate"],1.0)

    def test_fabricated_rejected(self):
        sc=[{"anchor":"x","name":"y","confidence":"high","commitment":"frozen",
             "quote":"없는 말","sections":["1. 원죄"]}]
        rep=verify_subconcepts(sc, SECS)
        self.assertEqual(rep["rejected"][0]["verdict"],"quote_not_found")

    def test_bad_commitment_flagged(self):
        sc=[{"anchor":"z","name":"n","confidence":"high","commitment":"확실함",
             "quote":"지식은 깔때기다","sections":["2. 깔때기"]}]
        rep=verify_subconcepts(sc, SECS)
        self.assertIn("z", rep["contract_violations"]["commitment_vocab"])

if __name__=="__main__":
    unittest.main()
