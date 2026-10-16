"""개념 canon-aware 정렬 — 새 앱 하위개념을 기존 공유 그래프에 병합(사일로 방지).
소유자(2026-08-01): 코어플랜 앱은 개념을 공유 → 앱별로 새로 mint 말고 기존 정본에 매핑.
관계의 relation_canon(어휘)을 개념 층에 적용. 핵심 게이트: 병합 대상이 그래프에 실재.
under-merge 규율: 애매하면 병합 않고 flag(소유자 검토). commitment는 가변, 어휘는 정형화 계열."""
import unittest
from concept_align import align_concepts

INDEX = {"ARCH-01", "NAME-02", "CB-02", "cb-server-status"}  # 정본 그래프 앵커
SUBS = ["new:domain-store", "new:server-status", "new:widget", "new:naming"]

class TestAlign(unittest.TestCase):
    def test_valid_merge_target_in_index(self):
        props=[{"sid":"new:domain-store","target":"ARCH-01","confidence":"high"}]
        out=align_concepts(props, INDEX, ["new:domain-store"])
        self.assertEqual(out["merged"][0]["target"],"ARCH-01")
        self.assertEqual(out["merged"][0]["sid"],"new:domain-store")
        # 표면(surface) provenance 기록: 새 sid가 기존 정본의 동의어/변이로
        self.assertEqual(out["synonym_record"]["new:domain-store"],"ARCH-01")

    def test_fabricated_target_rejected(self):
        # 제안 대상이 그래프에 없으면 = 지어냄 → error(관계 왕복 게이트에 해당)
        props=[{"sid":"new:server-status","target":"GHOST-99","confidence":"high"}]
        out=align_concepts(props, INDEX, ["new:server-status"])
        self.assertIn("new:server-status", [e["sid"] for e in out["errors"]])
        self.assertEqual(out["merged"], [])

    def test_genuinely_new_kept(self):
        props=[{"sid":"new:widget","target":"NEW","confidence":"high"}]
        out=align_concepts(props, INDEX, ["new:widget"])
        self.assertIn("new:widget", [n["sid"] for n in out["new"]])

    def test_low_confidence_downgraded_to_ambiguous(self):
        # under-merge: 낮은 확신 병합은 자동 병합 않고 ambiguous로 flag
        props=[{"sid":"new:naming","target":"NAME-02","confidence":"low"}]
        out=align_concepts(props, INDEX, ["new:naming"])
        self.assertIn("new:naming", [a["sid"] for a in out["ambiguous"]])
        self.assertEqual(out["merged"], [])

    def test_partition_every_sub_covered_no_phantom(self):
        props=[{"sid":"new:domain-store","target":"ARCH-01","confidence":"high"},
               {"sid":"new:server-status","target":"CB-02","confidence":"high"},
               {"sid":"new:widget","target":"NEW","confidence":"high"},
               {"sid":"new:naming","target":"NAME-02","confidence":"medium"},
               {"sid":"phantom:xyz","target":"ARCH-01","confidence":"high"}]
        out=align_concepts(props, INDEX, SUBS)
        self.assertIn("phantom:xyz", [e["sid"] for e in out["errors"]])   # 명단 밖 = error
        covered={p["sid"] for p in out["merged"]+out["new"]+out["ambiguous"]}
        self.assertEqual(covered, set(SUBS))                              # 전건 커버·분할

if __name__=="__main__":
    unittest.main()
