"""한 SHA 통합 — 본체(넓이) + 깊은층을 하나의 스냅샷으로 묶고 침식 감시를 관통시킨다."""
import unittest

from depth_snapshot import unify, depth_integrity


def _b(anchor, scope="inv", kind="article"):
    return {"anchor": anchor, "kind": kind, "scope": scope, "content": anchor,
            "refs": {"articles": [], "decisions": []}}


def _d(anchor, scope="meadow", name="X"):
    return {"anchor": anchor, "kind": "concept", "scope": scope, "name": name,
            "commitment": "hypothesis", "confidence": "high"}


class TestUnify(unittest.TestCase):
    def test_layers_are_labeled_and_both_present(self):
        u = unify([_b("INV-02")], {"concepts": [_d("meadow#sc-a")],
                                   "relations": [], "bodies": {}}, sha="abc1234")
        layers = {c["anchor"]: c["layer"] for c in u["concepts"]}
        self.assertEqual(layers, {"INV-02": "breadth", "meadow#sc-a": "depth"})
        self.assertEqual(u["meta"]["source_sha"], "abc1234")
        self.assertEqual(u["meta"]["breadth"], 1)
        self.assertEqual(u["meta"]["depth"], 1)

    def test_collision_is_scope_qualified_not_bare_anchor(self):
        # ★anchor는 전역 고유가 아니다 — (scope, anchor) 쌍으로만 고유하다.
        u = unify([_b("MRUN-01", scope="meadow/meadow"),
                   _b("MRUN-01", scope="meadow/meadow/source/run")],
                  {"concepts": [], "relations": [], "bodies": {}}, sha="abc1234")
        self.assertEqual(u["collisions"], [])
        self.assertEqual(len(u["concepts"]), 2)

    def test_cross_kind_anchor_sharing_is_by_design_not_collision(self):
        # ★field(존재)와 state_enum(값)이 같은 anchor를 공유하는 것은 **설계된 교차**다
        u = unify([_b("Item.Status", scope="inv", kind="field"),
                   _b("Item.Status", scope="inv", kind="state_enum")],
                  {"concepts": [], "relations": [], "bodies": {}}, sha="abc1234")
        self.assertEqual(u["collisions"], [])

    def test_same_scope_kind_and_anchor_is_a_real_collision(self):
        # 같은 scope·kind에서 같은 anchor면 둘 중 하나가 조용히 사라진다 = 최악.
        u = unify([_b("SHARED", scope="meadow", kind="concept")],
                  {"concepts": [_d("SHARED", scope="meadow")],
                   "relations": [], "bodies": {}}, sha="abc1234")
        self.assertEqual(u["collisions"],
                         [{"scope": "meadow", "kind": "concept", "anchor": "SHARED"}])
        self.assertEqual(len(u["concepts"]), 2)      # 소멸 금지 — 둘 다 남는다

    def test_no_collision_when_anchors_differ(self):
        u = unify([_b("INV-02")], {"concepts": [_d("meadow#sc-a")],
                                   "relations": [], "bodies": {}}, sha="abc1234")
        self.assertEqual(u["collisions"], [])

    def test_relations_and_bodies_carried(self):
        depth = {"concepts": [_d("m#sc-a"), _d("m#sc-b")],
                 "relations": [{"from": "m#sc-a", "to": "m#sc-b", "canonical": "part_of"}],
                 "bodies": {"m#sc-a": [{"key": "quote", "text": "가"}]}}
        u = unify([], depth, sha="abc1234")
        self.assertEqual(len(u["relations"]), 1)
        self.assertEqual(u["bodies"]["m#sc-a"][0]["text"], "가")

    def test_deterministic_order(self):
        depth = {"concepts": [_d("m#sc-b"), _d("m#sc-a")], "relations": [], "bodies": {}}
        a = unify([_b("INV-03"), _b("INV-02")], depth, sha="s")
        b = unify([_b("INV-03"), _b("INV-02")], depth, sha="s")
        self.assertEqual([c["anchor"] for c in a["concepts"]],
                         [c["anchor"] for c in b["concepts"]])


class TestDepthIntegrity(unittest.TestCase):
    DEPTH = {"concepts": [_d("m#sc-a"), _d("m#sc-b")],
             "relations": [{"from": "m#sc-a", "to": "m#sc-b", "canonical": "part_of"}],
             "bodies": {"m#sc-a": [{"key": "quote", "text": "살아 있는 문장"}],
                        "m#sc-b": [{"key": "quote", "text": "사라진 문장"}]}}

    def test_clean_layer_reports_zero(self):
        rep = depth_integrity(unify([], self.DEPTH, sha="s"),
                              ["살아 있는 문장이 여기 있다", "사라진 문장도 여기 있다"])
        self.assertEqual(rep["stats"], {"concepts": 2, "relations": 1,
                                        "dangling": 0, "stale_quotes": 0})

    def test_stale_quote_detected(self):
        rep = depth_integrity(unify([], self.DEPTH, sha="s"), ["살아 있는 문장뿐"])
        self.assertEqual(rep["stats"]["stale_quotes"], 1)
        self.assertEqual(rep["stale_quotes"][0]["anchor"], "m#sc-b")

    def test_quote_match_normalizes_whitespace(self):
        # 원문 재포맷(줄바꿈·들여쓰기)은 침식이 아니다 — 공백 정규화 후 대조.
        depth = {"concepts": [_d("m#sc-a")], "relations": [],
                 "bodies": {"m#sc-a": [{"key": "quote", "text": "한 줄  설명"}]}}
        rep = depth_integrity(unify([], depth, sha="s"), ["한 줄\n설명"])
        self.assertEqual(rep["stats"]["stale_quotes"], 0)

    def test_dangling_relation_endpoint_detected(self):
        depth = {"concepts": [_d("m#sc-a")], "relations": [
            {"from": "m#sc-a", "to": "m#sc-GONE", "canonical": "part_of"}], "bodies": {}}
        rep = depth_integrity(unify([], depth, sha="s"), [])
        self.assertEqual(rep["stats"]["dangling"], 1)
        self.assertEqual(rep["dangling"][0]["missing"], ["m#sc-GONE"])

    def test_relation_may_point_into_breadth_layer(self):
        # 깊은층→본체 관계는 정상이다(anti-silo: 조각의 집이 다른 앱일 수 있다).
        depth = {"concepts": [_d("m#sc-a")], "relations": [
            {"from": "m#sc-a", "to": "INV-02", "canonical": "delegates_to"}], "bodies": {}}
        rep = depth_integrity(unify([_b("INV-02")], depth, sha="s"), [])
        self.assertEqual(rep["stats"]["dangling"], 0)

    def test_empty_source_texts_does_not_fake_pass(self):
        # 원문을 못 받았으면 "전부 통과"가 아니라 전건 실효로 떨어져야 한다(fail-closed).
        rep = depth_integrity(unify([], self.DEPTH, sha="s"), [])
        self.assertEqual(rep["stats"]["stale_quotes"], 2)


if __name__ == "__main__":
    unittest.main()
