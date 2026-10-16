"""Phase 1 validation — the A-reducer must reproduce every fixture's hand-computed gold answers.

Run: python3 -m pytest engine/ -q   (from repo root)
 or: python3 engine/test_reducer.py  (plain, no pytest)
"""
from __future__ import annotations

from pathlib import Path
import yaml

from reducer import load_events
from queries import current_authority, history_rationale, option_evidence_profile

FIXTURES = Path(__file__).parent / "fixtures"


def _check_query(events, q):
    exp = q["expect"]
    qtype = q["type"]
    if qtype == "CURRENT_AUTHORITY":
        got = current_authority(events, q["target"], q["valid_at"], q["known_at"], q.get("scope"))
        assert got["current_option"] == exp["current_option"], \
            f'{q["name"]}: current_option {got["current_option"]!r} != {exp["current_option"]!r}'
        assert got["current_state"] == exp["current_state"], \
            f'{q["name"]}: current_state {got["current_state"]!r} != {exp["current_state"]!r}'
        assert got["states"] == exp["states"], \
            f'{q["name"]}: states {got["states"]!r} != {exp["states"]!r}'
    elif qtype == "OPTION_EVIDENCE_PROFILE":
        got = option_evidence_profile(events, q["target"], q["valid_at"], q["known_at"], q.get("scope"))
        for opt, want in exp["options"].items():
            have = got["options"].get(opt)
            assert have is not None, f'{q["name"]}: option {opt!r} missing from profile'
            for key, val in want.items():
                assert have[key] == val, \
                    f'{q["name"]}: {opt}.{key} {have[key]!r} != {val!r}'
        if "current_option" in exp:
            assert got["current_option"] == exp["current_option"], \
                f'{q["name"]}: current_option {got["current_option"]!r} != {exp["current_option"]!r}'
    elif qtype == "HISTORY_RATIONALE":
        got = history_rationale(events, q["target"], q["known_at"], q.get("scope"))
        assert got["current_option"] == exp["current_option"], \
            f'{q["name"]}: current_option {got["current_option"]!r} != {exp["current_option"]!r}'
        ids = [c["event_id"] for c in got["timeline"]]
        assert ids == exp["timeline_event_ids"], \
            f'{q["name"]}: timeline {ids!r} != {exp["timeline_event_ids"]!r}'
    elif qtype == "OPEN_DECISION":
        from queries import open_decisions
        got = open_decisions(events, q["valid_at"], q["known_at"], q.get("scope"))
        open_targets = sorted(o["target"] for o in got["open"])
        assert open_targets == sorted(exp["open_targets"]), \
            f'{q["name"]}: open {open_targets!r} != {exp["open_targets"]!r}'
        for tgt in exp["open_targets"]:
            detail = exp.get(tgt.rsplit(".", 1)[-1])
            if not detail:
                continue
            item = next(o for o in got["open"] if o["target"] == tgt)
            for key, val in detail.items():
                assert sorted(item[key]) == sorted(val), \
                    f'{q["name"]}: {tgt}.{key} {item[key]!r} != {val!r}'
    elif qtype == "WHY_CHANGED":
        # T3는 **파생 answer gold**(원 gold의 서술형 정답을 구조로 옮긴 층)이라
        # reducer 계약이 아니다 — 채점은 벤치 하니스(공개본 미포함)가 한다.
        # 여기서 조용히 통과시키지 않고 두 가지를 명시적으로 잠근다:
        #   ① candidate 표시가 실제로 붙어 있는가(헤드라인 합산 방지 장치)
        #   ② 두 축(reason_type·근거 집합) 스키마가 갖춰졌는가
        assert q.get("status") == "candidate", \
            f'{q["name"]}: T3 gold는 candidate여야 한다(파생 answer gold)'
        assert "reason_type" in exp and "evidence_event_ids" in exp, \
            f'{q["name"]}: T3 expect는 reason_type·evidence_event_ids 두 축을 가져야 한다'
        assert isinstance(exp["evidence_event_ids"], list), \
            f'{q["name"]}: evidence_event_ids는 집합(list)이어야 한다'
        ids = {e.get("event_id") for e in events}
        for ev in exp["evidence_event_ids"]:
            assert ev in ids, f'{q["name"]}: 근거 {ev!r}가 이 픽스처 원장에 없다'
    else:
        raise AssertionError(f'unknown query type {qtype}')


def _fixture_dirs():
    # fixtures are grouped by corpus: fixtures/<corpus>/<case>/events.yaml
    # ★심링크를 따라간다 — 코퍼스가 데이터 레포의 심링크로
    # 장착되는데 Path.rglob는 디렉터리 심링크를 안 탄다(corpus.load_all과 같은 수리).
    import os
    found = []
    for base, dirs, files in os.walk(FIXTURES, followlinks=True):
        dirs.sort()
        if "events.yaml" in files:
            found.append(Path(base))
    return sorted(found)


def _label(fx):
    return f"{fx.parent.name}/{fx.name}"


def test_all_fixtures():
    if not _fixture_dirs():
        import pytest
        pytest.skip("코퍼스 미장착(데이터 분리) — 검사할 픽스처 없음(통과 아님)")
    total = 0
    for fx in _fixture_dirs():
        events = load_events(fx / "events.yaml")
        spec = yaml.safe_load((fx / "expected.yaml").read_text(encoding="utf-8"))
        if "queries" not in spec:        # 리듀서 질의 픽스처가 아닌 gold(예: decision-code-drift) 건너뜀
            continue
        for q in spec["queries"]:
            _check_query(events, q)
            total += 1
    assert total > 0


def test_corpus_isolation():
    """전사 다중프로젝트 경계 — corpus는 하드 경계, 회사만 뽑아도 we-volley가 안 섞인다."""
    from corpus import load_all, events_in_corpus, check_isolation

    all_events = load_all()
    # 1. 실제 fixture는 자연히 격리돼 있어야 한다
    assert check_isolation(all_events) == [], f"boundary breach: {check_isolation(all_events)}"

    # 2. "회사만" 필터에 we-volley(WV.*)가 새어들면 안 된다
    company = events_in_corpus(all_events, "acme-docs")
    if not company:
        # 데이터 분리 — 엔진 레포는 동료 초청용이라 회사 코퍼스가 없을 수
        # 있다. 없으면 검사 대상이 없는 것이지 통과가 아니다(vacuous-pass 규약: skip).
        import pytest
        pytest.skip("회사 코퍼스 미장착(데이터 분리) — 격리 검사 대상 없음(통과 아님)")
    assert all(not (e.get("target") or "").startswith("WV") for e in company), "we-volley leaked into company"
    personal = events_in_corpus(all_events, "personal-wevolley")
    assert all((e.get("target") or "").startswith("WV") for e in personal if e.get("target")), "non-WV leaked into personal"

    # 3. 음성 테스트 — 회사 target을 personal corpus가 건드리면 가드가 잡아야 한다
    from corpus import check_isolation as _ci
    injected = all_events + [{"event_id": "X.bad", "type": "adopt",
                              "target": "INV.status_representation", "option": "oX",
                              "corpus": "personal-wevolley", "valid_at": "2026-01-01",
                              "recorded_at": "2026-01-01"}]
    assert any(v[0] == "corpus_collision" for v in _ci(injected)), "guard failed to catch cross-corpus breach"


def test_boundary_hierarchy():
    """전체 위계 경계 — corpus > tier(foundations 공유) > platform > app.
    foundations 인용은 합법, 앱 간 사적 참조·크로스 corpus는 위반."""
    from corpus import check_isolation, is_shared, platform_of, app_of

    # 위계 파싱
    assert is_shared("foundations/terminology") and not is_shared("summit/inv/items")
    assert platform_of("summit/inv/items") == "summit" and app_of("summit/inv/items") == "inv"
    assert platform_of("atlas/courier/docs") == "atlas"   # 플랫폼 계층 존재

    base = dict(type="adopt", option="o1", valid_at="2026-01-01", recorded_at="2026-01-01")
    evs = [
        {**base, "event_id": "F1", "target": "TERM.status_vocab",
         "corpus": "acme-docs", "scope": "foundations/terminology"},
        # summit/inv가 foundations 인용 = 합법
        {**base, "event_id": "A1", "target": "INV.items",
         "corpus": "acme-docs", "scope": "summit/inv/items",
         "refs": [{"to": "TERM.status_vocab", "type": "depends_on"}]},
        {**base, "event_id": "B1", "target": "ACOMP.docs",
         "corpus": "acme-docs", "scope": "atlas/courier/docs"},
    ]
    assert check_isolation(evs) == [], f"legal refs flagged: {check_isolation(evs)}"

    # 위반 1: summit/inv가 atlas/courier의 사적 target을 참조 (앱 간 침범)
    cross_app = evs + [{**base, "event_id": "A2", "target": "INV.z",
                        "corpus": "acme-docs", "scope": "summit/inv/items",
                        "refs": [{"to": "ACOMP.docs", "type": "depends_on"}]}]
    assert any(v[0] == "cross_app_ref" for v in check_isolation(cross_app)), "cross-app leak not caught"

    # 위반 2: 개인 corpus가 회사 target 참조 (크로스 corpus)
    cross_corpus = evs + [{**base, "event_id": "W1", "target": "WV.x",
                           "corpus": "personal-wevolley", "scope": "wevolley/chat",
                           "refs": [{"to": "INV.items", "type": "depends_on"}]}]
    assert any(v[0] == "cross_corpus_ref" for v in check_isolation(cross_corpus)), "cross-corpus leak not caught"


def test_open_ended_structure():
    """구조는 데이터에서 자란다 — 새 corpus·플랫폼·공유 tier가 corpus.py 수정 0으로 작동.
    (사용자: '새 프로젝트 추가·폐기가 반복될 텐데 하드코딩이면 안 됨')"""
    from corpus import check_isolation, is_shared, platform_of, app_of

    # 레지스트리(데이터)에만 존재하는, 엔진이 이름을 모르는 새 corpus + 새 공유 tier
    reg = {"corpora": {"company-neorepo": {"shared_tiers": ["conventions"]}}}
    sh = ("conventions",)

    # 엔진 코드에 없던 tier·플랫폼이 파싱됨
    assert is_shared("conventions/naming", sh) and not is_shared("meadow/hub/x", sh)
    assert platform_of("meadow/hub/x", sh) == "meadow"   # 처음 보는 플랫폼, 코드 변경 0
    assert app_of("meadow/hub/x", sh) == "hub"

    base = dict(type="adopt", option="o1", valid_at="2026-01-01", recorded_at="2026-01-01",
                corpus="company-neorepo")
    evs = [
        {**base, "event_id": "C1", "target": "CONV.naming", "scope": "conventions/naming"},
        # 새 플랫폼 meadow의 앱 hub가 새 공유 tier 인용 = 합법 (레지스트리가 shared로 선언)
        {**base, "event_id": "H1", "target": "HUB.x", "scope": "meadow/hub/feat",
         "refs": [{"to": "CONV.naming"}]},
        {**base, "event_id": "S1", "target": "STORE.y", "scope": "meadow/store/feat"},
    ]
    assert check_isolation(evs, registry=reg) == [], f"새 구조가 위반으로 오판: {check_isolation(evs, registry=reg)}"

    # 새 corpus 안에서도 앱 간 사적 침범은 잡힘
    leak = evs + [{**base, "event_id": "H2", "target": "HUB.z", "scope": "meadow/hub/feat",
                   "refs": [{"to": "STORE.y"}]}]
    assert any(v[0] == "cross_app_ref" for v in check_isolation(leak, registry=reg))

    # 폐기 = 부재. 앱 이벤트를 빼면 그냥 안 나타남 (에러 없음)
    assert check_isolation([e for e in evs if e["event_id"] != "S1"], registry=reg) == []


def test_ingest_generic_and_change_tolerant():
    """ingester는 (1) 제네릭(레지스트리 데이터 구동, acme-docs 전용 아님) (2) 폴더 재번호에 불변.
    실 acme-docs(지금 구조 변경 중)에 의존하지 않게 합성 코퍼스로 검증."""
    import tempfile
    from pathlib import Path as P
    from ingest import slug, discover, derive_scope

    # slug = 정체성 (번호는 순번일 뿐)
    assert slug("1-summit") == "summit" and slug("a-console-builder") == "console-builder"
    assert slug("2-inv") == "inv" and slug("atlas") == "atlas"

    cfg = {"shared_tiers": ["foundations"], "meta_tiers": ["corpdoc"],
           "decision_file": "decisions-log.md", "decision_format": "corpdoc-table"}
    reg = {"corpora": {"c": cfg}}

    with tempfile.TemporaryDirectory() as d:
        root = P(d)
        # 합성 레이아웃 — 깊이가 서로 다른 두 제품 라인 (prime-commerce=3단, neo=2단)
        (root / "2-foundations").mkdir()
        (root / "2-foundations" / "decisions-log.md").write_text("x", encoding="utf-8")
        (root / "3-prime-commerce" / "1-summit" / "2-inv").mkdir(parents=True)
        (root / "3-prime-commerce" / "1-summit" / "2-inv" / "decisions-log.md").write_text("x", encoding="utf-8")
        (root / "4-neo" / "1-billing").mkdir(parents=True)   # 깊이 다른 두 번째 제품 라인
        (root / "4-neo" / "1-billing" / "decisions-log.md").write_text("x", encoding="utf-8")

        r1 = discover("c", root, reg)
        by_scope = {x["scope"]: x for x in r1["found"]}
        assert set(by_scope) == {"foundations", "prime-commerce/summit/inv", "neo/billing"}, set(by_scope)
        # ★ 깊이 달라도 말단이 app: 3단이든 2단이든 정확
        assert by_scope["prime-commerce/summit/inv"]["app"] == "inv"
        assert by_scope["neo/billing"]["app"] == "billing"    # ← 재구조 전 버그(app=neomart)가 고쳐진 지점
        assert r1["warnings"] == []

        # 변경 내성: 폴더 재번호(3-→5-, 1-summit→4-summit) 해도 slug scope 불변
        (root / "3-prime-commerce").rename(root / "5-prime-commerce")
        (root / "5-prime-commerce" / "1-summit").rename(root / "5-prime-commerce" / "4-summit")
        r2 = discover("c", root, reg)
        assert "prime-commerce/summit/inv" in {x["scope"] for x in r2["found"]}

        # 새 제품 라인·플랫폼·앱 추가 = 자동 발견 (코드 변경 0)
        (root / "6-edge" / "1-gateway").mkdir(parents=True)
        (root / "6-edge" / "1-gateway" / "decisions-log.md").write_text("x", encoding="utf-8")
        r3 = discover("c", root, reg)
        assert "edge/gateway" in {x["scope"] for x in r3["found"]}


def test_corpdoc_decision_parser():
    """진화 레이어 파서 — decisions-log 표에서 결정·supersede 관계를 스켈레톤 추출.
    INV D-7318→D-8812 실형식(취소선 + 'D-7318 supersede')으로 검증."""
    from parsers import parse
    sample = "\n".join([
        "| ID | 날짜 | 결정 내용 | 출처 | 영향 조항 | 반영 상태 | 비고 |",
        "|----|------|-----------|------|-----------|-----------|------|",
        "| D-7318 | 2026-05-18 | 상태 **Held 단일화**(Paused → Held 개명) | `4-source/x.md` | INV-04, INV-07, INV-45 | ~~반영완료~~ → **D-8812로 정정** | 상태 명칭 재통합 (D-8812) |",
        "| D-8812 | 2026-07-28 | 상태 용어 **재통합** — Held를 Paused로 | 실측·설계 대조 | INV-04, INV-07, INV-19, INV-45 | 반영완료 | **D-7318 supersede.** 배포본 Listed/Hidden GAP |",
        "| D-8946 | 2026-07-28 | ItemCode 규칙 정정 | 위키 | INV-08, INV-36 | 반영완료 | 독립 정정 |",
    ])
    res = parse("corpdoc-table", sample, scope="prime-commerce/summit/inv")
    by_id = {d["decision_id"]: d for d in res["decisions"]}

    assert set(by_id) == {"D-7318", "D-8812", "D-8946"}
    # 취소선 + '→ D-8812' → D-7318는 D-8812로 대체됨, 아직 반영 아님(취소선)
    assert by_id["D-7318"]["superseded_by"] == "D-8812"
    assert by_id["D-7318"]["reflected"] is False
    # 비고 'D-7318 supersede' + 취소선 양쪽에서 같은 관계 감지·dedup → 딱 하나
    assert res["supersede_relations"] == [("D-8812", "D-7318")]
    # 영향 조항 추출
    assert by_id["D-8812"]["articles"] == ["INV-04", "INV-07", "INV-19", "INV-45"]
    # D-8946는 독립(정정이지만 supersede 아님) — 관계에 안 들어감
    assert by_id["D-8946"]["superseded_by"] is None
    # SourceDecision 계약의 content — 결정 문장 원문 보존 (중간 '|' 포함해도 통째로)
    assert by_id["D-8812"]["content"].startswith("상태 용어 **재통합**")
    assert "Held를 Paused로" in by_id["D-8812"]["content"]


def _parsed_sample():
    """corpdoc-table 파서 출력 모양의 최소 스켈레톤 (D-7318→D-8812 체인 + 독립 D-8946)."""
    return {
        "decisions": [
            {"decision_id": "D-7318", "date": "2026-05-18", "scope": "prime-commerce/summit/inv",
             "articles": ["INV-04"], "status": "~~반영완료~~ → **D-8812로 정정**",
             "note": "상태 명칭 재통합 (D-8812)", "superseded_by": "D-8812", "reflected": False},
            {"decision_id": "D-8812", "date": "2026-07-28", "scope": "prime-commerce/summit/inv",
             "articles": ["INV-04"], "status": "반영완료",
             "note": "**D-7318 supersede.**", "superseded_by": None, "reflected": True},
            {"decision_id": "D-8946", "date": "2026-07-28", "scope": "prime-commerce/summit/inv",
             "articles": ["INV-08"], "status": "반영완료",
             "note": "독립 정정", "superseded_by": None, "reflected": True},
        ],
        "supersede_relations": [("D-8812", "D-7318")],
    }


def test_skeleton_maps_standalone_to_adopt():
    """독립 결정 → adopt 후보 event. target/option은 anchor 기반 placeholder(proposal)이며
    reducer가 그대로 소비 가능해야 한다(Track-E-lite: 스켈레톤 자동, 의미는 adjudication)."""
    from map_events import skeleton_to_events
    out = skeleton_to_events(_parsed_sample(), prefix="INV")
    ev = {e["event_id"]: e for e in out["events"]}

    e89 = ev["INV.auto.D-8946"]
    assert e89["type"] == "adopt"
    assert e89["target"] == "INV.T.D-8946"          # anchor 기반 placeholder target
    assert e89["option"] == "o_D-8946"
    assert e89["valid_at"] == "2026-07-28" and e89["recorded_at"] == "2026-07-28"
    assert e89["scope"] == "prime-commerce/summit/inv"
    assert e89["confidence"] == "proposal"        # target/option 명명은 adjudication 대상


def test_skeleton_maps_supersede_chain_to_one_target():
    """(D-8812, D-7318) 체인 → 같은 target 위의 adopt+supersede. reducer fold 시 current=o_D-8812."""
    from map_events import skeleton_to_events
    from queries import current_authority
    out = skeleton_to_events(_parsed_sample(), prefix="INV")
    ev = {e["event_id"]: e for e in out["events"]}

    assert ev["INV.auto.D-7318"]["type"] == "adopt"
    e88 = ev["INV.auto.D-8812"]
    assert e88["type"] == "supersede"
    assert e88["supersedes"] == "o_D-7318"
    assert e88["target"] == ev["INV.auto.D-7318"]["target"] == "INV.T.D-7318"   # 체인 base

    got = current_authority(out["events"], "INV.T.D-7318", "2026-12-31", "2026-12-31")
    assert got["current_option"] == "o_D-8812"
    assert got["states"] == {"o_D-7318": "superseded", "o_D-8812": "active"}


def test_skeleton_flags_strikethrough_without_relation():
    """취소선(~~)인데 supersede 관계가 없으면 — 죽었지만 어떻게 죽었는지 모름 →
    adopt는 내되(제안 원장) flag로 owner adjudication을 요구한다(false-current 방지 책임 표시)."""
    from map_events import skeleton_to_events
    parsed = {
        "decisions": [
            {"decision_id": "D-1031", "date": "2026-03-01", "scope": "s",
             "articles": [], "status": "~~반영완료~~", "note": "",
             "superseded_by": None, "reflected": False},
        ],
        "supersede_relations": [],
    }
    out = skeleton_to_events(parsed, prefix="X")
    assert any(e["event_id"] == "X.auto.D-1031" and e["type"] == "adopt" for e in out["events"])
    assert any("D-1031" in f for f in out["flags"]), out["flags"]


def test_skeleton_flags_dangling_and_fanin_relations():
    """미지 anchor 관계(dangling)·한 결정이 여러 결정을 대체(fan-in: target 병합 모호)는
    지어내지 않고 flag로 남긴다."""
    from map_events import skeleton_to_events
    parsed = {
        "decisions": [
            {"decision_id": "D-1", "date": "2026-01-01", "scope": "s", "articles": [],
             "status": "반영완료", "note": "", "superseded_by": None, "reflected": True},
            {"decision_id": "D-2", "date": "2026-01-02", "scope": "s", "articles": [],
             "status": "반영완료", "note": "", "superseded_by": None, "reflected": True},
            {"decision_id": "D-3", "date": "2026-01-03", "scope": "s", "articles": [],
             "status": "반영완료", "note": "", "superseded_by": None, "reflected": True},
        ],
        # D-3이 D-1·D-2 둘 다 대체(fan-in) + D-9는 존재하지 않는 anchor(dangling)
        "supersede_relations": [("D-3", "D-1"), ("D-3", "D-2"), ("D-5", "D-9")],
    }
    out = skeleton_to_events(parsed, prefix="X")
    flags = "\n".join(out["flags"])
    assert "D-9" in flags                          # dangling
    assert "D-3" in flags                          # fan-in
    # fan-in은 임의 병합하지 않는다 — D-1·D-2·D-3 모두 독립 adopt로 남김
    types = {e["event_id"]: e["type"] for e in out["events"]}
    assert types["X.auto.D-3"] == "adopt"


def test_skeleton_normalizes_epoch_mixed_relation_refs():
    """★epoch 경계(구 D-N / 신 <APP>-D-N)를 관계 해소 전에 정규화한다.

    별칭 층(decision_alias) 없이는 두 가지가 동시에 깨진다:
      1. 구형 쪽이 dangling으로 떨어져 **supersede 관계가 조용히 소실**(false-current 직결)
      2. 정규화만 하고 중복을 안 접으면 같은 관계가 2건 = fan-in 오탐

    scope 접두사는 그 scope 결정 로그에서 관측 유도한다(하드코딩 금지)."""
    from map_events import skeleton_to_events
    from queries import current_authority
    parsed = {
        "decisions": [
            {"decision_id": "INV-D-7318", "date": "2026-05-18", "scope": "prime-commerce/summit/inv",
             "articles": [], "status": "~~반영완료~~ → **D-8812로 정정**", "note": "",
             "superseded_by": "D-8812", "reflected": False},
            {"decision_id": "INV-D-8812", "date": "2026-07-28", "scope": "prime-commerce/summit/inv",
             "articles": [], "status": "반영완료", "note": "**INV-D-7318 supersede.**",
             "superseded_by": None, "reflected": True},
        ],
        "supersede_relations": [("D-8812", "INV-D-7318"), ("INV-D-8812", "INV-D-7318")],
    }
    out = skeleton_to_events(parsed, prefix="INV")
    flags = "\n".join(out["flags"])
    assert "dangling" not in flags, flags        # 구형 참조가 미지 anchor로 떨어지면 안 됨
    assert "fan-in" not in flags, flags          # 같은 관계의 두 표기 = 중복, 접어야 함

    ev = {e["event_id"]: e for e in out["events"]}
    assert ev["INV.auto.INV-D-8812"]["type"] == "supersede"
    assert ev["INV.auto.INV-D-8812"]["supersedes"] == "o_INV-D-7318"
    got = current_authority(out["events"], "INV.T.INV-D-7318", "2026-12-31", "2026-12-31")
    assert got["current_option"] == "o_INV-D-8812"


def test_ledger_document_stamps_source_sha():
    """★결정층에도 source_sha를 박는다 — 개념층(l1_snapshot meta.source_sha)과 대칭.

    없으면 "이 원장이 코퍼스 어느 시점인가"를 기계가 못 묻는다. 실제로 그래서 결정층이
    개념층보다 78커밋 뒤진 걸 아무도 못 알아챘다(구 파일의 SHA 줄은 손으로 적은 주석).
    stale 판정은 사람 기억이 아니라 이 필드 대조여야 한다."""
    from extract import ledger_document
    doc = ledger_document("acme-docs", "/some/src",
                          {"events": [{"event_id": "X.auto.D-1"}], "flags": ["f1"],
                           "stats": {"files": 1, "decisions": 1, "events": 1}},
                          sha="abc1234", dirty=True)
    assert doc["meta"]["corpus"] == "acme-docs"
    assert doc["meta"]["source_sha"] == "abc1234"
    assert doc["meta"]["source_dirty"] is True
    assert doc["meta"]["decisions"] == 1
    assert doc["meta"]["flags"] == 1          # 미판정 flag 수도 원장 자신이 들고 있어야 함
    assert doc["flags"] == ["f1"]             # 주석이 아니라 기계 판독 필드로
    assert doc["events"] == [{"event_id": "X.auto.D-1"}]


def test_skeleton_flags_content_cell_relation_candidates():
    """실측 갭(구조 셀 마커는 극소수, 변경 마커 대부분은 내용 셀에 산다) 대응 —
    내용 셀의 변경 마커는 자동 관계로 만들지 않고 **후보 flag**로만 승격한다.
      1. 마커+타 결정(D-N) 언급 → 관계 후보 flag (D-3127이 D-2318를 대체하는 실형식)
      2. 마커만(대상 미상, 정책서 조항 폐기 등) → 관계 미상 flag
      3. 이미 구조 관계로 잡힌 언급(D-8812→D-7318)은 중복 flag 안 함"""
    from map_events import skeleton_to_events
    base = {"scope": "s", "articles": [], "superseded_by": None}
    parsed = {
        "decisions": [
            {**base, "decision_id": "D-2318", "date": "2026-06-01", "content": "미리보기 발송은 앱푸시만 지원",
             "status": "반영완료", "note": "", "reflected": True},
            {**base, "decision_id": "D-3127", "date": "2026-07-01",
             "content": "미리보기 발송은 앱푸시·문자 모두 지원. D-2318의 \"앱푸시만\" 결정을 대체",
             "status": "반영완료", "note": "", "reflected": True},
            {**base, "decision_id": "D-1147", "date": "2026-07-02",
             "content": "정책서 §3-2(진열 기간 저장) 표기를 폐기하고 프론트 구현으로 확정",
             "status": "반영완료", "note": "", "reflected": True},
            {**base, "decision_id": "D-7318", "date": "2026-05-18", "content": "Held 단일화",
             "status": "~~반영완료~~ → **D-8812로 정정**", "note": "", "superseded_by": "D-8812", "reflected": False},
            {**base, "decision_id": "D-8812", "date": "2026-07-28",
             "content": "재통합 — D-7318의 개명을 정정", "status": "반영완료",
             "note": "**D-7318 supersede.**", "reflected": True},
        ],
        "supersede_relations": [("D-8812", "D-7318")],
    }
    out = skeleton_to_events(parsed, prefix="X")
    flags = "\n".join(out["flags"])
    assert "D-3127" in flags and "D-2318" in flags       # ① 관계 후보 (내용 언급)
    assert "D-1147" in flags                            # ② 마커만 — 대상 미상
    assert "D-8812" not in flags                        # ③ 구조 관계 기존재 — 중복 flag 없음
    # 후보는 flag일 뿐 — 자동 원장에서 D-3127은 여전히 독립 adopt (관계를 지어내지 않음)
    types = {e["event_id"]: e["type"] for e in out["events"]}
    assert types["X.auto.D-3127"] == "adopt"


def test_extract_corpus_end_to_end():
    """discover→parse→map 결합 드라이버 — 레지스트리 데이터 구동, 코퍼스 이름 하드코딩 0.
    같은 D-N 번호를 쓰는 두 앱(실제: meadow/crate vs atlas/crate)이 있어도
    event_id·target이 scope로 유일해야 한다."""
    import tempfile
    from pathlib import Path as P
    from extract import extract_corpus

    row = ("| ID | 날짜 | 결정 내용 | 출처 | 영향 조항 | 반영 상태 | 비고 |\n"
           "|--|--|--|--|--|--|--|\n"
           "| D-1 | 2026-01-01 | 확정 | src | A-01 | 반영완료 | |\n")
    cfg = {"shared_tiers": [], "meta_tiers": [], "decision_file": "decisions-log.md",
           "decision_format": "corpdoc-table"}
    reg = {"corpora": {"c": cfg}}

    with tempfile.TemporaryDirectory() as d:
        root = P(d)
        for p in ["1-meadow/1-crate", "2-atlas/1-crate"]:
            (root / p).mkdir(parents=True)
            (root / p / "decisions-log.md").write_text(row, encoding="utf-8")
        out = extract_corpus("c", root, reg)

    ids = [e["event_id"] for e in out["events"]]
    assert len(ids) == 2 and len(set(ids)) == 2, ids          # 앱 간 D-1 충돌 없음
    targets = {e["target"] for e in out["events"]}
    assert len(targets) == 2                                   # target도 scope로 유일
    assert all(e["corpus"] == "c" for e in out["events"])
    scopes = {e["scope"] for e in out["events"]}
    assert scopes == {"meadow/crate", "atlas/crate"}


def test_corpdoc_rules_concept_parser():
    """L1 파일럿 — 1-rules 조항 문서 → SourceConcept 추출 (Tier A).
    실형식: `### [INV-NN] 규칙 본문` + 근거(D-N)·참조(`[INV-NN]`) 불릿 + 변경 이력 표.
    왕복 보존을 위해 line provenance 필수."""
    from parsers import parse
    sample = "\n".join([
        "---",
        'title: "INV 상품 규약"',
        'version: "1.2.0"',
        "---",
        "",
        "# 상품 규약",
        "",
        "## 상태",
        "",
        "### [INV-04] Paused 상태의 상품은 주문할 수 없다",
        "- 근거: D-7318 — 전 채널 동시 중지 (구 위키 02-0 §2)",
        "- 참조: Promo Code 적용 차단은 `[INV-19]`, 자동 전환 조건은 `[INV-45]`",
        "",
        "### [INV-07] Paused → Active 전환 시 단가 재확정이 필수다",
        "- 근거: D-7318",
        "",
        "## 변경 이력",
        "",
        "| 날짜 | 버전 | 변경 내용 | 작성자 |",
        "|------|------|-----------|--------|",
        "| 2026-07-24 | 1.0.0 | 구 위키에서 이관하며 조항화 | 작성자 |",
        "| 2026-07-28 | 1.1.0 | 상태 `Held`→`Paused` 재통합 (D-8812, D-7318 정정) — [INV-04]·[INV-07] | 기획 리드 |",
    ])
    res = parse("corpdoc-rules", sample, scope="prime-commerce/summit/inv")
    by_anchor = {c["anchor"]: c for c in res["concepts"]}

    # 조항 = SourceConcept (anchor·kind·content 원문·section·scope)
    assert set(by_anchor) == {"INV-04", "INV-07"}
    c5 = by_anchor["INV-04"]
    assert c5["kind"] == "article"
    assert c5["content"] == "Paused 상태의 상품은 주문할 수 없다"
    assert c5["section"] == "상태"
    assert c5["scope"] == "prime-commerce/summit/inv"
    # 결정층 다리: 근거의 D-N / 조항 간 참조 (자기 자신 제외)
    assert c5["refs"]["decisions"] == ["D-7318"]
    assert c5["refs"]["articles"] == ["INV-19", "INV-45"]
    # 왕복 보존: line provenance로 원문 재위치 가능
    assert sample.splitlines()[c5["line"] - 1].startswith("### [INV-04]")
    # 문서 버전(frontmatter)
    assert res["version"] == "1.2.0"

    # 변경 이력 표 → 개념 진화 행 (D-N ↔ 조항 매핑의 제2 출처)
    ev = [r for r in res["changelog"] if r["version"] == "1.1.0"][0]
    assert ev["date"] == "2026-07-24" or ev["date"] == "2026-07-28"
    assert ev["decisions"] == ["D-7318", "D-8812"]
    assert ev["articles"] == ["INV-04", "INV-07"]


def test_corpdoc_spec_concept_parser():
    """L1 kind 확장 — spec.md → SourceConcept 3종.
    템플릿 고정 헤딩(전 앱 동일 실측) 위의 Tier A: spec_section(섹션)·
    field(리소스·데이터 정의 표 행)·state_enum(상태값 목록, 리소스별 집계)."""
    from parsers import parse
    sample = "\n".join([
        "---",
        'title: "INV Spec 정의"',
        'version: "1.2.0"',
        "---",
        "",
        "# INV Spec 정의",
        "",
        "## 개요 · 정체성",
        "",
        "- 한 줄 정체성: 매장 내 INV",
        "",
        "## 리소스 · 데이터 정의",
        "",
        "> 필드의 존재·타입·필수만.",
        "",
        "| 리소스/엔티티 | 필드 | 타입 | 필수 | 설명 |",
        "|---------------|------|------|------|------|",
        "| Item | ItemCode | Text | O | 상품 코드. 제약 `[INV-08]` |",
        "| Item | Status | Enum | | 상태값 목록 참조. 기본값 Active |",
        "",
        "## 상태값 목록",
        "",
        "| 리소스 | 상태값 | 의미 |",
        "|--------|--------|------|",
        "| Item.Status | `Active` | 정상 |",
        "| Item.Status | `Paused` | 중지. 규칙 `[INV-04]`·`[INV-07]` |",
        "",
        "## 변경 이력",
        "",
        "| 날짜 | 버전 | 변경 내용 | 작성자 |",
        "|------|------|-----------|--------|",
        "| 2026-07-24 | 1.0.0 | 이관 | 작성자 |",
    ])
    res = parse("corpdoc-spec", sample, scope="prime-commerce/summit/inv")
    by_kind = {}
    for c in res["concepts"]:
        by_kind.setdefault(c["kind"], {})[c["anchor"]] = c

    # 섹션 (변경 이력은 개념 아님)
    assert set(by_kind["spec_section"]) == {"spec§개요 · 정체성", "spec§리소스 · 데이터 정의", "spec§상태값 목록"}
    # 필드: 존재·타입·필수 + 조항 참조
    f = by_kind["field"]["Item.ItemCode"]
    assert (f["type"], f["required"]) == ("Text", True)
    assert f["refs"]["articles"] == ["INV-08"]
    assert by_kind["field"]["Item.Status"]["required"] is False
    # 상태값 enum: 리소스별 집계 (행 2개 → 개념 1개)
    e = by_kind["state_enum"]["Item.Status"]
    assert e["values"] == ["Active", "Paused"]
    assert e["refs"]["articles"] == ["INV-04", "INV-07"]
    # 왕복: field 행·enum 첫 행 line provenance
    assert sample.splitlines()[f["line"] - 1].startswith("| Item | ItemCode |")
    assert res["version"] == "1.2.0"


def test_corpdoc_rules_article_table_rows():
    """의미층 round 2 ②: 조항 밑 표 행 텍스트를 보존한다(행 단위·원문 무수정).
    (파일럿 판정 반복 지적 — INV-17 수정표의 'Active ↔ Paused 상호 전환'이
    등장 검색에서 통째로 누락. refs는 기존에도 수집했으나 텍스트가 버려짐.)"""
    from parsers import parse
    sample = "\n".join([
        "## 수정",
        "",
        "### [K-16] 항목별 수정 가능 여부는 아래 표를 따라야 한다",
        "",
        "| 항목 | 수정 가능 | 제약 |",
        "|------|-----------|------|",
        "| Status | 가능 | Active ↔ Paused 상호 전환만 |",
        "| Expiration | 불가 | 생성 시 확정 `[K-14]` |",
        "",
        "### [K-17] 다음 조항",
        "- 근거: x",
    ])
    res = parse("corpdoc-rules", sample, scope="s")
    art = next(c for c in res["concepts"] if c["anchor"] == "K-16")
    assert art["table"] == [
        "| 항목 | 수정 가능 | 제약 |",
        "| Status | 가능 | Active ↔ Paused 상호 전환만 |",
        "| Expiration | 불가 | 생성 시 확정 `[K-14]` |",
    ]   # 구분선(|---|) 제외, 원문 그대로
    assert "K-14" in art["refs"]["articles"]          # refs 기존 동작 유지
    nxt = next(c for c in res["concepts"] if c["anchor"] == "K-17")
    assert "table" not in nxt or nxt["table"] == []   # 표 없는 조항은 비움


def test_corpdoc_spec_enum_value_notes():
    """의미층 round 2 ①: state_enum이 값별 행 note를 보존한다.
    (파일럿 판정 10·11 — enum 전체 blob 공유가 값-term 간 과통합의 원인.
    원문이 한 행에 값들을 묶으면 note도 공유 — 행 밖 분해는 지어내지 않는다.)"""
    from parsers import parse
    sample = "\n".join([
        "## 상태값 목록",
        "",
        "| 리소스 | 상태값 | 의미 |",
        "|--------|--------|------|",
        "| Item.Status | `Active` | 정상. 판매 가능 |",
        "| Item.Status | `Paused` | 중지 `[INV-45]` |",
        "| Coupon.Status | `Active` `Paused` | 한 행에 값 2개 — 공유 note |",
    ])
    res = parse("corpdoc-spec", sample, scope="s")
    enums = {c["anchor"]: c for c in res["concepts"] if c["kind"] == "state_enum"}
    u = enums["Item.Status"]
    assert u["value_notes"]["Active"] == "정상. 판매 가능"
    assert u["value_notes"]["Paused"] == "중지 `[INV-45]`"
    k = enums["Coupon.Status"]
    assert k["value_notes"]["Active"] == k["value_notes"]["Paused"] == "한 행에 값 2개 — 공유 note"
    assert u["content"].startswith("정상")   # 기존 blob은 하위 호환 유지


def test_corpdoc_spec_enum_variant_shapes():
    """상태값 표는 앱마다 형태가 다르다(실측: 3열 vs 소제목+2열·그룹 2열).
    세 형태 모두 결정론 파싱 — 같은 state_enum 개념으로 수렴."""
    from parsers import parse
    sample = "\n".join([
        "## 상태값 목록",
        "",
        "### Alert State",
        "| 값 | 의미 |",
        "|----|------|",
        "| `Firing` | 발생·최초 발송 |",
        "| `Acknowledged` | 운영자 확인 |",
        "",
        "### Severity / Source Type",
        "| 그룹 | 값 |",
        "|------|-----|",
        "| Severity | `critical` · `warning` |",
        "| Source Type | `metric` · `log` (§0-6은 `system`도 정의 — GAP) |",
    ])
    res = parse("corpdoc-spec", sample, scope="alert")
    enums = {c["anchor"]: c for c in res["concepts"] if c["kind"] == "state_enum"}

    assert enums["Alert State"]["values"] == ["Firing", "Acknowledged"]   # 소제목=리소스, 값|의미 2열
    assert enums["Severity"]["values"] == ["critical", "warning"]         # 그룹|값 2열
    assert enums["Source Type"]["values"] == ["metric", "log", "system"]


def test_corpdoc_spec_unknown_table_shape_flagged():
    """리소스·데이터 정의 표가 캐논 헤더(리소스/엔티티|필드|...)가 아니면
    데이터 행을 지어내지 않고 flag만 남긴다 (실측: meadow·mango가 필드|구분 형태)."""
    from parsers import parse
    sample = "\n".join([
        "## 리소스 · 데이터 정의",
        "",
        "| 필드 | 구분 | 타입 | 필수 | 설명 |",
        "|------|------|------|------|------|",
        "| name | 기본 | Text | O | 이름 |",
    ])
    res = parse("corpdoc-spec", sample, scope="meadow")
    assert [c for c in res["concepts"] if c["kind"] == "field"] == []   # 오파싱 0
    assert any("미지 표 형태" in f for f in res["flags"]), res["flags"]


def test_corpdoc_screen_concept_parser():
    """L1 kind 확장 2차 — 화면정의서 → screen·screen_section·gap.
    화면정의서는 정책서와 담당자가 달라 불일치 가능(소유자 지적) —
    author를 보존하고, 문서가 자기 기록한 GAP을 1급 개념으로 추출한다."""
    from parsers import parse
    sample = "\n".join([
        "---",
        'title: "INV Home 대시보드 화면 정의서 (매장)"',
        'version: "1.4.0"',
        'author: "기획 리드"',
        "---",
        "",
        "# INV Home 대시보드 화면 정의서 (매장)",
        "",
        "> 규칙은 `[INV-NN]`이 정본이고 여기선 인용만 한다.",
        "> 화면ID: **INV0102** (매장용 INV). 설계: 디자인 시안 v2 · 실측: demo 2026-07-27.",
        "",
        "## 2. SNB (매장 INV 메뉴)",
        "",
        "| 섹션 | 메뉴 (화면ID) |",
        "|------|----------------|",
        "| Catalog management | Items(INV02) — ~~Bundle catalog~~ **제거(D-9035)** |",
        "",
        "## 4. 현황 카드",
        "",
        "### 4.1 Items `[INV-04]`",
        "- Total · Active · Paused (설계·정책 기준)",
        "- > **GAP(배포 상이):** 배포본은 `Listed/Hidden`로 표기 — 설계·정책(`[INV-04]`, D-8812) 기준이므로 배포 수정 대상.",
        "",
        "### 4.2 Gift cards `[INV-64]`",
        "- > **GAP(배포 미구현):** 배포본 Home에는 이 카드가 없음.",
    ])
    res = parse("corpdoc-screen", sample, scope="prime-commerce/summit/inv")
    by_kind = {}
    for c in res["concepts"]:
        by_kind.setdefault(c["kind"], []).append(c)

    # screen: 화면ID가 anchor, author 보존(담당자 추적)
    s = by_kind["screen"][0]
    assert s["anchor"] == "INV0102"
    assert s["author"] == "기획 리드"
    assert "D-8812" in s["refs"]["decisions"] and "D-9035" in s["refs"]["decisions"]
    assert "INV-04" in s["refs"]["articles"]

    # 섹션: ## 단위, 섹션 내 refs
    secs = {c["anchor"]: c for c in by_kind["screen_section"]}
    assert "INV0102§2. SNB (매장 INV 메뉴)" in secs
    assert secs["INV0102§2. SNB (매장 INV 메뉴)"]["refs"]["decisions"] == ["D-9035"]

    # GAP: 문서가 자기 기록한 불일치 = 1급 개념 (유형 보존, 원문 보존)
    gaps = by_kind["gap"]
    assert len(gaps) == 2
    assert gaps[0]["gap_type"] == "배포 상이"
    assert "Listed/Hidden" in gaps[0]["content"]
    assert gaps[0]["refs"]["articles"] == ["INV-04"]
    assert gaps[1]["gap_type"] == "배포 미구현"
    # 왕복
    assert sample.splitlines()[gaps[0]["line"] - 1].lstrip("- >").strip().startswith("**GAP")


def test_l1_snapshot_collect_deterministic():
    """개념층 스냅샷 — 기계 파생물을 SHA 스냅샷 파일로 물질화(저작 아님·재생성 가능).
    같은 원본에서 두 번 수집하면 결과가 동일해야 하고(결정론), 문서 3종이 모두 담긴다."""
    import tempfile
    from pathlib import Path as P
    from l1_snapshot import collect_concepts

    rules = "## 상태\n\n### [X-01] 규칙이다\n- 근거: D-1\n"
    spec = "## 상태값 목록\n\n| 리소스 | 상태값 | 의미 |\n|--|--|--|\n| A.s | `On` | 켜짐 |\n"
    screen = "# S 화면 정의서\n\n> 화면ID: **S01** (테스트).\n\n## 1. 구조\n"
    with tempfile.TemporaryDirectory() as d:
        root = P(d)
        app = root / "1-app"
        (app / "1-rules").mkdir(parents=True)
        (app / "2-screens").mkdir(parents=True)
        (app / "1-rules" / "1-r.md").write_text(rules, encoding="utf-8")
        (app / "spec.md").write_text(spec, encoding="utf-8")
        (app / "2-screens" / "1-s.md").write_text(screen, encoding="utf-8")

        r1 = collect_concepts(root)
        r2 = collect_concepts(root)

    assert r1 == r2                                   # 결정론 (스냅샷 재생성 가능성의 전제)
    kinds = {c["kind"] for c in r1["concepts"]}
    assert {"article", "state_enum", "screen"} <= kinds
    by_anchor = {c["anchor"]: c for c in r1["concepts"]}
    assert by_anchor["X-01"]["scope"] == "app"        # slug scope 스탬프
    assert by_anchor["X-01"]["file"].endswith("1-rules/1-r.md")   # 원본 왕복 경로 보존
    assert r1["stats"]["concepts"] == len(r1["concepts"])


def test_integrity_dead_refs_and_rescue():
    """침식 상시 감시 — 스냅샷의 모든 참조(개념→조항·개념→결정)를 코퍼스 전체
    anchor 집합에 대조해 죽은 참조를 찾고, 역링크(근거 역인용)로 재해소를 제안한다.
    제안이지 확정 아님 — adjudication 큐 생성이 목적."""
    from l1_integrity import dead_ref_report
    concepts = [
        {"anchor": "A-01", "kind": "article", "scope": "x/app1", "file": "f1",
         "refs": {"decisions": ["D-1"], "articles": ["A-02"]}},
        {"anchor": "A-02", "kind": "article", "scope": "x/app1", "file": "f1",
         "refs": {"decisions": [], "articles": ["A-99"]}},          # A-99 = 죽은 참조
        {"anchor": "B-01", "kind": "article", "scope": "x/app2", "file": "f2",
         "refs": {"decisions": ["D-9"], "articles": []}},           # D-9 역인용 = 재해소 후보
    ]
    decisions = [
        {"decision_id": "D-1", "scope": "x/app1", "articles": ["A-01"]},
        {"decision_id": "D-9", "scope": "x/app2", "articles": ["A-99"]},  # A-99 죽음 → B-01 제안
    ]
    rep = dead_ref_report(concepts, decisions)

    # 결정→조항 죽은 참조: D-9의 A-99 (D-1의 A-01은 정상)
    dd = {(d["from_id"], d["ref"]): d for d in rep["dead"]}
    assert ("D-9", "A-99") in dd
    assert dd[("D-9", "A-99")]["rescue"] == ["B-01"]     # 역인용 기반 제안 (코퍼스 전체)
    # 개념→조항 죽은 참조: A-02의 A-99 (rescue 없음 — A-99를 역인용한 결정 없음… B-01은 D-9 경유라 동일 제안)
    assert ("A-02", "A-99") in dd
    # 정상 참조는 리포트에 없음
    assert ("D-1", "A-01") not in dd
    assert rep["stats"]["refs_checked"] >= 4 and rep["stats"]["dead"] == 2


def test_integrity_decision_refs_scope_aware():
    """실측 오분류 대응 — 영향 조항 칸의 D-N은 조항이 아니라 결정 참조다.
    같은 scope의 결정 로그에 존재하면 죽은 참조가 아니고, 없으면 dead(ref_kind=decision).
    재해소 제안은 조항류(article·state_enum·field)만 — 화면 섹션 잡음 제거."""
    from l1_integrity import dead_ref_report
    concepts = [
        {"anchor": "A-01", "kind": "article", "scope": "x/app1", "file": "f",
         "refs": {"decisions": ["D-5"], "articles": []}},
        {"anchor": "S§1", "kind": "screen_section", "scope": "x/app1", "file": "f",
         "refs": {"decisions": ["D-5"], "articles": []}},
    ]
    decisions = [
        {"decision_id": "D-5", "scope": "x/app1", "articles": ["D-4", "A-01"]},  # D-4 = 같은 scope 실존 결정
        {"decision_id": "D-4", "scope": "x/app1", "articles": []},
        {"decision_id": "D-9", "scope": "x/app2", "articles": ["D-4"]},          # 다른 scope의 D-4 참조 = dead
    ]
    rep = dead_ref_report(concepts, decisions)
    dd = {(d["from_id"], d["ref"]): d for d in rep["dead"]}
    amb = {(d["from_id"], d["ref"]): d for d in rep["ambiguous"]}
    assert ("D-5", "D-4") not in dd and ("D-5", "D-4") not in amb   # 같은 scope 실존 → 정상
    # 다른 scope에만 존재 → dead가 아니라 '모호 인용'(어느 앱의 D-4인지 명시 없음 — 교차 인용 관행)
    assert ("D-9", "D-4") in amb and ("D-9", "D-4") not in dd
    assert amb[("D-9", "D-4")]["exists_in"] == ["x/app1"]
    # 어느 scope에도 없는 결정 → 진짜 dead
    concepts2 = [{"anchor": "A-01", "kind": "article", "scope": "x/app1", "file": "f",
                  "refs": {"decisions": ["D-7764"], "articles": []}}]
    rep2 = dead_ref_report(concepts2, decisions)
    assert [(d["from_id"], d["ref"]) for d in rep2["dead"]] == [("A-01", "D-7764")]
    # 재해소 제안에 화면 섹션(S§1)은 안 들어감 — 조항류만
    for d in rep["dead"]:
        assert all(not r.startswith("S§") for r in d["rescue"])


def test_snapshot_diff_detects_change():
    """스냅샷 diff = 변경 관측 — 생성·소멸·내용 변경을 anchor(kind·scope) 단위로 잡는다."""
    from l1_integrity import snapshot_diff
    old = [{"anchor": "A-01", "kind": "article", "scope": "s", "content": "v1"},
           {"anchor": "A-02", "kind": "article", "scope": "s", "content": "same"},
           {"anchor": "A-03", "kind": "article", "scope": "s", "content": "bye"}]
    new = [{"anchor": "A-01", "kind": "article", "scope": "s", "content": "v2"},   # 변경
           {"anchor": "A-02", "kind": "article", "scope": "s", "content": "same"}, # 불변
           {"anchor": "A-04", "kind": "article", "scope": "s", "content": "hi"}]   # 생성 (A-03 소멸)
    d = snapshot_diff(old, new)
    assert [c["anchor"] for c in d["added"]] == ["A-04"]
    assert [c["anchor"] for c in d["removed"]] == ["A-03"]
    assert [c["anchor"] for c in d["changed"]] == ["A-01"]
    assert d["stats"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}


def test_idempotency_duplicate_event():
    if not _fixture_dirs():
        import pytest
        pytest.skip("코퍼스 미장착(데이터 분리) — 검사할 픽스처 없음(통과 아님)")
    """Invariant #4 — folding a duplicated event_id changes nothing."""
    events = load_events(_fixture_dirs()[0] / "events.yaml")
    base = current_authority(events, events[0]["target"], "2026-12-31", "2026-12-31")
    dup = current_authority(events + [dict(events[0])], events[0]["target"], "2026-12-31", "2026-12-31")
    assert base == dup


if __name__ == "__main__":
    # plain runner (no pytest dependency)
    count = 0
    for fx in _fixture_dirs():
        events = load_events(fx / "events.yaml")
        spec = yaml.safe_load((fx / "expected.yaml").read_text(encoding="utf-8"))
        if "queries" not in spec:        # 리듀서 질의 픽스처가 아닌 gold(예: decision-code-drift) 건너뜀
            continue
        for q in spec["queries"]:
            _check_query(events, q)
            count += 1
            print(f"  PASS  {_label(fx)} :: {q['name']}")
    test_idempotency_duplicate_event()
    print(f"\nOK — {count} gold queries reproduced across {len(_fixture_dirs())} fixtures + idempotency.")
