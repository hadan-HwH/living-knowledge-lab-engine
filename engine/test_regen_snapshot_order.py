"""정본을 **자기보다 오래된 스냅샷으로** 재생하지 않는다 — 불변식 11.

원인은 코드가 아니라 **선언이 정본보다 뒤처진 것**이었다:

    정본 `meta.source_sha`      = 4a0a003
    registry `canon_snap`       = aa0a005
    aa0a005의 screen_section 중앙값 = 제목 길이 수준
    4a0a003의 screen_section 중앙값 = 그 수십 배

`regen.sh`는 `--snap` 없으면 registry 선언을 쓴다. 그래서 **얇은 옛 텍스트로 본문을 다시
펼치고 두꺼운 현행 텍스트를 이력으로 밀어냈다.** 조각은 하나도 안 사라졌으므로
(축 2가 제 할 일을 했다) 보존 계열 게이트는 전부 초록이고, 겉보기엔 성공한 회차다.

★그래서 **시점 자체**에 게이트를 건다: 정본이 이미 T에서 만들어졌으면 T보다 오래된
스냅샷으로는 재생하지 않는다. 롤백은 정당한 작업이라 금지가 아니라 **명시**를 요구한다."""
import unittest

import structure_app as sa


class TestSnapshotRegression(unittest.TestCase):
    IDX = [{"sha": "4a0a003", "generated_at": "2026-08-05T23:54:04+00:00"},
           {"sha": "aa0a005", "generated_at": "2026-08-02T23:58:11+00:00"}]

    def test_regenerating_from_an_older_snapshot_is_refused(self):
        r = sa.check_snapshot_order("aa0a005", "4a0a003", self.IDX)
        self.assertFalse(r["ok"])
        self.assertEqual(r["canon"], "4a0a003")
        self.assertEqual(r["requested"], "aa0a005")

    def test_the_same_snapshot_is_fine(self):
        self.assertTrue(sa.check_snapshot_order("4a0a003", "4a0a003", self.IDX)["ok"])

    def test_a_newer_snapshot_is_fine(self):
        self.assertTrue(sa.check_snapshot_order("4a0a003", "aa0a005", self.IDX)["ok"])

    def test_a_canon_with_no_source_sha_passes(self):
        """첫 회차 — 대조할 게 없으면 위반이라 부르지 않는다(불변식 9와 같은 규율)."""
        self.assertTrue(sa.check_snapshot_order("aa0a005", None, self.IDX)["ok"])

    def test_an_unknown_sha_passes_rather_than_guessing(self):
        """시각을 모르면 **막지 않는다** — 모르는 것을 위반이라 부르면 게이트가 죽는다."""
        self.assertTrue(sa.check_snapshot_order("zzz9999", "4a0a003", self.IDX)["ok"])
        self.assertTrue(sa.check_snapshot_order("aa0a005", "zzz9999", self.IDX)["ok"])

    def test_a_snapshot_without_a_timestamp_passes(self):
        idx = [{"sha": "a"}, {"sha": "b", "generated_at": "2026-08-05T00:00:00+00:00"}]
        self.assertTrue(sa.check_snapshot_order("a", "b", idx)["ok"])

    def test_the_report_carries_both_timestamps_for_the_message(self):
        r = sa.check_snapshot_order("aa0a005", "4a0a003", self.IDX)
        self.assertEqual(r["requested_at"], "2026-08-02T23:58:11+00:00")
        self.assertEqual(r["canon_at"], "2026-08-05T23:54:04+00:00")


if __name__ == "__main__":
    unittest.main()
