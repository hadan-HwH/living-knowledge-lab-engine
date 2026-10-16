"""§9-B 비용 조건 하니스 — 계약 §9-B(v1 개정: 비용=AI 모델 비용).
설계: docs/2-method/model-ladder-cost-design.md. 결정론(LLM 0), 표준 라이브러리만.

정확도 조건은 벤치 하니스(공개본 미포함)가 채점한다. 여기는 비용 조건: target당 AI 비용 B7 ≤ B3의 2배.
단가는 pricing.yaml에서 읽어 소유자 정정 가능(게이트 수치를 좌우 → 정정 전 결과는 '잠정').

fail-closed 원칙: 데이터가 없으면 pass=None(미측정) — 절대 True(통과)로 세지 않는다.
"""
from __future__ import annotations

# B3(얕은 metadata)가 결정 target당 보는 필드 — status/supersedes/effective_from.
# B7(A-reducer)은 여기에 더해 type·option·valid_at·recorded_at·scope·authority_level.
_B3_FIELDS = ("target", "status", "supersedes", "effective_from")


def load_pricing(path=None):
    """pricing.yaml → {model: {input, output}}. 소유자 정정 가능한 데이터 단가."""
    import yaml
    from pathlib import Path
    p = Path(path) if path else Path(__file__).with_name("pricing.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("prices", {})


# 프롬프트 캐시 배수(Anthropic 표준): 캐시 쓰기 1.25× 입력가 · 캐시 읽기 0.1× 입력가.
# 단가 자체가 아니라 **배수**라 pricing.yaml의 모델별 input에 곱해 쓴다(소유자가 단가만
# 정정하면 캐시가도 따라 정정된다).
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.1


def model_price(model, input_tokens, output_tokens, pricing,
                cache_creation_tokens=0, cache_read_tokens=0):
    """USD = 토큰 × 각 단가(백만 토큰당). 모델 미등록이면 KeyError(추측 금지).
    ★캐시 축(첫 실 로그에서 필요해짐): 실 파이프라인 입력의 대부분은 캐시 읽기다
    (실측). 캐시 토큰을 균일 입력가로 세면 실 청구를 크게 과대계상하므로 분리한다.
    기본값 0 = 기존 호출부(분할 미기록 로그) 그대로 동작."""
    pr = pricing[model]
    return (input_tokens * pr["input"]
            + cache_creation_tokens * pr["input"] * CACHE_WRITE_MULT
            + cache_read_tokens * pr["input"] * CACHE_READ_MULT
            + output_tokens * pr["output"]) / 1_000_000


def cost_per_target(log, pricing):
    """비용 로그 → $/target. log: {model, input_tokens, output_tokens, n_targets}.
    n_targets 0/부재면 usd_per_target=None(fail-closed, 0 나눗셈 크래시 금지)."""
    usd = model_price(log["model"], log.get("input_tokens", 0),
                      log.get("output_tokens", 0), pricing,
                      cache_creation_tokens=log.get("cache_creation_tokens", 0),
                      cache_read_tokens=log.get("cache_read_tokens", 0))
    n = log.get("n_targets") or 0
    return {"model": log["model"], "usd": usd, "n_targets": n,
            "usd_per_target": (usd / n) if n else None}


def cost_gate(b3_cpt, b7_cpt, factor=2.0):
    """§9-B 비용 조건: (B7 $/target) ≤ factor × (B3 $/target). '2배 이내' = ≤ 포함.
    한쪽이라도 $/target 미측정(None/부재)이면 pass=None — fail-closed(통과 아님)."""
    b3 = b3_cpt.get("usd_per_target")
    b7 = b7_cpt.get("usd_per_target")
    if b3 is None or b7 is None or b3 == 0:
        return {"ratio": None, "factor": factor, "pass": None,
                "b3_usd_per_target": b3, "b7_usd_per_target": b7}
    ratio = b7 / b3
    return {"ratio": ratio, "factor": factor, "pass": ratio <= factor,
            "b3_usd_per_target": b3, "b7_usd_per_target": b7}


def b3_projection(events):
    """B7 이벤트 → B3 얕은 스키마 투영(§1a 구조 논거의 출력 측 실측용).
    이중시간(recorded_at)·scope·authority_level·reason_type 등 B3가 못 보는 필드 제거.
    결정 act 이벤트만 대상. supersede 이벤트의 supersedes는 보존(B3가 쓰는 필드)."""
    from reducer import DECISION_ACT_TYPES
    out = []
    for e in events:
        if e.get("type") not in DECISION_ACT_TYPES:
            continue
        rec = {"target": e.get("target"),
               "status": e.get("type"),           # adopt/supersede/revoke/re_adopt
               "effective_from": e.get("valid_at")}
        if e.get("supersedes"):
            rec["supersedes"] = e["supersedes"]
        out.append({k: v for k, v in rec.items() if k in _B3_FIELDS})
    return out


def serialized_size(obj):
    """직렬화 크기(문자 수) — 출력 토큰의 프록시. 비율(B7/B3)에서 프록시 편향 상당 상쇄.
    ★프록시임을 명시: 실 토큰이 아니라 YAML 직렬화 문자 길이."""
    import yaml
    return len(yaml.safe_dump(obj, allow_unicode=True, sort_keys=True))


def output_size_ratio(events):
    """B7 출력 / B3 출력 크기비(직렬화 프록시). §1a 비율의 출력 측을 실 데이터로 채움.
    입력(원문)은 두 추출이 공유하므로, 이 비율이 클수록 전체 비용비가 1에서 멀어진다."""
    b7 = serialized_size(events)
    b3 = serialized_size(b3_projection(events))
    return {"b7_output_size": b7, "b3_output_size": b3,
            "output_ratio": (b7 / b3) if b3 else None,
            "proxy": "yaml-serialized-chars"}


def break_even_input(output_ratio, model, pricing, factor=2.0):
    """게이트 통과의 손익분기 — 입력이 B7 출력의 몇 배 이상이어야 2× 게이트를 통과하나.

    §1a 비율 cost_B7/cost_B3 = (x + k)/(x + k/r) (x=입력/B7출력, k=출력단가/입력단가,
    r=출력비 O_B7/O_B3). ≤ factor 풀면  x ≥ k·(1 − factor/r)/(factor − 1) = x*.
    통과 조건: 입력 토큰 ≥ x* × (B7 출력 토큰).

    출력비 r 자체가 factor 이하면(출력만으로 게이트 안) x*≤0 → 입력 무관 항상 통과
    (전체 비율은 1과 r 사이 mediant이라 r≤factor면 전체도 ≤factor). r>factor면 입력이
    출력을 x* 배 넘게 지배해야만 통과 — 즉 이 실험의 판정은 입력/출력 분할에 달렸다."""
    pr = pricing[model]
    k = pr["output"] / pr["input"]
    if output_ratio is None:
        return {"break_even_x": None, "always_pass": None, "k": k, "factor": factor}
    if output_ratio <= factor:
        return {"break_even_x": 0.0, "always_pass": True, "k": k, "factor": factor,
                "output_ratio": output_ratio}
    x_star = k * (1 - factor / output_ratio) / (factor - 1)
    return {"break_even_x": x_star, "always_pass": False, "k": k, "factor": factor,
            "output_ratio": output_ratio,
            "meaning": f"입력 토큰이 B7 출력의 {x_star:.2f}배 이상이어야 2× 게이트 통과"}


def ladder_table(entries, pricing, factor=2.0):
    """모델 사다리 — 티어별 (정확도 통과 × 비용). 층/티어 합산 금지(§7).
    entries: [{tier, model, accuracy_pass, b3_log, b7_log}] (입력 순 = 저→고 티어).
    판정: '정확도를 통과하는 가장 싼 티어'의 비용 게이트로 §9-B 비용 조건을 정한다
    (정확도 못 내는 티어의 낮은 비용을 우위로 세지 않는다 — 설계 §2).
    데이터/통과 티어 없으면 judged_tier=None·cost_gate.pass=None(fail-closed)."""
    rows = []
    for e in entries:
        b3 = cost_per_target(e["b3_log"], pricing)
        b7 = cost_per_target(e["b7_log"], pricing)
        g = cost_gate(b3, b7, factor)
        rows.append({"tier": e.get("tier"), "model": e.get("model"),
                     "accuracy_pass": e.get("accuracy_pass"),
                     "b3_usd_per_target": b3["usd_per_target"],
                     "b7_usd_per_target": b7["usd_per_target"],
                     "cost_gate": g})
    # 정확도 통과 티어 중 B7 $/target 최저 = 판정 티어. 입력 순으로 tie-break(결정론).
    passing = [r for r in rows if r["accuracy_pass"]
               and r["b7_usd_per_target"] is not None]
    judged = min(passing, key=lambda r: r["b7_usd_per_target"]) if passing else None
    return {"rows": rows,
            "judged_tier": judged["tier"] if judged else None,
            "judged_model": judged["model"] if judged else None,
            "cost_gate": judged["cost_gate"] if judged
            else {"ratio": None, "factor": factor, "pass": None,
                  "b3_usd_per_target": None, "b7_usd_per_target": None}}
