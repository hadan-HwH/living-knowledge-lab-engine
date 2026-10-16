"""층간 대조 — 같은 개념 아래 조항과 화면이 다른 값을 말하는가 (소유자 지시 2026-08-05).

★검출 원리는 축 1이 만들어준 구조를 그대로 쓴다: 개념 하나 아래 **서로 다른 층**의
조각이 모였고, 각 층이 **같은 항목에 다른 값**을 말하면 후보다.

    [article]        | Cart Hold Timeout | 45분 | 20분–2시간 | …
    [screen_section] | **Cart hold timeout** * | 분 | 25 | 10–120분 (설계) |

★**기계는 판정하지 않는다.** 어느 쪽이 맞는지는 정책·화면 두 담당자의 몫이다
(파서 주석에 이미 그렇게 적혀 있다). 검출기는 "같은 항목인데 값이 다르다"까지만 말하고
값을 나란히 보여준다. 단위 환산(2시간 vs 120분)도 기계가 맞추지 않는다 — 맞추려 들면
지어내는 셈이고, 사람이 보면 3초면 판정한다."""
import unittest

from crosscheck import crosscheck_concept, normalize_item, table_rows


class TestTableRows(unittest.TestCase):
    def test_row_is_split_into_item_and_values(self):
        rows = table_rows("| Cart Hold Timeout | 45분 | 20분–2시간 | 설명 |")
        self.assertEqual(rows, [("Cart Hold Timeout", ["45분", "20분–2시간", "설명"])])

    def test_separator_and_header_noise_is_dropped(self):
        self.assertEqual(table_rows("|---|---|\n| 항목 | 기본값 |"), [])

    def test_non_table_text_yields_nothing(self):
        self.assertEqual(table_rows("그냥 산문이다"), [])


class TestNormalizeItem(unittest.TestCase):
    def test_case_and_markdown_and_marker_are_stripped(self):
        self.assertEqual(normalize_item("**Cart hold timeout** *"),
                         normalize_item("Cart Hold Timeout"))

    def test_backticks_and_spacing(self):
        self.assertEqual(normalize_item("`Max Coupon Attempts`"),
                         normalize_item("Max  Coupon Attempts"))

    def test_different_items_stay_different(self):
        self.assertNotEqual(normalize_item("Cart hold timeout"),
                            normalize_item("Cart max lifespan"))


class TestCrosscheck(unittest.TestCase):
    ARTICLE = {"key": "INV-55|table[1]",
               "text": "| Cart Hold Timeout | 45분 | 20분–2시간 | 장바구니 유지 |"}
    SCREEN = {"key": "screen:X§4|content",
              "text": "| **Cart hold timeout** * | 분 | 25 | 10–120분 (설계) |"}
    KINDS = {"INV-55": "article", "screen:X§4": "screen_section"}

    def test_same_item_different_values_is_flagged(self):
        out = crosscheck_concept("inv#sc-session", [self.ARTICLE, self.SCREEN], self.KINDS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["item"], normalize_item("Cart Hold Timeout"))
        self.assertEqual(sorted(out[0]["by_layer"]), ["article", "screen_section"])

    def test_agreeing_values_are_not_flagged(self):
        same = {"key": "screen:X§4|content", "text": "| Cart Hold Timeout | 45분 | 20분–2시간 | 장바구니 유지 |"}
        self.assertEqual(crosscheck_concept("c", [self.ARTICLE, same], self.KINDS), [])

    def test_one_layer_only_is_not_a_conflict(self):
        """한 층만 있으면 대조할 게 없다 — 축 1이 모아준 개념에서만 성립한다."""
        self.assertEqual(crosscheck_concept("c", [self.ARTICLE], self.KINDS), [])

    def test_same_layer_twice_is_not_a_conflict(self):
        """같은 층 안의 차이는 이 검출기의 일이 아니다(조항끼리는 조항 검토 몫)."""
        other = {"key": "INV-99|table[0]", "text": "| Cart Hold Timeout | 35분 |"}
        kinds = {**self.KINDS, "INV-99": "article"}
        self.assertEqual(crosscheck_concept("c", [self.ARTICLE, other], kinds), [])

    def test_history_fragments_are_ignored(self):
        """이력은 현행이 아니다 — 낡은 값과 현행 값을 불일치라 부르면 안 된다."""
        old = {**self.SCREEN, "superseded_at": "s2"}
        self.assertEqual(crosscheck_concept("c", [self.ARTICLE, old], self.KINDS), [])

    def test_report_carries_the_raw_rows_for_a_human(self):
        """기계는 판정하지 않는다 — 원문을 나란히 보여주고 사람이 3초에 판정한다."""
        out = crosscheck_concept("inv#sc-session", [self.ARTICLE, self.SCREEN], self.KINDS)
        vals = out[0]["by_layer"]
        self.assertIn("45분", " ".join(vals["article"]))
        self.assertIn("25", " ".join(vals["screen_section"]))




class TestCompareByNumbers(unittest.TestCase):
    """값 비교는 **숫자 집합**으로 한다 — 컬럼 구조가 층마다 다르기 때문.

    ★단위는 여전히 맞추지 않는다(2시간 vs 120분은 다르게 나온다). 그건 실제로 사람이
    봐야 하는 것이고, 기계가 환산하면 지어내는 셈이다."""

    def test_same_numbers_different_columns_is_not_a_conflict(self):
        art = {"key": "INV-55|t", "text": "| Checkout step timeout | 7분 | 2–12분 | 설명 |"}
        scr = {"key": "screen:X§4|content", "text": "| **Checkout step timeout** * | 분 | 7 | 2–12분 (각 단계) |"}
        kinds = {"INV-55": "article", "screen:X§4": "screen_section"}
        self.assertEqual(crosscheck_concept("c", [art, scr], kinds), [])

    def test_different_numbers_is_still_a_conflict(self):
        art = {"key": "INV-55|t", "text": "| Cart hold timeout | 45분 | 20분–2시간 | 설명 |"}
        scr = {"key": "screen:X§4|content", "text": "| **Cart hold timeout** * | 분 | 25 | 10–120분 |"}
        kinds = {"INV-55": "article", "screen:X§4": "screen_section"}
        out = crosscheck_concept("c", [art, scr], kinds)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["numbers"]["article"], ["2", "20", "45"])   # 숫자 순
        self.assertEqual(out[0]["numbers"]["screen_section"], ["10", "25", "120"])

    def test_rows_without_numbers_fall_back_to_text(self):
        """숫자가 없는 행은 텍스트로 본다 — 숫자 비교가 전부는 아니다."""
        art = {"key": "INV-1|t", "text": "| 바코드 형식 | EAN · QR |"}
        scr = {"key": "screen:X§1|content", "text": "| 바코드 형식 | EAN |"}
        kinds = {"INV-1": "article", "screen:X§1": "screen_section"}
        self.assertEqual(len(crosscheck_concept("c", [art, scr], kinds)), 1)

    def test_raw_rows_are_still_shown(self):
        """숫자로 판정해도 사람에게는 원문을 보여준다 — 단위 판단은 사람 몫."""
        art = {"key": "INV-55|t", "text": "| X | 45분 | 20분–2시간 |"}
        scr = {"key": "screen:X§4|content", "text": "| X | 분 | 25 | 10–120분 |"}
        kinds = {"INV-55": "article", "screen:X§4": "screen_section"}
        out = crosscheck_concept("c", [art, scr], kinds)
        self.assertIn("45분", " ".join(out[0]["by_layer"]["article"]))


if __name__ == "__main__":
    unittest.main()
