"""S3a 조항 귀속 · S3c 별칭 — Tier B 원장의 결정론 소비.
설계: docs/superpowers/specs/2026-08-04-tier-b-normative-redesign.md §2·§3.

LLM은 원장(members.yaml·aliases.yaml)을 낸다. 여기서 검증하는 건 그 원장을
읽어 정본에 반영하는 결정론 부분 — 게이트·비파괴 편입·단조성이다."""
import unittest

import structure_app as sa


class TestMembersLedger(unittest.TestCase):
    """S3a — 개념이 어느 조항의 것인가. 옛 계보가 전건 귀속을 얻은 방법(조항 주어 판정)."""

    def setUp(self):
        self.tier_a = [
            {"anchor": "A-1", "kind": "article", "scope": "x/inv",
             "content": "프로모션은 Rule로 구성한다", "fields": {"근거": "구 위키 05"}},
            {"anchor": "A-2", "kind": "article", "scope": "x/inv", "content": "삭제 규칙"},
        ]

    def test_members_expand_into_body_fragments(self):
        members = {"inv#sc-promotion": [{"article": "A-1", "quote": "프로모션은 Rule로 구성한다"}]}
        out = sa.assemble_body_fragments([{"sid": "inv#sc-promotion", "target": None}],
                                         self.tier_a, members=members)
        self.assertEqual([f["key"] for f in out["inv#sc-promotion"]],
                         ["A-1|content", "A-1|fields.근거"])

    def test_quote_not_in_article_is_rejected_not_absorbed(self):
        """왕복 게이트 — 원문에 없는 quote를 든 귀속은 조각을 만들지 않는다(지어냄 0)."""
        members = {"inv#sc-promotion": [{"article": "A-1", "quote": "원문에 없는 말"}]}
        out = sa.assemble_body_fragments([{"sid": "inv#sc-promotion", "target": None}],
                                         self.tier_a, members=members)
        self.assertNotIn("inv#sc-promotion", out)

    def test_target_and_members_are_unioned_and_deduped(self):
        members = {"inv#sc-promotion": [{"article": "A-2", "quote": "삭제 규칙"},
                                     {"article": "A-1", "quote": "프로모션은 Rule로 구성한다"}]}
        out = sa.assemble_body_fragments([{"sid": "inv#sc-promotion", "target": "A-1"}],
                                         self.tier_a, members=members)
        keys = [f["key"] for f in out["inv#sc-promotion"]]
        self.assertEqual(keys, ["A-1|content", "A-1|fields.근거", "A-2|content"])  # 정렬·dedup


class TestAliasesAreNonDestructive(unittest.TestCase):
    """S3c — 정체성 판정은 뭉개지 않는다. 별칭 링크로만 반영하고 원 개념을 둘 다 남긴다."""

    def test_alias_attaches_without_removing_either_concept(self):
        concepts = [{"anchor": "inv#sc-partition", "name": "Partition (앱별 작업 단위)"},
                    {"anchor": "inv#sc-파티션", "name": "파티션 (구 표기)"}]
        aliases = [{"anchor": "inv#sc-partition", "surface": "파티션",
                    "confidence": "high", "basis": "tier_b"}]
        out = sa.apply_aliases(concepts, aliases)
        self.assertEqual(len(out), 2)                     # 둘 다 살아 있다
        by = {c["anchor"]: c for c in out}
        self.assertEqual(by["inv#sc-partition"]["aliases"][0]["surface"], "파티션")
        self.assertTrue(by["inv#sc-partition"]["aliases"][0]["needs_review"])

    def test_alias_to_unknown_anchor_is_ignored(self):
        out = sa.apply_aliases([{"anchor": "a", "name": "A"}],
                               [{"anchor": "없음", "surface": "x"}])
        self.assertEqual(out, [{"anchor": "a", "name": "A"}])

    def test_aliases_are_monotone_across_passes(self):
        c = [{"anchor": "a", "name": "A", "aliases": [{"surface": "old", "basis": "owner"}]}]
        out = sa.apply_aliases(c, [{"anchor": "a", "surface": "new", "basis": "tier_b"}])
        self.assertEqual([x["surface"] for x in out[0]["aliases"]], ["new", "old"])


if __name__ == "__main__":
    unittest.main()


class TestPromoteWiring(unittest.TestCase):
    """work/<app>/{members,aliases}.yaml 을 promote가 읽어 정본에 반영한다."""

    def _setup(self, tmp, members=None, aliases=None):
        import yaml
        base = tmp / "probe"; base.mkdir()
        yaml.safe_dump({"subconcepts": [{"anchor": "sc-p", "name": "Promotion (프로모션)",
                                         "quote": "q"}]},
                       open(base / "subconcepts.yaml", "w"), allow_unicode=True)
        yaml.safe_dump({"relations": []}, open(base / "relations-canon.yaml", "w"))
        yaml.safe_dump({"queue": [{"sid": "inv#sc-p", "was": "article_only",
                                   "target": "A-1", "disposition": "new_code_only"}],
                        "carried": []},
                       open(base / "adjudication.yaml", "w"), allow_unicode=True)
        if members is not None:
            yaml.safe_dump({"members": members}, open(base / "members.yaml", "w"),
                           allow_unicode=True)
        if aliases is not None:
            yaml.safe_dump({"aliases": aliases}, open(base / "aliases.yaml", "w"),
                           allow_unicode=True)
        stack = tmp / "canon.yaml"
        yaml.safe_dump({"meta": {}, "concepts": [], "relations": [], "bodies": {},
                        "held": {"candidate": [], "ambiguous": [], "gap": []}},
                       open(stack, "w"), allow_unicode=True)
        return base, stack

    def test_promote_reads_members_and_aliases_from_work_dir(self, ):
        import tempfile, yaml
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base, stack = self._setup(
                tmp,
                members={"inv#sc-p": [{"article": "A-2", "quote": "삭제 규칙"}]},
                aliases=[{"anchor": "inv#sc-p", "surface": "정책", "confidence": "high"}])
            tier_a = [{"anchor": "A-1", "kind": "article", "scope": "x/inv",
                       "content": "프로모션은 Rule로 구성한다"},
                      {"anchor": "A-2", "kind": "article", "scope": "x/inv",
                       "content": "삭제 규칙"}]
            sa.run_promote(base, "inv", stack, app_scope="x/inv", tier_a=tier_a)
            saved = yaml.safe_load(open(stack))
        body_keys = [f["key"] for f in saved["bodies"]["inv#sc-p"]]
        self.assertIn("A-1|content", body_keys)      # 정렬된 조항
        self.assertIn("A-2|content", body_keys)      # ★귀속 원장에서 온 조항
        self.assertEqual(saved["concepts"][0]["aliases"][0]["surface"], "정책")
