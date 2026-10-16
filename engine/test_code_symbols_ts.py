"""code-symbols:typescript — 파서 의존 없는 TS/TSX 어댑터."""
import unittest

from parsers import parse, parse_code_symbols_ts

SRC = '''/**
 * 영속 정책 — 어떤 쿼리를 디스크에 저장할지 결정하는 순수 로직.
 * 정책: denylist 기본 (planning/40, DECISIONS 0008).
 */

/**
 * 영속에서 제외하는 prefix. 사유가 명확한 세 범주만.
 */
export const PERSIST_DENIED_PREFIXES = [
  // ── 초휘발성 카운터 — stale 표시가 거짓정보 ──
  'unread-count',
];

/** 저장 여부를 판정한다. */
export function shouldPersist(key: string): boolean {
  // 접두 일치만 본다
  return true;
}

export default function Screen() {
  return null;
}

export interface Club {
  id: string;
}
'''


class TestParseCodeSymbolsTs(unittest.TestCase):
    def setUp(self):
        self.res = parse_code_symbols_ts(SRC, scope="wevolley",
                                         module="lib.query-persist-policy")
        self.by = {c["anchor"]: c for c in self.res["concepts"]}

    def test_module_is_a_unit_with_leading_jsdoc(self):
        m = self.by["lib.query-persist-policy"]
        self.assertEqual(m["kind"], "module")
        self.assertIn("영속 정책", m["content"])
        self.assertNotIn("제외하는 prefix", m["content"])   # 두 번째 블록은 심볼 것

    def test_exported_symbols_found(self):
        for a in ("lib.query-persist-policy.PERSIST_DENIED_PREFIXES",
                  "lib.query-persist-policy.shouldPersist",
                  "lib.query-persist-policy.Club"):
            self.assertIn(a, self.by)

    def test_kinds_mapped(self):
        b = self.by
        self.assertEqual(b["lib.query-persist-policy.PERSIST_DENIED_PREFIXES"]["kind"], "const")
        self.assertEqual(b["lib.query-persist-policy.shouldPersist"]["kind"], "function")
        self.assertEqual(b["lib.query-persist-policy.Club"]["kind"], "interface")

    def test_default_export_named_by_its_identifier(self):
        """`export default function Screen()`은 이름이 있다 — `default`로 뭉개지 않는다."""
        self.assertIn("lib.query-persist-policy.Screen", self.by)

    def test_jsdoc_above_declaration_becomes_content(self):
        c = self.by["lib.query-persist-policy.shouldPersist"]
        self.assertEqual(c["content"], "저장 여부를 판정한다.")

    def test_signature_is_verbatim_source_slice(self):
        c = self.by["lib.query-persist-policy.shouldPersist"]
        self.assertEqual(c["fields"]["signature"],
                         "export function shouldPersist(key: string): boolean {")
        self.assertIn(c["fields"]["signature"], SRC)

    def test_inline_comments_carried(self):
        """★이 코퍼스는 한 줄 주석이 JSDoc보다 많다(83,194 vs 65,170자)."""
        c = self.by["lib.query-persist-policy.PERSIST_DENIED_PREFIXES"]
        self.assertIn("초휘발성 카운터", c["fields"]["comments"])

    def test_comments_belong_to_enclosing_symbol(self):
        c = self.by["lib.query-persist-policy.shouldPersist"]
        self.assertIn("접두 일치만 본다", c["fields"]["comments"])
        self.assertNotIn("초휘발성", c["fields"].get("comments", ""))

    def test_planning_and_decision_refs_collected(self):
        """★lab과 다르다 — 이 코드는 기획 문서를 실제로 인용한다."""
        m = self.by["lib.query-persist-policy"]
        self.assertIn("DECISIONS 0008", m["refs"]["decisions"])
        self.assertIn("planning/40", m["refs"]["docs"])

    def test_anchor_unique(self):
        anchors = [c["anchor"] for c in self.res["concepts"]]
        self.assertEqual(len(anchors), len(set(anchors)))

    def test_scope_and_confidence(self):
        for c in self.res["concepts"]:
            self.assertEqual(c["scope"], "wevolley")
            self.assertEqual(c["confidence"], "high")

    def test_non_exported_declarations_are_captured(self):
        """★계약 변경. 종전 규칙은 "내부 헬퍼는 단위가 아니다 — export
        관례가 경계 선언"이었다. 그 전제가 실측으로 깨졌다:

        경계 선언은 버리지 않고 `fields.exported`로 남긴다 — 공개 표면과 내부
        구현은 여전히 다른 것이고, 그 구분이 필요한 소비자는 필드를 보면 된다."""
        res = parse_code_symbols_ts("function hidden() {}\n", scope="x", module="m")
        self.assertEqual([c["anchor"] for c in res["concepts"]], ["m", "m.hidden"])
        hidden = res["concepts"][1]
        self.assertEqual(hidden["fields"]["exported"], "false")

    def test_registered_in_dispatch(self):
        res = parse("code-symbols:typescript", SRC, scope="x",
                    module="lib.query-persist-policy")
        self.assertTrue(any(c["kind"] == "function" for c in res["concepts"]))

    def test_empty_file_yields_module_only(self):
        res = parse_code_symbols_ts("", scope="x", module="m")
        self.assertEqual(len(res["concepts"]), 1)
        self.assertEqual(res["concepts"][0]["content"], "")


if __name__ == "__main__":
    unittest.main()


class TestIngestCarriesKnowledgeLayerForCode(unittest.TestCase):
    """★코드 단위의 추출 입력은 **지식층**이다 — 구현 본문이 아니다.

    ★Tier A는 그대로다 — 스냅샷은 저장소 사실을 전부 들고 있다. 좁아지는 건 Tier B
    입력뿐이고, 이건 `작업완료/`·봉인분과 같은 처리다(A는 포함, B는 제외).

    ★이건 설계가 이미 인정한 한계를 **명시**하는 것이기도 하다: code-symbols 초판은
    docstring·시그니처만 읽으므로 "코드가 사실"은 절반이고, **주석이 구현과 어긋나면
    이 어댑터는 주석 편을 든다.** 자르면 그 사실이 입력에 드러난다."""

    def test_code_text_is_signature_doc_and_comments(self):
        from structure_app import run_ingest
        src = ('/** 모듈 설명. */\n'
               '/** 판정한다. */\n'
               'export function f(a: string) {\n'
               '  // 접두만 본다\n'
               '  return heavyImplementation(a, b, c, d, e, f, g, h);\n'
               '}\n')
        secs = run_ingest([("lib/x.ts", src)], "wevolley",
                          fmt="code-symbols:typescript")
        by = {s["anchor"]: s["text"] for s in secs}
        t = by["lib.x.f"]
        self.assertIn("판정한다", t)              # 설명
        self.assertIn("export function f", t)      # 시그니처
        self.assertIn("접두만 본다", t)            # 주석
        self.assertNotIn("heavyImplementation", t)  # ★구현은 안 싣는다

    def test_markdown_ingest_unchanged(self):
        """문서 축은 종전 그대로 — 헤딩 포함 원문 슬라이스다."""
        from structure_app import run_ingest
        secs = run_ingest([("d.md", "# 제목\n본문 줄\n")], "app")
        self.assertIn("# 제목", secs[0]["text"])
        self.assertIn("본문 줄", secs[0]["text"])

    def test_quote_roundtrip_still_holds(self):
        """실은 것은 전부 **원문 조각**이라 왕복 게이트가 그대로 걸린다."""
        from structure_app import run_ingest
        src = '/** 설명 문장. */\nexport const A = 1;\n'
        secs = run_ingest([("lib/y.ts", src)], "w", fmt="code-symbols:typescript")
        for line in secs[1]["text"].splitlines():
            if line.strip():
                self.assertIn(line.strip().lstrip("* "), src)
