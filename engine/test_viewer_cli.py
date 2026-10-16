"""view 서브커맨드 — metrics와 같은 3인자(코퍼스 단위) 계열."""
import unittest

import structure_app


class TestViewCli(unittest.TestCase):
    def test_usage_lists_view(self):
        self.assertIn("view", structure_app._USAGE)

    def test_view_needs_only_corpus(self):
        """metrics처럼 app이 없다 — 3인자로 usage SystemExit이 나면 안 된다."""
        with self.assertRaises(SystemExit) as cm:
            structure_app.main(["structure_app.py", "view"])
        self.assertIn("usage", str(cm.exception))
