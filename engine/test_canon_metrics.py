"""정본 지표와 artifact 게이트 (불변식 9, 2026-08-04 소유자 지시).

정본 자체를 재는 지표를 파일로 남기고(`canon/metrics.yaml`), 회차마다
직전과 대조한다. STATUS에 손으로 적는 숫자는 이 파일에서만 인용한다 —
기억이 아니라 파일이 근거가 되게."""
import unittest

from structure_app import canon_metrics, metrics_gate


def _canon(concepts=None, bodies=None, relations=None, meta=None):
    return {"meta": meta or {}, "concepts": concepts or [], "relations": relations or [],
            "bodies": bodies or {}, "held": {"candidate": [], "ambiguous": [], "gap": []}}


class TestCanonMetrics(unittest.TestCase):
    def test_counts_the_things_a_reader_would_ask_for(self):
        doc = _canon(
            concepts=[{"anchor": "inv#a", "name": "A", "scope": "s/inv",
                       "current": {"value": "o1"}},
                      {"anchor": "inv#b", "name": "B", "scope": "s/inv"}],
            bodies={"inv#a": [{"key": "A-1|content", "text": "열두 글자짜리 본문"}]},
            relations=[{"from": "inv#a", "to": "inv#b"}],
            meta={"source_sha": "aa0a005", "dangling_auto_fold": ["inv#z"]})
        m = canon_metrics(doc)
        self.assertEqual(m["concepts"], 2)
        self.assertEqual(m["relations"], 1)
        self.assertEqual(m["body_chars"], len("열두 글자짜리 본문"))
        self.assertEqual(m["current_filled"], 1)
        self.assertEqual(m["nameless"], 0)
        self.assertEqual(m["scopes"], 1)
        self.assertEqual(m["dangling_auto_fold"], 1)
        self.assertEqual(m["source_sha"], "aa0a005")
        self.assertTrue(m["anchor_unique"])

    def test_tombstoned_fragments_do_not_count_as_live_body(self):
        """삭제 표시된 조각은 남지만 본문 총량에는 안 든다 — 아니면 시금석이 거짓말한다."""
        doc = _canon(concepts=[{"anchor": "inv#a", "name": "A", "scope": "s"}],
                     bodies={"inv#a": [{"key": "k1", "text": "살아있음"},
                                       {"key": "k2", "text": "죽음", "removed_at": "aa0a005"}]})
        m = canon_metrics(doc)
        self.assertEqual(m["body_chars"], len("살아있음"))
        self.assertEqual(m["tombstoned_fragments"], 1)

    def test_flags_duplicate_anchors_and_nameless(self):
        doc = _canon(concepts=[{"anchor": "inv#a", "name": "A", "scope": "s"},
                               {"anchor": "inv#a", "scope": "s"}])
        m = canon_metrics(doc)
        self.assertFalse(m["anchor_unique"])
        self.assertEqual(m["nameless"], 1)


class TestMetricsGate(unittest.TestCase):
    """불변식 9 — 정본은 회차를 거치며 줄지 않는다(코드가 아니라 산출물에 건다)."""

    def test_growth_passes(self):
        g = metrics_gate({"concepts": 73, "body_chars": 1982},
                         {"concepts": 479, "body_chars": 103316})
        self.assertTrue(g["ok"])
        self.assertEqual(g["regressions"], [])

    def test_shrinkage_fails_with_the_numbers(self):
        # ★회귀 축은 `body_chars_unique`다. `body_chars`는 중복 제거로도
        # 줄어 정당한 정렬 수리가 매번 위반으로 떴다 — 관측치로만 남긴다.
        g = metrics_gate({"concepts": 479, "body_chars_unique": 103316},
                         {"concepts": 73, "body_chars_unique": 1982})
        self.assertFalse(g["ok"])
        self.assertEqual([r["metric"] for r in g["regressions"]],
                         ["body_chars_unique", "concepts"])
        self.assertEqual(g["regressions"][1], {"metric": "concepts", "was": 479, "now": 73})

    def test_first_run_has_nothing_to_compare_and_passes(self):
        g = metrics_gate(None, {"concepts": 10})
        self.assertTrue(g["ok"])

    def test_duplicate_anchor_fails_the_gate_even_when_everything_grew(self):
        """중복은 늘어나는 방향이라 총량 게이트로는 절대 안 잡힌다 — 명시적으로 건다."""
        g = metrics_gate({"concepts": 10, "anchor_unique": True},
                         {"concepts": 20, "anchor_unique": False})
        self.assertFalse(g["ok"])
        self.assertIn("anchor_unique", [r["metric"] for r in g["regressions"]])




class TestGateKnowsRetirement(unittest.TestCase):
    """은퇴로 인한 감소는 위반이 아니다 — 다만 **기록이 있을 때만** 봐준다.

    ★불변식 9는 "정본은 줄지 않는다"인데, 은퇴는 그 예외로 소유자가 선언한 것이다
. 게이트가 이걸 모르면
    정당한 폐기가 매번 위반으로 뜨고, 그러면 사람이 게이트를 무시하기 시작한다 —
    게이트가 죽는 가장 흔한 경로다.

    ★단 **면제는 기록에 근거한다.** `meta.retired`에 무엇을 언제 왜 뺐는지 남아 있어야
    하고, 감소분이 은퇴분을 넘으면 그 초과분은 여전히 위반이다."""

    def test_reduction_within_retirement_passes(self):
        g = metrics_gate({"concepts": 662}, {"concepts": 149},
                         retired=[{"app": "mango", "concepts": 513}])
        self.assertTrue(g["ok"])
        self.assertEqual(g["retired_total"], 513)

    def test_reduction_beyond_retirement_still_fails(self):
        g = metrics_gate({"concepts": 662}, {"concepts": 100},
                         retired=[{"app": "mango", "concepts": 513}])
        self.assertFalse(g["ok"])
        self.assertEqual([r["metric"] for r in g["regressions"]], ["concepts"])

    def test_retirement_does_not_excuse_other_metrics(self):
        """개념을 은퇴시켰다고 본문·관계까지 마음대로 줄 수 있는 건 아니다 —
        각 지표는 자기 은퇴분만큼만 면제된다."""
        g = metrics_gate({"concepts": 662, "body_chars_unique": 151940},
                         {"concepts": 149, "body_chars_unique": 100},
                         retired=[{"app": "x", "concepts": 513}])
        self.assertFalse(g["ok"])
        self.assertEqual([r["metric"] for r in g["regressions"]], ["body_chars_unique"])

    def test_no_retirement_record_means_no_excuse(self):
        g = metrics_gate({"concepts": 662}, {"concepts": 149})
        self.assertFalse(g["ok"])




class TestReproducibilityGate(unittest.TestCase):
    """불변식 4(재현성) — "같은 입력 → 같은 산출"을 **기계가** 확인한다.

    ★감사에서 드러난 것: 불변식 9종 중 4번만 자동 검사가 없었다.
    규약으로만 두고 매 회차 사람이 손으로 확인했다 — 그게 게이트인 척했을 뿐이다.
    이 프로젝트가 "코드 게이트가 산출물을 안 잰다"를 고쳐놓고, 정작 재현성은
    아무도 안 재는 상태로 남아 있었다.

    재생은 결정론이므로 **한 번 더 돌려 같은 바이트가 나오는지** 보면 된다.
    다르면 어디가 달라졌는지 지표 이름으로 말한다(파일 diff는 사람이 못 읽는다)."""

    def test_identical_docs_reproduce(self):
        from structure_app import reproducibility_report
        doc = _canon(concepts=[{"anchor": "a", "name": "A", "scope": "s"}])
        self.assertTrue(reproducibility_report(doc, doc)["ok"])

    def test_changed_metric_is_named(self):
        from structure_app import reproducibility_report
        a = _canon(concepts=[{"anchor": "a", "name": "A", "scope": "s"}])
        b = _canon(concepts=[{"anchor": "a", "name": "A", "scope": "s"},
                             {"anchor": "b", "name": "B", "scope": "s"}])
        rep = reproducibility_report(a, b)
        self.assertFalse(rep["ok"])
        self.assertIn("concepts", [d["metric"] for d in rep["diffs"]])

    def test_volatile_meta_is_ignored(self):
        """실행 순서에 따라 바뀌는 메타는 재현성 위반이 아니다 — 내용이 같으면 같다.
        `last_promoted_app`이 그런 자리다(앱 순서만 바뀌어도 값이 달라진다)."""
        from structure_app import reproducibility_report
        a = _canon(meta={"last_promoted_app": "inv"})
        b = _canon(meta={"last_promoted_app": "alert"})
        self.assertTrue(reproducibility_report(a, b)["ok"])


if __name__ == "__main__":
    unittest.main()


class TestUnitMultiplicity(unittest.TestCase):
    """★개념이 **몇 개의 서술 단위를 모았나**.

    게이트는 전부 초록이었다: 왕복 100%·증발 0·anchor 유일·quote_gate 0 rejected.
    **형식은 다 맞는데 "개념다운가"를 재는 게이트가 하나도 없었다** — 
    "게이트가 코드를 재지 정본이 그렇게 됐나를 안 잰다"고 잡은 것의 한 층 위 판.

    기계는 판정하지 않는다 — 분포를 **드러내고** 회귀를 잡을 뿐이다."""

    def _doc(self, bodies):
        return {"concepts": [{"anchor": k} for k in bodies], "bodies": bodies}

    def test_counts_distinct_units_not_fragments(self):
        """한 단위에서 여러 필드를 가져와도 단위는 하나다 — 조각 수로 세면 부풀림이 숨는다."""
        doc = self._doc({"a#x": [{"key": "U1|content"}, {"key": "U1|fields.comments"}]})
        m = canon_metrics(doc)["unit_multiplicity"]
        self.assertEqual(m["one"], 1)
        self.assertEqual(m["multi"], 0)

    def test_multi_unit_concept_counted(self):
        doc = self._doc({"a#x": [{"key": "U1|content"}, {"key": "U2|content"}]})
        self.assertEqual(canon_metrics(doc)["unit_multiplicity"]["multi"], 1)

    def test_quote_only_concept_is_none(self):
        """`quote` 조각은 왕복 증거지 단위 귀속이 아니다(계약이 그렇게 갈랐다)."""
        doc = self._doc({"a#x": [{"key": "quote"}]})
        m = canon_metrics(doc)["unit_multiplicity"]
        self.assertEqual(m["none"], 1)
        self.assertEqual(m["one"], 0)

    def test_aggregation_rate_is_multi_over_total(self):
        doc = self._doc({"a#1": [{"key": "U1|c"}, {"key": "U2|c"}],
                         "a#2": [{"key": "U1|c"}],
                         "a#3": [{"key": "quote"}],
                         "a#4": [{"key": "U3|c"}]})
        m = canon_metrics(doc)["unit_multiplicity"]
        self.assertEqual((m["none"], m["one"], m["multi"]), (1, 2, 1))
        self.assertEqual(m["aggregation_rate"], 0.25)

    def test_empty_canon_does_not_divide_by_zero(self):
        m = canon_metrics({"concepts": [], "bodies": {}})["unit_multiplicity"]
        self.assertEqual(m["aggregation_rate"], 0.0)

    def test_aggregation_rate_is_tracked_for_regression(self):
        """지표만 찍고 회귀를 안 잡으면 또 조용히 내려간다."""
        from structure_app import _METRIC_KEYS
        self.assertIn("aggregation_rate", _METRIC_KEYS)
