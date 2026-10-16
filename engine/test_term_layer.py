"""의미 층(용어 통합) — 결정론 부분 검증. Run: python3 -m pytest engine/test_term_layer.py -q"""
from __future__ import annotations

from term_layer import bridge, build_vocab, find_occurrences, make_terms

CONCEPTS = [
    {"anchor": "Item.Status", "kind": "state_enum", "scope": "s",
     "content": "정상/중지", "values": ["Active", "Paused"]},
    {"anchor": "Key.Status", "kind": "state_enum", "scope": "s",
     "content": "키 상태", "values": ["Active"]},
    {"anchor": "Gift Card", "kind": "state_enum", "scope": "s",       # 점 없는 anchor → 전체가 리소스
     "content": "발급/폐기", "values": ["Issued"]},
    {"anchor": "Item.ItemCode", "kind": "field", "scope": "s", "content": "3–128자"},
    {"anchor": "A-1", "kind": "article", "scope": "s",
     "content": "Paused 상품은 주문 불가",
     "fields": {"참조": "ItemCode 규칙은 spec"},
     "refs": {"decisions": ["D-9"], "articles": []}},
    {"anchor": "A-2", "kind": "article", "scope": "s",
     "content": "Active 상태에서만 사용 가능", "refs": {"decisions": [], "articles": []}},
    {"anchor": "SCR-1", "kind": "screen", "scope": "s", "content": "Active 배지"},  # 화면 계열 — 소스 제외
]


def test_build_vocab_from_spec_kinds_only():
    vocab = build_vocab(CONCEPTS)
    entries = {(v["surface"], v["resource"]) for v in vocab}
    assert ("Paused", "Item") in entries
    assert ("Active", "Item") in entries and ("Active", "Key") in entries   # 동일 표면형·복수 리소스
    assert ("Issued", "Gift Card") in entries                              # 점 없는 anchor
    assert ("ItemCode", "Item") in entries                                  # field 필드명
    # article·screen에서는 어휘를 만들지 않는다 (원자화 금지)
    assert all(v["source_kind"] in ("state_enum", "field") for v in vocab)


def test_vocab_records_source_anchor():
    vocab = build_vocab(CONCEPTS)
    deact = next(v for v in vocab if v["surface"] == "Paused")
    assert deact["source_anchor"] == "Item.Status" and deact["source_kind"] == "state_enum"


def test_find_occurrences_in_articles_only():
    vocab = build_vocab(CONCEPTS)
    occ = find_occurrences(vocab, CONCEPTS)
    got = {(o["surface"], o["concept"], o["field"]) for o in occ}
    assert ("Paused", "A-1", "content") in got
    assert ("ItemCode", "A-1", "fields.참조") in got     # fields dict도 검색
    assert ("Active", "A-2", "content") in got
    assert not any(o["concept"] == "SCR-1" for o in occ)  # 화면 계열 제외


def test_occurrence_keeps_matched_text_for_roundtrip():
    occ = find_occurrences(build_vocab(CONCEPTS), CONCEPTS)
    d = next(o for o in occ if o["surface"] == "Paused")
    assert d["text"] == "Paused 상품은 주문 불가"   # 원문 무수정 보존


def test_whole_word_matching():
    concepts = CONCEPTS + [{"anchor": "A-3", "kind": "article", "scope": "s",
                            "content": "Reactivated 이력", "refs": {"decisions": [], "articles": []}}]
    occ = find_occurrences(build_vocab(concepts), concepts)
    assert not any(o["concept"] == "A-3" for o in occ)   # 'Reactivated'에 부분 일치 금지


def test_make_terms_unambiguous_promoted():
    vocab = build_vocab(CONCEPTS)
    occ = find_occurrences(vocab, CONCEPTS)
    res = make_terms(vocab, occ)
    t = next(t for t in res["terms"] if t["anchor"] == "term:Item.Paused")
    # 표면형의 리소스가 유일 → 조항 등장 자동 귀속, 전 멤버 machine → promoted
    assert t["status"] == "promoted" and t["basis"] == "machine"
    kinds = {(m["concept"], m["basis"]) for m in t["members"]}
    assert ("Item.Status", "machine") in kinds and ("A-1", "machine") in kinds


def test_make_terms_ambiguous_goes_to_queue():
    vocab = build_vocab(CONCEPTS)
    occ = find_occurrences(vocab, CONCEPTS)
    res = make_terms(vocab, occ)
    # 'Active'는 리소스 2개(Item·Key) → spec 멤버만으로 term 2개 promoted, 조항 등장은 큐로
    actives = [t for t in res["terms"] if t["surface"] == "Active"]
    assert {t["anchor"] for t in actives} == {"term:Item.Active", "term:Key.Active"}
    assert all(t["status"] == "promoted" for t in actives)
    q = res["ambiguous"]
    assert len(q) == 1 and q[0]["surface"] == "Active" and q[0]["concept"] == "A-2"
    assert set(q[0]["resource_options"]) == {"Item", "Key"}


def test_make_terms_llm_judgment_demotes_to_candidate():
    vocab = build_vocab(CONCEPTS)
    occ = find_occurrences(vocab, CONCEPTS)
    judgments = [{"surface": "Active", "concept": "A-2", "field": "content",
                  "resource": "Key", "quote": "Active 상태에서만 사용 가능",
                  "confidence": "high"}]
    res = make_terms(vocab, occ, judgments=judgments)
    key_active = next(t for t in res["terms"] if t["anchor"] == "term:Key.Active")
    assert key_active["status"] == "candidate" and key_active["basis"] == "llm"
    assert any(m["concept"] == "A-2" and m["basis"] == "llm" for m in key_active["members"])
    assert res["ambiguous"] == []   # 판정 반영으로 큐 소진


def test_find_occurrences_searches_article_table_rows():
    """round 2 ②: 조항 밑 표 행에서도 등장을 찾는다 — 행 단위 field 앵커(table[i])."""
    concepts = [
        {"anchor": "Item.Status", "kind": "state_enum", "scope": "s",
         "content": "", "values": ["Active", "Paused"]},
        {"anchor": "A-16", "kind": "article", "scope": "s",
         "content": "항목별 수정 가능 여부는 아래 표를 따라야 한다",
         "table": ["| 항목 | 수정 가능 | 제약 |",
                   "| Status | 가능 | Active ↔ Paused 상호 전환만 |"],
         "refs": {"decisions": [], "articles": []}},
    ]
    occ = find_occurrences(build_vocab(concepts), concepts)
    got = {(o["surface"], o["concept"], o["field"]) for o in occ}
    assert ("Active", "A-16", "table[1]") in got
    assert ("Paused", "A-16", "table[1]") in got
    row = next(o for o in occ if o["field"] == "table[1]")
    assert row["text"] == "| Status | 가능 | Active ↔ Paused 상호 전환만 |"  # 원문 행 그대로


def test_state_enum_member_carries_value_note_only():
    """round 2 ①: 값-term의 spec 멤버는 자기 값의 행 note만 나른다 — 남의 행 침입 제거
    (파일럿 판정 10·11의 과통합 원인 수정)."""
    concepts = [
        {"anchor": "Item.Status", "kind": "state_enum", "scope": "s",
         "content": "정상. 판매 가능; 중지. 자동 전환", "values": ["Active", "Paused"],
         "value_notes": {"Active": "정상. 판매 가능", "Paused": "중지. 자동 전환"}},
    ]
    vocab = build_vocab(concepts)
    res = make_terms(vocab, [])
    a = next(t for t in res["terms"] if t["anchor"] == "term:Item.Active")
    d = next(t for t in res["terms"] if t["anchor"] == "term:Item.Paused")
    assert a["members"][0]["note"] == "정상. 판매 가능"      # "중지" 행이 안 섞임
    assert d["members"][0]["note"] == "중지. 자동 전환"


def test_state_enum_without_value_notes_has_no_note():
    """value_notes 없는 구 스냅샷 입력도 동작 — note 필드만 생략(blob을 지어 넣지 않음)."""
    concepts = [{"anchor": "K.Status", "kind": "state_enum", "scope": "s",
                 "content": "합쳐진 blob", "values": ["Active"]}]
    res = make_terms(build_vocab(concepts), [])
    t = next(t for t in res["terms"] if t["anchor"] == "term:K.Active")
    assert "note" not in t["members"][0]


EVENTS = [
    {"event_id": "e1", "type": "adopt", "target": "T.name", "option": "o_paused",
     "actor": "기획", "authority_level": "product", "scope": "INV/x",
     "valid_at": "2026-04-14", "recorded_at": "2026-07-24", "source": ["D-9 비고"]},
    {"event_id": "e2", "type": "supersede", "target": "T.name", "option": "o_held",
     "supersedes": "o_paused", "actor": "기획", "authority_level": "product",
     "scope": "INV/x", "valid_at": "2026-05-18", "recorded_at": "2026-07-24",
     "source": ["D-1031 개명"]},
    {"event_id": "e3", "type": "supersede", "target": "T.name", "option": "o_paused",
     "supersedes": "o_held", "actor": "기획 리드", "authority_level": "product",
     "scope": "INV/x", "valid_at": "2026-07-28", "recorded_at": "2026-07-28",
     "source": ["D-1062 정정"]},
]

ARTICLE_WITH_DECISION = {"anchor": "A-1", "kind": "article", "scope": "s",
                         "content": "Paused ...", "refs": {"decisions": ["D-9"], "articles": []}}


def test_bridge_resolves_currency_via_decision_refs():
    term = {"anchor": "term:Item.Paused", "kind": "term", "surface": "Paused",
            "resource": "Item", "status": "promoted", "basis": "machine",
            "members": [{"concept": "A-1", "kind": "article", "basis": "machine"}]}
    rep = bridge(term, [ARTICLE_WITH_DECISION], EVENTS,
                 valid_at="2026-07-30", known_at="2026-07-30")
    assert rep["decisions"] == ["D-9"]
    assert rep["targets"] == ["T.name"]                       # D-9가 source에 언급된 이벤트의 target
    cur = rep["currency"]["T.name"]
    assert cur["current_option"] == "o_paused"           # 재채택 후 현행
    assert cur["surface_match"] is True                       # 'paused' ⊂ 'o_paused'
    # N1′ 핵심: 모든 전이가 actor 있는 사람 행위(DecisionAct) — 자동 규칙 아님
    assert cur["transitions"] == [("e1", "adopt", "기획"), ("e2", "supersede", "기획"),
                                  ("e3", "supersede", "기획 리드")]
    assert cur["all_transitions_are_decision_acts"] is True
