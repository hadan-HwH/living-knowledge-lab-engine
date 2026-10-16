"""정본 주입 이원화 — Tier B는 코퍼스 전량, Tier A만 좁힌다 (소유자 결정 2026-08-04).

★소유자 원칙: **코퍼스 경계 = 제품 경계**(wevolley·acme-docs·lab). 코퍼스 안에서
앱은 provenance일 뿐 정체성 경계가 아니다."""
import unittest

from canon_select import select_canon


SECTIONS = [{"text": "이 화면은 묶음 배송을 붙인다"}]


def _a(anchor, scope):
    return {"anchor": anchor, "scope": scope, "name": None, "tier": "A"}


def _b(anchor, scope, name):
    return {"anchor": anchor, "scope": scope, "name": name, "tier": "B"}


class TestTierBIsInjectedWhole(unittest.TestCase):
    def test_other_product_family_concept_is_injected(self):
        """atlas 개념이 summit 앱 추출에 보여야 한다 — 같은 코퍼스이므로."""
        canon = [_b("courier#sc-parcel", "prime-commerce/atlas/courier", "Parcel (묶음 배송)")]
        picked = select_canon("prime-commerce/summit/inv", SECTIONS, canon)
        self.assertEqual([c["anchor"] for c in picked], ["courier#sc-parcel"])

    def test_tier_b_needs_no_name_match(self):
        """이름이 섹션과 안 겹쳐도 주입된다 — 겹칠 때만 보이면 '못 본 개념'을 또 NEW로 짓는다."""
        canon = [_b("meadow#sc-quite-unrelated", "prime-commerce/meadow/meadow", "전혀 무관한 것")]
        picked = select_canon("prime-commerce/summit/inv", SECTIONS, canon)
        self.assertEqual(len(picked), 1)

    def test_tombstoned_shape_is_not_this_layers_job(self):
        """죽은 개념 제외는 canon_store.depth_to_canon의 일 — 여기서 두 번 거르지 않는다."""
        canon = [_b("inv#sc-x", "prime-commerce/summit/inv", "X")]
        self.assertEqual(len(select_canon("prime-commerce/summit/inv", SECTIONS, canon)), 1)


class TestTierAStaysNarrow(unittest.TestCase):
    def test_other_product_family_article_is_not_injected(self):
        """조항 전량을 주입하면 수백 K자다 — 비용 때문에 좁히기를 유지한다."""
        canon = [_a("STORAGE-01", "prime-commerce/atlas/stock")]
        picked = select_canon("prime-commerce/summit/inv", SECTIONS, canon)
        self.assertEqual(picked, [])

    def test_sibling_app_article_is_no_longer_injected(self):
        """★2026-08-04 재조정: 제품군 → 앱 단위(test_canon_narrowing.py에 근거).
        3단계에서 이 테스트는 형제 앱 주입을 고정했는데, 실측으로 주입분 중 실제
        인용은 극소수였다. 좁히되 인용 경로는 그대로 둔다(아래 cited 테스트)."""
        canon = [_a("ALERT-01", "prime-commerce/summit/alert")]
        picked = select_canon("prime-commerce/summit/inv", SECTIONS, canon)
        self.assertEqual(picked, [])

    def test_cited_article_from_elsewhere_is_still_injected(self):
        """식별자를 문서가 통째로 인용하면 제품군 밖 조항도 종전대로 들어온다."""
        canon = [_a("STORAGE-01", "prime-commerce/atlas/stock")]
        picked = select_canon("prime-commerce/summit/inv",
                              [{"text": "STORAGE-01에 따라 처리한다"}], canon)
        self.assertEqual([c["anchor"] for c in picked], ["STORAGE-01"])


class TestUntieredInputIsUnchanged(unittest.TestCase):
    """tier 표시가 없는 입력(구 호출자·테스트)은 종전 동작 그대로 — 조용한 확대 금지."""

    def test_untagged_record_from_another_family_is_not_injected(self):
        canon = [{"anchor": "X-1", "scope": "prime-commerce/atlas/stock", "name": None}]
        self.assertEqual(select_canon("prime-commerce/summit/inv", SECTIONS, canon), [])


if __name__ == "__main__":
    unittest.main()
