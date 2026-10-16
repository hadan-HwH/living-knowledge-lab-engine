"""용어 정형화 양방향 검출 — scope/sense를 살려 모으기(동의어)와 가르기(동형이의) 둘 다.
소유자(2026-08-01): 어휘는 반대 두 방향으로 깨진다.
  · 동의어(synonymy): 여러 표면→한 sense = merge 제안 (예 Partition=store/branch/project)
  · 동형이의(homonymy): 한 표면→여러 sense = split 경고 (예 role=직원role@console-builder vs 할인role@inv)
표면만 보면 한쪽 필패(어시스턴트 ②=동형이의를 병합). 그래서 member에 sense를 달고
sense-일치를 게이트로 삼는다. 데이터는 이미 scope를 달고 있으므로 가르기가 거의 공짜."""
import unittest
from concept_divergence import verify_divergence

APP_TEXT = {
    "courier":      "리소스는 Store 단위로 관리한다",
    "crate":    "Branch(Region.Branch)로 구분한다",
    "console-builder":"Staff.Role은 Floor Manager로 고정",
    "inv":          "임시 Role로만 할인을 적용받는다",
}

class TestDivergence(unittest.TestCase):
    def test_synonym_merge_verified(self):
        # 여러 표면·한 sense·≥2앱 = 동의어 병합 제안
        f=[{"kind":"synonym","canonical":"Partition","members":[
            {"app":"courier","surface":"Store","sense":"작업 파티션","quote":"Store 단위"},
            {"app":"crate","surface":"Branch","sense":"작업 파티션","quote":"Branch(Region.Branch)"}]}]
        out=verify_divergence(f, APP_TEXT)
        self.assertEqual(out["stats"]["merges"],1)
        self.assertEqual(out["merges"][0]["canonical"],"Partition")

    def test_synonym_rejected_on_sense_mismatch(self):
        # ★②의 자동 방지: 다른 표면을 병합 주장하나 sense가 다름(위계/무관) → 거부
        f=[{"kind":"synonym","canonical":"할인단위","members":[
            {"app":"inv","surface":"Role","sense":"임시 할인 등급","quote":"임시 Role로만 할인을 적용받는다"},
            {"app":"console-builder","surface":"역할","sense":"매장 직무 기능","quote":"Staff.Role은 Floor Manager로 고정"}]}]
        out=verify_divergence(f, APP_TEXT)
        self.assertEqual(out["stats"]["merges"],0)
        self.assertIn("sense 불일치", out["rejected"][0]["reason"])

    def test_homonym_split_verified(self):
        # 같은 표면·여러 sense·≥2앱 = 동형이의 분리 경고
        f=[{"kind":"homonym","surface":"Role","members":[
            {"app":"console-builder","surface":"Role","sense":"매장 직무 기능","quote":"Staff.Role은 Floor Manager로 고정"},
            {"app":"inv","surface":"Role","sense":"임시 할인 등급","quote":"임시 Role로만 할인을 적용받는다"}]}]
        out=verify_divergence(f, APP_TEXT)
        self.assertEqual(out["stats"]["splits"],1)
        self.assertEqual(out["splits"][0]["surface"],"Role")

    def test_homonym_rejected_single_sense(self):
        # 같은 표면인데 sense 하나 = 동형이의 아님(이미 통일)
        f=[{"kind":"homonym","surface":"Store","members":[
            {"app":"courier","surface":"Store","sense":"작업 파티션","quote":"Store 단위"},
            {"app":"crate","surface":"Store","sense":"작업 파티션","quote":"Branch(Region.Branch)"}]}]
        out=verify_divergence(f, {"courier":"Store 단위","crate":"Store 단위 Branch(Region.Branch)"})
        self.assertEqual(out["stats"]["splits"],0)
        self.assertIn("sense 1종", out["rejected"][0]["reason"])

    def test_single_app_rejected(self):
        f=[{"kind":"synonym","canonical":"X","members":[
            {"app":"courier","surface":"Store","sense":"작업 파티션","quote":"Store 단위"}]}]
        out=verify_divergence(f, APP_TEXT)
        self.assertEqual(out["stats"]["merges"],0)
        self.assertIn("단일 앱", out["rejected"][0]["reason"])

    def test_fabricated_quote_rejected(self):
        f=[{"kind":"synonym","canonical":"Partition","members":[
            {"app":"courier","surface":"Store","sense":"작업 파티션","quote":"Store 단위"},
            {"app":"crate","surface":"Aisle","sense":"작업 파티션","quote":"존재하지 않는 인용"}]}]
        out=verify_divergence(f, APP_TEXT)
        self.assertEqual(out["stats"]["merges"],0)
        self.assertIn("provenance", out["rejected"][0]["reason"])

if __name__=="__main__":
    unittest.main()
