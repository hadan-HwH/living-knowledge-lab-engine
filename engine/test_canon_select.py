import canon_select as cs


def test_narrows_to_the_app_not_the_product_line():
    """★2026-08-04 동작 변경: 제품군(2세그먼트) → **앱 단위**."""
    canon = [{"anchor": "meadow#a", "name": "A", "scope": "prime-commerce/meadow/meadow"},
             {"anchor": "admin#c", "name": "C", "scope": "prime-commerce/meadow/meadow-admin"},
             {"anchor": "inv#b", "name": "B", "scope": "prime-commerce/summit/inv"}]
    out = cs.select_canon("prime-commerce/meadow/meadow-admin", [], canon)
    got = {c["anchor"] for c in out}
    assert got == {"admin#c"}                        # 이 앱만 (형제 meadow도 제외)


def test_includes_shared_foundations():
    canon = [{"anchor": "ARCH-01", "name": "TRN", "scope": "foundations"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", [], canon)
    assert any(c["anchor"] == "ARCH-01" for c in out)


def test_includes_name_matched_cross_product():
    canon = [{"anchor": "inv#item", "name": "Item Paused",
              "scope": "prime-commerce/summit/inv"}]
    sections = [{"anchor": "s1", "text": "이 화면은 Item 상태를 보여준다"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", sections, canon)
    assert any(c["anchor"] == "inv#item" for c in out)   # 'Item' 토큰 매칭


def test_excludes_unrelated():
    canon = [{"anchor": "sec#z", "name": "Fraud Rule",
              "scope": "prime-commerce/summit/security"}]
    sections = [{"anchor": "s1", "text": "야간 배송 배치 스케줄링"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", sections, canon)
    assert out == []                                    # 제품군·foundations·이름매칭 전부 아님


def test_bounded_not_all_and_deterministic():
    canon = [{"anchor": f"inv#{i}", "name": f"Concept{i}",
              "scope": "prime-commerce/summit/inv"} for i in range(100)]
    out = cs.select_canon("prime-commerce/meadow/meadow", [], canon)
    assert len(out) < 100                               # 무관 대량 제외(비용 유한)
    assert [c["anchor"] for c in out] == sorted(c["anchor"] for c in out)  # 결정론 정렬


def test_app_scope_none_is_safe():
    canon = [{"anchor": "a", "name": "N", "scope": "prime-commerce/meadow/meadow"}]
    assert cs.select_canon(None, [], canon) == []   # 크래시 없이 빈 결과


def test_descriptive_name_tail_does_not_overmatch():
    canon = [{"anchor": "x#p", "name": "Store 컨텍스트 (INV 소유 — 진열 구역 경계)",
              "scope": "prime-commerce/summit/inv"}]
    secs = [{"anchor": "s1", "text": "이 앱은 진열 구역이 필요하다"}]  # 괄호 꼬리 단어만 겹침
    assert cs.select_canon("prime-commerce/meadow/meadow", secs, canon) == []


def test_identifier_head_still_matches():
    canon = [{"anchor": "x#p", "name": "Store 컨텍스트 (INV 소유)",
              "scope": "prime-commerce/summit/inv"}]
    secs = [{"anchor": "s1", "text": "Store 단위로 귀속된다"}]     # 머리 식별자 겹침
    assert [c["anchor"] for c in cs.select_canon("prime-commerce/meadow/meadow", secs, canon)] == ["x#p"]


def test_scope_prefix_respects_segment_boundary():
    canon = [{"anchor": "m2#a", "name": "A", "scope": "prime-commerce/meadow2/other"}]
    assert cs.select_canon("prime-commerce/meadow/meadow", [], canon) == []


def test_name_match_falls_back_to_anchor_for_snapshot_concepts():
    # 실 0a0a001 스타일: name 없음, anchor가 식별자
    canon = [{"anchor": "StoreType", "kind": "state_enum",
              "scope": "prime-commerce/summit/inv", "content": "enum..."}]
    secs = [{"anchor": "s1", "text": "StoreType 값을 조회한다"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", secs, canon)
    assert [c["anchor"] for c in out] == ["StoreType"]   # anchor 토큰 매칭


def test_anchor_fallback_requires_full_identifier_citation():
    canon = [{"anchor": "화면-01", "kind": "screen", "scope": "prime-commerce/summit/inv",
              "content": "..."},
             {"anchor": "INV-59", "kind": "article", "scope": "prime-commerce/summit/inv",
              "content": "..."}]
    secs = [{"anchor": "s1", "text": "이 화면은 01번 항목과 INV-59 조항을 따른다"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", secs, canon)
    # "화면"·"01" 토큰이 따로 있어도 "화면-01" 통째가 없으면 미매칭; "INV-59"은 통째 인용=매칭
    assert [c["anchor"] for c in out] == ["INV-59"]


def test_short_anchor_never_matches_by_substring():
    canon = [{"anchor": "gap", "kind": "gap", "scope": "prime-commerce/summit/inv",
              "content": "..."}]
    secs = [{"anchor": "s1", "text": "gap 분석을 수행한다"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", secs, canon)
    assert out == []          # len<4 anchor는 폴백 매칭 제외


def test_anchor_collision_prefers_app_scope():
    """★실데이터 결함: anchor는 스코프 간 유일하지 않다(비공개 코퍼스에서 실측 — 상당수 충돌).
    picked[anchor] 덮어쓰기는 '마지막 승'이라 대상 앱이 아닌 다른 앱(일반 앱 추출인데
    admin 앱) 레코드가 주입됐다. 같은 anchor면 app_scope에 가까운 것."""
    canon = [{"anchor": "spec§개요", "kind": "spec_section",
              "scope": "prime-commerce/mango/mango-admin", "content": "admin"},
             {"anchor": "spec§개요", "kind": "spec_section",
              "scope": "prime-commerce/mango/mango", "content": "user app"}]
    out = cs.select_canon("prime-commerce/mango/mango", [], canon)
    assert len(out) == 1
    assert out[0]["scope"] == "prime-commerce/mango/mango"


def test_anchor_collision_winner_is_order_independent():
    canon = [{"anchor": "spec§개요", "scope": "prime-commerce/mango/mango-admin/source/x"},
             {"anchor": "spec§개요", "scope": "prime-commerce/mango/mango/source/run"},
             {"anchor": "spec§개요", "scope": "prime-commerce/mango/mango-admin"}]
    app = "prime-commerce/mango/mango"
    a = cs.select_canon(app, [], canon)[0]["scope"]
    b = cs.select_canon(app, [], list(reversed(canon)))[0]["scope"]
    assert a == b == "prime-commerce/mango/mango/source/run"   # app_scope 하위가 타 앱보다 우선


def test_canon_collisions_reports_dropped_scopes():
    """침묵 소실 감시 — 어떤 anchor에서 무엇이 버려졌는지 보고(진단, 선택 동작 불변)."""
    # 앱 단위 좁히기 이후 형제 앱은 애초에 후보가 아니다 — 충돌은 이제
    # 앱과 그 **하위 scope**(source/ 아카이브 등) 사이에서 난다. 실제로 그 케이스가
    # `_scope_rank` 0 vs 1을 두려고 만든 자리다.
    canon = [{"anchor": "spec§개요", "scope": "prime-commerce/mango/mango"},
             {"anchor": "spec§개요", "scope": "prime-commerce/mango/mango/source"},
             {"anchor": "MANGO-01", "scope": "prime-commerce/mango/mango"}]
    rep = cs.canon_collisions("prime-commerce/mango/mango", [], canon)
    assert [r["anchor"] for r in rep] == ["spec§개요"]        # 충돌한 것만
    assert rep[0]["kept_scope"] == "prime-commerce/mango/mango"
    assert rep[0]["dropped_scopes"] == ["prime-commerce/mango/mango/source"]


def test_content_is_never_used_for_matching():
    canon = [{"anchor": "zzz-unrelated", "kind": "article",
              "scope": "prime-commerce/summit/inv",
              "content": "이 조항은 야간 배송 배치 스케줄링을 다룬다"}]
    secs = [{"anchor": "s1", "text": "야간 배송 배치 스케줄링"}]
    out = cs.select_canon("prime-commerce/meadow/meadow", secs, canon)
    assert out == []                                        # content 매칭 금지(과다선택 방지)
