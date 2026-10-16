"""관계 어휘 정형화 — 자유 추출 → 정본 수렴 + 동의어 기록(별도). 소유자 지적:
어휘를 자유롭게 냅두면 증식 쓰레기. 같은 의미는 정본으로 정형화, 동의어는 provenance."""
import unittest
from relation_canon import canonicalize

# 정본 레지스트리: {정본: [표면 동의어/역방향]}
REGISTRY = {
    "computes": {"synonyms": ["computes", "calculates", "produces"]},
    "part_of": {"synonyms": ["part_of"], "inverse_of": "partitions_into"},
    "constrains": {"synonyms": ["constrains", "gates_change_of", "always_requires"]},
}

class TestCanon(unittest.TestCase):
    def test_surface_maps_to_canonical(self):
        rels=[{"from":"a","to":"b","rel":"calculates","quote":"q"}]
        out=canonicalize(rels, REGISTRY)
        self.assertEqual(out["relations"][0]["canonical"],"computes")
        self.assertEqual(out["relations"][0]["surface"],"calculates")  # 동의어 보존

    def test_inverse_normalized_with_flip(self):
        # X partitions_into Y = Y part_of X — 정본 방향으로 뒤집어 기록
        rels=[{"from":"X","to":"Y","rel":"partitions_into","quote":"q"}]
        out=canonicalize(rels, REGISTRY)
        r=out["relations"][0]
        self.assertEqual(r["canonical"],"part_of")
        self.assertEqual((r["from"],r["to"]),("Y","X"))   # 방향 뒤집힘

    def test_unmapped_flagged_not_dropped(self):
        rels=[{"from":"a","to":"b","rel":"신규관계","quote":"q"}]
        out=canonicalize(rels, REGISTRY)
        self.assertIn("신규관계", out["unmapped"])         # 새 어휘=정본 후보(버리지 않음)
        self.assertEqual(out["relations"][0]["canonical"], None)

    def test_multiple_inverses_per_canonical(self):
        # 스케일 실측: 정본 하나에 역방향 표면이 여럿(part_of ← includes·partitions_into·instantiates).
        # inverses 리스트로 다수 역방향을 정본 방향으로 뒤집는다.
        reg={"part_of":{"synonyms":["part_of"],
                        "inverses":["includes","partitions_into","instantiates"]}}
        rels=[{"from":"X","to":"Y","rel":"includes","quote":"q"},
              {"from":"P","to":"Q","rel":"instantiates","quote":"q"}]
        out=canonicalize(rels, reg)
        self.assertEqual(out["relations"][0]["canonical"],"part_of")
        self.assertEqual((out["relations"][0]["from"],out["relations"][0]["to"]),("Y","X"))
        self.assertEqual(out["relations"][1]["canonical"],"part_of")
        self.assertEqual((out["relations"][1]["from"],out["relations"][1]["to"]),("Q","P"))
        self.assertEqual(out["synonym_record"]["includes"],"part_of (inverse)")

    def test_synonym_record_separate(self):
        rels=[{"from":"a","to":"b","rel":"produces","quote":"q"},
              {"from":"c","to":"d","rel":"gates_change_of","quote":"q"}]
        out=canonicalize(rels, REGISTRY)
        # 동의어→정본 매핑이 별도 기록(소유자 "동의어 따로 기록")
        self.assertEqual(out["synonym_record"]["produces"],"computes")
        self.assertEqual(out["synonym_record"]["gates_change_of"],"constrains")


# ── 등록 게이트 ────────────────────────────────────────────

_REG = {"core_13": ["part_of", "constrains"],
        "extensions": [{"family": "delegates_to", "status": "candidate"},
                       {"family": "overrides", "status": "candidate"}],
        "not_a_relation": [{"surface": "out_of_scope"}]}


class TestVocabularyGate(unittest.TestCase):
    def test_registered_vocabulary_comes_from_data(self):
        """어휘 목록은 **데이터 선언**(canon-extensions.yaml)에서 온다 — 코드가 안 갖는다."""
        from relation_canon import registered_vocabulary
        self.assertEqual(registered_vocabulary(_REG),
                         {"part_of", "constrains", "delegates_to", "overrides"})

    def test_not_a_relation_is_not_vocabulary(self):
        """'관계가 아님'으로 판정된 표면을 통과시키면 그 판정이 무의미해진다."""
        from relation_canon import registered_vocabulary
        self.assertNotIn("out_of_scope", registered_vocabulary(_REG))

    def test_flags_unregistered_separately_from_NEW_proposals(self):
        """NEW와 미등록 어휘는 다른 것이다 — NEW는 계약이 허용한 **제안 절차**(소유자 승격
        대기)이고, 미등록은 계약 위반이다. 섞으면 판정 큐가 오염된다."""
        from relation_canon import validate_vocabulary
        rels = [{"canonical": "part_of"}, {"canonical": "NEW", "new_family": "x"},
                {"canonical": "슬쩍_지어낸_어휘"}, {"canonical": "delegates_to"}]
        out = validate_vocabulary(rels, _REG)
        self.assertEqual(out["unregistered"], ["슬쩍_지어낸_어휘"])
        self.assertEqual(out["new_proposals"], 1)
        self.assertEqual(out["ok"], 2)

    def test_unregistered_is_deduped_and_sorted(self):
        from relation_canon import validate_vocabulary
        rels = [{"canonical": "b"}, {"canonical": "a"}, {"canonical": "b"}]
        self.assertEqual(validate_vocabulary(rels, _REG)["unregistered"], ["a", "b"])

    def test_missing_canonical_field_is_not_silently_passed(self):
        from relation_canon import validate_vocabulary
        out = validate_vocabulary([{"from": "x", "to": "y"}], _REG)
        self.assertEqual(out["unregistered"], ["(없음)"])


if __name__=="__main__":
    unittest.main()
