"""왕복 게이트의 진실 원천 — 이 회차에 준 원문 **전부** (파일럿 1회차에서 드러남).

★파일럿이 드러낸 것: 추출 대상은 문서 몇 편인데 `articles.yaml`은 같은 scope 조항
전량이다. 그래서 일부 개념은 실질 본문이 조항에만 있는데 S2 `quote`는
`sections.yaml`에서만 대야 해서 **spec 표 한 줄**로 때웠다 — 개념의 인용이 개념의 실질을
못 담는다. 추출 에이전트가 계약을 지키느라 얄팍한 인용을 고르게 만드는 구조였다.

★고치는 방향(두 갈래 중 선택):
  (a) articles를 sections 범위로 좁힌다 → S3a가 볼 조항이 줄어 **축 1이 약해진다.** 기각.
  (b) 왕복 게이트의 진실 원천을 `sections ∪ articles`로 넓힌다 → 채택.

근거: 게이트의 의미는 "네가 인용한 것이 **원문에 실제로 있다**"이다. `articles.yaml`도
Tier A 스냅샷에서 그대로 뽑은 원문이지 파생물이 아니다. 좁혀야 할 이유가 없었고,
좁힌 탓에 인용 품질만 떨어뜨렸다. 지어냄 차단력은 그대로다 — 둘 다 기계가 만든 원문이라
에이전트가 내용을 지어낼 여지가 없다.
"""
import unittest

from subconcept import verify_subconcepts


SECTIONS = [{"anchor": "s1", "text": "상품은 최소 1개 카테고리에 소속되어야 한다"}]
ARTICLES = [{"anchor": "INV-13",
             "texts": [{"key": "content", "text": "Promo Code는 상품당 최대 2개까지 발급된다"},
                       {"key": "fields.근거", "text": "INV-D-7286 — 발급 상한 결정"}]}]


def _sc(quote):
    return [{"anchor": "sc-x", "name": "X", "commitment": "frozen",
             "confidence": "high", "quote": quote}]


class TestSectionsStillWork(unittest.TestCase):
    def test_quote_from_sections_passes(self):
        r = verify_subconcepts(_sc("최소 1개 카테고리에 소속"), SECTIONS)
        self.assertEqual(r["totals"]["ok"], 1)

    def test_invented_quote_still_fails(self):
        r = verify_subconcepts(_sc("완전히 지어낸 문장"), SECTIONS, articles=ARTICLES)
        self.assertEqual(r["totals"]["rejected"], 1)
        self.assertEqual(r["rejected"][0]["verdict"], "quote_not_found")


class TestArticlesAreAlsoTruth(unittest.TestCase):
    def test_quote_from_an_article_passes(self):
        """★파일럿에서 막히던 자리 — 실질 본문이 조항에만 있는 개념."""
        r = verify_subconcepts(_sc("상품당 최대 2개까지 발급"), SECTIONS, articles=ARTICLES)
        self.assertEqual(r["totals"]["ok"], 1)

    def test_without_articles_the_same_quote_fails(self):
        """넓히기 전 동작 — 회귀 방지용으로 대비를 고정한다."""
        r = verify_subconcepts(_sc("상품당 최대 2개까지 발급"), SECTIONS)
        self.assertEqual(r["totals"]["rejected"], 1)

    def test_article_field_text_counts_too(self):
        """조항의 필드(`근거` 등)도 원문이다 — governed_by 출처가 여기 산다."""
        r = verify_subconcepts(_sc("INV-D-7286 — 발급 상한"), SECTIONS, articles=ARTICLES)
        self.assertEqual(r["totals"]["ok"], 1)


class TestGovernedByProvenance(unittest.TestCase):
    """② `governed_by` 출처 — 결정 ID는 조항 `근거` 필드에 산다."""

    def test_governed_by_is_not_quote_gated(self):
        subs = [{"anchor": "sc-x", "name": "X", "commitment": "frozen",
                 "confidence": "high", "quote": "최소 1개 카테고리에 소속",
                 "governed_by": "INV-D-7286"}]
        r = verify_subconcepts(subs, SECTIONS)
        self.assertEqual(r["totals"]["ok"], 1)          # governed_by는 게이트를 안 탄다
        self.assertEqual(r["ok"][0]["governed_by"], "INV-D-7286")


if __name__ == "__main__":
    unittest.main()
