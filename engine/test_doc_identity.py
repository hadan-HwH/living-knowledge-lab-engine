"""문서 정체성 층 — 경로가 바뀌어도 문서는 같은 문서다.

`doc_slug` 자신의 docstring이 "폴더 번호는 순번이라 재배정된다 → 정체성은 slug"라고
말한다. 같은 논리가 **경로 깊이**에도 걸린다 — 루트는 언제든 옮겨진다.

처방은 `decision_alias`와 같은 층위다: 원장·앵커는 무수정, **읽기 시점 정규화**만 한다.
정체성 = 그 스냅샷 안에서 **유일해지는 최소 경로 접미**. 관측 유도라 하드코딩이 없고,
루트가 위로 가든 아래로 가든 흡수하며, 파일이 폴더를 옮겨도 살아남는다."""
from __future__ import annotations

import pytest

from doc_identity import (doc_identity_map, canonical_doc, same_document,
                          split_fragment_key, key_alias_map)


# ── 근인 재현: 루트 이동이 신원을 쪼갠다 ──────────────────────────────────

def test_root_move_does_not_split_identity():
    """실제 사고: 코퍼스 루트가 planning/ 위로 올라가 문서마다 신원이 둘이 됐다."""
    before = {"reference/improvement-catalog", "reference/perf-loading-realtime-history"}
    after = {"planning/reference/improvement-catalog",
             "planning/reference/perf-loading-realtime-history"}
    m_before, m_after = doc_identity_map(before), doc_identity_map(after)
    assert m_before["reference/improvement-catalog"] == \
           m_after["planning/reference/improvement-catalog"]
    assert same_document("reference/improvement-catalog",
                         "planning/reference/improvement-catalog")


def test_root_move_downward_also_absorbed():
    """반대 방향(루트가 더 깊어짐)도 같은 문서로 본다 — 접미가 불변량이다."""
    assert same_document("planning/reference/x", "x")
    assert same_document("a/b/c/notes", "c/notes")


# ── 오병합 방지: 같은 basename이 진짜 다른 문서일 때 ────────────────────

def test_same_basename_in_one_snapshot_stays_distinct():
    """wevolley 실데이터의 유일한 충돌: guest-request가 backlog/와 작업완료/에 각각 있다.
    같은 스냅샷에 공존하면 다른 문서다 — 합치면 기획본과 완료본이 뭉개진다."""
    slugs = {"backlog/guest-request", "작업완료/guest-request", "reference/improvement-catalog"}
    m = doc_identity_map(slugs)
    assert m["backlog/guest-request"] != m["작업완료/guest-request"]
    assert m["backlog/guest-request"] == "backlog/guest-request"
    assert m["작업완료/guest-request"] == "작업완료/guest-request"
    # 충돌 안 하는 문서는 basename까지 줄어든다
    assert m["reference/improvement-catalog"] == "improvement-catalog"


def test_collision_resolved_at_minimal_distinguishing_depth():
    """구분에 필요한 만큼만 경로를 남긴다 — 전체 경로로 후퇴하지 않는다."""
    slugs = {"a/deep/x/notes", "b/deep/x/notes"}
    m = doc_identity_map(slugs)
    assert m["a/deep/x/notes"] == "a/deep/x/notes"
    assert m["b/deep/x/notes"] == "b/deep/x/notes"
    slugs2 = {"a/x/notes", "b/y/notes"}
    m2 = doc_identity_map(slugs2)
    assert m2["a/x/notes"] == "x/notes"      # y와 갈리는 최소 깊이
    assert m2["b/y/notes"] == "y/notes"


def test_distinct_basenames_never_merge():
    assert not same_document("reference/improvement-catalog", "reference/perf-history")
    assert not same_document("a/config", "a/settings")


def test_suffix_must_align_on_segment_boundary():
    """문자열 접미가 아니라 **경로 조각** 접미다 — `x/my-notes`와 `notes`는 다른 문서."""
    assert not same_document("x/my-notes", "notes")
    assert not same_document("planning/catalog", "improvement-catalog")


# ── 이동 내성 ────────────────────────────────────────────────────────────

def test_document_survives_folder_move_via_snapshot_map():
    """파일이 폴더를 옮겨도(번호 재배정과 같은 층) 같은 문서다 — 단 **지도를 거쳐서**.

    이동은 형제 경로 간 이동이라 어느 쪽도 상대의 접미가 아니다. 짝 비교
    `same_document`는 스냅샷 문맥이 없어 이걸 판정할 수 없고, 판정하려 들면
    `backlog/guest-request`와 `작업완료/guest-request`까지 뭉갠다. 그래서
    이동 내성은 정체성 지도가 담당한다 — basename이 그 스냅샷에서 유일하면
    양쪽 다 같은 정체성으로 접힌다."""
    assert doc_identity_map({"backlog/treasury"})["backlog/treasury"] == "treasury"
    assert doc_identity_map({"reference/treasury"})["reference/treasury"] == "treasury"


def test_pairwise_alias_refuses_sibling_move_by_design():
    """짝 비교는 **루트 이동**(접미 관계)만 흡수한다. 형제 이동에 대해 거짓을
    돌려주는 건 결함이 아니라 오병합 방지 — 공존 판정은 지도의 몫이다."""
    assert not same_document("backlog/treasury", "reference/treasury")
    assert not same_document("backlog/guest-request", "작업완료/guest-request")


def test_numeric_prefix_already_stripped_is_untouched():
    """doc_slug이 이미 번호를 뗀 뒤에 들어온다 — 이 층은 깊이만 다룬다."""
    assert canonical_doc("planning/reference/improvement-catalog") == "improvement-catalog"


# ── 결정론·멱등 ──────────────────────────────────────────────────────────

def test_deterministic_and_idempotent():
    slugs = {"a/x/notes", "b/y/notes", "reference/catalog"}
    m1, m2 = doc_identity_map(slugs), doc_identity_map(slugs)
    assert m1 == m2
    # 정체성을 다시 넣어도 자기 자신 (고정점)
    m3 = doc_identity_map(set(m1.values()))
    for v in m1.values():
        assert m3[v] == v


def test_empty_and_degenerate_inputs():
    assert doc_identity_map(set()) == {}
    assert doc_identity_map({"solo"}) == {"solo": "solo"}
    assert canonical_doc("") == ""


# ── 실 코퍼스: 이중 네임스페이스가 실제로 합쳐지는가 ────────────────────

WEVOLLEY_DUAL = [
    ("reference/bot-ops-runbook", "planning/reference/bot-ops-runbook"),
    ("backlog/club-treasury", "planning/backlog/club-treasury"),
    ("backlog/guest-request", "planning/backlog/guest-request"),
    ("reference/improvement-catalog", "planning/reference/improvement-catalog"),
    ("reference/linkedin-100days-series", "planning/reference/linkedin-100days-series"),
    ("reference/linkedin-ep1-draft", "planning/reference/linkedin-ep1-draft"),
    ("reference/perf-loading-realtime-history", "planning/reference/perf-loading-realtime-history"),
    ("reference/prod-key-rotation-runbook", "planning/reference/prod-key-rotation-runbook"),
    ("backlog/view-as-member-v2", "planning/backlog/view-as-member-v2"),
]


@pytest.mark.parametrize("old,new", WEVOLLEY_DUAL)
def test_real_wevolley_dual_namespace_collapses(old, new):
    """정본에서 실측된 9쌍 — 전부 한 문서로 접혀야 한다."""
    assert same_document(old, new)



def test_split_fragment_key_markdown():
    doc, rest = split_fragment_key("planning/reference/improvement-catalog#D1.-제품-분석|content")
    assert doc == "planning/reference/improvement-catalog"
    assert rest == "#D1.-제품-분석|content"


def test_split_fragment_key_code_has_no_doc_axis():
    """코드 키는 점 표기 모듈 경로라 문서 축이 없다 — 건드리지 않는다."""
    assert split_fragment_key("lib.analytics.identifyUser|fields.signature") == (None, None)
    assert split_fragment_key("quote") == (None, None)


def test_key_alias_maps_old_namespace_onto_current():
    """실사고 재현: prev는 옛 루트, now는 새 루트. 같은 조각으로 이어야 한다."""
    prev = ["reference/improvement-catalog#D1|content",
            "reference/improvement-catalog#F1|content"]
    now = ["planning/reference/improvement-catalog#D1|content",
           "planning/reference/improvement-catalog#F1|content"]
    m = key_alias_map(prev, now)
    assert m["reference/improvement-catalog#D1|content"] == \
           "planning/reference/improvement-catalog#D1|content"


def test_key_alias_leaves_genuinely_removed_alone():
    """now에 대응 문서가 없으면 별칭을 만들지 않는다 — 진짜 삭제는 삭제로 남아야 한다."""
    prev = ["reference/deleted-doc#H|content"]
    now = ["planning/reference/other#H|content"]
    assert key_alias_map(prev, now) == {}


def test_key_alias_refuses_when_ambiguous():
    """두 현행 문서에 걸리면 지어내지 않는다 — 모르면 안 합친다(원장 규율)."""
    prev = ["guest-request#H|content"]
    now = ["planning/backlog/guest-request#H|content",
           "planning/작업완료/guest-request#H|content"]
    assert key_alias_map(prev, now) == {}


def test_key_alias_requires_same_heading_and_field():
    """문서만 같고 섹션이 다르면 다른 조각이다."""
    prev = ["reference/catalog#D1|content"]
    now = ["planning/reference/catalog#G1|content"]
    assert key_alias_map(prev, now) == {}


def test_key_alias_identity_when_already_aligned():
    """이미 같은 네임스페이스면 별칭이 필요 없다(빈 지도)."""
    keys = ["planning/reference/catalog#D1|content"]
    assert key_alias_map(keys, keys) == {}


def test_key_alias_ignores_code_and_quote_keys():
    prev = ["lib.analytics.identifyUser|fields.signature", "quote"]
    now = ["lib.analytics.identifyUser|fields.signature", "quote"]
    assert key_alias_map(prev, now) == {}
