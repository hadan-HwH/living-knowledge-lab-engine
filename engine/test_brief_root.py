"""brief는 promote가 쓴 정본을 읽어야 한다 — 쓰는 곳과 읽는 곳의 일치."""
import unittest
from pathlib import Path

import yaml

import brief


class TestBriefRoot(unittest.TestCase):
    def test_reads_canon_from_given_root(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "fixtures"
            (root / "c" / "canon").mkdir(parents=True)
            yaml.safe_dump({"concepts": [{"anchor": "a#x", "kind": "concept",
                                          "scope": "s", "name": "X"}],
                            "bodies": {}, "relations": [], "held": {}},
                           open(root / "c" / "canon" / "concepts.yaml", "w"),
                           allow_unicode=True)
            doc = brief.load_and_build("c", "a", "s", None, "2030-01-01", "2030-01-01",
                                       root=root)
        names = [i.get("name") for b in doc["blocks"] for i in b.get("items", [])]
        self.assertIn("X", names)


if __name__ == "__main__":
    unittest.main()
