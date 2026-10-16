"""루트 이동 보존 — 코퍼스 루트가 옮겨져도 조각은 죽지 않는다 (불변식 11)."""
from __future__ import annotations

from structure_app import (fold_fragment_versions, tombstone_lost_fragments,
                           doc_identity_report, canon_metrics, metrics_gate)

AT = "5e773ff"

# 실사고 그대로: 같은 문서, 같은 섹션, 루트만 달라진 key
PREV = {"wevolley#sc-analytics-blind-spot": [
    {"key": "reference/improvement-catalog#D1|content", "text": "analytics는 스텁이고 호출처 0건"},
    {"key": "reference/improvement-catalog#F1|content", "text": "데이터 루프"},
]}
NOW = {"wevolley#sc-analytics-blind-spot": [
    {"key": "planning/reference/improvement-catalog#D1|content",
     "text": "PostHog capture HTTP API로 실전송 중"},
    {"key": "planning/reference/improvement-catalog#F1|content", "text": "데이터 루프"},
]}


def _keys(frags):
    return {f["key"] for f in frags}


def test_root_move_does_not_tombstone_fragments():
    """근인 재현 — 종전엔 옛 2개가 죽고 새 2개가 들어와 4개가 됐다."""
    out = fold_fragment_versions(PREV, NOW, AT)
    frags = out["wevolley#sc-analytics-blind-spot"]
    assert not [f for f in frags if f.get("removed_at")], \
        "루트 이동은 삭제가 아니다 — removed_at이 찍히면 안 된다"


def test_root_move_is_treated_as_update_not_duplication():
    """텍스트가 바뀐 조각은 **갱신**이다 — 현행 1 + 이력 1이지 현행 2가 아니다."""
    out = fold_fragment_versions(PREV, NOW, AT)
    frags = out["wevolley#sc-analytics-blind-spot"]
    live = [f for f in frags if not f.get("removed_at") and not f.get("superseded_at")]
    # D1은 텍스트가 바뀌었으니 현행은 새 서술 하나뿐이어야 한다
    d1_live = [f for f in live if f["key"].endswith("#D1|content")]
    assert len(d1_live) == 1, f"D1 현행이 {len(d1_live)}개 — 옛 서술이 같이 살아있다"
    assert "PostHog" in d1_live[0]["text"], "옛 서술이 현행 자리를 차지했다"
    # 옛 서술은 지워지지 않고 이력으로 내려간다
    aged = [f for f in frags if f.get("superseded_at")]
    assert any("스텁" in f["text"] for f in aged), "옛 서술이 이력에 없다 — 증발"


def test_root_move_converges_to_one_namespace():
    """정본이 한 네임스페이스로 수렴해야 한다 — 안 그러면 다음 회차에 또 갈린다."""
    out = fold_fragment_versions(PREV, NOW, AT)
    docs = {f["key"].split("#")[0] for f in out["wevolley#sc-analytics-blind-spot"]}
    assert docs == {"planning/reference/improvement-catalog"}, \
        f"네임스페이스가 둘로 남았다: {sorted(docs)}"


def test_unchanged_text_across_root_move_is_not_versioned():
    """내용이 같으면 이력을 만들지 않는다 — 루트 이동만으로 버전이 생기면 안 된다."""
    out = fold_fragment_versions(PREV, NOW, AT)
    frags = out["wevolley#sc-analytics-blind-spot"]
    f1 = [f for f in frags if f["key"].endswith("#F1|content")]
    assert len(f1) == 1 and not f1[0].get("superseded_at")


def test_tombstone_lost_fragments_also_absorbs_root_move():
    """같은 비교가 두 곳에 있다 — 한쪽만 고치면 다른 경로로 재발한다."""
    out = tombstone_lost_fragments(PREV, NOW, AT)
    frags = out["wevolley#sc-analytics-blind-spot"]
    assert not [f for f in frags if f.get("removed_at")]
    assert _keys(frags) == {"planning/reference/improvement-catalog#D1|content",
                            "planning/reference/improvement-catalog#F1|content"}


def test_heals_documents_absent_from_this_round():
    """실 재생 2차가 드러낸 갭: 이번 회차에 조각이 안 실린 문서는 기준점을 못 찾아
    갈린 채 남았다(10건 중 5건). 정본 안에 이미 현행 루트로 사는 사본이 기준점이다."""
    prev = {"A": [{"key": "reference/runbook#H|content", "text": "옛 사본"},
                  {"key": "planning/reference/runbook#H2|content", "text": "현행 사본"}],
            "B": [{"key": "planning/reference/other#H|content", "text": "이번 회차 문서"}]}
    fresh = {"B": [{"key": "planning/reference/other#H|content", "text": "이번 회차 문서"}]}
    out = fold_fragment_versions(prev, fresh, AT)
    docs = {f["key"].split("#")[0] for f in out["A"]}
    assert docs == {"planning/reference/runbook"}, f"갈린 채 남았다: {sorted(docs)}"


def test_root_observation_does_not_invent_a_namespace():
    """fresh에 경로형 문서가 없으면 루트를 추정하지 않는다 — 지어냄 0."""
    prev = {"A": [{"key": "reference/runbook#H|content", "text": "x"}]}
    fresh = {"A": [{"key": "quote", "text": "q"}]}
    out = fold_fragment_versions(prev, fresh, AT)
    assert {f["key"] for f in out["A"]} >= {"reference/runbook#H|content"}


def test_genuine_removal_still_tombstones():
    """오병합 방지 — 진짜 사라진 문서는 여전히 죽어야 한다(게이트를 무디게 만들지 않기)."""
    prev = {"A": [{"key": "reference/deleted-doc#H|content", "text": "x"}]}
    now = {"A": [{"key": "planning/reference/other-doc#H|content", "text": "y"}]}
    out = fold_fragment_versions(prev, now, AT)
    dead = [f for f in out["A"] if f.get("removed_at")]
    assert [f["key"] for f in dead] == ["reference/deleted-doc#H|content"]


def test_sibling_docs_with_same_basename_never_merge():
    """`backlog/guest-request`와 `작업완료/guest-request`는 다른 문서다(실측 유일 충돌)."""
    prev = {"A": [{"key": "guest-request#H|content", "text": "옛것"}]}
    now = {"A": [{"key": "planning/backlog/guest-request#H|content", "text": "기획본"},
                 {"key": "planning/작업완료/guest-request#H|content", "text": "완료본"}]}
    out = fold_fragment_versions(prev, now, AT)
    texts = {f["text"] for f in out["A"]}
    assert "기획본" in texts and "완료본" in texts
    # 모호하므로 옛 조각을 어느 쪽에도 붙이지 않는다(지어냄 0)
    assert any(f.get("removed_at") for f in out["A"] if f["key"] == "guest-request#H|content")


def test_code_and_quote_keys_untouched():
    """코드 키·게이트 인용은 문서 축이 없다 — 이 층이 건드리면 안 된다."""
    prev = {"A": [{"key": "lib.analytics.identifyUser|fields.signature", "text": "a"},
                  {"key": "quote", "text": "q"}]}
    now = {"A": [{"key": "lib.analytics.identifyUser|fields.signature", "text": "a"},
                 {"key": "quote", "text": "q"}]}
    out = fold_fragment_versions(prev, now, AT)
    assert _keys(out["A"]) == {"lib.analytics.identifyUser|fields.signature", "quote"}
    assert not [f for f in out["A"] if f.get("removed_at") or f.get("superseded_at")]


def test_idempotent_under_repeat():
    """멱등 — regen.sh가 promote를 두 번 돌린다(재생 + 재현성 확인)."""
    once = fold_fragment_versions(PREV, NOW, AT)
    twice = fold_fragment_versions(once, NOW, AT)
    assert once == twice



def test_report_flags_split_document_identity():
    """한 문서가 두 신원으로 갈리면 잡아야 한다."""
    bodies = {"A": [{"key": "reference/catalog#D1|content", "text": "x"},
                    {"key": "planning/reference/catalog#D1|content", "text": "y"}]}
    r = doc_identity_report(bodies)
    assert r["ok"] is False
    assert r["split"] == [{"identity": "catalog",
                           "slugs": ["planning/reference/catalog", "reference/catalog"]}]


def test_report_ok_on_single_namespace():
    bodies = {"A": [{"key": "planning/reference/catalog#D1|content", "text": "x"},
                    {"key": "planning/backlog/treasury#H|content", "text": "y"}]}
    assert doc_identity_report(bodies)["ok"] is True


def test_report_does_not_flag_genuine_sibling_docs():
    """같은 basename이어도 접미 관계가 아니면 갈린 게 아니다(실측 유일 충돌)."""
    bodies = {"A": [{"key": "planning/backlog/guest-request#H|content", "text": "x"},
                    {"key": "planning/작업완료/guest-request#H|content", "text": "y"}]}
    assert doc_identity_report(bodies)["ok"] is True


def test_report_ignores_code_and_quote_keys():
    bodies = {"A": [{"key": "lib.analytics.identifyUser|fields.signature", "text": "a"},
                    {"key": "quote", "text": "q"}]}
    assert doc_identity_report(bodies)["ok"] is True


def test_metrics_expose_doc_identity_unique():
    doc = {"concepts": [{"anchor": "A", "scope": "s"}],
           "bodies": {"A": [{"key": "reference/catalog#D1|content", "text": "x"},
                            {"key": "planning/reference/catalog#D1|content", "text": "y"}]}}
    assert canon_metrics(doc)["doc_identity_unique"] is False


def test_gate_catches_regression_into_split_identity():
    """초록 → 빨강 전이를 회귀로 잡는다(anchor_unique와 같은 축)."""
    prev = {"doc_identity_unique": True, "concepts": 1}
    cur = {"doc_identity_unique": False, "concepts": 1}
    g = metrics_gate(prev, cur)
    assert g["ok"] is False
    assert {"metric": "doc_identity_unique", "was": True, "now": False} in g["regressions"]


def test_gate_allows_repair_direction():
    """빨강 → 초록(수리)은 회귀가 아니다."""
    assert metrics_gate({"doc_identity_unique": False, "concepts": 1},
                        {"doc_identity_unique": True, "concepts": 1})["ok"] is True


# ── 불변식 9 정정 — 중복 제거는 소실이 아니다 ──────────────────────────
#
# 실 재생에서 `body_chars`가 크게 줄어 불변식 9가
# 울렸다. 전수 대조 결과 **사라진 고유 텍스트 0자**, 감소분 전부가 이중
# 네임스페이스 중복이었다. 총량 게이트는 "왜 줄었나"를 못 가른다 —
# `tombstone_lost_fragments` 주석이 이미 같은 말을 한다("정당한 편집으로도 글자 수는
# 준다"). 고유 텍스트 총량은 중복 제거로 **줄 수 없으므로** 그쪽을 회귀 축으로 쓴다.

def test_unique_body_chars_ignores_duplication():
    """같은 텍스트가 두 네임스페이스에 있어도 고유 총량은 한 번만 센다."""
    doc = {"concepts": [{"anchor": "A", "scope": "s"}],
           "bodies": {"A": [{"key": "reference/x#H|content", "text": "같은 내용"},
                            {"key": "planning/reference/x#H|content", "text": "같은 내용"}]}}
    m = canon_metrics(doc)
    assert m["body_chars"] == len("같은 내용") * 2      # 관측치는 그대로 남긴다
    assert m["body_chars_unique"] == len("같은 내용")


def test_dedup_does_not_trip_the_shrink_gate():
    """실 재생 그대로 — 중복만 줄었으면 통과해야 한다."""
    g = metrics_gate({"body_chars": 886082, "body_chars_unique": 500000, "concepts": 297},
                     {"body_chars": 753396, "body_chars_unique": 500000, "concepts": 297})
    assert g["ok"] is True, g["regressions"]


def test_real_content_loss_still_trips_the_gate():
    """게이트를 무디게 만들지 않는다 — 고유 내용이 줄면 여전히 위반이다."""
    g = metrics_gate({"body_chars": 100, "body_chars_unique": 100, "concepts": 1},
                     {"body_chars": 90, "body_chars_unique": 90, "concepts": 1})
    assert g["ok"] is False
    assert [r["metric"] for r in g["regressions"]] == ["body_chars_unique"]


# ── 4차 수리 — 현행 네임스페이스의 진실 원천은 스냅샷이다 ──────────────
#
# 계측으로 확정: promote가 `merged_bodies = dict(prev_bodies)`로 시작해

def test_snapshot_wins_over_contaminated_fresh():
    """fresh가 옛 키를 물고 있어도 스냅샷이 현행을 정한다."""
    prev = {"A": [{"key": "reference/runbook#H|content", "text": "옛것"}]}
    fresh = {"A": [{"key": "reference/runbook#H|content", "text": "옛것"}]}   # 오염된 fresh
    units = {"planning/reference/runbook#H", "planning/reference/other#H"}
    out = fold_fragment_versions(prev, fresh, AT, visible_units=units)
    assert {f["key"] for f in out["A"]} == {"planning/reference/runbook#H|content"}


def test_without_snapshot_falls_back_to_fresh():
    """스냅샷 정보가 없으면 종전대로 fresh를 본다(옛 호출자 보존)."""
    prev = {"A": [{"key": "reference/runbook#H|content", "text": "x"}]}
    fresh = {"A": [{"key": "planning/reference/runbook#H|content", "text": "y"}]}
    out = fold_fragment_versions(prev, fresh, AT)
    assert {f["key"] for f in out["A"]} == {"planning/reference/runbook#H|content"}


def test_snapshot_does_not_invent_documents_it_lacks():
    """스냅샷에 없는 문서는 정규화 대상이 아니다 — 진짜 삭제는 삭제로 남는다."""
    prev = {"A": [{"key": "reference/gone#H|content", "text": "x"}]}
    units = {"planning/reference/other#H"}
    out = fold_fragment_versions(prev, {"A": []}, AT, visible_units=units)
    assert [f["key"] for f in out["A"]] == ["reference/gone#H|content"]
