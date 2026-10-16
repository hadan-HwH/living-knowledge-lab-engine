"""canon_store — 통합 정본 뷰(Tier A ∪ Tier B) 테스트.
설계: docs/2-method/canon-loop-and-consumption-design.md §3 P1-a."""
import unittest

import canon_store as cs


_STACK = {
    "concepts": [
        {"anchor": "mango#sc-devspace-status", "kind": "concept", "scope": "prime-commerce/mango/mango",
         "name": "DevSpace 상태 정책", "basis": "document_stated", "commitment": "working"},
        {"anchor": "mango#sc-step-status", "kind": "state_enum", "scope": "prime-commerce/mango/mango",
         "name": "StepStatus", "basis": "implemented_without_mandate"},
        {"anchor": "mango#sc-gone", "kind": "concept", "scope": "prime-commerce/mango/mango",
         "name": "사라진 개념", "removed_at": "aa0a005"},
    ],
    "bodies": {
        "mango#sc-devspace-status": [{"key": "quote", "text": "DevSpace 상태는 이러하다"}],
        "mango#sc-step-status": [{"key": "quote", "text": "StepStatus"}],
        "mango#sc-gone": [{"key": "quote", "text": "지워진 문장"}],
    },
}


class DepthProjection(unittest.TestCase):
    def test_projects_depth_concepts_into_canon_record_shape(self):
        """★루프 닫기의 심장 — 정본에 올린 Tier B 개념이 canon 레코드로 투영돼야
        다음 회차 추출의 align target 공간에 들어간다.

        canon 레코드 모양은 Tier A와 같아야 한다 — canon_select·_slim_canon이 그
        모양만 안다(투영 계층에서 흡수, 소비자 무수정)."""
        out = cs.depth_to_canon(_STACK)
        by = {c["anchor"]: c for c in out}
        c = by["mango#sc-devspace-status"]
        self.assertEqual(c["kind"], "concept")
        self.assertEqual(c["scope"], "prime-commerce/mango/mango")
        self.assertEqual(c["name"], "DevSpace 상태 정책")
        self.assertEqual(c["content"], "DevSpace 상태는 이러하다")   # head 유도원
        self.assertEqual(c["tier"], "B")
        self.assertEqual(by["mango#sc-step-status"]["kind"], "state_enum")  # kind 보존

    def test_tombstones_are_not_injected(self):
        """삭제 표시된 개념은 주입하지 않는다 — 죽은 개념을 다시 겨냥하게 만들면
        tombstone이 무의미해진다. 이력 조회에는 남지만 추출 입력에는 안 들어간다."""
        anchors = {c["anchor"] for c in cs.depth_to_canon(_STACK)}
        self.assertNotIn("mango#sc-gone", anchors)
        self.assertEqual(len(anchors), 2)

    def test_projection_is_deterministic(self):
        self.assertEqual([c["anchor"] for c in cs.depth_to_canon(_STACK)],
                         ["mango#sc-devspace-status", "mango#sc-step-status"])

    def test_missing_body_yields_empty_content_not_crash(self):
        """bodies에 없는 개념(구 스택·수기 편집)도 죽지 않는다 — content 없으면 빈 문자열.
        head가 비면 canon-context에서 식별자만 보이는 상태이고, 그건 이미 알려진
        한계(mango §6-7)지 크래시 사유가 아니다."""
        out = cs.depth_to_canon({"concepts": [{"anchor": "a#x", "kind": "concept",
                                               "scope": "s", "name": "X"}], "bodies": {}})
        self.assertEqual(out[0]["content"], "")


class MergedView(unittest.TestCase):
    def test_merge_tags_tier_and_keeps_both_sources(self):
        """통합 뷰 = Tier A ∪ Tier B. 두 층을 구분할 수 있어야 진단이 가능하다
        (어느 층이 정렬에 실제로 쓰이는지 = brief의 층별 기여도 계측 전제)."""
        tier_a = [{"anchor": "MANGO-01", "kind": "clause", "scope": "prime-commerce/mango/mango",
                   "content": "조항 본문"}]
        out = cs.merge_canon(tier_a, _STACK)
        by = {c["anchor"]: c for c in out}
        self.assertEqual(by["MANGO-01"]["tier"], "A")
        self.assertEqual(by["mango#sc-step-status"]["tier"], "B")
        self.assertEqual(len(out), 3)                      # A 1 + B 2 (tombstone 제외)

    def test_tier_a_wins_on_anchor_collision(self):
        """같은 anchor면 Tier A가 이긴다 — 결정론이고, 원문 정본이 파생물보다 권위가 높다.
        구조상 Tier B anchor는 `app#` 접두라 충돌이 드물지만 규칙은 명시한다(침묵 금지)."""
        tier_a = [{"anchor": "mango#sc-step-status", "kind": "clause",
                   "scope": "prime-commerce/mango/mango", "content": "A층 본문"}]
        by = {c["anchor"]: c for c in cs.merge_canon(tier_a, _STACK)}
        self.assertEqual(by["mango#sc-step-status"]["tier"], "A")
        self.assertEqual(by["mango#sc-step-status"]["content"], "A층 본문")

    def test_tier_a_internal_collisions_are_preserved_not_deduped(self):
        """★Tier A 내부의 동명 anchor를 삼키면 안 된다 — 스코프가 다르면 다른 레코드다.

        충돌 해소는 이 계층의 일이 아니다. `canon_select._scope_rank`가 스코프 근접도로
        결정론 해소하고 `canon_collisions`가 소실을 보고한다 — 그 앞단에서 미리 지워버리면
        그 장치가 볼 것이 없어진다."""
        tier_a = [{"anchor": "spec§개요", "scope": "x/y/a", "content": "A앱"},
                  {"anchor": "spec§개요", "scope": "x/y/b", "content": "B앱"}]
        out = cs.merge_canon(tier_a, None)
        self.assertEqual(len(out), 2)
        self.assertEqual({c["scope"] for c in out}, {"x/y/a", "x/y/b"})
        self.assertTrue(all(c["tier"] == "A" for c in out))

    def test_no_stack_is_tier_a_only(self):
        """스택이 없거나 비어도(첫 회차·신규 코퍼스) 종전 동작 그대로."""
        tier_a = [{"anchor": "X-1", "kind": "clause", "scope": "s", "content": "c"}]
        self.assertEqual(cs.merge_canon(tier_a, None), [{**tier_a[0], "tier": "A"}])
        self.assertEqual(cs.merge_canon(tier_a, {}), [{**tier_a[0], "tier": "A"}])


if __name__ == "__main__":
    unittest.main()
