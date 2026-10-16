"""S3a 조항 전문 입력과 `governed_by` 해소 (설계 §2-1·§2-2, 소유자 결정 2026-08-04).

★왜 짧은 ID를 받나: 현행 평면은 이벤트 `target`(`PRIME-COMMERCE.SUMMIT.INV.T.INV-D-7318`)과
대조하는데, 그 dotted 문자열은 **문서에 없다.** LLM에게 쓰게 하면 지어냄 위험이 크고
왕복 게이트로 검증할 수도 없다. 문서 표기(`INV-D-7318`)를 받아 결정론이 해소한다 —
원장에 없는 ID는 해소되지 않으므로 지어냄이 구조적으로 무력하다."""
import tempfile
import unittest
from pathlib import Path

import yaml

import structure_app as sa


EVENTS = [{"event_id": "e1", "type": "adopt", "option": "o_INV-D-7318",
           "target": "PRIME-COMMERCE.SUMMIT.INV.T.INV-D-7318",
           "scope": "prime-commerce/summit/inv", "authority_level": "product",
           "valid_at": "2026-01-01", "recorded_at": "2026-01-01"}]


class TestDecisionRefIndex(unittest.TestCase):
    def test_short_id_resolves_to_the_event_target(self):
        idx = sa.decision_ref_index(EVENTS)
        self.assertEqual(idx["INV-D-7318"], "PRIME-COMMERCE.SUMMIT.INV.T.INV-D-7318")

    def test_full_dotted_target_still_resolves_to_itself(self):
        """이미 정본 표기로 준 경우도 받아준다(구 원장 호환)."""
        idx = sa.decision_ref_index(EVENTS)
        t = "PRIME-COMMERCE.SUMMIT.INV.T.INV-D-7318"
        self.assertEqual(sa.resolve_decision_ref(t, idx), t)

    def test_invented_id_does_not_resolve(self):
        """지어낸 ID는 정본에 못 들어간다 — 게이트가 아니라 구조가 막는다."""
        idx = sa.decision_ref_index(EVENTS)
        self.assertIsNone(sa.resolve_decision_ref("INV-D-9999", idx))

    def test_index_is_built_from_the_last_dotted_segment(self):
        evs = [{"target": "A.B.C.T.FOO-D-1"}, {"target": "A.B.C.T.FOO-D-2"}]
        self.assertEqual(sorted(sa.decision_ref_index(evs)), ["FOO-D-1", "FOO-D-2"])


class TestPromoteResolvesGovernedBy(unittest.TestCase):
    def _run(self, tmp, governed_by):
        base = tmp / "probe"
        base.mkdir()
        sc = {"anchor": "sc-x", "name": "X", "quote": "q"}
        if governed_by:
            sc["governed_by"] = governed_by
        yaml.safe_dump({"subconcepts": [sc]}, open(base / "subconcepts.yaml", "w"),
                       allow_unicode=True)
        yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
        yaml.safe_dump({"queue": [{"sid": "inv#sc-x", "was": "new",
                                   "disposition": "auto_adopt", "quote": "q"}], "carried": []},
                       open(base / "adjudication.yaml", "w"), allow_unicode=True)
        stack = tmp / "canon.yaml"
        yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                        "held": {"candidate": [], "ambiguous": [], "gap": []}},
                       open(stack, "w"), allow_unicode=True)
        sa.run_promote(base, "inv", stack, app_scope="prime-commerce/summit/inv",
                       events=EVENTS)
        return yaml.safe_load(open(stack))

    def test_document_notation_fills_the_current_plane(self):
        with tempfile.TemporaryDirectory() as td:
            saved = self._run(Path(td), "INV-D-7318")
        node = {c["anchor"]: c for c in saved["concepts"]}["inv#sc-x"]
        self.assertEqual(node["current"]["value"], "o_INV-D-7318")

    def test_unresolvable_ref_is_recorded_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            saved = self._run(Path(td), "INV-D-9999")
        self.assertEqual(saved["meta"]["unresolved_governed_by"],
                         [{"sid": "inv#sc-x", "ref": "INV-D-9999"}])
        node = {c["anchor"]: c for c in saved["concepts"]}["inv#sc-x"]
        self.assertNotIn("current", node)          # 지어낸 건 정본에 안 들어간다

    def test_absent_governed_by_is_normal_not_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            saved = self._run(Path(td), None)
        self.assertNotIn("unresolved_governed_by", saved["meta"])
        self.assertIn("current_plane", saved["meta"].get("skipped", {}))


class TestPrepWritesArticles(unittest.TestCase):
    TIER_A = [
        {"anchor": "INV-09", "kind": "article", "scope": "prime-commerce/summit/inv",
         "section": "생성·수정", "content": "상품은 최소 1개 카테고리에 소속되어야 하며"},
        {"anchor": "STK-01", "kind": "article", "scope": "prime-commerce/atlas/stock",
         "content": "다른 앱 조항"},
        {"anchor": "spec§개요", "kind": "spec_section", "scope": "prime-commerce/summit/inv",
         "content": "조항이 아니다"},
    ]

    def _prep(self, tmp):
        base = tmp / "probe"
        base.mkdir()
        yaml.safe_dump({"sections": [{"anchor": "s1", "doc": "d", "text": "본문"}]},
                       open(base / "sections.yaml", "w"), allow_unicode=True)
        sa.run_prep(base, "prime-commerce/summit/inv", self.TIER_A, snap="aaa")
        return yaml.safe_load(open(base / "articles.yaml"))

    def test_same_scope_units_get_full_text(self):
        """★2026-08-05 일반화: 서술 단위는 조항만이 아니다."""
        with tempfile.TemporaryDirectory() as td:
            doc = self._prep(Path(td))
        arts = {a["anchor"]: a for a in doc["articles"]}
        self.assertEqual(sorted(arts), ["INV-09", "spec§개요"])   # 타 앱만 제외
        self.assertEqual(arts["spec§개요"]["kind"], "spec_section")
        joined = " ".join(t["text"] for t in arts["INV-09"]["texts"])
        self.assertIn("최소 1개 카테고리에 소속되어야 하며", joined)   # head 120자 절단 없음
        self.assertEqual(arts["INV-09"]["section"], "생성·수정")

    def test_canon_context_stays_slim(self):
        """조항 전문을 canon-context에 합치지 않는다 — S2 입력까지 부풀리지 않는다."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            self._prep(tmp)
            ctx = yaml.safe_load(open(tmp / "probe" / "canon-context.yaml"))["canon"]
        for c in ctx:
            self.assertLessEqual(len(c.get("head") or ""), 120)
            self.assertNotIn("texts", c)




class TestSlimCanonKeepsTier(unittest.TestCase):
    """canon-context는 Tier A와 Tier B를 구분해서 보여준다.

    ★계약 §1b는 "Tier B 항목은 `tier: B`로 표시된다"고 말한다. 그런데 `_slim_canon`이
    투영에서 `tier`를 떨어뜨리고 있었다 — 추출기가 '이건 지난 회차에
    내가 정본화한 개념'과 '원문 조항'을 구분할 수 없다. anchor 모양(`app#sc-x`)으로
    유추할 수는 있지만, 계약이 명시한 신호를 코드가 안 주는 건 그냥 계약 위반이다."""

    def test_tier_survives_the_slim_projection(self):
        out = sa._slim_canon({"anchor": "inv#sc-x", "kind": "concept",
                              "scope": "s/inv", "name": "X", "content": "c", "tier": "B"})
        self.assertEqual(out["tier"], "B")

    def test_tier_a_is_labelled_too(self):
        out = sa._slim_canon({"anchor": "INV-09", "kind": "article",
                              "scope": "s/inv", "content": "c", "tier": "A"})
        self.assertEqual(out["tier"], "A")

    def test_untiered_record_stays_untiered(self):
        out = sa._slim_canon({"anchor": "X", "kind": "article", "scope": "s", "content": "c"})
        self.assertNotIn("tier", out)


if __name__ == "__main__":
    unittest.main()


class TestDecisionRefIndexCoversEvents(unittest.TestCase):
    """결정 참조는 **결정 지점**만이 아니라 **그 지점을 바꾼 사건**도 가리킨다.

    그런데 **문서는 그렇게 안 쓴다.** 문서는 "INV-D-7318 → INV-D-8812로 정정"이라 쓰고,
    개념의 현재 모습을 정한 건 D-8812이다. 원장이 틀린 게 아니라 인덱스가 좁았다 —
    원장은 `source: ['INV-D-8812']`로 이미 정확히 알고 있었다.

    해소 대상: 그 사건이 작용한 target. D-8812 → `…T.INV-D-7318`(그 지점의 현행이 o_INV-D-8812)."""

    EVENTS = [
        {"event_id": "P.S.INV.auto.INV-D-7318", "type": "adopt", "option": "o_INV-D-7318",
         "target": "P.S.INV.T.INV-D-7318", "source": ["INV-D-7318"],
         "scope": "s/inv", "authority_level": "product",
         "valid_at": "2026-05-18", "recorded_at": "2026-05-18"},
        {"event_id": "P.S.INV.auto.INV-D-8812", "type": "supersede", "option": "o_INV-D-8812",
         "target": "P.S.INV.T.INV-D-7318", "source": ["INV-D-8812"], "supersedes": "o_INV-D-7318",
         "scope": "s/inv", "authority_level": "product",
         "valid_at": "2026-07-28", "recorded_at": "2026-07-28"},
    ]

    def test_event_id_resolves_to_the_target_it_acted_on(self):
        idx = sa.decision_ref_index(self.EVENTS)
        self.assertEqual(idx["INV-D-8812"], "P.S.INV.T.INV-D-7318")

    def test_the_decision_point_itself_still_resolves(self):
        idx = sa.decision_ref_index(self.EVENTS)
        self.assertEqual(idx["INV-D-7318"], "P.S.INV.T.INV-D-7318")

    def test_target_wins_when_a_ref_is_both(self):
        """같은 표기가 지점이자 사건이면 **지점**이 이긴다(더 안정적인 정체성)."""
        idx = sa.decision_ref_index(self.EVENTS)
        self.assertEqual(idx["INV-D-7318"], "P.S.INV.T.INV-D-7318")

    def test_still_refuses_an_invented_id(self):
        self.assertIsNone(sa.resolve_decision_ref("INV-D-9999",
                                                  sa.decision_ref_index(self.EVENTS)))

    def test_superseding_decision_yields_the_current_option(self):
        """D-8812로 해소하면 그 지점의 **현행**이 나온다 — 이게 현행 평면의 값이다."""
        idx = sa.decision_ref_index(self.EVENTS)
        cur = sa.resolve_current(sa.resolve_decision_ref("INV-D-8812", idx),
                                 self.EVENTS, "2030-12-31", "2030-12-31")
        self.assertEqual(cur["value"], "o_INV-D-8812")
        self.assertEqual(cur["superseded"], ["o_INV-D-7318"])


class TestGovernedByViaArticles(unittest.TestCase):
    """조항 경유 `governed_by` 전파 — 개념이 조항을 물려받으면 그 조항의 근거도 물려받는다.

    ★근거: 화면정의서 장르는 결정 ID를 안 쓰고 `[INV-NN]` 조항 ID로만 근거를 댄다.
    그런데 결정 ID는 그 조항의 `근거` 필드에 살아 있다(`INV-45` → `INV-D-8812`).
    개념이 이미 그 조항을 본문으로 갖고 있으면, 근거도 같이 따라오는 게 맞다.

    ★단 **추출기가 직접 쓴 `governed_by`가 언제나 이긴다.** 전파는 빈자리만 채운다 —
    사람(문서)이 명시한 것이 기계 유도보다 권위가 높다는 원칙(계약 §자동 편입과 동형)."""

    ARTICLES = [{"anchor": "INV-45", "texts": [
        {"key": "content", "text": "결제 실패에 따른 주문 보류는"},
        {"key": "fields.근거", "text": "INV-D-8812 — 보류 해제 시 단가 재확정"}]}]

    def test_decision_id_is_read_from_article_fields(self):
        self.assertEqual(sa.article_decision_refs(self.ARTICLES), {"INV-45": "INV-D-8812"})

    def test_article_without_a_decision_id_yields_nothing(self):
        self.assertEqual(sa.article_decision_refs(
            [{"anchor": "X-1", "texts": [{"key": "content", "text": "근거 없음"}]}]), {})

    def test_propagation_fills_only_empty_slots(self):
        subs = [{"anchor": "sc-a"}, {"anchor": "sc-b", "governed_by": "INV-D-9917"}]
        members = {"inv#sc-a": [{"article": "INV-45"}], "inv#sc-b": [{"article": "INV-45"}]}
        got = sa.propagate_governed_by(subs, members, self.ARTICLES, app="inv")
        self.assertEqual(got["inv#sc-a"], "INV-D-8812")
        self.assertNotIn("inv#sc-b", got)          # 추출기가 쓴 것이 이긴다

    def test_two_articles_disagreeing_is_left_alone(self):
        """조항마다 다른 결정을 가리키면 기계가 고르지 않는다 — 지어냄 방지."""
        arts = self.ARTICLES + [{"anchor": "INV-52", "texts": [
            {"key": "fields.근거", "text": "INV-D-7764 — 다른 결정"}]}]
        members = {"inv#sc-a": [{"article": "INV-45"}, {"article": "INV-52"}]}
        self.assertEqual(sa.propagate_governed_by([{"anchor": "sc-a"}], members, arts, "inv"), {})
