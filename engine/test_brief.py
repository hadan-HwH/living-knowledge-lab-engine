"""brief — 정본 소비 경로 + 층별 관련성 계측기.
설계: docs/2-method/canon-loop-and-consumption-design.md §3 P2."""
import unittest

import brief


SCOPE = "x/y/app"
TIER_A = [
    {"anchor": "spec§개요", "kind": "spec_section", "scope": SCOPE, "content": "이 앱은 A를 한다"},
    {"anchor": "APP-01", "kind": "article", "scope": SCOPE, "content": "규칙 하나"},
    {"anchor": "APP-02", "kind": "article", "scope": SCOPE, "content": "규칙 둘"},
    {"anchor": "OTHER-01", "kind": "article", "scope": "x/y/other", "content": "남의 앱"},
]
STACK = {
    "concepts": [
        {"anchor": "app#sc-live", "scope": SCOPE, "name": "살아있는 개념",
         "basis": "document_stated", "last_seen": "sha1"},
        {"anchor": "app#sc-gapish", "scope": SCOPE, "name": "코드에만 존재",
         "basis": "implemented_without_mandate"},
        {"anchor": "app#sc-review", "scope": SCOPE, "name": "애매", "needs_review": True},
        {"anchor": "app#sc-dead", "scope": SCOPE, "name": "삭제됨", "removed_at": "sha1"},
        {"anchor": "z#sc-other", "scope": "x/y/other", "name": "남의 개념"},
    ],
    "held": {"gap": [{"sid": "app#sc-heldgap", "name": "보류 갭"}],
             "candidate": [], "ambiguous": []},
}
EVENTS = [
    {"event_id": "E1", "type": "adopt", "target": "T.a", "option": "o1", "scope": SCOPE,
     "authority_level": "product", "valid_at": "2026-01-01", "recorded_at": "2026-01-01"},
    {"event_id": "E2", "type": "defer", "target": "T.b", "option": "o2", "scope": SCOPE,
     "authority_level": "product", "valid_at": "2026-01-02", "recorded_at": "2026-01-02"},
]
INTEGRITY = {"dead": [{"from_id": "APP-D-1", "scope": SCOPE, "ref": "APP-99"},
                      {"from_id": "OTH-D-1", "scope": "x/y/other", "ref": "OTH-9"}],
             "ambiguous": []}
ADJ = [{"sid": "app#sc-bad", "was": "quote_gate_failed", "quote_gate_failed": True},
       {"sid": "app#sc-phantom", "was": "phantom_target"},
       {"sid": "app#sc-normal", "was": "new"}]


def _run(**kw):
    args = dict(scope=SCOPE, tier_a=TIER_A, stack=STACK, events=EVENTS,
                integrity=INTEGRITY, adjudications=ADJ,
                valid_at="2026-12-31", known_at="2026-12-31")
    args.update(kw)
    return brief.build(**args)


class Blocks(unittest.TestCase):
    def test_eight_blocks_always_present_in_fixed_order(self):
        """블록은 조건부로 사라지지 않는다 — 비어도 자리를 지킨다.
        빈 블록이 사라지면 "이 앱은 갭이 없다"와 "갭을 볼 재료가 없다"를 구별할 수 없다."""
        names = [b["name"] for b in _run()["blocks"]]
        self.assertEqual(names, ["정체성", "조항", "개념", "현재 유효 결정",
                                 "미결", "갭", "침식", "리뷰 대기"])

    def test_每_block_declares_its_source_layer(self):
        """각 블록은 어느 층에서 왔는지 밝힌다 — 이게 P4(덜어내기) 판단의 원자료다."""
        layers = {b["name"]: b["layer"] for b in _run()["blocks"]}
        self.assertEqual(layers["조항"], "tier_a")
        self.assertEqual(layers["개념"], "tier_b")
        self.assertEqual(layers["현재 유효 결정"], "decision")
        self.assertEqual(layers["침식"], "integrity")

    def test_scope_filters_every_block(self):
        """남의 앱 것이 섞이면 브리핑이 거짓이 된다."""
        by = {b["name"]: b for b in _run()["blocks"]}
        self.assertEqual([i["anchor"] for i in by["조항"]["items"]], ["APP-01", "APP-02"])
        self.assertNotIn("z#sc-other", [i["anchor"] for i in by["개념"]["items"]])
        self.assertEqual(len(by["침식"]["items"]), 1)

    def test_tombstones_excluded_from_concepts_but_counted(self):
        """삭제된 개념은 현행 목록에 안 나오되 사라지지도 않는다(이력 보존)."""
        by = {b["name"]: b for b in _run()["blocks"]}
        anchors = [i["anchor"] for i in by["개념"]["items"]]
        self.assertNotIn("app#sc-dead", anchors)
        self.assertEqual(by["개념"]["removed"], 1)

    def test_gap_block_merges_basis_and_held(self):
        """갭은 두 곳에서 온다 — 편입된 갭 개념(basis)과 보류 큐의 gap."""
        by = {b["name"]: b for b in _run()["blocks"]}
        self.assertEqual(by["갭"]["count"], 2)

    def test_review_block_is_only_what_a_human_must_see(self):
        """리뷰 대기 = needs_review + 게이트 격리 + 지어냄 격리. 보통 큐 항목은 아니다
        (자동 편입 계약 이후 new/ambiguous는 사람 대기가 아니다)."""
        by = {b["name"]: b for b in _run()["blocks"]}
        sids = {i["anchor"] for i in by["리뷰 대기"]["items"]}
        self.assertEqual(sids, {"app#sc-review", "app#sc-bad", "app#sc-phantom"})

    def test_empty_block_says_why_not_just_zero(self):
        """★침묵 금지 — 빈 블록은 이유를 밝힌다. "재료가 없다"와 "재료는 있는데 해당
        없다"는 다른 진단이고, 이 구별이 P4에서 층을 자를지 말지를 가른다."""
        by = {b["name"]: b for b in _run(events=[])["blocks"]}
        self.assertEqual(by["현재 유효 결정"]["count"], 0)
        self.assertIn("결정층 입력이 없다", by["현재 유효 결정"]["empty_reason"])

        by2 = {b["name"]: b for b in _run(integrity={"dead": [], "ambiguous": []})["blocks"]}
        self.assertEqual(by2["침식"]["count"], 0)
        self.assertIn("해당 없음", by2["침식"]["empty_reason"])


class LayerContribution(unittest.TestCase):
    def test_reports_contribution_per_layer(self):
        """★P4의 계측기 — 층별 기여 항목 수. 0인 층은 이 앱에서 값을 못 낸 것이고,
        전 앱에서 0이면 그 층은 지금 쓸모가 없다는 데이터다(감이 아니라)."""
        c = _run()["contribution"]
        self.assertEqual(c["tier_a"], 3)          # spec 1 + article 2
        # tier_b는 **distinct**다: 개념 3(live·gapish·review) + 갭의 held 1 = 4.
        # gapish는 개념·갭 두 블록에 나오지만 한 번만 센다 — 이중 계상하면 층이 부풀어
        # P4에서 잘라야 할 층을 못 자른다.
        self.assertEqual(c["tier_b"], 4)
        self.assertEqual(c["decision"], 2)        # 활성 T.a + 미결 T.b (서로 다른 target)
        self.assertEqual(c["integrity"], 1)

    def test_zero_contribution_layer_is_reported_not_omitted(self):
        c = _run(integrity={"dead": [], "ambiguous": []})["contribution"]
        self.assertEqual(c["integrity"], 0)
        self.assertIn("integrity", c)


class Render(unittest.TestCase):
    def test_renders_markdown_with_all_blocks_and_reasons(self):
        md = brief.render(_run(events=[]))
        self.assertIn("# 브리핑", md)
        for n in ("정체성", "조항", "개념", "현재 유효 결정", "미결", "갭", "침식", "리뷰 대기"):
            self.assertIn(n, md)
        self.assertIn("결정층 입력이 없다", md)      # 빈 블록도 이유가 보인다


if __name__ == "__main__":
    unittest.main()
