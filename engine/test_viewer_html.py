"""렌더는 얇다 — 로직이 아니라 '모델이 통째로 실렸는가'만 잰다."""
import json
import unittest

from viewer_html import render_html

MODEL = {"meta": {"corpus": "t", "source_sha": "sha1", "source_root": "/src",
                  "generated_from": "x"},
         "concepts": [{"anchor": "c#1", "name": "가", "scope": "s",
                       "fragments": {"current": [{"key": "A-1|content", "text": "현행"}],
                                     "history": [], "removed": []},
                       "neighbors": [], "issues": []}],
         "sources": {"A-1": {"kind": "article", "family": "조항", "file": "x.md",
                             "line": 3}},
         "issues": [], "coverage": {"crosscheck": None, "integrity": None, "drift": None,
                                    "families": {}, "other_kinds": {},
                                    "unresolved_anchors": 0},
         "metrics": {"concepts": 1}, "warnings": []}


class TestRenderHtml(unittest.TestCase):
    def test_is_a_self_contained_document(self):
        html = render_html(MODEL)
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("</html>", html)
        self.assertNotIn("http://", html)      # 외부 의존 0
        self.assertNotIn("https://", html)

    def test_embeds_the_whole_model_as_json(self):
        html = render_html(MODEL)
        marker = 'id="model" type="application/json">'
        blob = html.split(marker, 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(blob), MODEL)

    def test_has_three_pages_in_the_menu(self):
        html = render_html(MODEL)
        for label in ("개념", "어긋남", "현황"):
            self.assertIn(f'data-page="{label}"', html)

    def test_escapes_script_close_inside_data(self):
        """정본 본문에 </script>가 들어 있어도 문서가 깨지지 않아야 한다."""
        model = json.loads(json.dumps(MODEL))
        model["concepts"][0]["fragments"]["current"][0]["text"] = "</script><b>x"
        html = render_html(model)
        self.assertNotIn("</script><b>x", html)

    def test_no_unfilled_template_placeholder_remains(self):
        self.assertNotIn("{{", render_html(MODEL))

    def test_relative_source_root_builds_relative_links(self):
        """상대 원천 경로면 file:// 없이 HTML 위치 기준 링크를 만든다(기계마다 같은 산출물)."""
        html = render_html(MODEL)
        self.assertIn('root.startsWith("/")', html)

    def test_source_path_survives_even_if_link_is_blocked(self):
        """★file:// 링크가 정책에 막혀도 경로·줄은 텍스트로 남아야 한다(설계 §3-1-2)."""
        html = render_html(MODEL)
        self.assertIn("s.file", html)   # 렌더 코드가 경로를 실제로 그린다
        self.assertIn('"file":"x.md"', html.replace(" ", ""))  # 모델에 경로가 실려 있다
