"""cost_ladder TDD — §9-B 비용 조건 하니스. 결정론(LLM 0). 계약 §9-B v1 개정.
설계: docs/2-method/model-ladder-cost-design.md.
"""
import cost_ladder as cl

PRICING = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
}


# ── model_price: 단가 × 토큰 (백만 토큰당) ──────────────────────────────
def test_model_price_input_output_split():
    # sonnet: in 1e6 tok @ $3 + out 1e6 tok @ $15 = $18
    assert cl.model_price("claude-sonnet-5", 1_000_000, 1_000_000, PRICING) == 18.0


def test_model_price_scales_linearly():
    assert cl.model_price("claude-haiku-4-5", 200_000, 100_000, PRICING) == \
        0.2 * 1.0 + 0.1 * 5.0


def test_model_price_unknown_model_raises():
    import pytest
    with pytest.raises(KeyError):
        cl.model_price("gpt-9", 1, 1, PRICING)


def test_model_price_cache_tiers():
    """★첫 실 파이프라인 토큰 로그가 드러낸 갭 — 입력 대부분이 **캐시 읽기**였다
    캐시 읽기는 표준 단가의 0.1×, 캐시 쓰기는
    1.25×라 균일 입력 단가로 계산하면 실 청구를 크게 과대계상한다. 분할 없는 추정은
    금지(설계 §6 정직 원칙)이므로 단가 축도 분할한다."""
    # sonnet in=$3: fresh 1e6 → 3.0 · cache_write 1e6 → 3.75 · cache_read 1e6 → 0.3
    usd = cl.model_price("claude-sonnet-5", 1_000_000, 0, PRICING,
                         cache_creation_tokens=1_000_000, cache_read_tokens=1_000_000)
    assert abs(usd - (3.0 + 3.75 + 0.3)) < 1e-9


def test_model_price_cache_defaults_to_zero_backward_compat():
    assert cl.model_price("claude-sonnet-5", 1_000_000, 1_000_000, PRICING) == 18.0


def test_cost_per_target_uses_cache_tiers_when_logged():
    log = {"model": "claude-sonnet-5", "input_tokens": 0, "output_tokens": 100_000,
           "cache_creation_tokens": 800_000, "cache_read_tokens": 4_000_000,
           "n_targets": 70}
    r = cl.cost_per_target(log, PRICING)
    usd = 0.8 * 3.0 * 1.25 + 4.0 * 3.0 * 0.1 + 0.1 * 15.0
    assert abs(r["usd"] - usd) < 1e-9


# ── cost_per_target: $/target 정규화 ──────────────────────────────────
def test_cost_per_target_divides_by_n_targets():
    log = {"model": "claude-sonnet-5", "input_tokens": 200_000,
           "output_tokens": 40_000, "n_targets": 60}
    r = cl.cost_per_target(log, PRICING)
    usd = 0.2 * 3.0 + 0.04 * 15.0  # = 0.6 + 0.6 = 1.2
    assert abs(r["usd"] - usd) < 1e-9
    assert abs(r["usd_per_target"] - usd / 60) < 1e-9
    assert r["n_targets"] == 60


def test_cost_per_target_zero_targets_is_none_not_crash():
    # fail-closed: n_targets 0이면 usd_per_target=None (0 나눗셈 크래시 금지)
    log = {"model": "claude-haiku-4-5", "input_tokens": 100, "output_tokens": 10,
           "n_targets": 0}
    r = cl.cost_per_target(log, PRICING)
    assert r["usd_per_target"] is None


# ── cost_gate: B7 ≤ 2× B3 판정 (fail-closed) ──────────────────────────
def test_cost_gate_pass_when_ratio_under_2():
    b3 = {"usd_per_target": 1.0}
    b7 = {"usd_per_target": 1.8}
    g = cl.cost_gate(b3, b7)
    assert abs(g["ratio"] - 1.8) < 1e-9
    assert g["pass"] is True
    assert g["factor"] == 2.0


def test_cost_gate_fail_when_ratio_over_2():
    g = cl.cost_gate({"usd_per_target": 1.0}, {"usd_per_target": 2.5})
    assert g["pass"] is False


def test_cost_gate_boundary_exactly_2_passes():
    # "2배 이내" = ≤ 2.0 포함
    g = cl.cost_gate({"usd_per_target": 1.0}, {"usd_per_target": 2.0})
    assert g["pass"] is True


def test_cost_gate_missing_data_is_unmeasured_not_pass():
    # fail-closed: 데이터 없으면 pass=None(미측정), 절대 True 아님
    g = cl.cost_gate({"usd_per_target": None}, {"usd_per_target": 1.0})
    assert g["pass"] is None
    assert g["ratio"] is None
    g2 = cl.cost_gate({"usd_per_target": 1.0}, {})
    assert g2["pass"] is None


# ── b3_projection: B7 이벤트 → B3 얕은 스키마 ─────────────────────────
def test_b3_projection_keeps_only_shallow_fields():
    events = [
        {"type": "adopt", "target": "T1", "option": "o1", "valid_at": "2026-01-01",
         "recorded_at": "2026-01-02", "scope": "app", "authority_level": "owner"},
        {"type": "supersede", "target": "T1", "option": "o2", "valid_at": "2026-03-01",
         "supersedes": "o1", "recorded_at": "2026-03-02"},
    ]
    proj = cl.b3_projection(events)
    # target당 얕은 레코드: status/supersedes/effective_from만, 이중시간·scope·rank 제거
    assert all(set(p) <= {"target", "status", "supersedes", "effective_from"}
               for p in proj)
    # recorded_at·authority_level은 투영에 없어야(B3가 못 보는 필드)
    assert all("recorded_at" not in p and "authority_level" not in p for p in proj)


def test_b3_projection_output_smaller_than_b7():
    # §1a 구조 논거의 출력 측: B3 투영이 B7 원본보다 작다(직렬화 크기 프록시)
    events = [
        {"type": "adopt", "target": "T1", "option": "o1", "valid_at": "2026-01-01",
         "recorded_at": "2026-01-02", "scope": "app", "authority_level": "owner",
         "reason_type": "policy"},
    ]
    b7_size = cl.serialized_size(events)
    b3_size = cl.serialized_size(cl.b3_projection(events))
    assert b3_size < b7_size


# ── ladder_table: 티어별 행 + 정확도 통과하는 최저 티어로 판정 ─────────
def test_ladder_picks_cheapest_accuracy_passing_tier():
    entries = [
        {"tier": "저", "model": "claude-haiku-4-5", "accuracy_pass": False,
         "b3_log": {"model": "claude-haiku-4-5", "input_tokens": 100_000,
                    "output_tokens": 10_000, "n_targets": 10},
         "b7_log": {"model": "claude-haiku-4-5", "input_tokens": 100_000,
                    "output_tokens": 18_000, "n_targets": 10}},
        {"tier": "중", "model": "claude-sonnet-5", "accuracy_pass": True,
         "b3_log": {"model": "claude-sonnet-5", "input_tokens": 100_000,
                    "output_tokens": 10_000, "n_targets": 10},
         "b7_log": {"model": "claude-sonnet-5", "input_tokens": 100_000,
                    "output_tokens": 18_000, "n_targets": 10}},
    ]
    out = cl.ladder_table(entries, PRICING)
    # 정확도 통과하는 최저 티어 = 중(sonnet), 저(haiku)는 정확도 미달이라 판정 제외
    assert out["judged_tier"] == "중"
    assert out["cost_gate"]["pass"] is True  # 출력만 8k 차이 → 2× 이내
    # 티어별 행 전부 보존(층 합산 금지)
    assert len(out["rows"]) == 2


def test_ladder_no_accuracy_passing_tier_is_unjudged():
    entries = [
        {"tier": "저", "model": "claude-haiku-4-5", "accuracy_pass": False,
         "b3_log": {"model": "claude-haiku-4-5", "input_tokens": 1, "output_tokens": 1,
                    "n_targets": 1},
         "b7_log": {"model": "claude-haiku-4-5", "input_tokens": 1, "output_tokens": 1,
                    "n_targets": 1}},
    ]
    out = cl.ladder_table(entries, PRICING)
    assert out["judged_tier"] is None
    assert out["cost_gate"]["pass"] is None  # 미측정 — 통과 아님


def test_ladder_deterministic_order():
    # 결정론: 같은 입력 → 같은 rows 순서(tier 입력 순 보존)
    entries = [
        {"tier": "중", "model": "claude-sonnet-5", "accuracy_pass": True,
         "b3_log": {"model": "claude-sonnet-5", "input_tokens": 100, "output_tokens": 10,
                    "n_targets": 5},
         "b7_log": {"model": "claude-sonnet-5", "input_tokens": 100, "output_tokens": 18,
                    "n_targets": 5}},
    ]
    a = cl.ladder_table(entries, PRICING)
    b = cl.ladder_table(entries, PRICING)
    assert a == b


# ── break_even_input: 게이트 통과의 입력/출력 손익분기 ────────────────
def test_break_even_output_ratio_within_factor_always_passes():
    # 출력비 자체가 ≤2 → 입력 무관 항상 통과(x*≤0)
    be = cl.break_even_input(1.8, "claude-sonnet-5", PRICING)
    assert be["always_pass"] is True
    assert be["break_even_x"] == 0.0


def test_break_even_sonnet_matches_closed_form():
    # sonnet k=5, factor=2, r=4.77 → x* = 5*(1-2/4.77)/(2-1)
    be = cl.break_even_input(4.77, "claude-sonnet-5", PRICING)
    expect = 5.0 * (1 - 2 / 4.77) / (2 - 1)
    assert abs(be["break_even_x"] - expect) < 1e-9
    assert be["always_pass"] is False


def test_break_even_none_ratio_is_none():
    be = cl.break_even_input(None, "claude-haiku-4-5", PRICING)
    assert be["break_even_x"] is None


def test_break_even_verifies_gate_consistency():
    # x*에서 정확히 ratio==factor여야(정의 일관성). O_B7=100 임의, O_B3=100/r.
    r, factor, model = 4.77, 2.0, "claude-sonnet-5"
    be = cl.break_even_input(r, model, PRICING, factor)
    pr = PRICING[model]
    o_b7 = 100.0
    o_b3 = o_b7 / r
    inp = be["break_even_x"] * o_b7
    cost_b7 = cl.model_price(model, inp, o_b7, PRICING)
    cost_b3 = cl.model_price(model, inp, o_b3, PRICING)
    assert abs(cost_b7 / cost_b3 - factor) < 1e-9


# ── load_pricing: 데이터에서 단가 로드(소유자 정정 가능) ────────────────
def test_load_pricing_reads_yaml():
    p = cl.load_pricing()  # engine/pricing.yaml
    assert "claude-sonnet-5" in p
    assert p["claude-sonnet-5"]["input"] > 0
