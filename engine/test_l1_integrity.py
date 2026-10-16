"""결정↔코드 드리프트 검출기 — reflected_but_present.

새 침식 유형(dead/ambiguous·낡은 권위 인용과 다름): '반영완료'로 선언된 결정이
값 폐지를 명시했는데 대상 state_enum에 그 값이 잔존. depth-fill 1회성 발견
(StoreType.popup 잔존)을 상설 검출기로. 출력=제안, 확정=담당자 몫.
"""
import unittest
from pathlib import Path

import yaml

from l1_integrity import reflected_but_present

_HERE = Path(__file__).parent
_GOLD = _HERE / "fixtures" / "acme-docs" / "bench" / "decision-code-drift"


def _enum(anchor, values, scope="meadow/inv"):
    return {"anchor": anchor, "kind": "state_enum", "scope": scope,
            "values": list(values), "refs": {"decisions": [], "articles": []}}


class TestReflectedButPresent(unittest.TestCase):
    ENUMS = [_enum("StoreType", ["default", "personal", "group"])]

    def test_reflected_removes_but_value_present_flags_drift(self):
        # 반영완료 + personal 폐지 선언인데 state_enum에 personal 잔존 → 1건
        decs = [{"decision_id": "D-4406", "scope": "meadow/inv", "reflected": True,
                 "target": "StoreType", "removes": ["personal"]}]
        rep = reflected_but_present(decs, self.ENUMS)
        self.assertEqual(rep["stats"]["drift"], 1)
        d = rep["drift"][0]
        self.assertEqual((d["decision_id"], d["target"], d["value"]),
                         ("D-4406", "StoreType", "personal"))

    def test_value_already_removed_no_flag(self):
        # 폐지 대상 값이 이미 enum에서 사라짐 → abstention(0건)
        decs = [{"decision_id": "D-4406", "scope": "meadow/inv", "reflected": True,
                 "target": "StoreType", "removes": ["legacy_admin"]}]
        self.assertEqual(reflected_but_present(decs, self.ENUMS)["stats"]["drift"], 0)

    def test_not_reflected_no_flag(self):
        # 아직 반영 안 된 결정 → 드리프트 아님
        decs = [{"decision_id": "D-9917", "scope": "meadow/inv", "reflected": False,
                 "target": "StoreType", "removes": ["group"]}]
        self.assertEqual(reflected_but_present(decs, self.ENUMS)["stats"]["drift"], 0)

    def test_no_removes_no_flag(self):
        # 폐지 의미가 없는 결정(removes 미표기) → 무시
        decs = [{"decision_id": "D-7802", "scope": "meadow/inv", "reflected": True,
                 "target": "StoreType"}]
        self.assertEqual(reflected_but_present(decs, self.ENUMS)["stats"]["drift"], 0)

    def test_missing_target_enum_no_flag(self):
        # 대상 state_enum 자체가 없음 → 무플래그(드리프트 유형 아님)
        decs = [{"decision_id": "D-4406", "scope": "meadow/inv", "reflected": True,
                 "target": "NonExistentType", "removes": ["personal"]}]
        self.assertEqual(reflected_but_present(decs, self.ENUMS)["stats"]["drift"], 0)

    def test_scope_filters_wrong_app_enum(self):
        # 같은 anchor라도 다른 scope의 enum은 대상 아님 (오귀속 방지)
        enums = [_enum("StoreType", ["default", "personal", "group"], scope="other/app")]
        decs = [{"decision_id": "D-4406", "scope": "meadow/inv", "reflected": True,
                 "target": "StoreType", "removes": ["personal"]}]
        self.assertEqual(reflected_but_present(decs, enums)["stats"]["drift"], 0)


class TestDecisionCodeDriftGold(unittest.TestCase):
    def setUp(self):
        # 데이터 분리 — 엔진 레포는 동료 초청용이라 회사 코퍼스가 없을 수
        # 있다. 없으면 skip이지 통과가 아니다(vacuous-pass 규약).
        from pathlib import Path
        if not (Path(__file__).parent /
                "fixtures/acme-docs/bench/decision-code-drift").exists():
            self.skipTest("회사 코퍼스 미장착(데이터 분리) — gold 검사 대상 없음(통과 아님)")

    def _load(self, name):
        return yaml.safe_load((_GOLD / name).read_text(encoding="utf-8"))

    def test_gold_matches_expected(self):
        events = self._load("events.yaml")
        expected = self._load("expected.yaml")
        rep = reflected_but_present(events["decisions"], events["concepts"])
        got = sorted((d["decision_id"], d["target"], d["value"]) for d in rep["drift"])
        want = sorted((e["decision_id"], e["target"], e["value"])
                      for e in expected["drift"])
        self.assertEqual(got, want)
        self.assertEqual(rep["stats"]["drift"], expected["stats"]["drift"])

    def test_gold_has_exactly_one_drift_and_abstentions(self):
        events = self._load("events.yaml")
        rep = reflected_but_present(events["decisions"], events["concepts"])
        self.assertEqual(rep["stats"]["drift"], 1)          # personal 잔존 정확히 1건


if __name__ == "__main__":
    unittest.main()


class TestLoadDecisionsNeedsSource(unittest.TestCase):
    def test_missing_source_refuses_instead_of_empty_decisions(self):
        """원천 부재 시 빈 목록으로 대조하지 않는다 — 결정 참조 전부가 '죽은 참조'로 오독된다."""
        import tempfile
        from pathlib import Path
        from l1_integrity import _load_decisions
        with tempfile.TemporaryDirectory() as d:
            here = Path(d)
            (here / "registry.yaml").write_text(
                "corpora:\n  t:\n    source: ./no-such-source\n    decision_format: x\n",
                encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                _load_decisions("t", here)
