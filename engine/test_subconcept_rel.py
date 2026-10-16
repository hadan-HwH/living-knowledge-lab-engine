"""하위개념 간 관계 게이트 — 자유 명명 어휘·quote 왕복(관계가 원문 근거)·confidence 보존."""
import unittest
from subconcept import verify_relations

SUBS = [{"sid":"d#a","name":"권위 A"},{"sid":"d#b","name":"근거 S"},{"sid":"d#c","name":"오염"}]
SECS = [{"heading":"5. M1","text":"권위 A와 근거 S의 불일치가 미래 재검토를 설명한다."}]

class TestRel(unittest.TestCase):
    def test_real_quote_relation_ok(self):
        rels=[{"from":"d#a","to":"d#b","rel":"tension_with","confidence":"high",
               "quote":"권위 A와 근거 S의 불일치"}]
        rep=verify_relations(rels, SUBS, SECS)
        self.assertEqual(rep["ok"][0]["rel"],"tension_with")
        self.assertEqual(rep["vocab"],{"tension_with":1})

    def test_fabricated_quote_rejected(self):
        rels=[{"from":"d#a","to":"d#c","rel":"causes","confidence":"high","quote":"없는 말"}]
        rep=verify_relations(rels, SUBS, SECS)
        self.assertEqual(rep["rejected"][0]["verdict"],"quote_not_found")

    def test_unknown_endpoint_rejected(self):
        rels=[{"from":"d#a","to":"d#zzz","rel":"x","confidence":"high","quote":"권위 A와 근거 S의 불일치"}]
        rep=verify_relations(rels, SUBS, SECS)
        self.assertEqual(rep["rejected"][0]["verdict"],"unknown_endpoint")

if __name__=="__main__":
    unittest.main()
