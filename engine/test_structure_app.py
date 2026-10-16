from pathlib import Path

import pytest

import structure_app as sa


def test_prep_first_run_extracts_all_and_selects_canon():
    sections = [{"anchor": "s1", "text": "Item 상태 화면"},
                {"anchor": "s2", "text": "야간 배송 배치"}]
    canon = [{"anchor": "inv#item", "name": "Item Paused",
              "scope": "prime-commerce/summit/inv"}]
    plan = sa.prep_plan("prime-commerce/meadow/meadow", sections, canon)
    assert [s["anchor"] for s in plan["to_extract"]] == ["s1", "s2"]  # 첫 실행=전부
    assert plan["carried"] == [] and plan["removed"] == []
    assert any(c["anchor"] == "inv#item" for c in plan["canon_context"])  # 이름매칭 주입


def test_prep_incremental_only_changed():
    prev = [{"anchor": "s1", "kind": "spec_section", "scope": "x", "content": "old A"},
            {"anchor": "s2", "kind": "spec_section", "scope": "x", "content": "B"}]
    new = [{"anchor": "s1", "kind": "spec_section", "scope": "x", "content": "NEW A",
            "text": "NEW A"},                                     # 수정
           {"anchor": "s2", "kind": "spec_section", "scope": "x", "content": "B",
            "text": "B"},                                         # 불변
           {"anchor": "s3", "kind": "spec_section", "scope": "x", "content": "C",
            "text": "C"}]                                         # 추가
    plan = sa.prep_plan("x", new, [], prev_sections=prev)
    ext = {s["anchor"] for s in plan["to_extract"]}
    carried = {s["anchor"] for s in plan["carried"]}
    assert ext == {"s1", "s3"}          # 수정+추가만 재추출
    assert carried == {"s2"}            # 불변 이월(Tier B 0)


def test_prep_incremental_detects_removed():
    prev = [{"anchor": "s1", "kind": "spec_section", "scope": "x", "content": "A"},
            {"anchor": "s9", "kind": "spec_section", "scope": "x", "content": "gone"}]
    new = [{"anchor": "s1", "kind": "spec_section", "scope": "x", "content": "A", "text": "A"}]
    plan = sa.prep_plan("x", new, [], prev_sections=prev)
    assert {s["anchor"] for s in plan["removed"]} == {"s9"}


def test_prep_incremental_normalizes_bare_sections():
    # 실 probe sections.yaml 형태: anchor/doc/text만(kind·scope·content 없음)
    prev = [{"anchor": "s1", "doc": "d.md", "text": "같음"},
            {"anchor": "s2", "doc": "d.md", "text": "옛날"}]
    new = [{"anchor": "s1", "doc": "d.md", "text": "같음"},
           {"anchor": "s2", "doc": "d.md", "text": "바뀜"}]
    plan = sa.prep_plan("x", new, [], prev_sections=prev)
    assert {s["anchor"] for s in plan["to_extract"]} == {"s2"}   # 정규화 없으면 전건 added 오판
    assert {s["anchor"] for s in plan["carried"]} == {"s1"}


def test_prep_incremental_whitespace_only_change_is_carried():
    prev = [{"anchor": "s1", "doc": "d.md", "text": "한 줄\n설명"}]
    new = [{"anchor": "s1", "doc": "d.md", "text": "한 줄  설명"}]   # 공백만 재포맷
    plan = sa.prep_plan("x", new, [], prev_sections=prev)
    assert plan["to_extract"] == []                 # 의미 불변 → Tier B 0
    assert {s["anchor"] for s in plan["carried"]} == {"s1"}


def test_prep_incremental_content_takes_priority_over_text():
    prev = [{"anchor": "s1", "content": "A", "text": "무시될 텍스트"}]
    new = [{"anchor": "s1", "content": "A", "text": "다른 무시될 텍스트"}]  # content 같음
    plan = sa.prep_plan("x", new, [], prev_sections=prev)
    assert plan["to_extract"] == []                 # content 우선이면 불변


def test_fold_plan_auto_folds_merged_queues_new_and_ambiguous():
    # 추출 에이전트 산출(proposals) — target: 정본앵커 | NEW | AMBIGUOUS
    proposals = [{"sid": "meadow#sc-a", "target": "INV-59", "confidence": "high"},
                 {"sid": "meadow#sc-b", "target": "NEW", "confidence": "high"},
                 {"sid": "meadow#sc-c", "target": "AMBIGUOUS", "confidence": "low"}]
    subconcepts = [{"anchor": "sc-a"}, {"anchor": "sc-b"}, {"anchor": "sc-c"}]
    out = sa.fold_plan("meadow", proposals, subconcepts, canonical_index={"INV-59"})
    assert out["align"]["stats"]["errors"] == 0
    assert [m["sid"] for m in out["auto_fold"]] == ["meadow#sc-a"]     # merged 자동
    queued = {q["sid"] for q in out["adjudication_queue"]}
    assert queued == {"meadow#sc-b", "meadow#sc-c"}                     # new+ambiguous 대기


def test_fold_plan_missing_proposal_is_error():
    proposals = [{"sid": "meadow#sc-a", "target": "INV-59", "confidence": "high"}]
    subconcepts = [{"anchor": "sc-a"}, {"anchor": "sc-b"}]     # sc-b 제안 누락
    out = sa.fold_plan("meadow", proposals, subconcepts, {"INV-59"})
    assert out["align"]["stats"]["errors"] == 1                 # 누락=에러(전건 커버)


def test_fold_plan_queue_preserves_adjudication_context():
    proposals = [{"sid": "meadow#sc-c", "target": "INV-59", "confidence": "low",
                  "evidence": "거의 일치"}]
    subconcepts = [{"anchor": "sc-c"}]
    out = sa.fold_plan("meadow", proposals, subconcepts, {"INV-59"})
    q = out["adjudication_queue"][0]
    assert q["was"] == "ambiguous" and q.get("downgraded") is True
    assert q["target"] == "INV-59" and q["evidence"] == "거의 일치"   # 판정 맥락 보존


def test_fold_plan_fail_closed_on_errors():
    proposals = [{"sid": "meadow#sc-a", "target": "INV-59", "confidence": "high"}]
    subconcepts = [{"anchor": "sc-a"}, {"anchor": "sc-b"}]     # sc-b 누락=error
    out = sa.fold_plan("meadow", proposals, subconcepts, {"INV-59"})
    assert out["align"]["stats"]["errors"] == 1
    assert out["auto_fold"] == []          # 무결성 깨진 배치는 자동 fold 0(fail-closed)


def test_fold_plan_blocked_merge_is_recoverable_from_queue():
    proposals = [{"sid": "meadow#sc-a", "target": "INV-59", "confidence": "high"}]
    subconcepts = [{"anchor": "sc-a"}, {"anchor": "sc-b"}]     # sc-b 누락=error
    out = sa.fold_plan("meadow", proposals, subconcepts, {"INV-59"})
    assert out["auto_fold"] == []
    blocked = [q for q in out["adjudication_queue"] if q["was"] == "merged_blocked"]
    assert [q["sid"] for q in blocked] == ["meadow#sc-a"]        # 차단 병합=큐로(사라지지 않음)
    assert blocked[0]["target"] == "INV-59"                     # 판정 맥락 보존


def test_fold_plan_carries_prior_dispositions_for_unchanged():
    proposals = [{"sid": "meadow#sc-a", "target": "INV-59", "confidence": "high"}]
    subconcepts = [{"anchor": "sc-a"}]
    prev = {"meadow#sc-x": {"sid": "meadow#sc-x", "disposition": "gap_hold"}}  # 이전 보류
    out = sa.fold_plan("meadow", proposals, subconcepts, {"INV-59"},
                       prev_dispositions=prev)
    carried = {c["sid"] for c in out["carried_dispositions"]}
    assert carried == {"meadow#sc-x"}          # 안 바뀐 이전 판정 이월(재판정 0)


def test_fold_plan_does_not_carry_reproposed_sids():
    proposals = [{"sid": "meadow#sc-a", "target": "NEW", "confidence": "high"}]
    subconcepts = [{"anchor": "sc-a"}]
    prev = {"meadow#sc-a": {"sid": "meadow#sc-a", "disposition": "gap_hold"}}  # 같은 sid 재추출
    out = sa.fold_plan("meadow", proposals, subconcepts, {"INV-59"},
                       prev_dispositions=prev)
    assert out["carried_dispositions"] == []   # 재추출분은 이월 금지(새 흐름이 판정)
    assert {q["sid"] for q in out["adjudication_queue"]} == {"meadow#sc-a"}


def test_cost_summary_counts_tier_b_calls_and_model_cost():
    # Tier B 호출 수 = 추출할 섹션 수(증분이면 바뀐 것만). 계약 v1 개정: 비용=AI 모델 비용.
    plan = {"to_extract": [{"anchor": "s1"}, {"anchor": "s2"}], "carried": [{"anchor": "s3"}]}
    cost = sa.cost_summary(plan, model="claude-sonnet-5", tokens=151000)
    assert cost["tier_b_calls"] == 2       # 바뀐 2개만 LLM
    assert cost["carried"] == 1            # 이월 1개는 LLM 0
    assert cost["model"] == "claude-sonnet-5" and cost["tokens"] == 151000  # Track R 축적 단위


def test_cost_summary_records_input_output_split_when_given():
    # §9-B 비용 게이트 load-bearing: 분할을 알면 기록(cost_ladder 정밀 $/target 입력).
    plan = {"to_extract": [{"anchor": "s1"}], "carried": []}
    cost = sa.cost_summary(plan, model="claude-sonnet-5", tokens=151000,
                           input_tokens=140000, output_tokens=11000)
    assert cost["input_tokens"] == 140000 and cost["output_tokens"] == 11000
    # 미지정이면 분할 키 부재(backward-compat) — 합계만.
    c2 = sa.cost_summary(plan, model="claude-sonnet-5", tokens=151000)
    assert "input_tokens" not in c2 and "output_tokens" not in c2


def test_cost_summary_records_cache_split():
    """실 로그는 입력 대부분이 캐시 읽기다 — cost_ladder.cost_per_target이
    캐시 단가로 정밀 계산하려면 이 축까지 기록돼야 한다(미기록이면 키 부재=backward-compat)."""
    plan = {"to_extract": [{"anchor": "a"}], "carried": [], "removed": []}
    c = sa.cost_summary(plan, model="claude-sonnet-5", input_tokens=72,
                        output_tokens=79369, cache_creation_tokens=803839,
                        cache_read_tokens=4575097)
    assert c["cache_creation_tokens"] == 803839 and c["cache_read_tokens"] == 4575097
    c2 = sa.cost_summary(plan, model="claude-sonnet-5", tokens=1)
    assert "cache_read_tokens" not in c2


def test_main_fold_accepts_scope_and_prev_dir(tmp_path, monkeypatch):
    """CLI fold의 두 갭 — ①app_scope를 probe 슬러그로 고정(sid 접두가 슬러그와 다르면
    전건 phantom error) ②증분 이월 미배선. 실 2회차가 둘 다 드러냈다."""
    import yaml
    base = tmp_path / "fixtures/acme-docs/work/mango-r2"
    prev = tmp_path / "fixtures/acme-docs/work/mango-r1"
    for d in (base, prev):
        d.mkdir(parents=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "quote": "A"},
                                    {"anchor": "sc-b", "quote": "B"}]},
                   open(prev / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "mango#sc-a", "target": "M-1", "confidence": "high"},
                                  {"sid": "mango#sc-b", "target": "M-2", "confidence": "high"}]},
                   open(prev / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "quote": "A"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "mango#sc-a", "target": "M-1", "confidence": "high"}]},
                   open(base / "align-proposals.yaml", "w"), allow_unicode=True)
    monkeypatch.setenv("LKL_FIXTURES", str(tmp_path / "fixtures"))
    sa.main(["structure_app.py", "fold", "acme-docs", "mango-r2",
             "--scope", "mango", "--prev-dir", str(prev)])
    saved = yaml.safe_load(open(base / "adjudication.yaml"))
    assert saved["stats"]["errors"] == 0                       # 슬러그≠scope인데도 phantom 0
    assert [m["sid"] for m in saved["auto_fold"]] == ["mango#sc-a", "mango#sc-b"]


def test_main_usage_error_on_bad_args():
    with pytest.raises(SystemExit):
        sa.main(["structure_app.py"])              # 인자 부족
    with pytest.raises(SystemExit):
        sa.main(["structure_app.py", "nope", "c", "a"])   # 미지 서브커맨드


def _skip_if_no_company(path):
    from pathlib import Path
    import pytest
    if not (Path(__file__).parent / path).exists():
        pytest.skip("회사 코퍼스 미장착(데이터 분리) — 실 앱 통합 검사 대상 없음(통과 아님)")


def test_integration_prep_on_real_app_selects_canon_subset():
    _skip_if_no_company("fixtures/acme-docs/canon/tier-a")
    """0a0a001 정본 + 실 앱 섹션으로 prep이 유한 부분집합을 고른다.

    ★2026-08-04: cargo는 은퇴(폐기된 설계 산출)로 원장이 ledger/legacy로 갔다.
    실 원장에 기대는 통합 테스트라 대상이 없으면 **통과가 아니라 skip**이다."""
    import yaml
    fixtures = Path(__file__).parent / "fixtures"   # cwd 무관(리포 루트 실행도 동일)
    canon = yaml.safe_load(
        (fixtures / "acme-docs/canon/tier-a/0a0a001.yaml")
        .read_text(encoding="utf-8"))["concepts"]
    secs = yaml.safe_load(
        (fixtures / "acme-docs/work/inv/sections.yaml")
        .read_text(encoding="utf-8"))["sections"]
    plan = sa.prep_plan("prime-commerce/summit/inv", secs, canon)
    ctx = plan["canon_context"]
    assert 0 < len(ctx) < len(canon)          # 부분집합(전부도 0도 아님)
    assert any((c.get("scope") or "").startswith("prime-commerce/summit/inv") for c in ctx)


def test_run_fold_roundtrip_with_prior_dispositions(tmp_path):
    """run_fold가 기존 판정을 이월하고 queue+carried를 영속화(멱등 배선)."""
    import yaml
    base = tmp_path
    yaml.safe_dump({"proposals": [
        {"sid": "cargo#sc-a", "target": "CCONT-01", "confidence": "high"}]},
        open(base / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a"}]},
        open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    # 이전 실행에서 소유자가 판정해둔 항목(disposition 있음) + 미판정 항목(없음)
    yaml.safe_dump({"queue": [
        {"sid": "cargo#sc-old", "was": "new", "disposition": "gap_hold"},
        {"sid": "cargo#sc-pending", "was": "new"}],
        "carried": []},
        open(base / "adjudication.yaml", "w"), allow_unicode=True)
    out = sa.run_fold(base, "cargo")
    saved = yaml.safe_load(open(base / "adjudication.yaml"))
    carried_sids = {c["sid"] for c in saved["carried"]}
    assert "cargo#sc-old" in carried_sids            # 판정된 항목 이월(재판정 0)
    assert saved["stats"]["auto_fold"] == 1           # sc-a는 자동 fold
    assert all(q["sid"] != "cargo#sc-old" for q in saved["queue"])  # 큐에 재등장 금지


def test_run_fold_pending_items_survive_in_queue(tmp_path):
    import yaml
    base = tmp_path
    yaml.safe_dump({"proposals": [
        {"sid": "cargo#sc-a", "target": "CCONT-01", "confidence": "high"}]},
        open(base / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a"}]},
        open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"queue": [
        {"sid": "cargo#sc-pending", "was": "new", "target": "NEW"}],  # 미판정·재제안 안 됨
        "carried": []},
        open(base / "adjudication.yaml", "w"), allow_unicode=True)
    sa.run_fold(base, "cargo")
    saved = yaml.safe_load(open(base / "adjudication.yaml"))
    q = [x for x in saved["queue"] if x["sid"] == "cargo#sc-pending"]
    assert len(q) == 1 and q[0].get("target") == "NEW"   # 큐 잔류(맥락 보존, 소멸 금지)
    assert all(c["sid"] != "cargo#sc-pending" for c in saved["carried"])  # carried 오염 금지


def test_main_trailing_flag_without_value_raises_system_exit():
    with pytest.raises(SystemExit):
        sa.main(["structure_app.py", "prep", "acme-docs", "cargo", "--scope"])


def test_run_fold_persists_auto_fold_ledger(tmp_path):
    import yaml
    yaml.safe_dump({"proposals": [{"sid": "a#sc-1", "target": "INV-59", "confidence": "high"}]},
                   open(tmp_path / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-1"}]},
                   open(tmp_path / "subconcepts.yaml", "w"), allow_unicode=True)
    sa.run_fold(tmp_path, "a")
    saved = yaml.safe_load(open(tmp_path / "adjudication.yaml"))
    assert saved["auto_fold"][0]["sid"] == "a#sc-1"           # 리스트 영속(카운트만 금지)
    assert saved["synonym_record"] == {"a#sc-1": "INV-59"}    # provenance 보존


def test_run_promote_folds_judged_into_stack(tmp_path):
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-n", "name": "N", "quote": "q",
                    "commitment": "hypothesis", "confidence": "low"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"queue": [{"sid": "napp#sc-n", "was": "new", "target": "NEW",
                    "disposition": "new_code_only"}],   # 소유자 판정 완료
                    "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [{"anchor": "other#sc-o", "kind": "concept",
                    "scope": "x", "name": "O", "basis": "decision"}],
                    "relations": [], "bodies": {"other#sc-o": [{"key": "quote", "text": "t"}]},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    out = sa.run_promote(base, "napp", stack, app_scope="neomart/napp")
    saved = yaml.safe_load(open(stack))
    anchors = {c["anchor"] for c in saved["concepts"]}
    assert "napp#sc-n" in anchors                    # 판정분 편입
    assert "other#sc-o" in anchors                   # 타 앱 보존
    assert saved["bodies"]["napp#sc-n"][0]["text"] == "q"
    # 멱등: 재실행 diff 0
    out2 = sa.run_promote(base, "napp", stack, app_scope="neomart/napp")
    assert yaml.safe_load(open(stack)) == saved


def test_second_pass_never_drops_bodies_of_carried_concepts(tmp_path):
    """★단조성 — 2회차 promote 후에도 살아있는 정본 개념은 본문을 잃지 않는다.

    정본에서 무언가 빠지는 유일한 경로는 tombstone이어야 한다 — 이 불변식의 본문 판이다."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    # 2회차 추출: 정본에 이미 있는 sc-a를 재관측(auto_fold) + 신규 sc-b 1건.
    # 실제 2회차 원장 모양(auto_fold 다수 · queue 소수)의 축소판이다.
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "name": "A", "quote": "qa"},
                                    {"anchor": "sc-b", "name": "B", "quote": "qb"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
    yaml.safe_dump({"auto_fold": [{"sid": "napp#sc-a", "target": "napp#sc-a",
                                   "evidence": "정본 개념 재관측"}],
                    "queue": [{"sid": "napp#sc-b", "was": "new", "target": "NEW",
                               "disposition": "new_code_only"}],
                    "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [{"anchor": "napp#sc-a", "kind": "concept",
                    "scope": "neomart/napp", "name": "A", "basis": "document_stated"}],
                    "relations": [],
                    "bodies": {"napp#sc-a": [{"key": "quote", "text": "qa"}]},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)

    sa.run_promote(base, "napp", stack, app_scope="neomart/napp")

    saved = yaml.safe_load(open(stack))
    live = [c["anchor"] for c in saved["concepts"] if not c.get("removed_at")]
    assert "napp#sc-a" in live and "napp#sc-b" in live       # 개념은 둘 다 생존
    assert saved["bodies"]["napp#sc-a"][0]["text"] == "qa"   # ★재관측분 본문 보존
    assert saved["bodies"]["napp#sc-b"][0]["text"] == "qb"   # 신규분 본문 편입
    assert [a for a in live if a not in saved["bodies"]] == []   # 본문 없는 생존 개념 0


def test_auto_fold_to_absent_canon_target_is_surfaced_not_silently_dropped(tmp_path):
    """★보존 — 추출된 하위개념은 승격되거나 보류되거나 정본 노드에 붙는다. 조용히 사라지면 안 된다.

    `auto_fold`(재관측)는 "이미 정본에 있는 개념을 다시 봤다"는 선언이라 승격 대상이 아니다
    (build_dispositions는 queue+carried만 순회). 그런데 target이 정본에 **없으면** 승격도
    안 되고 stamp_last_seen이 찍을 데도 없어 그냥 증발한다.

    승격 여부는 소유자 판정 사안이라 여기서 바꾸지 않는다. 다만 **사라진 사실 자체는
    기계가 세어 정본에 남겨야** 한다 — 안 보이면 다음 회차에도 같은 일이 반복된다."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "name": "A", "quote": "qa"},
                                    {"anchor": "sc-b", "name": "B", "quote": "qb"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
    # sc-a는 정본에 실재하는 노드로 재관측(정상), sc-b는 Tier A 조항으로 재관측(증발).
    yaml.safe_dump({"auto_fold": [{"sid": "napp#sc-a", "target": "napp#sc-a"},
                                  {"sid": "napp#sc-b", "target": "NAPP-58"}],
                    "queue": [], "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [{"anchor": "napp#sc-a", "kind": "concept",
                    "scope": "neomart/napp", "name": "A", "basis": "document_stated"}],
                    "relations": [],
                    "bodies": {"napp#sc-a": [{"key": "quote", "text": "qa"}]},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)

    sa.run_promote(base, "napp", stack, app_scope="neomart/napp")

    meta = yaml.safe_load(open(stack))["meta"]
    assert meta["dangling_auto_fold"] == ["napp#sc-b"]   # 증발분이 정본에 기록된다


def test_promote_reports_evaporated_count_on_stdout(tmp_path, capsys):
    """증발 건수는 실행 출력에도 뜬다 — 파일에만 남으면 돌린 사람이 그 자리에서 못 본다."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-b", "name": "B", "quote": "qb"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
    yaml.safe_dump({"auto_fold": [{"sid": "napp#sc-b", "target": "NAPP-58"}],
                    "queue": [], "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)

    sa.run_promote(base, "napp", stack, app_scope="neomart/napp")

    assert "증발 1" in capsys.readouterr().out


def test_absorb_legacy_bodies_bridges_by_surface_and_queues_the_rest():
    """★고아 계보 흡수 — 0a0a001의 조립 본문(소유자 전건 승인)을 현 정본으로.

    두 계보는 개념을 다르게 부른다: 0a0a001 `concept:Promotion`·`term:Promotion.Rules`
    (의미 이름) vs 현 정본 `inv#sc-promotion`(문서 위치). 표면형(`이름 (설명)`의 앞부분)이
    같으면 같은 개념으로 잇는다 — 결정론·LLM 0. term 노드는 리소스 머리(`Promotion.Rules`
    → `Promotion`)로 부모 개념에 접는다(현 스키마에 term 층이 없다)."""
    concepts = [{"anchor": "inv#sc-promotion", "name": "Promotion (프로모션 — 할인 단위)"},
                {"anchor": "inv#sc-voucher", "name": "Voucher (임시 지급 인스턴스)"}]
    legacy = {"concept:Promotion": {"fragments": [{"key": "INV-58|content", "text": "프로모션 구성"}]},
              "term:Promotion.Rules": {"fragments": [{"key": "INV-59|content", "text": "S 구조"},
                                                       {"key": "INV-58|content", "text": "프로모션 구성"}]},
              "concept:Voucher (임시 지급)": {"fragments": [{"key": "INV-72|content", "text": "지급"}]},
              "concept:주문": {"fragments": [{"key": "INV-93|content", "text": "주문"}]}}

    bodies, unbridged = sa.absorb_legacy_bodies(concepts, legacy)

    assert bodies["inv#sc-promotion"] == [                       # 조각 dedup·키 정렬
        {"key": "INV-58|content", "text": "프로모션 구성"},
        {"key": "INV-59|content", "text": "S 구조"}]
    assert bodies["inv#sc-voucher"] == [{"key": "INV-72|content", "text": "지급"}]
    assert [u["node"] for u in unbridged] == ["concept:주문"]   # 소실 아님 — 큐로
    assert unbridged[0]["fragments"][0]["text"] == "주문"


def test_run_absorb_merges_into_stack_and_persists_queue(tmp_path):
    """I/O 다리 — 흡수분은 스택 본문에 병합(기존 조각 보존), 미연결은 원장 파일로 남는다.
    단조성 불변식과 같은 규칙: 정본은 줄지 않고, 사라지는 것은 기록된다."""
    import yaml
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [{"anchor": "inv#sc-promotion", "kind": "concept",
                    "scope": "x/inv", "name": "Promotion (프로모션)"}],
                    "relations": [],
                    "bodies": {"inv#sc-promotion": [{"key": "quote", "text": "게이트 인용"}]},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    legacy = tmp_path / "legacy.yaml"
    yaml.safe_dump({"nodes": {"concept:Promotion": {"fragments": [
                        {"key": "INV-58|content", "text": "프로모션 구성"}]},
                              "concept:주문": {"fragments": [
                        {"key": "INV-93|content", "text": "주문"}]}}},
                   open(legacy, "w"), allow_unicode=True)

    sa.run_absorb(stack, legacy, tmp_path / "unbridged.yaml")

    body = yaml.safe_load(open(stack))["bodies"]["inv#sc-promotion"]
    assert [f["key"] for f in body] == ["quote", "INV-58|content"]   # 기존 조각 보존
    q = yaml.safe_load(open(tmp_path / "unbridged.yaml"))["unbridged"]
    assert [u["node"] for u in q] == ["concept:주문"]


def test_assemble_body_fragments_expands_article_into_source_text():
    """★본문 층 — 개념은 자기가 나타난 조항의 **원문**을 들고 있어야 한다.

    계약상 `quote`는 왕복 게이트의 증거("원문에 그대로 존재하는 부분 문자열")지 본문이
    아닌데, depth_promote가 그것을 bodies에 넣어 정본 본문이 개념당 수십 자에 머물렀다
    (옛 계보 한 앱의 조립 본문이 세 코퍼스 정본 전체보다 길었다)."""
    tier_a = [{"anchor": "A-1", "kind": "article",
               "content": "프로모션은 하나 이상의 Rule로 구성한다",
               "fields": {"근거": "구 위키 05 §2", "참조": "[A-2]"}}]
    rows = [{"sid": "inv#sc-promotion", "target": "A-1"},
            {"sid": "inv#sc-ghost", "target": "A-404"}]   # 정본에 없는 조항

    out = sa.assemble_body_fragments(rows, tier_a)

    assert list(out) == ["inv#sc-promotion"]                 # 미해소는 만들지 않는다
    assert out["inv#sc-promotion"] == [
        {"key": "A-1|content", "text": "프로모션은 하나 이상의 Rule로 구성한다"},
        {"key": "A-1|fields.근거", "text": "구 위키 05 §2"},
        {"key": "A-1|fields.참조", "text": "[A-2]"}]


def test_run_promote_assembles_body_from_tier_a(tmp_path):
    """I/O 배선 — tier_a를 주면 승격 개념의 본문이 게이트 인용 + 조항 원문 조각이 된다."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-promotion", "name": "Promotion",
                                     "quote": "정책은 하나 이상"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
    yaml.safe_dump({"queue": [{"sid": "inv#sc-promotion", "was": "article_only",
                               "target": "A-1", "disposition": "new_code_only"}],
                    "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    tier_a = [{"anchor": "A-1", "kind": "article",
               "content": "프로모션은 하나 이상의 Rule로 구성한다",
               "fields": {"근거": "구 위키 05 §2"}}]

    sa.run_promote(base, "inv", stack, app_scope="x/inv", tier_a=tier_a)

    body = yaml.safe_load(open(stack))["bodies"]["inv#sc-promotion"]
    assert [f["key"] for f in body] == ["quote", "A-1|content", "A-1|fields.근거"]
    assert body[1]["text"] == "프로모션은 하나 이상의 Rule로 구성한다"


def test_merge_into_tier_a_article_does_not_auto_fold():
    """★개념은 조항에 병합되지 않는다 — 조항은 개념이 나타난 자리(provenance)지 개념이 아니다.

    소유자 결정(concept-body-design.md:11·19): "우리는 개념 통채로 들고 있고, 코어플랜의
    inv-15,16에 이 개념이 들어가있다 정도" / 시금석 = "acme-docs이 삭제돼도 개념층만으로
    온전한 지식이 남아야 한다"."""
    subs = [{"anchor": "sc-promotion"}, {"anchor": "sc-project"}]
    props = [{"sid": "inv#sc-promotion", "target": "INV-59", "confidence": "high"},
             {"sid": "inv#sc-project", "target": "mango#sc-store", "confidence": "high"}]
    canon = {"INV-59", "mango#sc-store"}          # Tier A 조항 + 깊은층 개념
    deep = {"mango#sc-store"}                     # 깊은층에 실재하는 anchor만

    out = sa.fold_plan("inv", props, subs, canon, deep_index=deep)

    folded = {m["sid"] for m in out["auto_fold"]}
    queued = {q["sid"]: q for q in out["adjudication_queue"]}
    assert folded == {"inv#sc-project"}             # 깊은층 병합만 재관측
    assert "inv#sc-promotion" in queued                # 조항 병합은 증발하지 않고 큐로
    assert queued["inv#sc-promotion"]["was"] == "article_only"
    assert queued["inv#sc-promotion"]["target"] == "INV-59"   # 조항은 provenance로 보존


def test_run_fold_reads_deep_index_from_stack(tmp_path):
    """I/O 배선 — run_fold에 stack을 주면 깊은층 anchor 집합이 fold_plan으로 전달된다.
    순수 코어(fold_plan)는 파일을 모르고, 스택 로드는 CLI가 한다(run_prep과 같은 형태)."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-promotion", "name": "Promotion", "quote": "q"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "inv#sc-promotion", "target": "INV-59",
                                   "confidence": "high"}]},
                   open(base / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"canon": [{"anchor": "INV-59"}]},
                   open(base / "canon-context.yaml", "w"), allow_unicode=True)
    stack = {"concepts": [{"anchor": "mango#sc-store"}]}   # 깊은층에 INV-59은 없다

    out = sa.run_fold(base, "inv", stack=stack)

    assert out["auto_fold"] == []
    assert [q["was"] for q in out["adjudication_queue"]] == ["article_only"]


def test_canon_is_monotone_across_passes(tmp_path):
    """★정본 단조성 — promote를 거쳐도 개념과 그 본문은 줄지 않는다(tombstone만 예외).

    항목 단위 게이트(왕복 인용·재제안 0·결정론 diff 0)는 전부 통과하는 사건이었다.
    "정본은 줄지 않는다"를 재는 장치가 없었기 때문이다 — 이 테스트가 그 자리다.
    새 층(예: 관계 본문·근거 링크)을 붙일 때 같은 실수를 하면 여기서 걸린다.

    relations·held는 제외한다 — 판정분의 **파생**이라 매 회차 재계산이 설계다
    (개념이 남아 있으면 다음 회차에 다시 만들어진다). 단조여야 하는 건 원본 층뿐이다."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
    stack = tmp_path / "depth-stack.yaml"

    def pass_(subs, adj):
        yaml.safe_dump({"subconcepts": subs}, open(base / "subconcepts.yaml", "w"),
                       allow_unicode=True)
        yaml.safe_dump(adj, open(base / "adjudication.yaml", "w"), allow_unicode=True)
        before = yaml.safe_load(open(stack))
        sa.run_promote(base, "napp", stack, app_scope="neomart/napp")
        after = yaml.safe_load(open(stack))
        live_before = {c["anchor"] for c in before["concepts"] if not c.get("removed_at")}
        assert live_before <= {c["anchor"] for c in after["concepts"]}      # 개념 단조
        assert set(before["bodies"]) <= set(after["bodies"])                # 본문 단조
        return after

    yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    # 1회차 — 신규 2건 편입
    pass_([{"anchor": "sc-a", "name": "A", "quote": "qa"},
           {"anchor": "sc-b", "name": "B", "quote": "qb"}],
          {"queue": [{"sid": "napp#sc-a", "was": "new", "disposition": "new_code_only"},
                     {"sid": "napp#sc-b", "was": "new", "disposition": "new_code_only"}],
           "carried": []})
    # 2회차 — 기존 2건 재관측 + 신규 1건. 재관측분은 승격 목록에 없다.
    after = pass_([{"anchor": "sc-c", "name": "C", "quote": "qc"}],
                  {"auto_fold": [{"sid": "napp#sc-a", "target": "napp#sc-a"},
                                 {"sid": "napp#sc-b", "target": "napp#sc-b"}],
                   "queue": [{"sid": "napp#sc-c", "was": "new",
                              "disposition": "new_code_only"}],
                   "carried": []})
    assert len(after["concepts"]) == 3 and len(after["bodies"]) == 3
    assert after["meta"]["dangling_auto_fold"] == []      # 증발 0 (target 전부 실재)


def test_run_promote_stamps_own_provenance(tmp_path):
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-n", "name": "N", "quote": "q",
                    "commitment": "hypothesis", "confidence": "low"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"queue": [{"sid": "napp#sc-n", "was": "new", "target": "NEW",
                    "disposition": "new_code_only"}], "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {"generator": "depth_promote.py",
                    "source": "adjudication-ledger.yaml", "promoted": 3, "relations": 1,
                    "held": {"candidate": 2, "ambiguous": 1, "gap": 1}},
                    "concepts": [{"anchor": "other#sc-o", "kind": "concept", "scope": "x",
                    "name": "O", "basis": "decision"}],
                    "relations": [], "bodies": {"other#sc-o": [{"key": "quote", "text": "t"}]},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    sa.run_promote(base, "napp", stack, app_scope="neomart/napp")
    saved = yaml.safe_load(open(stack))
    meta = saved["meta"]
    assert meta["generator"] == "structure_app.run_promote"
    assert meta["last_promoted_app"] == "napp"
    assert meta["promoted_total"] == len(saved["concepts"]) == 2   # other#sc-o + napp#sc-n
    assert meta["relations_total"] == 0
    assert meta["held_total"] == {"candidate": 0, "ambiguous": 0, "gap": 0}
    assert "source" not in meta                        # 옛 판정 원장 출처 주장 유지 안 함
    assert "promoted" not in meta and "relations" not in meta and "held" not in meta


def test_split_removed_subconcepts_tombstones_only_provable_deletions():
    """★섹션이 문서에서 사라지면 그 개념은 '삭제됨'으로 표시하고 **지우지 않는다**(tombstone).

    지금까지 prep의 removed는 계산만 되고 아무 일도 안 했다 — 섹션이 없어져도 개념은
    스택에 유령으로 남거나, 왕복 게이트가 quote_not_found로 잡아 **정당한 삭제가 지어냄
    오류처럼 배치 전체를 막았다**(fail-closed). 둘 다 틀렸다.

    규율: 증명 가능할 때만 표시한다 — quote가 삭제된 섹션 원문에 실재했음을 역조회로
    확인한 경우만 tombstone. 출처 미상(quote가 어디서도 안 나옴)은 지어내지 않고
    그대로 두어 게이트가 잡게 한다(조용한 소실 금지)."""
    subs = [
        {"anchor": "sc-live", "quote": "살아있는 문장"},
        {"anchor": "sc-gone", "quote": "지워진 문장"},
        {"anchor": "sc-orphan", "quote": "어디에도 없는 문장"},
    ]
    sections = [{"anchor": "s1", "text": "여기 살아있는 문장 이 있다"}]
    removed = [{"anchor": "s2", "text": "여기 지워진 문장 이 있었다"}]
    live, tombs = sa.split_removed_subconcepts(subs, sections, removed, at="aa0a005")

    assert [s["anchor"] for s in live] == ["sc-live", "sc-orphan"]   # 미상은 게이트 몫
    assert len(tombs) == 1
    assert tombs[0]["anchor"] == "sc-gone"
    assert tombs[0]["removed_at"] == "aa0a005"
    assert tombs[0]["removed_from"] == ["s2"]          # 어느 섹션이 사라졌는지 근거 보존
    assert tombs[0]["quote"] == "지워진 문장"           # 원문 증거 자체는 남긴다


def test_tombstone_node_marked_removed_but_kept_in_stack():
    """tombstone은 정본에서 **삭제가 아니라 표시**다 — 노드는 남고 removed_at이 찍힌다.
    이력이 사라지면 '예전엔 이런 게 있었다'를 물을 수 없게 된다(발전 위키의 반대)."""
    import depth_promote as dp
    rows = [{"sid": "a#sc-gone", "app": "a", "name": "사라진 개념", "was": "carried",
             "disposition": "tombstone", "removed_at": "aa0a005",
             "quote": "지워진 문장"}]
    out = dp.fold_depth({"dispositions": rows}, {"a": {"subconcepts": [], "relations": []}},
                        app_scopes={"a": "x/y/a"})
    node = out["concepts"][0]
    assert node["anchor"] == "a#sc-gone"
    assert node["removed_at"] == "aa0a005"
    assert node["name"] == "사라진 개념"
    # probe에 더 이상 없는 개념이라 quote는 row가 들고 온다(증거 소실 금지)
    assert out["bodies"]["a#sc-gone"] == [{"key": "quote", "text": "지워진 문장"}]


def test_quote_gate_quarantines_offender_not_batch():
    """★게이트 실패는 **그 항목만** 격리한다 — 배치 전체를 막지 않는다(계약 개정 2026-08-03).

    격리 대상은 여전히 정본에 못 들어간다 — 지어냄 차단은 그대로다."""
    auto_fold = [{"sid": "a#ok1", "target": "T1"}, {"sid": "a#ok2", "target": "T2"},
                 {"sid": "a#bad", "target": "T3"}]
    queue = [{"sid": "a#n1", "was": "new"}]
    gate = {"ok": [{"anchor": "ok1"}, {"anchor": "ok2"}], "rejected": [{"anchor": "bad"}]}
    af, q, stat = sa.apply_quote_gate("a", auto_fold, queue, gate)

    assert [x["sid"] for x in af] == ["a#ok1", "a#ok2"]     # 검증된 것은 그대로 통과
    by_sid = {x["sid"]: x for x in q}
    assert by_sid["a#bad"]["was"] == "quote_gate_failed"
    assert by_sid["a#bad"]["quote_gate_failed"] is True
    assert "a#ok1" not in by_sid and "a#ok2" not in by_sid   # 연좌 없음
    assert by_sid["a#n1"]["was"] == "new"                    # 기존 큐 보존
    assert stat == {"ok": 2, "rejected": 1}


def test_promote_output_is_order_independent(tmp_path):
    """★멱등 — 앱을 어떤 순서로 promote하든 depth-stack.yaml 내용이 같아야 한다.

    concepts/relations/held는 정렬돼 있었지만 **bodies(dict)만 정렬이 없어** 삽입 순서가
    그대로 파일 순서가 됐다. 여러 앱을 순서만 바꿔 재실행하면 내용은 같은데 diff가 뜬다 —
    "같은 입력 재실행 diff 0"이 이 파이프라인의 선언된 불변식이라 그냥 지저분한 게
    아니라 계약 위반이고, 스냅샷 대조로 변경을 감시하는 층이 전부 오탐을 낸다."""
    import yaml
    stack = tmp_path / "s.yaml"
    base_doc = {"meta": {}, "concepts": [], "relations": [], "bodies": {},
                "held": {"candidate": [], "ambiguous": [], "gap": []}}

    def promote_seq(apps):
        yaml.safe_dump(base_doc, open(stack, "w"), allow_unicode=True)
        for a in apps:
            d = tmp_path / a; d.mkdir(exist_ok=True)
            yaml.safe_dump({"subconcepts": [{"anchor": "sc-1", "name": a, "quote": a}]},
                           open(d / "subconcepts.yaml", "w"), allow_unicode=True)
            yaml.safe_dump({"relations": []}, open(d / "relations-canon.yaml", "w"))
            yaml.safe_dump({"queue": [{"sid": f"{a}#sc-1", "was": "new"}]},
                           open(d / "adjudication.yaml", "w"), allow_unicode=True)
            sa.run_promote(d, a, stack, app_scope=f"x/{a}")
        return open(stack).read()

    assert promote_seq(["zeta", "alpha"]) == promote_seq(["alpha", "zeta"]) \
        .replace("last_promoted_app: zeta", "last_promoted_app: alpha")


def test_prep_injects_promoted_concepts_so_they_are_not_reproposed(tmp_path):
    """★루프 닫힘 e2e — 1회차에 정본화한 개념이 2회차 추출 입력(canon-context)에 보인다.

    검증은 "canon-context에 그 anchor가 실린다"까지 — 추출기가 실제로 그걸 겨냥하는지는
    LLM 행동이라 계약(extraction-handoff-contract)이 담당하고 여기서 단정하지 않는다."""
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "DevSpace 상태는 이러하다"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    tier_a = [{"anchor": "MANGO-01", "kind": "clause", "scope": "x/y/a",
               "content": "DevSpace 상태는 이러하다"}]
    stack = {"concepts": [{"anchor": "a#sc-devspace", "kind": "concept", "scope": "x/y/a",
                           "name": "DevSpace 상태 정책"}],
             "bodies": {"a#sc-devspace": [{"key": "quote", "text": "DevSpace 상태는 이러하다"}]}}

    sa.run_prep(tmp_path, "x/y/a", tier_a, stack=stack)
    ctx = yaml.safe_load(open(tmp_path / "canon-context.yaml"))["canon"]
    anchors = {c["anchor"] for c in ctx}
    assert "a#sc-devspace" in anchors        # ← 루프가 닫혔다
    assert "MANGO-01" in anchors             # Tier A는 그대로

    # stack 미지정(첫 회차·신규 코퍼스)이면 종전 동작
    sa.run_prep(tmp_path, "x/y/a", tier_a)
    assert {c["anchor"] for c in
            yaml.safe_load(open(tmp_path / "canon-context.yaml"))["canon"]} == {"MANGO-01"}


def test_fold_validates_targets_against_real_canon_three_ways(tmp_path):
    """★P1-b — fold의 정본 인덱스를 실제 canon으로. 단 **3분류**다(2분류면 틀린다).

    지금까지 `run_fold`는 인덱스를 proposals에서 역산했다 — 코드 주석이 스스로 인정하듯
    "지어낸 target은 자기참조라 못 잡는다". Tier B anchor가 target 공간에 들어온 지금
    (P1-a) 이 구멍은 load-bearing 결함이다."""
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "본문"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"canon": [{"anchor": "A-01"}]},
                   open(tmp_path / "canon-context.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"anchors": ["A-01", "FAR-09"]},      # prep 산출 형식(앵커 목록)
                   open(tmp_path / "canon-full.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": f"sc-{k}", "name": k, "quote": "본문"}
                                    for k in ("in", "cross", "fake")]},
                   open(tmp_path / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [
        {"sid": "a#sc-in", "target": "A-01", "confidence": "high"},
        {"sid": "a#sc-cross", "target": "FAR-09", "confidence": "high"},
        {"sid": "a#sc-fake", "target": "지어낸-앵커", "confidence": "high"}]},
        open(tmp_path / "align-proposals.yaml", "w"), allow_unicode=True)

    sa.run_fold(tmp_path, "a")
    adj = yaml.safe_load(open(tmp_path / "adjudication.yaml"))
    auto = {x["sid"]: x for x in adj["auto_fold"]}
    q = {x["sid"]: x for x in adj["queue"]}

    assert "a#sc-in" in auto and "cross_scope" not in auto["a#sc-in"]
    assert auto["a#sc-cross"]["cross_scope"] is True      # 정당 — 주입 부족 표시
    assert q["a#sc-fake"]["was"] == "phantom_target"      # 지어냄만 격리
    assert "a#sc-fake" not in auto
    assert adj["stats"]["errors"] == 0                    # 배치는 안 막힌다


def test_fold_reattaches_owner_judgment_to_reproposed_sid():
    """★소유자 판정은 재실행에서 살아남아야 한다 — 지금은 조용히 소멸한다.

    판정은 사람이 내린 것이라 재추출이 무효화하지 않는다. 내용이 실제로 바뀌었는지는
    왕복 게이트·변경 섹션 판정이 따로 본다. 판정 변경은 명시적 편집으로만."""
    props = [{"sid": "a#sc-1", "target": "T1", "confidence": "high"},
             {"sid": "a#sc-2", "target": "NEW"}]
    subs = [{"anchor": "sc-1"}, {"anchor": "sc-2"}]
    prev = {"a#sc-2": {"sid": "a#sc-2", "was": "new", "disposition": "new_decision",
                       "align_to": "X"}}
    out = sa.fold_plan("a", props, subs, {"T1"}, prev_dispositions=prev)
    q = {x["sid"]: x for x in out["adjudication_queue"]}
    assert q["a#sc-2"]["disposition"] == "new_decision"   # 판정 생존
    assert q["a#sc-2"]["align_to"] == "X"
    assert q["a#sc-2"]["was"] == "new"                    # 이번 회차 맥락은 그대로


def test_stamp_last_seen_marks_reobserved_concepts():
    """★P1-c — 재관측은 새 노드가 아니라 **갱신**이다. 이게 "발전"의 기계적 정의.

    남겨야 하는 이유는 tombstone의 짝이기 때문이다: 삭제는 섹션이 사라질 때만 잡히는데
    (§ split_removed_subconcepts), 섹션은 남고 그 개념 서술만 빠지는 경우는 못 잡는다.
    `last_seen`이 있으면 "몇 회차째 안 보이는 개념"이 tombstone 후보로 드러난다.

    새 노드가 안 생기는 게 정상이다 — 그게 재제안이 사라졌다는 뜻이다."""
    stack = [{"anchor": "a#sc-live", "name": "L"},
             {"anchor": "a#sc-old", "name": "O", "last_seen": "sha0"}]
    auto_fold = [{"sid": "a#sc-x", "target": "a#sc-live"},      # Tier B 재관측
                 {"sid": "a#sc-y", "target": "A-01"}]           # Tier A 병합(스택 무관)
    out, n = sa.stamp_last_seen(stack, auto_fold, "sha1")
    by = {c["anchor"]: c for c in out}
    assert by["a#sc-live"]["last_seen"] == "sha1"
    assert by["a#sc-old"]["last_seen"] == "sha0"     # 이번에 안 보인 것은 그대로 — 노후 신호
    assert n == 1
    assert len(out) == 2                              # 새 노드 0 = 재제안 소멸의 증거


def test_promote_never_silently_drops_existing_canon(tmp_path):
    """★루프를 닫으면 promote의 '앱 슬라이스 통째 교체'가 **정본을 지운다**.

    2회차에는 이미 정본인 개념을 추출기가 그 anchor로 겨냥한다 → merged → auto_fold.
    auto_fold는 disposition이 아니므로 `out["concepts"]`에 안 들어가고, 슬라이스 교체
    방식이면 그 개념이 스택에서 **사라진다**. 즉 P1-a만 하고 여기를 안 고치면 루프를
    닫는 행위 자체가 정본 삭제가 된다.

    그래서 promote는 교체가 아니라 **anchor 기준 병합**이다: 새 판정분은 덮어쓰고,
    이번에 재관측된 것도 못 본 것도 남긴다. 정본에서 개념이 빠지는 유일한 경로는
    tombstone(명시적 removed_at)이다 — 조용한 소실 금지.
    """
    import yaml
    base, stack_path = _promote_fixture(tmp_path, [])
    yaml.safe_dump({"queue": [], "auto_fold": [{"sid": "a#x", "target": "napp#sc-kept"}]},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"meta": {},
                    "concepts": [{"anchor": "napp#sc-kept", "name": "재관측됨", "scope": "s"},
                                 {"anchor": "napp#sc-unseen", "name": "이번엔 안 보임", "scope": "s"},
                                 {"anchor": "other#sc-z", "name": "타 앱", "scope": "s"}],
                    "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack_path, "w"), allow_unicode=True)
    sa.run_promote(base, "napp", stack_path, app_scope="neomart/napp")
    got = {c["anchor"] for c in yaml.safe_load(open(stack_path))["concepts"]}
    assert got == {"napp#sc-kept", "napp#sc-unseen", "other#sc-z"}   # 아무것도 안 사라진다


def test_promote_stamps_last_seen_from_manifest_snapshot(tmp_path):
    """promote가 스냅샷 SHA를 manifest에서 읽어 재관측을 정본에 새긴다(다리 배선)."""
    import yaml
    base, stack_path = _promote_fixture(tmp_path, [])
    yaml.safe_dump({"snap": "aa0a005"}, open(base / "extract-manifest.yaml", "w"))
    yaml.safe_dump({"queue": [], "auto_fold": [{"sid": "a#sc-1", "target": "napp#sc-known"}]},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"meta": {}, "concepts": [{"anchor": "napp#sc-known", "name": "K",
                                              "scope": "neomart/napp"}],
                    "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack_path, "w"), allow_unicode=True)
    sa.run_promote(base, "napp", stack_path, app_scope="neomart/napp")
    got = yaml.safe_load(open(stack_path))["concepts"]
    assert got[0]["last_seen"] == "aa0a005"
    assert len(got) == 1                              # 갱신이지 추가가 아니다


def test_app_scopes_declared_in_registry_not_code():
    """★앱→정본 scope는 **데이터 선언**이다 — 엔진은 앱 이름을 모른다(registry 원칙).

    그동안 이 매핑은 depth_promote.APP_SCOPE에 일부 앱만 하드코딩돼 있어, 나머지
    앱은 promote 자체가 불가능했다(하위개념 대부분이 편입되지 못한 진짜 이유)."""
    from corpus import app_scopes_for
    m = app_scopes_for("acme-docs")
    assert m["cargo"] == "prime-commerce/cargo/crate-platform"   # slug 불일치
    assert m["consolebuilder"] == "prime-commerce/summit/console-builder"  # slug 불일치
    assert m["crate"] == "prime-commerce/atlas/crate"          # 동명 앱 — 선언으로 확정
    assert m["hub"] == "prime-commerce/summit/hub"
    assert m["neomart-billing"] == "neomart/billing"
    assert app_scopes_for("없는-코퍼스") == {}                        # 미선언은 빈 맵


def test_prior_anchor_hints_are_derived_from_previous_sections():
    """★anchor 연속성 — 재추출 섹션마다 '지난 회차에 이 섹션에서 나온 개념'을 유도한다.

    귀속은 지어내지 않는다 — quote 역조회다. §8 왕복 게이트가 "quote ⊂ 섹션 원문"을
    이미 강제하므로 **이전** 섹션 원문에서 되찾는 것은 결정론이다.
    quote가 이전 섹션 어디에도 없는(이미 낡은) 개념은 힌트에서 빠진다 — 없는 계보를
    만들어내지 않는다."""
    prev_secs = [{"anchor": "sec-a", "text": "DevSpace 상태 정책은 이러하다"},
                 {"anchor": "sec-b", "text": "다른 섹션"}]
    prev_subs = [{"anchor": "sc-devspace-status-policy", "name": "DevSpace 상태 정책",
                  "quote": "DevSpace 상태 정책은"},
                 {"anchor": "sc-stale", "name": "낡음", "quote": "어디에도 없는 문장"}]
    hints = sa.prior_anchor_hints(prev_subs, prev_secs)
    assert hints == {"sec-a": [{"anchor": "sc-devspace-status-policy",
                                "name": "DevSpace 상태 정책"}]}
    assert "sec-b" not in hints          # 개념이 안 나온 섹션은 키 자체가 없다


def test_prep_manifest_carries_prior_anchors_for_reextracted_sections(tmp_path):
    """힌트는 재추출 대상 섹션에만 실린다(이월 섹션은 재추출 안 하므로 불필요) —
    추출 에이전트가 읽는 유일한 영속 신호가 extract-manifest다."""
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "sec-a", "text": "바뀐 본문 DevSpace 상태"},
                                 {"anchor": "sec-b", "text": "그대로"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    prev_secs = [{"anchor": "sec-a", "text": "옛 본문 DevSpace 상태"},
                 {"anchor": "sec-b", "text": "그대로"}]
    prev_subs = [{"anchor": "sc-old-name", "name": "N", "quote": "옛 본문 DevSpace"}]

    sa.run_prep(tmp_path, "a", [], prev_sections=prev_secs, snap="sha1",
                prev_subconcepts=prev_subs)
    man = yaml.safe_load(open(tmp_path / "extract-manifest.yaml"))
    assert man["to_extract"] == ["sec-a"] and man["carried"] == ["sec-b"]
    assert man["prior_anchors"] == {"sec-a": [{"anchor": "sc-old-name", "name": "N"}]}


def test_removed_sections_flow_from_prep_to_stack_as_tombstone(tmp_path):
    """★삭제 경로 e2e — 섹션이 사라지면 prep이 증거를 남기고, fold가 tombstone으로 접고,
    promote가 정본에 removed_at으로 표시한다. 세 다리가 다 있어야 '삭제됨 표시'가 성립한다."""
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    prev = tmp_path / "prev"; prev.mkdir()

    # 1회차: 섹션 둘. 2회차: s2가 문서에서 사라짐.
    prev_secs = [{"anchor": "s1", "text": "살아있는 문장"},
                 {"anchor": "s2", "text": "지워질 문장"}]
    now_secs = [{"anchor": "s1", "text": "살아있는 문장"}]
    for d, secs in ((prev, prev_secs), (base, now_secs)):
        yaml.safe_dump({"sections": secs}, open(d / "sections.yaml", "w"), allow_unicode=True)

    plan, _ = sa.run_prep(base, "a", [], prev_sections=prev_secs, snap="aa0a005")
    assert [s["anchor"] for s in plan["removed"]] == ["s2"]
    ev = yaml.safe_load(open(base / "removed-sections.yaml"))
    assert ev["at"] == "aa0a005"
    assert ev["sections"][0]["text"] == "지워질 문장"     # 원문 증거 보존(이름만 적지 않는다)

    # 1회차 산출(개념 둘) — s2에서 온 sc-gone은 이번 회차 추출에 없다
    for d, subs, props in (
        (prev, [{"anchor": "sc-live", "name": "L", "quote": "살아있는 문장"},
                {"anchor": "sc-gone", "name": "G", "quote": "지워질 문장"}],
         [{"sid": "a#sc-live", "target": "NEW"}, {"sid": "a#sc-gone", "target": "NEW"}]),
        (base, [{"anchor": "sc-live", "name": "L", "quote": "살아있는 문장"}],
         [{"sid": "a#sc-live", "target": "NEW"}])):
        yaml.safe_dump({"subconcepts": subs}, open(d / "subconcepts.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"proposals": props}, open(d / "align-proposals.yaml", "w"),
                       allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"), allow_unicode=True)

    sa.run_fold(base, "a", prev_dir=prev)
    adj = yaml.safe_load(open(base / "adjudication.yaml"))
    assert [t["sid"] for t in adj["tombstones"]] == ["a#sc-gone"]
    # ★핵심: 삭제가 게이트 실패로 배치를 막지 않는다 — 살아있는 개념은 그대로 통과
    assert adj["stats"]["quote_gate"] == {"ok": 1, "rejected": 0}

    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    sa.run_promote(base, "a", stack, app_scope="x/y/a")
    got = {c["anchor"]: c for c in yaml.safe_load(open(stack))["concepts"]}
    assert got["a#sc-gone"]["removed_at"] == "aa0a005"   # 지워지지 않고 표시됨
    assert "removed_at" not in got["a#sc-live"]


def _promote_fixture(tmp_path, queue):
    import yaml
    base = tmp_path / "probe"; base.mkdir()
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-p", "name": "P", "quote": "q",
                    "commitment": "hypothesis", "confidence": "low"}]},
                   open(base / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"queue": queue, "carried": []},
                   open(base / "adjudication.yaml", "w"), allow_unicode=True)
    stack = tmp_path / "depth-stack.yaml"
    yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                    "held": {"candidate": [], "ambiguous": [], "gap": []}},
                   open(stack, "w"), allow_unicode=True)
    return base, stack


def test_run_promote_auto_adopts_unjudged_by_default(tmp_path):
    """★계약 개정 — promote 기본값이 자동 편입이다(구 계약: 판정 완료분만).
    미판정 new는 사람을 기다리지 않고 document_stated로 편입된다."""
    import yaml
    base, stack = _promote_fixture(
        tmp_path, [{"sid": "napp#sc-p", "was": "new", "target": "NEW"}])
    sa.run_promote(base, "napp", stack, app_scope="neomart/napp")
    saved = yaml.safe_load(open(stack))
    assert [c["anchor"] for c in saved["concepts"]] == ["napp#sc-p"]
    assert saved["concepts"][0]["basis"] == "document_stated"


def test_run_promote_owner_only_still_skips_unjudged(tmp_path):
    """옵트아웃(auto_adopt=False)은 구 계약 그대로 — 판정 완료분만. 되돌릴 길을 남긴다."""
    import yaml
    base, stack = _promote_fixture(
        tmp_path, [{"sid": "napp#sc-p", "was": "new", "target": "NEW"}])
    sa.run_promote(base, "napp", stack, app_scope="neomart/napp", auto_adopt=False)
    assert yaml.safe_load(open(stack))["concepts"] == []


def test_run_promote_never_auto_adopts_gate_failures(tmp_path):
    """자동 편입에도 뚫리면 안 되는 선 — 왕복 게이트 실패분은 사람 판정 없이 정본에
    못 들어간다(원문에 없는 말 = 지어냄). 자동화의 유일한 예외다."""
    import yaml
    base, stack = _promote_fixture(tmp_path, [
        {"sid": "napp#sc-p", "was": "quote_gate_failed", "quote_gate_failed": True}])
    sa.run_promote(base, "napp", stack, app_scope="neomart/napp")
    assert yaml.safe_load(open(stack))["concepts"] == []


def test_run_prep_writes_slim_canon_context(tmp_path):
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "StoreType"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    snap = [{"anchor": "StoreType", "kind": "state_enum", "scope": "x/y/z",
             "content": "긴 " * 200, "table": [["큰", "표"]], "refs": {"a": [1]}}]
    sa.run_prep(tmp_path, "x/y/other", snap)
    saved = yaml.safe_load(open(tmp_path / "canon-context.yaml"))["canon"]
    assert saved and set(saved[0]) <= {"anchor", "kind", "scope", "name", "section", "head"}
    assert "table" not in saved[0] and "refs" not in saved[0]   # 무거운 필드 제거
    assert len(saved[0]["head"]) <= 120


# ── Task 10: prep 영속화 + §8 게이트 배선 ──────────────────────────────────

def test_run_prep_writes_manifest_and_canon_context(tmp_path):
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "StoreType"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    plan, cost = sa.run_prep(tmp_path, "x/y/z", [])
    m = yaml.safe_load(open(tmp_path / "extract-manifest.yaml"))
    assert m["to_extract"] == ["s1"] and m["carried"] == [] and m["removed"] == []
    assert (tmp_path / "canon-context.yaml").exists()
    assert cost["tier_b_calls"] == 1


def test_run_prep_incremental_writes_carried_to_manifest(tmp_path):
    import yaml
    yaml.safe_dump({"sections": [
        {"anchor": "s1", "text": "바뀐 내용"},
        {"anchor": "s2", "text": "안 바뀐 내용"}]},
        open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    prev_path = tmp_path / "prev-sections.yaml"
    yaml.safe_dump({"sections": [
        {"anchor": "s1", "text": "옛 내용"},
        {"anchor": "s2", "text": "안 바뀐 내용"}]},
        open(prev_path, "w"), allow_unicode=True)
    prev_sections = yaml.safe_load(open(prev_path))["sections"]
    sa.run_prep(tmp_path, "x/y/z", [], prev_sections=prev_sections)
    m = yaml.safe_load(open(tmp_path / "extract-manifest.yaml"))
    assert m["to_extract"] == ["s1"]
    assert m["carried"] == ["s2"]
    assert m["removed"] == []


def test_run_prep_records_canon_anchor_collisions(tmp_path):
    """★실데이터 결함: 정본 anchor는 스코프 간 유일하지 않아 주입 시 조용히
    소실된다(mango 제품군 298 → distinct 245). canon-context.yaml은 anchor당 1행이라
    소실 자체는 불가피하나, **무엇이 사라졌는지 기록이 없으면 아무도 모른다** →
    canon-collisions.yaml로 영속화."""
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "본문"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    # 앱 단위 좁히기 이후 형제 앱은 후보가 아니다 — 충돌은 앱과 하위 scope 사이.
    snap = [{"anchor": "spec§개요", "scope": "x/y/z", "content": "이 앱"},
            {"anchor": "spec§개요", "scope": "x/y/z/source", "content": "이 앱 아카이브"}]
    sa.run_prep(tmp_path, "x/y/z", snap)
    saved = yaml.safe_load(open(tmp_path / "canon-context.yaml"))["canon"]
    assert [c["scope"] for c in saved] == ["x/y/z"]           # 이 앱 것이 이김
    col = yaml.safe_load(open(tmp_path / "canon-collisions.yaml"))["collisions"]
    assert col == [{"anchor": "spec§개요", "kept_scope": "x/y/z",
                    "dropped_scopes": ["x/y/z/source"]}]


def test_merge_carried_subconcepts_prefers_new():
    new = [{"anchor": "sc-a", "quote": "새"}]
    prev = [{"anchor": "sc-a", "quote": "옛"}, {"anchor": "sc-b", "quote": "이월"}]
    out = sa.merge_carried_subconcepts(new, prev)
    assert {s["anchor"]: s["quote"] for s in out} == {"sc-a": "새", "sc-b": "이월"}
    assert [s["anchor"] for s in out] == ["sc-a", "sc-b"]     # 정렬 결정론


def test_apply_quote_gate_remaps_only_the_rejected_item_pure():
    """apply_quote_gate 순수함수 — 격리 재매핑 검증(I/O 없이).
    ★2026-08-03 개정: 구 계약은 여기서 auto_fold 전량을 막고 sc-2를 merged_blocked로
    바꿨다. 이제 검증된 sc-2는 통과한다 — 근거는 test_quote_gate_quarantines_offender_not_batch."""
    auto_fold = [{"sid": "a#sc-1"}, {"sid": "a#sc-2"}]     # sc-1=quote 거부, sc-2=검증됨
    queue = [{"sid": "a#sc-3", "was": "new"}]              # 이미 큐에 있는 무관 항목(안 건드림)
    gate = {"ok": [{"anchor": "sc-2"}], "rejected": [{"anchor": "sc-1"}]}

    auto_fold2, queue2, stat = sa.apply_quote_gate("a", auto_fold, queue, gate)

    assert auto_fold2 == [{"sid": "a#sc-2"}]                 # 격리는 sc-1만
    assert stat == {"ok": 1, "rejected": 1}
    by_sid = {q["sid"]: q for q in queue2}
    assert by_sid["a#sc-1"]["was"] == "quote_gate_failed"
    assert by_sid["a#sc-1"]["quote_gate_failed"] is True
    assert "a#sc-2" not in by_sid                            # 연좌 없음
    assert by_sid["a#sc-3"] == {"sid": "a#sc-3", "was": "new"}  # 무관 항목 불변


def test_apply_quote_gate_no_rejection_is_noop_pure():
    auto_fold = [{"sid": "a#sc-1"}]
    queue = [{"sid": "a#sc-2", "was": "new"}]
    gate = {"ok": [{"anchor": "sc-1"}], "rejected": []}

    auto_fold2, queue2, stat = sa.apply_quote_gate("a", auto_fold, queue, gate)

    assert auto_fold2 == auto_fold                           # 통과=불변
    assert queue2 == queue
    assert stat == {"ok": 1, "rejected": 0}


def test_run_fold_quote_gate_fail_closed(tmp_path):
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "실제 원문"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-1", "target": "INV-59", "confidence": "high"}]},
                   open(tmp_path / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-1", "quote": "지어낸 인용",
                    "commitment": "working", "confidence": "high"}]},
                   open(tmp_path / "subconcepts.yaml", "w"), allow_unicode=True)
    sa.run_fold(tmp_path, "a")
    saved = yaml.safe_load(open(tmp_path / "adjudication.yaml"))
    assert saved["auto_fold"] == []                            # 게이트 실패=fail-closed
    assert any(q.get("was") == "quote_gate_failed" for q in saved["queue"])
    assert saved["stats"]["quote_gate"]["rejected"] == 1


def test_run_fold_quote_gate_passes_verbatim(tmp_path):
    import yaml
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "실제 원문"}]},
                   open(tmp_path / "sections.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-1", "target": "INV-59", "confidence": "high"}]},
                   open(tmp_path / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-1", "quote": "실제 원문",
                    "commitment": "working", "confidence": "high"}]},
                   open(tmp_path / "subconcepts.yaml", "w"), allow_unicode=True)
    sa.run_fold(tmp_path, "a")
    saved = yaml.safe_load(open(tmp_path / "adjudication.yaml"))
    assert [m["sid"] for m in saved["auto_fold"]] == ["a#sc-1"]   # 게이트 통과=정상 fold
    assert saved["stats"]["quote_gate"]["rejected"] == 0
    assert saved["stats"]["quote_gate"]["ok"] == 1


def test_run_fold_quote_gate_skips_without_sections(tmp_path):
    import yaml
    yaml.safe_dump({"proposals": [{"sid": "a#sc-1", "target": "INV-59", "confidence": "high"}]},
                   open(tmp_path / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-1"}]},
                   open(tmp_path / "subconcepts.yaml", "w"), allow_unicode=True)
    sa.run_fold(tmp_path, "a")
    saved = yaml.safe_load(open(tmp_path / "adjudication.yaml"))
    assert saved["stats"]["quote_gate"] == "skipped(no sections)"   # 조용한 통과 금지 명시
    assert [m["sid"] for m in saved["auto_fold"]] == ["a#sc-1"]     # sections 없으면 정상 fold


def test_merge_carried_drops_superseded_by_changed_section():
    """★실 2회차가 드러낸 최대 결함 — 무상태 재추출은 같은 개념에 **다른 anchor**를
    붙인다(실측 anchor 연속성이 매우 낮았다). anchor 기준 이월은 그래서 갱신이 아니라 **중복**을
    만든다: 바뀐 섹션의 낡은 개념이 새 개념과 나란히 살아남는다.
    귀속은 지어내지 않고 결정론으로 가능하다 — quote는 §8 왕복 게이트상 어느 섹션 원문의
    부분문자열이어야 하므로, quote가 속한 섹션이 곧 출처다. 그 섹션이 재추출 대상이면
    이월분은 **대체된 것**으로 보고 버린다."""
    # 실측 다수 패턴: 섹션은 바뀌었지만 낡은 개념의 quote 문장 자체는 살아남는다
    # (변경이 '근거' 줄에 국소적) → 왕복 게이트로는 안 잡히고 중복만 남는다.
    prev = [{"anchor": "sc-old-identity", "quote": "학습·개발·평가를 담당한다"},
            {"anchor": "sc-untouched", "quote": "안 바뀐 섹션 문장"}]
    new = [{"anchor": "sc-new-identity", "quote": "분리 재편(`MEADOW-D-6271`)"}]
    sections = [{"anchor": "spec#identity",
                 "text": "학습·개발·평가를 담당한다. 분리 재편(`MEADOW-D-6271`)으로 합쳤다"},
                {"anchor": "spec#other", "text": "안 바뀐 섹션 문장 이다"}]
    out = sa.merge_carried_subconcepts(new, prev, sections=sections,
                                       changed_anchors={"spec#identity"})
    assert [s["anchor"] for s in out] == ["sc-new-identity", "sc-untouched"]


def test_merge_carried_without_section_info_is_unchanged_behavior():
    """sections/changed 미지정이면 기존 계약(anchor 기준 전량 이월) 그대로 — backward-compat."""
    prev = [{"anchor": "sc-a", "quote": "옛"}, {"anchor": "sc-b", "quote": "이월"}]
    new = [{"anchor": "sc-a", "quote": "새"}]
    out = sa.merge_carried_subconcepts(new, prev)
    assert [s["anchor"] for s in out] == ["sc-a", "sc-b"]


def test_merge_carried_keeps_prev_when_quote_owner_unknown():
    """quote가 어느 섹션에도 없으면(이미 낡음) 임의 삭제하지 않는다 — 왕복 게이트가
    fail-closed로 잡게 남긴다(조용한 소실 금지)."""
    prev = [{"anchor": "sc-stale", "quote": "어느 섹션에도 없는 문장"}]
    sections = [{"anchor": "s1", "text": "전혀 다른 내용"}]
    out = sa.merge_carried_subconcepts([], prev, sections=sections, changed_anchors={"s1"})
    assert [s["anchor"] for s in out] == ["sc-stale"]


def test_merge_carried_proposals_prefers_new_and_drops_orphans():
    """증분 fold의 두 번째 이월 축 — 이전 align-proposals도 이월해야 한다.
    ★실 2회차가 드러낸 갭: 재추출 에이전트는 바뀐 섹션의 proposal만 낸다.
    subconcept만 이월하면 이월분이 전부 '미제안(누락)' error → fail-closed로 전 배치가
    막힌다. sid 기준 새 것 우선, 병합된 subconcept 명단 밖 sid는 버린다(phantom 방지)."""
    new = [{"sid": "app#sc-a", "target": "INV-1", "confidence": "high"}]
    prev = [{"sid": "app#sc-a", "target": "OLD", "confidence": "high"},
            {"sid": "app#sc-b", "target": "INV-2", "confidence": "high"},
            {"sid": "app#sc-gone", "target": "INV-9", "confidence": "high"}]
    subs = [{"anchor": "sc-a"}, {"anchor": "sc-b"}]
    out = sa.merge_carried_proposals(new, prev, subs, "app")
    assert [p["sid"] for p in out] == ["app#sc-a", "app#sc-b"]     # 정렬 결정론
    assert out[0]["target"] == "INV-1"                             # 재추출분 우선


def test_run_fold_prev_dir_carries_subconcepts_and_proposals(tmp_path):
    """run_fold(prev_dir=...) = 증분 뒷단 배선. 이전 회차 산출(subconcepts+proposals)을
    이월해 전건 fold — 재추출 안 된 개념이 조용히 사라지지도, 누락 error를 내지도 않는다."""
    import yaml
    prev = tmp_path / "r1"; prev.mkdir()
    cur = tmp_path / "r2"; cur.mkdir()
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "A 원문"},
                                 {"anchor": "s2", "text": "B 원문"}]},
                   open(cur / "sections.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "quote": "A 원문"},
                                    {"anchor": "sc-b", "quote": "B 원문"}]},
                   open(prev / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-a", "target": "INV-1", "confidence": "high"},
                                  {"sid": "a#sc-b", "target": "INV-2", "confidence": "high"}]},
                   open(prev / "align-proposals.yaml", "w"), allow_unicode=True)
    # 2회차: sc-a만 재추출
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "quote": "A 원문"}]},
                   open(cur / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-a", "target": "INV-1", "confidence": "high"}]},
                   open(cur / "align-proposals.yaml", "w"), allow_unicode=True)

    sa.run_fold(cur, "a", prev_dir=prev)
    saved = yaml.safe_load(open(cur / "adjudication.yaml"))
    assert saved["stats"]["errors"] == 0                       # 이월분 누락 error 0
    assert [m["sid"] for m in saved["auto_fold"]] == ["a#sc-a", "a#sc-b"]
    assert saved["stats"]["carried_inputs"]["subconcepts"] == 1
    assert saved["stats"]["carried_inputs"]["proposals"] == 1


def test_run_fold_prev_dir_carries_prior_dispositions(tmp_path):
    """판정 이월의 세 번째 축 — 회차 디렉토리가 분리되면(r1/r2) 이전 회차 `adjudication.yaml`의
    **소유자 판정**이 따라오지 않아 재판정을 요구하게 된다. prev_dir이 있으면 판정도 이월한다
    (같은 sid는 현 회차가 우선). 실 2회차에서 드러난 갭 — 다만 그 회차엔 소유자
    판정 자체가 0건이라 실 이월 수는 0이었다."""
    import yaml
    prev = tmp_path / "r1"; prev.mkdir()
    cur = tmp_path / "r2"; cur.mkdir()
    yaml.safe_dump({"queue": [{"sid": "a#sc-gone", "was": "new",
                               "disposition": "candidate"}],
                    "carried": []},
                   open(prev / "adjudication.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": []}, open(prev / "subconcepts.yaml", "w"))
    yaml.safe_dump({"proposals": []}, open(prev / "align-proposals.yaml", "w"))
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-a", "quote": "A"}]},
                   open(cur / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-a", "target": "T", "confidence": "high"}]},
                   open(cur / "align-proposals.yaml", "w"), allow_unicode=True)

    sa.run_fold(cur, "a", prev_dir=prev)
    saved = yaml.safe_load(open(cur / "adjudication.yaml"))
    assert [c["sid"] for c in saved["carried"]] == ["a#sc-gone"]   # 판정 이월(재판정 0)


def test_run_fold_supersedes_prev_concepts_from_reextracted_sections(tmp_path):
    """run_fold가 extract-manifest.to_extract를 읽어 대체 판정까지 수행한다 —
    재추출 섹션에서 온 이전 개념은 이월하지 않는다(중복 방지). 원장에 superseded 기록."""
    import yaml
    prev = tmp_path / "r1"; prev.mkdir()
    cur = tmp_path / "r2"; cur.mkdir()
    yaml.safe_dump({"sections": [{"anchor": "s1", "text": "바뀐 섹션 공통 문장 새 근거"},
                                 {"anchor": "s2", "text": "안 바뀐 섹션"}]},
                   open(cur / "sections.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"to_extract": ["s1"], "carried": ["s2"], "removed": []},
                   open(cur / "extract-manifest.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-old", "quote": "바뀐 섹션 공통 문장"},
                                    {"anchor": "sc-keep", "quote": "안 바뀐 섹션"}]},
                   open(prev / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-old", "target": "T1", "confidence": "high"},
                                  {"sid": "a#sc-keep", "target": "T2", "confidence": "high"}]},
                   open(prev / "align-proposals.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-new", "quote": "새 근거"}]},
                   open(cur / "subconcepts.yaml", "w"), allow_unicode=True)
    yaml.safe_dump({"proposals": [{"sid": "a#sc-new", "target": "T1", "confidence": "high"}]},
                   open(cur / "align-proposals.yaml", "w"), allow_unicode=True)

    sa.run_fold(cur, "a", prev_dir=prev)
    saved = yaml.safe_load(open(cur / "adjudication.yaml"))
    assert [m["sid"] for m in saved["auto_fold"]] == ["a#sc-keep", "a#sc-new"]  # sc-old 대체
    assert saved["stats"]["carried_inputs"]["superseded"] == 1


def test_incremental_merge_equals_full_extraction_for_fold():
    """§8 불변식 — merge_carried_subconcepts 거친 증분 입력이 전체 재추출과 fold_plan에서
    동일 산출을 낸다(안 바뀐 섹션의 subconcept가 조용히 사라지지 않음)."""
    full_subs = [{"anchor": "sc-a", "quote": "A 원문", "name": "A"},
                 {"anchor": "sc-b", "quote": "B 원문", "name": "B"}]
    proposals = [{"sid": "app#sc-a", "target": "INV-1", "confidence": "high"},
                 {"sid": "app#sc-b", "target": "INV-2", "confidence": "high"}]
    idx = {"INV-1", "INV-2"}
    full_out = sa.fold_plan("app", proposals, full_subs, idx)

    # 증분: sc-a만 재추출(결정론이라 결과 동일), sc-b는 carried(이전 fold 입력에서 이월)
    new_subs = [{"anchor": "sc-a", "quote": "A 원문", "name": "A"}]
    prev_subs = [{"anchor": "sc-a", "quote": "A 원문", "name": "A"},
                 {"anchor": "sc-b", "quote": "B 원문", "name": "B"}]
    merged_subs = sa.merge_carried_subconcepts(new_subs, prev_subs)
    inc_out = sa.fold_plan("app", proposals, merged_subs, idx)

    assert merged_subs == full_subs
    assert inc_out["auto_fold"] == full_out["auto_fold"]
    assert inc_out["adjudication_queue"] == full_out["adjudication_queue"]


# ── Task 11: S0 ingest — 새 앱 sections.yaml 기계 생성 초안 (마지막 다리) ──────────

def test_run_ingest_produces_probe_sections_schema():
    md = "## 개요\n\n한 줄 정체성.\n\n## 범위\n\n포함 A."
    secs = sa.run_ingest([("spec.md", md)], "x/y/z")
    assert all(set(s) >= {"anchor", "doc", "text"} for s in secs)
    assert secs[0]["doc"] == "spec.md"
    assert "한 줄 정체성" in secs[0]["text"]          # verbatim
    assert len(secs) == 2


def test_run_ingest_anchor_unique_across_docs():
    md = "## 개요\n\n내용."
    secs = sa.run_ingest([("a.md", md), ("b.md", md)], "x")
    anchors = [s["anchor"] for s in secs]
    assert len(anchors) == len(set(anchors))          # 문서 간 충돌 없음


def test_run_ingest_preserves_document_order():
    md = "## 셋째로 정의\n\nc.\n\n## 첫째로 정의\n\na."
    secs = sa.run_ingest([("spec.md", md)], "x")
    assert [("셋째" in s["text"], "첫째" in s["text"]) for s in secs] == [(True, False), (False, True)]
    # 등장 순서 보존(사전순 정렬 금지)


def test_run_ingest_cli_refuses_overwrite(tmp_path):  # 수기 저작물 보호
    import yaml
    src = tmp_path / "src"; src.mkdir()
    (src / "spec.md").write_text("## 개요\n\n내용.", encoding="utf-8")
    out_dir = tmp_path / "probe"; out_dir.mkdir()
    yaml.safe_dump({"sections": [{"anchor": "manual", "doc": "d.md", "text": "수기 저작"}]},
                   open(out_dir / "sections.yaml", "w"), allow_unicode=True)

    with pytest.raises(SystemExit):
        sa.run_ingest_cli(tmp_path, "src", out_dir, "x")   # 기존 파일 보호
    still = yaml.safe_load(open(out_dir / "sections.yaml"))
    assert still["sections"][0]["anchor"] == "manual"       # 안 덮임

    sa.run_ingest_cli(tmp_path, "src", out_dir, "x", force=True)   # --force만 허용
    overwritten = yaml.safe_load(open(out_dir / "sections.yaml"))
    assert overwritten["sections"][0]["anchor"] != "manual"  # 덮임


def test_run_ingest_empty_source_yields_no_sections():
    assert sa.run_ingest([("e.md", "")], "x") == []


def test_run_ingest_whitespace_only_source_yields_no_sections():
    assert sa.run_ingest([("w.md", "   \n\n  \n")], "x") == []


def test_run_ingest_headingless_doc_becomes_single_preamble_section():
    secs = sa.run_ingest([("n.md", "그냥 본문입니다.\n둘째 줄.")], "x")
    assert len(secs) == 1
    assert secs[0]["anchor"] == "n#_preamble"
    assert secs[0]["text"] == "그냥 본문입니다.\n둘째 줄."   # verbatim


def test_run_ingest_cli_reads_nested_md_recursively(tmp_path):
    import yaml
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "top.md").write_text("## A\n\ntop.", encoding="utf-8")
    (src / "sub" / "nested.md").write_text("## B\n\nnested.", encoding="utf-8")
    out_dir = tmp_path / "probe"
    secs = sa.run_ingest_cli(tmp_path, "src", out_dir, "x")
    docs = {s["doc"] for s in secs}
    assert docs == {"src/top.md", "src/sub/nested.md"}      # source_root 기준 상대경로
    saved = yaml.safe_load(open(out_dir / "sections.yaml"))
    assert len(saved["sections"]) == 2


def test_auto_adopt_promotes_gate_passed_items_without_owner_judgment():
    """★계약 개정(소유자, 2026-08-03): 사람 판정은 편입의 **사전 게이트가 아니라 사후 리뷰**다.

    근거 — 문서 자체가 이미 사람 판정이 들어간 산출물이다. 왕복 게이트(quote ⊂ 원문)를
    통과했다는 건 "문서에 실제로 그렇게 쓰여 있다"는 뜻이고, 거기까지가 기계가 아는 전부다.
    그래서 자동 disposition은 소유자 4정책(new_decision/new_code_only/…) 중 하나를 고르지
    않는다 — 그건 '왜 새로운가'라는 의미 판정이라 지어내는 셈이 된다. 대신 중립 basis
    `document_stated`를 쓴다(주장 = 문서가 그렇게 말한다, 그 이상 아님).

    경계: 게이트 실패분(quote_gate_failed·merged_blocked)은 자동 편입하지 않는다 —
    원문에 없는 말 = 지어냄 위험이고, 그것만이 여전히 사람 몫이다."""
    saved = {"queue": [
        {"sid": "a#sc-new", "was": "new", "target": "NEW"},
        {"sid": "a#sc-amb", "was": "ambiguous", "target": "AMBIGUOUS"},
        {"sid": "a#sc-bad", "was": "quote_gate_failed", "quote_gate_failed": True},
        {"sid": "a#sc-blocked", "was": "merged_blocked"},
        {"sid": "a#sc-owner", "was": "new", "disposition": "new_decision"},
    ]}
    subs = [{"anchor": f"sc-{k}", "name": k, "quote": "q"}
            for k in ("new", "amb", "bad", "blocked", "owner")]
    rows = {r["sid"]: r for r in sa.build_dispositions(saved, subs, "a", auto_adopt=True)}

    assert rows["a#sc-new"]["disposition"] == "auto_adopt"
    assert rows["a#sc-amb"]["disposition"] == "auto_adopt"
    assert rows["a#sc-amb"]["needs_review"] is True      # 편입하되 사후 리뷰 표시
    assert "needs_review" not in rows["a#sc-new"]
    assert rows["a#sc-owner"]["disposition"] == "new_decision"   # 소유자 판정이 이김
    assert "a#sc-bad" not in rows and "a#sc-blocked" not in rows  # 게이트 실패는 사람 몫

    # auto_adopt=False(기본)면 종전대로 판정 완료분만 — 기존 운영 무영향
    assert [r["sid"] for r in sa.build_dispositions(saved, subs, "a")] == ["a#sc-owner"]


def test_auto_adopt_node_declares_document_stated_basis_and_review_flag():
    """자동 편입 node는 근거를 정직하게 남긴다 — basis=document_stated(문서 진술),
    needs_review는 스택까지 관통해 사후 리뷰 대상 목록이 스택 안에서 구성되게 한다."""
    import depth_promote as dp
    subs = [{"anchor": "sc-amb", "name": "X", "quote": "q",
             "commitment": "working", "confidence": "high"}]
    rows = [{"sid": "a#sc-amb", "app": "a", "name": "X", "was": "ambiguous",
             "disposition": "auto_adopt", "needs_review": True}]
    out = dp.fold_depth({"dispositions": rows},
                        {"a": {"subconcepts": subs, "relations": []}},
                        app_scopes={"a": "x/y/a"})
    node = out["concepts"][0]
    assert node["basis"] == "document_stated"
    assert node["needs_review"] is True
    assert node["scope"] == "x/y/a" and node["kind"] == "concept"
    assert out["bodies"]["a#sc-amb"] == [{"key": "quote", "text": "q"}]


def test_gate_failed_audit_trail_survives_to_stack(tmp_path):
    import yaml, depth_promote as dp
    saved = {"queue": [{"sid": "a#sc-1", "was": "quote_gate_failed", "target": "NEW",
                        "quote_gate_failed": True, "disposition": "new_code_only"}]}
    subs = [{"anchor": "sc-1", "name": "X", "quote": "q", "commitment": "hypothesis",
             "confidence": "low"}]
    rows = sa.build_dispositions(saved, subs, "a")
    assert rows[0]["quote_gate_failed"] is True                      # 다리에서 보존
    out = dp.fold_depth({"dispositions": rows},
                        {"a": {"subconcepts": subs, "relations": []}},
                        app_scopes={"a": "x/y/a"})
    assert out["concepts"][0]["quote_gate_failed"] is True           # 스택 node까지 관통


def test_force_extract_keeps_lineage_hints(tmp_path):
    """★재추출 모드 — 문서가 안 바뀌어도 전건 추출하되 `prior_anchors`는 준다."""
    import yaml
    sections = [{"anchor": "s1", "doc": "d", "text": "상품은 카테고리에 속한다"}]
    yaml.safe_dump({"sections": sections}, open(tmp_path / "sections.yaml", "w"),
                   allow_unicode=True)
    prev = tmp_path / "prev"
    prev.mkdir()
    yaml.safe_dump({"sections": sections}, open(prev / "sections.yaml", "w"),
                   allow_unicode=True)
    yaml.safe_dump({"subconcepts": [{"anchor": "sc-user", "name": "Item",
                                     "quote": "상품은 카테고리에 속한다"}]},
                   open(prev / "subconcepts.yaml", "w"), allow_unicode=True)
    prev_secs = yaml.safe_load(open(prev / "sections.yaml"))["sections"]
    prev_subs = yaml.safe_load(open(prev / "subconcepts.yaml"))["subconcepts"]

    # 평시: 같은 섹션 → 재추출 0(비용 목표)
    sa.run_prep(tmp_path, "x/inv", [], prev_sections=prev_secs,
                prev_subconcepts=prev_subs, snap="s")
    man = yaml.safe_load(open(tmp_path / "extract-manifest.yaml"))
    assert man["to_extract"] == [] and man["carried"] == ["s1"]

    # 강제: 전건 추출 + 계보 힌트 유지
    sa.run_prep(tmp_path, "x/inv", [], prev_sections=prev_secs,
                prev_subconcepts=prev_subs, snap="s", force_extract=True)
    man = yaml.safe_load(open(tmp_path / "extract-manifest.yaml"))
    assert man["to_extract"] == ["s1"] and man["carried"] == []
    assert man["prior_anchors"]["s1"] == [{"anchor": "sc-user", "name": "Item"}]
