"""구성 평면 — 파생 **제품 하나**를 lab이 실제로 "들고 있는" 형태로 접는다.

★원칙은 파생 평면과 같다 — 엔진은 제품 이름을 모른다(registry `composition` 선언),
  결정론·LLM 0·재생성 가능, 판정하지 않고 사람이 쓴 것을 접는다."""
import unittest

import composition as C

CFG = {
    "product": "neomart",
    "sources": [
        {"path": "draft/spec.md", "role": "spec"},
        {"path": "draft/screens.md", "role": "screens"},
    ],
    "screen_id_prefix": "NEO-S-",
    "decision_ns": ["NEOMART", "BILL"],
}

SPEC = """---
title: "스펙 초안"
---
# 스펙

## 개요 · 정체성

한 줄 정체성: **동네 상점용 주문·배송 플랫폼.**

| 축 | 내용 |
|---|---|
| 소유 단위 | 본사 > 매장 |
"""

SCREENS = """---
title: "화면 초안"
---
# 화면

## 2. 전역 IA

트리.

### NEO-S-01 · 입점 신청 (`/signup`)

- **필드** 매장명 · 연락처

### 진열 매트릭스 (NEO-S-62 종속)

참조지 정의가 아니다.

### NEO-S-12 · 상품 등록 폼 (`/items/new`)

| 필드 | 필수 |
|---|---|
| 상품 SKU | ✅ |

상한 {TBD} · 실측 ❓ · 미납은 `BILL-D-3` 결번 참조.
"""

DECISIONS = {
    "neomart": """
### 미확정 · 검토 중 (조항화 금지)

- **G2 — 조항 prefix**: 채번 전 팀 합의.
- ~~**배송 권역 수준**: 검토.~~ → **종결(2026-08-06)**: 단일 권역.
- **정기배송 도입**: 나중에 얹을 수 있는 구조까지만 합의.

## 결정 이력 (D-N)

| ID | 날짜 | 결정 내용 | 출처 | 영향 조항 | 반영 상태 | 비고 |
|----|------|-----------|------|-----------|-----------|------|
| NEOMART-D-9221 | 2026-08-04 | 정산 단위 — 매장 단위만 | 기획 | - | 보류 | |
| NEOMART-D-9840 | 2026-08-06 | 직원 직무 3층 | 회의 | - | 보류 | |
""",
    "billing": """
| ID | 날짜 | 결정 내용 | 출처 | 영향 조항 | 반영 상태 | 비고 |
|----|------|-----------|------|-----------|-----------|------|
| BILL-D-1 | 2026-08-06 | 결제 그룹 레이어 | 회의 | - | 보류 | |
| INV-D-7 | 2026-05-01 | 남의 네임스페이스 결정 | - | - | 반영완료 | |
""",
}


def build():
    return C.compose(CFG, {"draft/spec.md": SPEC, "draft/screens.md": SCREENS},
                     decision_texts=list(DECISIONS.values()),
                     derivation={"rows": [{"관계": "adopts", "상태": "확정"},
                                          {"관계": "hides", "상태": "판정대기"}]})


class TestSections(unittest.TestCase):
    def test_bodies_survive_with_tables(self):
        """★표가 본문에 살아야 한다 — spec 파서가 몇 글자짜리 껍데기를 냈다(실측)."""
        out = build()
        spec = [s for s in out["sections"] if s["role"] == "spec"]
        joined = "\n".join(s["content"] for s in spec)
        self.assertIn("본사 > 매장", joined)

    def test_sections_tagged_by_role(self):
        roles = {s["role"] for s in build()["sections"]}
        self.assertEqual(roles, {"spec", "screens"})


class TestScreens(unittest.TestCase):
    def test_screen_headings_become_screen_units(self):
        """`### NEO-S-NN` 헤딩은 화면 단위다 — 인벤토리가 아니라 정의 절에서 센다."""
        screens = build()["screens"]
        self.assertEqual([s["id"] for s in screens], ["NEO-S-01", "NEO-S-12"])

    def test_reference_in_title_is_not_a_definition(self):
        """★제목 중간의 ID는 참조다 — `진열 매트릭스 (NEO-S-62 종속)`이 화면으로
        오인되면 인벤토리와 정의 수가 어긋난다(실측). 정의는 ID로 **시작**한다."""
        ids = [s["id"] for s in build()["screens"]]
        self.assertNotIn("NEO-S-62", ids)
        sec = [x["section"] for x in build()["sections"]]
        self.assertIn("진열 매트릭스 (NEO-S-62 종속)", sec)

    def test_screen_carries_its_body(self):
        s12 = next(s for s in build()["screens"] if s["id"] == "NEO-S-12")
        self.assertIn("상품 SKU", s12["content"])


class TestDecisions(unittest.TestCase):
    def test_own_namespaces_collected(self):
        ids = [d["decision_id"] for d in build()["decisions"]]
        self.assertEqual(ids, ["NEOMART-D-9221", "NEOMART-D-9840", "BILL-D-1"])

    def test_foreign_namespace_excluded(self):
        """남의 결정(INV-D-7)은 이 제품의 구성이 아니다."""
        ids = [d["decision_id"] for d in build()["decisions"]]
        self.assertNotIn("INV-D-7", ids)


class TestOpenItems(unittest.TestCase):
    """★검토 목록은 제품 지식의 절반이다 — D-N 표만 읽으면 미결 항목이 통째로 빠진다(실측).

    판정하지 않는다: 취소선(~~)은 원문이 스스로 닫았다고 말한 것이므로 closed로 옮긴다."""

    def test_open_items_collected(self):
        names = [o["name"] for o in build()["open_items"]]
        self.assertIn("G2 — 조항 prefix", names)
        self.assertIn("정기배송 도입", names)

    def test_struck_item_is_closed_not_dropped(self):
        by = {o["name"]: o for o in build()["open_items"]}
        self.assertEqual(by["배송 권역 수준"]["status"], "closed")
        self.assertEqual(by["G2 — 조항 prefix"]["status"], "open")


class TestUnresolvedCitations(unittest.TestCase):
    def test_retired_decision_citation_is_flagged_not_silent(self):
        """★인용됐는데 미보유인 결정(결번 등)은 무성이면 안 된다 — 결번인지 누락인지
        평면만 봐선 구분이 안 된다(실측: BILL-D-3)."""
        out = build()
        self.assertEqual(out["미해소_결정인용"], ["BILL-D-3"])


class TestStats(unittest.TestCase):
    def test_meta_counts(self):
        m = build()["meta"]
        self.assertEqual(m["product"], "neomart")
        self.assertEqual(m["screens"], 2)
        self.assertEqual(m["decisions"], 3)
        self.assertEqual(m["derivation_rows"], 2)

    def test_open_axis_counted(self):
        """미결 축 — {TBD}·❓가 안 세지면 "완성처럼 보이는" 평면이 된다."""
        m = build()["meta"]
        self.assertEqual(m["tbd"], 1)
        self.assertEqual(m["unverified"], 1)
        self.assertEqual(m["open_items"], 2)      # closed 제외

    def test_deterministic(self):
        self.assertEqual(build(), build())

    def test_missing_source_is_flagged_not_dropped(self):
        """소스가 없으면 조용히 0이 아니라 flag다 — 부재와 공백을 구분한다."""
        out = C.compose(CFG, {"draft/spec.md": SPEC}, decision_texts=[], derivation=None)
        self.assertTrue(any("draft/screens.md" in f for f in out["flags"]))


if __name__ == "__main__":
    unittest.main()
