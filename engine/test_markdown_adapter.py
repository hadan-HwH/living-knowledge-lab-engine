"""마크다운 코퍼스 어댑터 테스트 — 설계: docs/2-method/markdown-corpus-adapter.md.
범용(코퍼스 무지) — 테스트에도 특정 코퍼스 이름 하드코딩 없음."""
import unittest

from parsers import parse_markdown_sections
from ingest import doc_slug
from change_layer import rebind_proposals

MD = """서문 첫 줄이다.

# 제목 문서

## 원리

원칙 A를 유지한다. 근거는 `[INV-81]`과 D-7149 판정이다.
(참고: "D-7149다"처럼 한글이 붙으면 유니코드 \\b 때문에 미검출 — 기존 파서 공통 한계, flag)

## 파일럿

지표를 사전 등록한다.

### 지표

왕복 100%가 게이트다.

## 파일럿

두 번째 동명 헤딩이다.
"""


class TestParseMarkdownSections(unittest.TestCase):
    def setUp(self):
        self.res = parse_markdown_sections(MD, scope="x", doc_slug="docs/method/foo")
        self.by = {c["anchor"]: c for c in self.res["concepts"]}

    def test_anchor_scheme_doc_heading(self):
        self.assertIn("docs/method/foo#원리", self.by)
        self.assertIn("docs/method/foo#지표", self.by)

    def test_preamble_captured(self):
        p = self.by["docs/method/foo#_preamble"]
        self.assertIn("서문 첫 줄이다.", p["content"])

    def test_duplicate_heading_disambiguated_deterministically(self):
        self.assertIn("docs/method/foo#파일럿", self.by)
        self.assertIn("docs/method/foo#파일럿-2", self.by)
        self.assertIn("두 번째 동명 헤딩이다.", self.by["docs/method/foo#파일럿-2"]["content"])

    def test_content_roundtrip_verbatim(self):
        for c in self.res["concepts"]:
            for line in c["content"].splitlines():
                if line.strip():
                    self.assertIn(line, MD)      # 원문 무수정(재서술 0)

    def test_refs_extracted_with_existing_generic_regexes(self):
        c = self.by["docs/method/foo#원리"]
        self.assertEqual(c["refs"]["articles"], ["INV-81"])
        self.assertEqual(c["refs"]["decisions"], ["D-7149"])

    def test_kind_and_scope(self):
        self.assertTrue(all(c["kind"] == "section" for c in self.res["concepts"]))
        self.assertTrue(all(c["scope"] == "x" for c in self.res["concepts"]))


class TestDocSlug(unittest.TestCase):
    def test_number_prefixes_stripped_per_part(self):
        self.assertEqual(doc_slug("docs/2-method/relation-layer-design.md"),
                         "docs/method/relation-layer-design")

    def test_root_file(self):
        self.assertEqual(doc_slug("STATUS.md"), "STATUS")


class TestOccurrenceKinds(unittest.TestCase):
    def test_find_occurrences_kinds_parameter(self):
        # 범용화: 등장 검색 대상 kind를 파라미터로 (기본값=기존 article 유지)
        from term_layer import find_occurrences
        vocab = [{"surface": "relation_layer", "resource": "relation_layer"}]
        concepts = [{"anchor": "d#s", "kind": "section",
                     "content": "relation_layer 가 어휘를 동결한다"}]
        self.assertEqual(find_occurrences(vocab, concepts), [])          # 기존 동작
        occ = find_occurrences(vocab, concepts, kinds=("section",))
        self.assertEqual(occ[0]["concept"], "d#s")


class TestGenericGate(unittest.TestCase):
    def test_engine_code_has_no_corpus_name(self):
        # 설계 §4-⑤ — 엔진 모듈에 코퍼스 이름 하드코딩 0 (registry 데이터만 허용).
        # 테스트 파일은 제외(픽스처 데이터는 코드가 아님).
        import pathlib
        here = pathlib.Path(__file__).parent
        hits = []
        for p in sorted(here.glob("*.py")):
            if p.name.startswith("test_"):
                continue
            src = p.read_text(encoding="utf-8")
            for name in ("lab-self", "lab_self", "acme-docs-repo", "acme-docs-full"):
                if name in src:
                    hits.append(f"{p.name}:{name}")
        self.assertEqual(hits, [])

    def test_promote_pipeline_is_corpus_generic(self):
        # promote 파이프라인은 특정 코퍼스명을 모른다(registry 구동).
        # 2026-08-04: 대상을 구 snapshot_pipeline(아카이브)에서 라이브 structure_app으로 옮김.
        import io, pathlib, tokenize
        src = (pathlib.Path(__file__).parent / "structure_app.py").read_text(encoding="utf-8")
        # 주석은 제외한다 — 규칙은 "코드가 코퍼스를 모른다"이지 "실측 사례를 설명하지
        # 말라"가 아니다. 문자열 리터럴은 게이트 안에 남긴다(진짜 하드코딩의 자리).
        code = "".join(t.string if t.type != tokenize.COMMENT else ""
                       for t in tokenize.generate_tokens(io.StringIO(src).readline))
        for name in ("acme-docs", "inv-paused", "prime-commerce/summit"):
            self.assertNotIn(name, code, f"promote에 {name} 하드코딩 잔존")


class TestRebindProposals(unittest.TestCase):
    def test_similar_content_rebinding_proposed(self):
        removed = [{"anchor": "docs/old#원리", "text": "원칙 A를 유지한다. 근거는 X다."}]
        added = [{"anchor": "docs/method/new#원리", "text": "원칙 A를 유지한다. 근거는 X다."},
                 {"anchor": "docs/method/new#무관", "text": "완전히 다른 내용."}]
        out = rebind_proposals(removed, added)
        self.assertEqual(out[0]["from"], "docs/old#원리")
        self.assertEqual(out[0]["to"], "docs/method/new#원리")
        self.assertGreater(out[0]["similarity"], 0.9)

    def test_no_match_below_threshold_reported_as_unbound(self):
        removed = [{"anchor": "a#x", "text": "고유한 내용 하나"}]
        added = [{"anchor": "b#y", "text": "전혀 무관한 다른 글"}]
        out = rebind_proposals(removed, added, threshold=0.8)
        self.assertEqual(out[0]["to"], None)                # 제안 없음 = 정직 보고


if __name__ == "__main__":
    unittest.main()
