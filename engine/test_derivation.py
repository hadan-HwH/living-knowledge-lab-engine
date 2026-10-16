"""파생 평면 — 한 제품이 **다른 두 제품에서 유도**될 때의 원장.

★기존 3코퍼스와 다른 점: 지식의 원자가 조항이 아니라 **짝**이다.
  (가진 쪽 근거, 베낄 쪽 근거, 관계, 결정) 하나가 한 행.

★기계는 판정하지 않는다. 통합은 이미 사람이 했고(매핑 문서 40행), 여기서 하는 일은
  ①그 판정을 구조로 옮기고 ②인용을 앵커로 해소하고 ③완결 조건으로 상태를 **계산**하는
  것뿐이다. 새 판정 0 — 원문이 "⚠️ 결정 필요"라 하면 원장도 미정으로 남긴다."""
import unittest

import derivation as D

AXES = [{"column": "Meadow", "kind": "spec_article", "cite": ["article", "canon"]},
        {"column": "RivalCo", "kind": "survey_section", "cite": ["volume", "screen"]}]


# 매핑 문서의 실제 표 모양을 줄인 것 (열 구성·표기 그대로)
DOC = """---
platform: "neomart"
---
# 매핑

## 2. ①통 — 그대로 쓴다

### 2-1. ①-A 구조·값 모두 대응

| 항목 | Meadow 근거 | RivalCo 대응 | 비고 |
|---|---|---|---|
| 포인트 적립만 허용 | `[MEADOW-07]` 차감 불가 | "cannot be decreased" 📄 | 완전 일치 |
| 어디에도 근거 없음 | — | — | |

### 2-2. ①-B 재매핑 필요 — 개념은 대응되나 축이 다름 ⚠️

| 항목 | Meadow 축 | RivalCo 축 | 결정 필요 |
|---|---|---|---|
| 배송 슬롯 파라미터 | Min/Max Slots | Active/Max couriers | 대응표가 필요 |

## 3. ②통 — 감춘다 / 값을 고정한다 (권고안 포함)

| # | 항목 | Meadow | RivalCo | **[권고]** | 이유 |
|---|---|---|---|---|---|
| ②-1 | PackingMode | `[MEADOW-06]` 수정 불가 | 없음 | **감춤.** 2택으로 대체 | 물류 용어 번역 |
| ②-2 | Shipping Class | `[MEADOW-06]` | 2 tier 📄 | **감추지 말고 번역.** | tier를 숨기지 않는다 |
| ②-3 | retryPolicy | 코드 존재·정책 미정의 (lab `meadow#sc-retry-policy`) | 없음 | **Always 고정, 미노출** | 결제 재시도는 항상 켜짐 |
| ②-12 | 매장 귀속 | `[MEADOW-09]` | 없음 | ⚠️ **결정 필요** | 소유 축의 선택 |

## 4. ③통 — 새로 만든다

### 4-1. ③-A 정산

| 항목 | 근거 |
|---|---|
| 정산 항목 23종 | 07권 §1 |

## 5. ④통 — 쓰면 안 되는 것

| 항목 | 출처 | 이유 |
|---|---|---|
| Instant Delivery | 소유자 결정(2026-08-03) NEOMART-D-8357 | 범위 제외 |
| 멤버 초대 링크 | 08권 §3-4 📄 | 법인 고객에겐 안 통한다 |

## 6. 결정 대기 목록

| # | 결정할 것 | 통 |
|---|---|---|
| 1 | 소유 축 | ③-C |
"""


class TestRelationFromBucket(unittest.TestCase):
    """관계는 통에서 결정론으로 유도한다 — 섹션 제목이 명시적이라 추측이 없다."""

    def setUp(self):
        self.rows = {r["항목"]: r for r in D.parse_ledger(DOC, AXES)}

    def test_only_ledger_sections_are_read(self):
        """§1 분류기준·§6 결정대기·§9 GAP은 원장 행이 아니다(메타)."""
        self.assertNotIn("소유 축", self.rows)      # §6 결정대기
        self.assertNotIn("**①**", self.rows)          # §1 분류기준
        self.assertEqual(len(self.rows), 10)          # §2-1 2 · §2-2 1 · §3 4 · §4-1 1 · §5 2

    def test_bucket_1a_is_adopts(self):
        self.assertEqual(self.rows["포인트 적립만 허용"]["관계"], "adopts")

    def test_bucket_1b_is_remaps(self):
        self.assertEqual(self.rows["배송 슬롯 파라미터"]["관계"], "remaps")

    def test_bucket_3_is_builds(self):
        self.assertEqual(self.rows["정산 항목 23종"]["관계"], "builds")

    def test_bucket_4_is_excludes(self):
        self.assertEqual(self.rows["Instant Delivery"]["관계"], "excludes")


class TestBucket2Split(unittest.TestCase):
    """②통은 hides와 translates가 갈린다 — 후속 작업이 전혀 다르기 때문이다.

    ★갈래는 지어내지 않고 **[권고] 셀이 말한 것을 옮긴다.** 근거 문자열을 함께
      기록해 사람이 3초에 검증할 수 있게 한다(판정이 아니라 전달).
    """

    def setUp(self):
        self.rows = {r["항목"]: r for r in D.parse_ledger(DOC, AXES)}

    def test_hide_recommendation_becomes_hides(self):
        self.assertEqual(self.rows["PackingMode"]["관계"], "hides")

    def test_translate_recommendation_becomes_translates(self):
        self.assertEqual(self.rows["Shipping Class"]["관계"], "translates")

    def test_decision_needed_leaves_relation_undecided(self):
        """★원문이 "결정 필요"라 하면 원장도 미정이다 — 여기서 정하면 판정을 훔치는 것."""
        self.assertIsNone(self.rows["매장 귀속"]["관계"])

    def test_relation_carries_its_evidence(self):
        r = self.rows["Shipping Class"]
        self.assertIn("번역", r["관계_근거"])


class TestCitations(unittest.TestCase):
    def setUp(self):
        self.rows = {r["항목"]: r for r in D.parse_ledger(DOC, AXES)}

    def test_meadow_and_rivalco_evidence_are_separate_axes(self):
        r = self.rows["포인트 적립만 허용"]
        self.assertEqual(r["Meadow_근거"], ["MEADOW-07"])
        self.assertEqual(r["RivalCo_근거"], [])

    def test_volume_section_citation_is_a_rivalco_anchor(self):
        self.assertEqual(self.rows["멤버 초대 링크"]["RivalCo_근거"], ["08권§3-4"])

    def test_lab_canon_is_a_third_evidence_axis(self):
        """★근거 축이 둘이 아니라 셋이다 — Meadow spec · RivalCo 관측 · **lab 정본**."""
        self.assertEqual(self.rows["retryPolicy"]["Meadow_근거"],
                         ["meadow#sc-retry-policy"])

    def test_decision_id_extracted(self):
        self.assertEqual(self.rows["Instant Delivery"]["결정"], ["NEOMART-D-8357"])


class TestCompletionGate(unittest.TestCase):
    """상태는 손으로 안 매긴다 — 관계가 완결 조건을 정하고 조건이 상태를 계산한다."""

    def setUp(self):
        self.rows = {r["항목"]: r for r in D.parse_ledger(DOC, AXES)}

    def test_adopts_with_both_evidence_is_settled(self):
        self.assertEqual(self.rows["포인트 적립만 허용"]["상태"], "확정")

    def test_no_evidence_at_all_is_evidence_gap(self):
        """★근거부족이 판정대기보다 앞선다 — 근거 없이 결정할 수는 없다."""
        self.assertEqual(self.rows["어디에도 근거 없음"]["상태"], "근거부족")

    def test_excludes_needs_a_reintroduction_decision(self):
        """④통은 "안 쓴다"로 안 끝난다 — 재도입 조건이 결정으로 남아야 한다(§7 권고)."""
        self.assertEqual(self.rows["Instant Delivery"]["상태"], "확정")
        self.assertEqual(self.rows["멤버 초대 링크"]["상태"], "판정대기")

    def test_hides_without_a_decision_is_pending(self):
        """고정값은 결정이다 — [권고]만으로는 확정이 아니다(문서 스스로 그렇게 말한다)."""
        self.assertEqual(self.rows["PackingMode"]["상태"], "판정대기")

    def test_undecided_relation_is_pending(self):
        self.assertEqual(self.rows["매장 귀속"]["상태"], "판정대기")

    def test_every_row_has_a_state(self):
        self.assertTrue(all(r["상태"] for r in self.rows.values()))


FOREIGN = """---
platform: "neomart"
---
# 매핑

## 5. ④통 — 쓰면 안 되는 것

| 항목 | 출처 | 이유 |
|---|---|---|
| 남의 결정 인용 | INV 소관 (`MEADOW-D-9840`로 아카이브) | 대응물이 없다 |
| 자기 결정 있음 | 소유자 결정 NEOMART-D-8357 | 범위 제외 |

## 4. ③통 — 새로 만든다

### 4-3. ③-C 소유 구조 ⚠️ 최대 쟁점

| | Meadow | RivalCo |
|---|---|---|
| 소유자 축 | **매장** | **계정** |
| 조직 계층 | 본사/지점/매장 | 없음 |
"""


class TestForeignDecisionIsEvidenceNotSettlement(unittest.TestCase):
    """★남의 결정을 인용하는 건 **근거**지 이 행을 끝내는 결정이 아니다.

    자기 namespace는 지어내지 않고 문서 프론트매터 `platform:` 선언에서 읽는다."""

    def setUp(self):
        self.rows = {r["항목"]: r for r in D.parse_ledger(FOREIGN, AXES)}

    def test_foreign_decision_does_not_settle(self):
        r = self.rows["남의 결정 인용"]
        self.assertEqual(r["결정"], [])
        self.assertEqual(r["상태"], "판정대기")

    def test_foreign_decision_is_kept_as_evidence(self):
        self.assertEqual(self.rows["남의 결정 인용"]["인용_결정"], ["MEADOW-D-9840"])

    def test_own_decision_settles(self):
        r = self.rows["자기 결정 있음"]
        self.assertEqual(r["결정"], ["NEOMART-D-8357"])
        self.assertEqual(r["상태"], "확정")

    def test_undeclared_platform_settles_nothing(self):
        """선언이 없으면 보수적으로 간다 — 추측해서 확정을 만들지 않는다."""
        no_fm = FOREIGN.split("---\n", 2)[-1]
        rows = {r["항목"]: r for r in D.parse_ledger(no_fm, AXES)}
        self.assertEqual(rows["자기 결정 있음"]["결정"], [])
        self.assertEqual(rows["자기 결정 있음"]["상태"], "판정대기")


class TestGranularityFlag(unittest.TestCase):
    """★표마다 행의 의미가 다르다 — 어떤 표는 한 행이 한 항목이고, 어떤 표는
    한 행이 **한 항목의 속성**이다(§4-3 소유 구조: 소유자 축·조직 계층·역할).

    기계가 못 가른다. 그래서 판정하지 않고 **표시**한다 — 머리글에 항목 열이
    명시되지 않은 표(첫 칸이 빈 비교표)가 그 신호다.
    """

    def test_attribute_table_rows_are_flagged(self):
        rows = {r["항목"]: r for r in D.parse_ledger(FOREIGN, AXES)}
        self.assertTrue(rows["소유자 축"]["입도주의"])
        self.assertTrue(rows["조직 계층"]["입도주의"])

    def test_normal_table_rows_are_not_flagged(self):
        rows = {r["항목"]: r for r in D.parse_ledger(FOREIGN, AXES)}
        self.assertFalse(rows["자기 결정 있음"]["입도주의"])


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        self.assertEqual(D.parse_ledger(DOC, AXES), D.parse_ledger(DOC, AXES))

    def test_row_order_is_document_order(self):
        got = [r["항목"] for r in D.parse_ledger(DOC, AXES)]
        self.assertEqual(got[0], "포인트 적립만 허용")
        self.assertEqual(got[-1], "멤버 초대 링크")


if __name__ == "__main__":
    unittest.main()
