"""depth_promote fold 어댑터 — disposition 판정 원장을 정본 깊은층으로 접합(결정론)."""
from pathlib import Path

import depth_promote as dp

FIXTURES = Path(__file__).parent / "fixtures"   # cwd 무관(리포 루트 실행도 동일)

#: 앱 → 정본 scope — 엔진은 앱 이름을 모르므로 테스트가 선언을 넘긴다(registry `app_scopes`와 같은 모양).
SCOPES = {"meadow": "prime-commerce/meadow/meadow",
          "meadow-admin": "prime-commerce/meadow/meadow-admin",
          "mango": "prime-commerce/mango/mango",
          "cargo": "prime-commerce/cargo/crate-platform",
          "neomart-billing": "neomart/billing"}


def test_new_code_only_becomes_concept_with_mandate_flag():
    adj = {"dispositions": [{"sid": "meadow#sc-x", "app": "meadow", "name": "X",
                             "was": "NEW", "disposition": "new_code_only"}]}
    probes = {"meadow": {"subconcepts": [{"anchor": "sc-x", "name": "X", "quote": "q",
                                         "commitment": "hypothesis", "confidence": "low"}],
                        "relations": []}}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    assert len(out["concepts"]) == 1
    c = out["concepts"][0]
    assert c["kind"] == "concept"
    assert c["basis"] == "implemented_without_mandate"
    assert c["anchor"] == "meadow#sc-x"
    assert c["scope"] == "prime-commerce/meadow/meadow"
    assert out["bodies"]["meadow#sc-x"][0]["text"] == "q"


def test_new_decision_basis_is_decision():
    adj = {"dispositions": [{"sid": "meadow-admin#sc-app", "app": "meadow-admin",
                             "name": "Admin", "was": "NEW", "disposition": "new_decision"}]}
    probes = {"meadow-admin": {"subconcepts": [{"anchor": "sc-app", "name": "Admin",
                              "quote": "q", "commitment": "working", "confidence": "high"}],
                              "relations": []}}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    assert out["concepts"][0]["basis"] == "decision"


def test_align_owner_scope_homes_to_owner():
    adj = {"dispositions": [{"sid": "mango#sc-vllm", "app": "mango", "name": "V",
                             "was": "AMBIGUOUS", "disposition": "align_owner_scope",
                             "align_to": "prime-commerce/meadow/meadow"}]}
    probes = {"mango": {"subconcepts": [{"anchor": "sc-vllm", "name": "V", "quote": "q",
                                         "commitment": "working", "confidence": "high"}],
                        "relations": []}}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    c = out["concepts"][0]
    assert c["scope"] == "prime-commerce/meadow/meadow"      # 소유앱으로 집이 감
    assert c["basis"] == "cross_app_owned"
    assert c["provenance_scope"] == "prime-commerce/mango/mango"   # 발견 앱 기록


def test_state_enum_observed_kind():
    adj = {"dispositions": [{"sid": "meadow#sc-sec", "app": "meadow", "name": "SectionStatus",
                             "was": "AMBIGUOUS", "disposition": "state_enum_observed"}]}
    probes = {"meadow": {"subconcepts": [{"anchor": "sc-sec", "name": "SectionStatus",
                        "quote": "q", "commitment": "hypothesis", "confidence": "low"}],
                        "relations": []}}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    c = out["concepts"][0]
    assert c["kind"] == "state_enum"
    assert c["observed"] is True                          # lab 관측(화면정의서 편집 아님)


def test_held_dispositions_not_promoted():
    adj = {"dispositions": [
        {"sid": "neomart-billing#sc-a", "app": "neomart-billing", "name": "A",
         "was": "NEW", "disposition": "candidate_hold"},
        {"sid": "cargo#sc-b", "app": "cargo", "name": "B",
         "was": "AMBIGUOUS", "disposition": "gap_hold"},
        {"sid": "meadow-admin#sc-c", "app": "meadow-admin", "name": "C",
         "was": "AMBIGUOUS", "disposition": "ambiguous_hold"}]}
    probes = {a.split("#")[0]: {"subconcepts": [], "relations": []}
              for a in ("neomart-billing#", "cargo#", "meadow-admin#")}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    assert out["concepts"] == []
    assert len(out["held"]["candidate"]) == 1
    assert len(out["held"]["gap"]) == 1
    assert len(out["held"]["ambiguous"]) == 1


def test_relations_only_among_promoted():
    adj = {"dispositions": [
        {"sid": "meadow#sc-x", "app": "meadow", "name": "X", "was": "NEW",
         "disposition": "new_code_only"},
        {"sid": "meadow#sc-y", "app": "meadow", "name": "Y", "was": "AMBIGUOUS",
         "disposition": "gap_hold"}]}
    probes = {"meadow": {"subconcepts": [
        {"anchor": "sc-x", "name": "X", "quote": "q", "commitment": "hypothesis", "confidence": "low"},
        {"anchor": "sc-y", "name": "Y", "quote": "q2", "commitment": "hypothesis", "confidence": "low"}],
        "relations": [{"from": "sc-x", "to": "sc-y", "canonical": "part_of", "quote": "q"},
                      {"from": "sc-x", "to": "sc-x", "canonical": "constrains", "quote": "q"}]}}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    # sc-y 보류 → x→y 관계 탈락, x→x(양끝 승격) 생존
    assert all(r["to"] != "meadow#sc-y" and r["from"] != "meadow#sc-y"
               for r in out["relations"])
    assert len(out["relations"]) == 1


def test_deterministic_sorted():
    adj = {"dispositions": [
        {"sid": "meadow#sc-b", "app": "meadow", "name": "B", "was": "NEW", "disposition": "new_code_only"},
        {"sid": "meadow#sc-a", "app": "meadow", "name": "A", "was": "NEW", "disposition": "new_code_only"}]}
    probes = {"meadow": {"subconcepts": [
        {"anchor": "sc-a", "name": "A", "quote": "qa", "commitment": "hypothesis", "confidence": "low"},
        {"anchor": "sc-b", "name": "B", "quote": "qb", "commitment": "hypothesis", "confidence": "low"}],
        "relations": []}}
    out = dp.fold_depth(adj, probes, app_scopes=SCOPES)
    assert [c["anchor"] for c in out["concepts"]] == ["meadow#sc-a", "meadow#sc-b"]


def test_fold_depth_accepts_app_scopes_override():
    adj = {"dispositions": [{"sid": "newapp#sc-x", "app": "newapp", "name": "X",
                             "was": "new", "disposition": "new_code_only"}]}
    probes = {"newapp": {"subconcepts": [{"anchor": "sc-x", "name": "X", "quote": "q",
                         "commitment": "hypothesis", "confidence": "low"}], "relations": []}}
    out = dp.fold_depth(adj, probes, app_scopes={"newapp": "neomart/newapp"})
    assert out["concepts"][0]["scope"] == "neomart/newapp"


# ── 관계 끝점이 **병합된 개념**일 때 ──
# `fold_depth`는 정본 끝점을 `f"{app}#{anc}"`로 조회한다 — 병합된 개념은 정본에 그 이름으로 없다.

def _merged_probe():
    return {"lab": {"subconcepts": [{"anchor": "sc-new", "name": "새 개념"}],
                    "relations": [{"from": "sc-new", "to": "sc-merged",
                                   "canonical": "part_of", "quote": "q"}]}}


def _merged_rows():
    return [{"sid": "lab#sc-new", "app": "lab", "name": "새 개념",
             "disposition": "auto_adopt"}]


def test_merged_endpoint_dropped_without_map():
    """수리 전 동작 — 병합 끝점을 못 풀면 관계가 조용히 사라진다."""
    out = dp.fold_depth({"dispositions": _merged_rows()}, _merged_probe(),
                        app_scopes={"lab": "lab"}, canon_anchors={"pipeline#sc-merged"})
    assert out["relations"] == []


def test_merged_endpoint_resolved_via_synonym_record():
    out = dp.fold_depth({"dispositions": _merged_rows()}, _merged_probe(),
                        app_scopes={"lab": "lab"}, canon_anchors={"pipeline#sc-merged"},
                        merged_into={"lab#sc-merged": "pipeline#sc-merged"})
    assert [(r["from"], r["to"]) for r in out["relations"]] == \
        [("lab#sc-new", "pipeline#sc-merged")]


def test_merged_target_must_exist_in_canon():
    """지어냄 차단은 그대로 — 정본에 없는 target은 끝점이 못 된다."""
    out = dp.fold_depth({"dispositions": _merged_rows()}, _merged_probe(),
                        app_scopes={"lab": "lab"}, canon_anchors=set(),
                        merged_into={"lab#sc-merged": "pipeline#sc-merged"})
    assert out["relations"] == []


def test_article_only_target_is_not_an_endpoint():
    """정렬 target이 Tier A 서술 단위면 개념이 아니다 — 끝점으로 쓰지 않는다."""
    out = dp.fold_depth({"dispositions": _merged_rows()}, _merged_probe(),
                        app_scopes={"lab": "lab"}, canon_anchors={"pipeline#sc-merged"},
                        merged_into={"lab#sc-merged": "docs/method/x#헤딩"})
    assert out["relations"] == []


def test_same_app_prefix_still_works():
    """기존 경로(같은 접두) 회귀 없음."""
    out = dp.fold_depth({"dispositions": _merged_rows()}, _merged_probe(),
                        app_scopes={"lab": "lab"}, canon_anchors={"lab#sc-merged"})
    assert [(r["from"], r["to"]) for r in out["relations"]] == \
        [("lab#sc-new", "lab#sc-merged")]
