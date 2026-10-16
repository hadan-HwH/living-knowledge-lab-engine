"""통합 패스 후보 생성 — 배치 경계를 넘는 유일한 경로.

이 모듈은 **후보만** 낸다. 무엇이 같은 개념인지는 판정하지 않는다."""
import unittest

from consolidate import merge_candidates, candidate_groups, apply_consolidation


def C(anchor, name):
    return {"anchor": anchor, "name": name}


class TestMergeCandidates(unittest.TestCase):
    def test_pairs_concepts_sharing_two_name_tokens(self):
        concepts = [C("a", "청킹은 턴 경계로만 — 예산 초과 단일 턴은 자르지 않는다"),
                    C("b", "chunk_turns — 턴 경계로만 분할, 예산 초과 단일 턴 보존"),
                    C("c", "전혀 무관한 주제의 서술")]
        out = merge_candidates(concepts, {})
        self.assertEqual([(p["a"], p["b"]) for p in out], [("a", "b")])
        self.assertIn("예산", out[0]["shared"])          # 어간화 안 걸리는 토큰
        self.assertIn("경계로", out[0]["shared"])        # `경계로만`의 어간

    def test_one_shared_token_is_not_enough(self):
        """낱말 하나 겹침은 신호가 아니다 — 오탐이 판정 비용을 잡아먹는다."""
        out = merge_candidates([C("a", "게이트 통과 기준"), C("b", "게이트")], {})
        self.assertEqual(out, [])

    def test_common_words_do_not_link(self):
        """흔한 낱말로 묶이면 전부가 후보가 된다 — 상한을 넘는 토큰은 신호에서 뺀다."""
        concepts = [C(f"x{i}", f"정본 개념 항목{i}") for i in range(30)]
        self.assertEqual(merge_candidates(concepts, {}, max_docfreq=20), [])

    def test_multi_unit_concepts_are_not_candidates(self):
        """이미 모은 개념은 통합 대상이 아니다 — 대상은 단위 1개짜리다."""
        bodies = {"a": [{"key": "U1|content"}, {"key": "U2|content"}],
                  "b": [{"key": "U3|content"}]}
        concepts = [C("a", "청킹은 턴 경계로만 — 예산 초과 단일 턴은 자르지 않는다"),
                    C("b", "chunk_turns — 턴 경계로만 분할, 예산 초과 단일 턴 보존")]
        self.assertEqual(merge_candidates(concepts, bodies), [])

    def test_quote_only_concepts_are_candidates(self):
        """조각이 quote뿐이면 단위 0이라 여전히 대상이다."""
        bodies = {"a": [{"key": "quote"}], "b": [{"key": "quote"}]}
        concepts = [C("a", "청킹은 턴 경계로만 — 예산 초과 단일 턴은 자르지 않는다"),
                    C("b", "chunk_turns — 턴 경계로만 분할, 예산 초과 단일 턴 보존")]
        self.assertEqual(len(merge_candidates(concepts, bodies)), 1)

    def test_deterministic_and_sorted(self):
        concepts = [C("z", "시점 필드 분리 계약"), C("a", "시점 필드 분리 규약")]
        a = merge_candidates(concepts, {})
        b = merge_candidates(list(reversed(concepts)), {})
        self.assertEqual(a, b)
        self.assertEqual((a[0]["a"], a[0]["b"]), ("a", "z"))

    def test_nameless_concept_is_skipped(self):
        out = merge_candidates([C("a", None), C("b", None)], {})
        self.assertEqual(out, [])

    def test_machine_does_not_decide_sameness(self):
        """★후보에 판정 필드가 없다 — 있으면 그건 병합이 아니라 추출이다."""
        out = merge_candidates([C("a", "청킹은 턴 경계로만 — 예산 초과 단일 턴은 자르지 않는다"),
                                C("b", "chunk_turns — 턴 경계로만 분할, 예산 초과 단일 턴 보존")], {})
        self.assertNotIn("same", out[0])
        self.assertNotIn("merge", out[0])
        self.assertEqual(set(out[0]) & {"verdict", "decision"}, set())


class TestCandidateGroups(unittest.TestCase):
    """판정 비용은 **묶음 단위**로 든다 — 쌍으로 주면 같은 개념을 여러 번 묻는다."""

    def test_transitive_pairs_become_one_group(self):
        pairs = [{"a": "x", "b": "y", "shared": ["t1", "t2"]},
                 {"a": "y", "b": "z", "shared": ["t1", "t3"]}]
        self.assertEqual(candidate_groups(pairs), [["x", "y", "z"]])

    def test_disjoint_pairs_stay_separate(self):
        pairs = [{"a": "x", "b": "y", "shared": []},
                 {"a": "p", "b": "q", "shared": []}]
        self.assertEqual(candidate_groups(pairs), [["p", "q"], ["x", "y"]])

    def test_groups_are_sorted_deterministically(self):
        pairs = [{"a": "b", "b": "a", "shared": []}]
        self.assertEqual(candidate_groups(pairs), [["a", "b"]])


if __name__ == "__main__":
    unittest.main()


class TestJaccardPreventsBlowup(unittest.TestCase):
    """★공유 개수만 쓰면 전이 폐포가 폭주한다 (실측: 수백 개짜리 묶음 하나).

    긴 이름이 허브가 되어 약한 연결이 사슬로 이어진다. 판정 단위로 못 쓰는 묶음은
    후보가 아니라 잡음이다 — 기계가 좁혀 주는 게 이 모듈의 존재 이유인데 안 좁힌 셈.
    비율(Jaccard)을 걸면 같은 데이터에서 최대 묶음이 9로 떨어진다.
    """

    def test_weak_overlap_on_long_names_is_rejected(self):
        long_a = "게이트 통과 기준 정본 편입 판정 큐 사후 리뷰 소유자 대기 항목"
        long_b = "게이트 통과 기준 전혀 다른 축의 서술 단위 귀속 조각 본문 조립"
        out = merge_candidates([C("a", long_a), C("b", long_b)], {}, min_jaccard=0.5)
        self.assertEqual(out, [])

    def test_strong_overlap_survives(self):
        out = merge_candidates([C("a", "시점 필드 분리 계약 valid_at observed_at"),
                                C("b", "시점 필드 분리 규약 valid_at observed_at")],
                               {}, min_jaccard=0.5)
        self.assertEqual(len(out), 1)
        self.assertGreaterEqual(out[0]["jaccard"], 0.5)

    def test_jaccard_recorded_for_audit(self):
        out = merge_candidates([C("a", "시점 필드 분리 계약 valid_at"),
                                C("b", "시점 필드 분리 규약 valid_at")], {})
        self.assertIn("jaccard", out[0])


class TestSameUnitSignal(unittest.TestCase):
    """★두 번째 축 — **같은 출처 단위에서 나온 개념들** (판정 패스가 지적해서 넣었다)."""

    def test_same_single_unit_becomes_candidate(self):
        bodies = {"a": [{"key": "U1|content"}], "b": [{"key": "U1|content"}]}
        out = merge_candidates([C("a", "전혀 다른 이름"), C("b", "겹치지 않는 이름")],
                               bodies)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["signal"], "same_unit")

    def test_different_units_are_not_candidates(self):
        bodies = {"a": [{"key": "U1|content"}], "b": [{"key": "U2|content"}]}
        self.assertEqual(merge_candidates([C("a", "가나다라"), C("b", "마바사아")],
                                          bodies), [])

    def test_name_signal_is_labelled(self):
        out = merge_candidates([C("a", "시점 필드 분리 계약 valid_at observed_at"),
                                C("b", "시점 필드 분리 규약 valid_at observed_at")], {})
        self.assertEqual(out[0]["signal"], "name")

    def test_hub_unit_is_not_a_signal(self):
        """한 단위에 개념이 잔뜩 물려 있으면 신호가 아니라 그냥 긴 문서다."""
        bodies = {f"x{i}": [{"key": "U1|content"}] for i in range(12)}
        concepts = [C(f"x{i}", f"이름{i}") for i in range(12)]
        self.assertEqual(merge_candidates(concepts, bodies, max_unit_group=8), [])

    def test_structure_words_do_not_link(self):
        """★판정 패스 실측 오탐 — 절 제목 어휘(`사전 등록`·`하지 않을 것`)로 묶인 것."""
        out = merge_candidates([C("a", "사전 등록 — 한계와 다음"),
                                C("b", "사전 등록 — 한계와 다음")], {})
        self.assertEqual(out, [])


class TestApplyConsolidation(unittest.TestCase):
    """★판정을 정본에 반영한다 — 결정론. 판정은 이미 났고 여기선 옮기기만 한다.

    규율(이 프로젝트가 반복해서 지켜온 것):
      · **조각은 사라지지 않는다** — 흡수된 개념의 본문은 keep으로 옮겨간다.
      · **계보는 끊기지 않는다** — 흡수된 anchor는 keep의 별칭으로 남는다.
        (그래야 다음 회차 추출이 옛 anchor를 내도 같은 개념으로 이어진다)
      · **관계 끝점도 따라간다** — 안 옮기면 관계가 사라진 개념을 가리킨다.
    """

    def _canon(self):
        return {"concepts": [{"anchor": "lab#sc-keep", "name": "남는다"},
                             {"anchor": "lab#sc-gone", "name": "흡수된다"},
                             {"anchor": "lab#sc-other", "name": "무관"}],
                "bodies": {"lab#sc-keep": [{"key": "U1|content", "text": "가"}],
                           "lab#sc-gone": [{"key": "U2|content", "text": "나"}],
                           "lab#sc-other": [{"key": "U3|content", "text": "다"}]},
                "relations": [{"from": "lab#sc-other", "to": "lab#sc-gone",
                               "canonical": "part_of"}]}

    def _props(self, verdict="merge"):
        return [{"group": 1, "verdict": verdict, "keep": "sc-keep",
                 "absorb": ["sc-gone"], "reason": "같은 명제"}]

    def test_absorbed_concept_removed(self):
        out = apply_consolidation(self._canon(), self._props(), prefix="lab#")
        self.assertEqual({c["anchor"] for c in out["concepts"]},
                         {"lab#sc-keep", "lab#sc-other"})

    def test_fragments_move_not_vanish(self):
        """★시금석 — 조각 총수가 줄면 안 된다."""
        before = self._canon()
        n = sum(len(v) for v in before["bodies"].values())
        out = apply_consolidation(before, self._props(), prefix="lab#")
        self.assertEqual(sum(len(v) for v in out["bodies"].values()), n)
        keys = {f["key"] for f in out["bodies"]["lab#sc-keep"]}
        self.assertEqual(keys, {"U1|content", "U2|content"})

    def test_absorbed_anchor_recorded_for_lineage(self):
        """계보 — 다음 회차가 옛 anchor를 내도 같은 개념으로 이어져야 한다."""
        out = apply_consolidation(self._canon(), self._props(), prefix="lab#")
        keep = [c for c in out["concepts"] if c["anchor"] == "lab#sc-keep"][0]
        self.assertIn("lab#sc-gone", keep.get("absorbed_anchors") or [])

    def test_lexical_aliases_are_not_touched(self):
        """★`aliases`는 **표기 별칭**이라 층이 다르다 — 실 정본은 dict 목록이다.
        섞으면 "뭐라 부르나"와 "뭘 흡수했나"가 한 칸에 산다(합성 테스트가 놓쳤던 자리)."""
        canon = self._canon()
        canon["concepts"][0]["aliases"] = [{"surface": "약칭", "basis": "tier_b"}]
        out = apply_consolidation(canon, self._props(), prefix="lab#")
        keep = [c for c in out["concepts"] if c["anchor"] == "lab#sc-keep"][0]
        self.assertEqual(keep["aliases"], [{"surface": "약칭", "basis": "tier_b"}])

    def test_relations_rekeyed_to_keep(self):
        out = apply_consolidation(self._canon(), self._props(), prefix="lab#")
        self.assertEqual([(r["from"], r["to"]) for r in out["relations"]],
                         [("lab#sc-other", "lab#sc-keep")])

    def test_self_loop_relation_dropped(self):
        canon = self._canon()
        canon["relations"] = [{"from": "lab#sc-keep", "to": "lab#sc-gone",
                               "canonical": "part_of"}]
        out = apply_consolidation(canon, self._props(), prefix="lab#")
        self.assertEqual(out["relations"], [])   # 자기 자신과의 관계는 관계가 아니다

    def test_separate_verdict_changes_nothing(self):
        before = self._canon()
        out = apply_consolidation(before, self._props("separate"), prefix="lab#")
        self.assertEqual(len(out["concepts"]), 3)

    def test_unsure_verdict_changes_nothing(self):
        out = apply_consolidation(self._canon(), self._props("unsure"), prefix="lab#")
        self.assertEqual(len(out["concepts"]), 3)

    def test_unknown_anchor_is_reported_not_silently_skipped(self):
        """무성 누락 금지 — 못 찾은 anchor는 이름을 붙여 돌려준다."""
        props = [{"group": 1, "verdict": "merge", "keep": "sc-keep",
                  "absorb": ["sc-nonexistent"]}]
        out = apply_consolidation(self._canon(), props, prefix="lab#")
        self.assertIn("lab#sc-nonexistent", out["_unresolved"])

    def test_idempotent(self):
        once = apply_consolidation(self._canon(), self._props(), prefix="lab#")
        twice = apply_consolidation(once, self._props(), prefix="lab#")
        self.assertEqual(len(once["concepts"]), len(twice["concepts"]))


class TestConsolidationRecordsRetirement(unittest.TestCase):
    """★정당한 감소는 **기록이 있을 때만** 봐준다(불변식 9의 설계 그대로).

    통합은 개념을 줄인다 — 그게 목적이다. 그런데 기록을 안 남기면 불변식 9가 매번
    위반으로 띄우고, 그러면 *"게이트가 정당한 폐기를 매번 위반으로 띄우면 사람이
    게이트를 무시하기 시작한다"*(`metrics_gate` docstring)는 그 경로를 탄다.
    """

    def _canon(self):
        return {"meta": {}, "concepts": [{"anchor": "lab#sc-keep", "name": "A"},
                                         {"anchor": "lab#sc-gone", "name": "B"}],
                "bodies": {"lab#sc-keep": [{"key": "U1|c", "text": "가"}],
                           "lab#sc-gone": [{"key": "U2|c", "text": "나다"}]},
                "relations": []}

    def _props(self):
        return [{"group": 1, "verdict": "merge", "keep": "sc-keep",
                 "absorb": ["sc-gone"], "reason": "같은 명제"}]

    def test_retirement_is_scoped_to_this_snapshot(self):
        """★`at`이 없으면 면제가 안 걸린다 — 게이트가 source_sha와 대조한다(실측)."""
        canon = self._canon()
        canon["meta"] = {"source_sha": "abc1234"}
        out = apply_consolidation(canon, self._props(), prefix="lab#")
        self.assertEqual(out["meta"]["retired"][0]["at"], "abc1234")

    def test_retirement_recorded_in_meta(self):
        out = apply_consolidation(self._canon(), self._props(), prefix="lab#")
        rec = (out["meta"].get("retired") or [])
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["reason"], "consolidation")
        self.assertEqual(rec[0]["concepts"], 1)

    def test_retirement_covers_every_shrinking_metric(self):
        """개념만 적으면 본문·관계 감소가 위반으로 뜬다."""
        out = apply_consolidation(self._canon(), self._props(), prefix="lab#")
        rec = out["meta"]["retired"][0]
        for k in ("concepts", "bodies", "body_chars", "relations"):
            self.assertIn(k, rec)

    def test_no_record_when_nothing_merged(self):
        props = [{"group": 1, "verdict": "separate"}]
        out = apply_consolidation(self._canon(), props, prefix="lab#")
        self.assertFalse((out.get("meta") or {}).get("retired"))

    def test_distinct_keys_are_preserved_dedup_is_not_loss(self):
        """★시금석 정정 — 통합은 **같은 키**를 합친다. 총수가 주는 건 정상이고,
        **서로 다른 키**가 사라지면 그게 손실이다(실측 감소분은 전부 키 중복이었다)."""
        canon = self._canon()
        canon["bodies"]["lab#sc-gone"] = [{"key": "U1|c", "text": "가"},
                                          {"key": "U9|c", "text": "라"}]
        before = {f["key"] for v in canon["bodies"].values() for f in v}
        out = apply_consolidation(canon, self._props(), prefix="lab#")
        after = {f["key"] for v in out["bodies"].values() for f in v}
        self.assertEqual(before, after)


class TestAbsorbedAnchorsBlockRevival(unittest.TestCase):
    """★유령 부활의 근본 수리.

    통합으로 흡수된 개념의 sid가 낡은 판정 원장에 남아 있어, promote(판정 재적용)가
    돌 때마다 무명 개념 48개로 부활했다. 수동 재적용(apply_consolidation)은 다음
    regen에서 도로 살아나는 수습일 뿐이다 — **판정 재적용이 흡수 기록을 알아야 한다.**
    지식은 안 사라진다: 그 sid의 조각은 이미 keep으로 옮겨가 있다.
    """

    def test_absorbed_sid_rows_are_dropped(self):
        from structure_app import build_dispositions
        adj = {"queue": [{"sid": "lab#sc-gone", "was": "NEW"},
                         {"sid": "lab#sc-alive", "was": "NEW"}]}
        rows = build_dispositions(adj, [{"anchor": "sc-alive", "name": "산다"}],
                                  "lab", auto_adopt=True,
                                  absorbed={"lab#sc-gone"})
        self.assertEqual([r["sid"] for r in rows], ["lab#sc-alive"])

    def test_no_absorbed_set_keeps_old_behavior(self):
        from structure_app import build_dispositions
        adj = {"queue": [{"sid": "lab#sc-gone", "was": "NEW"}]}
        rows = build_dispositions(adj, [{"anchor": "sc-gone", "name": "이름"}],
                                  "lab", auto_adopt=True)
        self.assertEqual(len(rows), 1)
