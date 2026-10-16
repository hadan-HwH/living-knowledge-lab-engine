"""원장 2단 — 인용을 조각으로 해소하고, 두 제품이 같은 항목에 다른 값을 말하는지 본다.

★kind는 파서를 안 고치고 **조립 시점에 출처로 붙인다**. `markdown-sections`의
  `kind: "section"`을 건드리면 wevolley·lab-self까지 흔들린다. "이 조각이 어느
  제품에서 왔나"는 파싱 사실이 아니라 **경계 선언**이므로 여기가 제자리다."""
import unittest

import derivation as D
import derivation_members as M

AXES = [{"column": "Meadow", "kind": "spec_article", "cite": ["article", "canon"]},
        {"column": "RivalCo", "kind": "survey_section", "cite": ["volume", "screen"]}]


RIVALCO = {"07-billing-accounts.md": """---
platform: "neomart"
---
# 빌링

## 1. 요금 단위 마스터

### 1-1. 보관함

| 항목 | 단가 | 비고 |
|---|---|---|
| Locker rental | $0.10/hr | 연체 시 2배 |
| Idle timeout | 5초 | |
"""}

MEADOW_ARTICLES = [
    {"anchor": "MEADOW-07", "kind": "article", "content": "포인트는 적립만 가능하다",
     "table": ["| 항목 | 값 |", "| Idle timeout | 30초 |"]},
    {"anchor": "MEADOW-99", "kind": "article", "content": "표 없는 조항"},
]

DOC = """---
platform: "neomart"
---
# 매핑

## 2. ①통 — 그대로 쓴다

### 2-1. ①-A 구조·값 모두 대응

| 항목 | Meadow 근거 | RivalCo 대응 | 비고 |
|---|---|---|---|
| 유휴 타임아웃 | `[MEADOW-07]` | 07권 §1-1 ✅ | |
| 근거 없는 행 | `[MEADOW-99]` | 없음 | |
| 못 찾는 인용 | `[MEADOW-404]` | 99권 §9-9 | |
"""


#: 축 이름 → 인덱스. 어느 축이 어느 인덱스를 쓰는지는 registry `evidence_root`가 선언한다.
IDX = {}


def setUpModule():
    IDX["Meadow"] = M.index_articles(MEADOW_ARTICLES)
    IDX["RivalCo"] = M.index_sections(RIVALCO)


class TestIndexing(unittest.TestCase):
    def test_rivalco_citation_key_is_volume_and_section(self):
        idx = M.index_sections(RIVALCO)
        self.assertIn("07권§1-1", idx)
        self.assertIn("Locker rental", idx["07권§1-1"]["text"])

    def test_meadow_article_carries_its_table(self):
        """★표가 안 실리면 대조할 게 없다 — crosscheck는 표 행을 비교한다."""
        idx = M.index_articles(MEADOW_ARTICLES)
        self.assertIn("Idle timeout", idx["MEADOW-07"]["text"])

    def test_article_without_table_still_indexed(self):
        self.assertIn("MEADOW-99", M.index_articles(MEADOW_ARTICLES))


class TestAttach(unittest.TestCase):
    def setUp(self):
        self.rows = M.attach(D.parse_ledger(DOC, AXES), AXES, IDX)
        self.by = {r["항목"]: r for r in self.rows}

    def test_members_carry_kind_by_source(self):
        """★두 근거가 **다른 층**이어야 crosscheck가 돈다(len(layers) < 2면 스킵)."""
        kinds = {m["kind"] for m in self.by["유휴 타임아웃"]["members"]}
        self.assertEqual(kinds, {"spec_article", "survey_section"})

    def test_member_text_is_verbatim_source(self):
        m = next(m for m in self.by["유휴 타임아웃"]["members"]
                 if m["kind"] == "survey_section")
        self.assertIn("$0.10/hr", m["text"])

    def test_single_layer_row_gets_one_member(self):
        self.assertEqual(len(self.by["근거 없는 행"]["members"]), 1)

    def test_unresolved_citation_is_flagged_not_dropped(self):
        """★조용히 버리면 "근거가 있는데 안 붙었다"를 영영 못 본다."""
        r = self.by["못 찾는 인용"]
        self.assertEqual(r["members"], [])
        self.assertEqual(sorted(r["미해소"]), ["99권§9-9", "MEADOW-404"])

    def test_resolved_rows_have_no_unresolved(self):
        self.assertEqual(self.by["유휴 타임아웃"]["미해소"], [])


class TestConflicts(unittest.TestCase):
    def test_same_item_different_value_surfaces(self):
        """Meadow 30초 vs RivalCo 5초 — 같은 항목에 다른 값이면 후보다."""
        rows = M.attach(D.parse_ledger(DOC, AXES), AXES, IDX)
        cf = M.conflicts(rows)
        self.assertEqual(len(cf), 1)
        self.assertEqual(cf[0]["item"], "idle timeout")
        self.assertEqual(set(cf[0]["by_layer"]), {"spec_article", "survey_section"})

    def test_machine_does_not_adjudicate(self):
        """어느 쪽이 맞는지는 기계가 말하지 않는다 — 원문을 나란히 보여줄 뿐."""
        rows = M.attach(D.parse_ledger(DOC, AXES), AXES, IDX)
        self.assertNotIn("verdict", M.conflicts(rows)[0])


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        a = M.attach(D.parse_ledger(DOC, AXES), AXES, IDX)
        b = M.attach(D.parse_ledger(DOC, AXES), AXES, IDX)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
