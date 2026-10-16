"""지도 모델 — 정본이 **어떤 구조로 되어 있나**를 한 화면에 담는다.

지금 뷰어의 개념 페이지는 수백~천여 개를 평평한 목록 하나로 낸다.
그건 지도가 아니라 명부다. 크기도 무리도 안 보이니 "어디가 두껍고 어디가 비었나"를
읽을 수 없다.

★묶는 축은 **데이터가 정한다.** acme-docs은 scope가 `prime-commerce/summit/inv`처럼
3단이라 platform → app으로 묶이지만, wevolley·lab은 scope가 하나뿐이다.
코퍼스마다 다른 축을 코드에 박으면 한 코퍼스에서만 맞고 나머지에서 조용히 틀린다.
"""
import unittest

import viewer_map as vm


def _c(anchor, scope, name=None, commitment="working"):
    return {"anchor": anchor, "scope": scope, "name": name or anchor,
            "commitment": commitment}


def _rel(a, b, canonical="part_of"):
    return {"from": a, "to": b, "canonical": canonical}


class TestGroupingAxis(unittest.TestCase):

    def test_a_layered_scope_groups_by_its_path(self):
        concepts = [_c("inv#a", "prime-commerce/summit/inv"),
                    _c("inv#b", "prime-commerce/summit/inv"),
                    _c("kms#a", "prime-commerce/summit/kms"),
                    _c("cont#a", "prime-commerce/atlas/crate")]
        m = vm.build_map_model(concepts, [], {})
        self.assertEqual(m["axis"], "scope")
        self.assertEqual([g["name"] for g in m["groups"]], ["summit", "atlas"],
                         "크기 순 — summit이 3개념, atlas가 1개념")
        summit = [g for g in m["groups"] if g["name"] == "summit"][0]
        self.assertEqual([(c["name"], c["concepts"]) for c in summit["children"]],
                         [("inv", 2), ("kms", 1)])

    def test_a_flat_scope_falls_back_to_the_part_of_axis(self):
        """scope가 하나뿐인 코퍼스는 관계가 유일한 구조 신호다."""
        concepts = [_c("w#root", "wevolley"), _c("w#a", "wevolley"), _c("w#b", "wevolley"),
                    _c("w#lone", "wevolley")]
        rels = [_rel("w#a", "w#root"), _rel("w#b", "w#root")]
        m = vm.build_map_model(concepts, rels, {})
        self.assertEqual(m["axis"], "part_of")
        root = [g for g in m["groups"] if g["name"] == "w#root"][0]
        self.assertEqual(sorted(c["anchor"] for c in root["children"]),
                         ["w#a", "w#b", "w#root"], "무리 머리도 개념이다")

    def test_a_concept_with_no_group_still_appears(self):
        """무리가 없는 개념을 숨기면 지도가 정본보다 작아진다."""
        concepts = [_c("w#root", "wevolley"), _c("w#a", "wevolley"), _c("w#lone", "wevolley")]
        m = vm.build_map_model(concepts, [_rel("w#a", "w#root")], {})
        self.assertIn("w#lone", [c["anchor"] for g in m["groups"] for c in g["children"]])

    def test_every_concept_lands_somewhere(self):
        concepts = [_c(f"x#{i}", "flat") for i in range(7)]
        m = vm.build_map_model(concepts, [], {})
        placed = [c["anchor"] for g in m["groups"] for c in g["children"]]
        self.assertEqual(sorted(placed), sorted(c["anchor"] for c in concepts))


class TestSize(unittest.TestCase):
    """크기는 조각 수다 — 개념 하나가 얼마나 두꺼운지가 지도의 요점이다."""

    def test_a_concept_is_sized_by_its_fragments(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("inv#b", "p/t/inv")]
        bodies = {"inv#a": [{"key": "k1"}, {"key": "k2"}, {"key": "k3"}], "inv#b": []}
        m = vm.build_map_model(concepts, [], bodies)
        sizes = {c["anchor"]: c["fragments"] for g in m["groups"] for c in g["children"]}
        self.assertEqual(sizes, {"inv#a": 3, "inv#b": 0})

    def test_history_fragments_do_not_count_as_current_thickness(self):
        """이력을 세면 두께가 거짓말을 한다(불변식 6 — 평면 분리)."""
        bodies = {"inv#a": [{"key": "k"}, {"key": "k", "superseded_at": "abc"},
                            {"key": "old", "removed_at": "abc"}]}
        m = vm.build_map_model([_c("inv#a", "p/t/inv")], [], bodies)
        self.assertEqual(m["groups"][0]["children"][0]["fragments"], 1)

    def test_a_group_carries_the_totals_of_its_children(self):
        """무리(platform)는 제 갈래(app)들의 합을 든다."""
        concepts = [_c("inv#a", "p/t/inv"), _c("kms#b", "p/t/kms")]
        bodies = {"inv#a": [{"key": "k1"}, {"key": "k2"}], "kms#b": [{"key": "k3"}]}
        m = vm.build_map_model(concepts, [], bodies)
        self.assertEqual(m["groups"][0]["name"], "t")
        self.assertEqual(m["groups"][0]["fragments"], 3)
        self.assertEqual(m["groups"][0]["concepts"], 2)


class TestCrossGroupLinks(unittest.TestCase):
    """무리를 관통하는 관계 — 지도에서 유일하게 선으로 그릴 값어치가 있는 것."""

    def test_links_inside_a_group_are_counted_not_drawn(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("inv#b", "p/t/inv")]
        m = vm.build_map_model(concepts, [_rel("inv#a", "inv#b", "constrains")], {})
        self.assertEqual(m["links"], [])
        self.assertEqual(m["stats"]["relations_within"], 1)

    def test_a_link_across_groups_is_drawn_with_its_kind(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("sec#b", "p/t/security")]
        m = vm.build_map_model(concepts, [_rel("inv#a", "sec#b", "constrains")], {})
        # ★끝점은 anchor 접두("sec")가 아니라 scope 말단("security")이다
        self.assertEqual(m["links"], [{"from": "inv", "to": "security",
                                       "canonical": "constrains", "count": 1}])

    def test_repeated_links_between_the_same_groups_merge_with_a_count(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("inv#b", "p/t/inv"), _c("sec#c", "p/t/security")]
        rels = [_rel("inv#a", "sec#c", "constrains"), _rel("inv#b", "sec#c", "constrains")]
        m = vm.build_map_model(concepts, rels, {})
        self.assertEqual(m["links"][0]["count"], 2)

    def test_a_link_to_a_concept_that_is_not_in_canon_is_dropped_not_guessed(self):
        m = vm.build_map_model([_c("inv#a", "p/t/inv")], [_rel("inv#a", "ghost#z")], {})
        self.assertEqual(m["links"], [])
        self.assertEqual(m["stats"]["relations_dangling"], 1)


class TestReadingAids(unittest.TestCase):

    def test_the_model_says_which_axis_it_used_and_why(self):
        m = vm.build_map_model([_c("w#a", "flat")], [], {})
        self.assertIn("axis_note", m)
        self.assertTrue(m["axis_note"])

    def test_commitment_is_summarised_per_group(self):
        concepts = [_c("inv#a", "p/t/inv", commitment="frozen"),
                    _c("inv#b", "p/t/inv", commitment="working"),
                    _c("inv#c", "p/t/inv", commitment="frozen"),
                    _c("kms#a", "p/t/kms", commitment="working")]
        m = vm.build_map_model(concepts, [], {})
        inv = [a for a in m["groups"][0]["children"] if a["name"] == "inv"][0]
        self.assertEqual(inv["commitment"], {"frozen": 2, "working": 1})

    def test_empty_canon_does_not_crash(self):
        m = vm.build_map_model([], [], {})
        self.assertEqual(m["groups"], [])
        self.assertEqual(m["stats"]["concepts"], 0)


class TestOriginAxis(unittest.TestCase):
    """scope가 하나뿐이면 **조각이 어디서 왔나**가 다음 구조 신호다.

    실측이 `part_of`를 밀어냈다: wevolley 297개념에 part_of 무리가 261개(≈개념당 하나)라
    지도가 다시 명부가 됐다. 같은 정본을 조각 출처로 묶으면 30무리
    (`planning/reference` 66 · `planning/backlog` 61 · `lib/hooks` 26)로 구조가 드러난다.
    """

    def test_fragments_group_by_their_source_path(self):
        concepts = [_c("w#a", "w"), _c("w#b", "w"), _c("w#c", "w")]
        bodies = {"w#a": [{"key": "planning/backlog/x#s|content"}],
                  "w#b": [{"key": "planning/backlog/y#s|content"}],
                  "w#c": [{"key": "lib/hooks/z#s|content"}]}
        m = vm.build_map_model(concepts, [], bodies)
        self.assertEqual(m["axis"], "origin")
        self.assertEqual([(g["name"], g["concepts"]) for g in m["groups"]],
                         [("planning/backlog", 2), ("lib/hooks", 1)])

    def test_dotted_code_symbols_group_the_same_way(self):
        """코드 조각 키는 `engine.structure_app.run_prep`처럼 점으로 온다."""
        concepts = [_c("l#a", "l"), _c("l#b", "l")]
        bodies = {"l#a": [{"key": "engine.structure_app.run_prep|signature"}],
                  "l#b": [{"key": "engine.structure_app.fold_plan|signature"}]}
        m = vm.build_map_model(concepts, [], bodies)
        self.assertEqual([g["name"] for g in m["groups"]], ["engine/structure_app"])

    def test_a_concept_is_homed_where_most_of_its_fragments_are(self):
        concepts = [_c("w#a", "w")]
        bodies = {"w#a": [{"key": "lib/api/x#s|content"},
                          {"key": "planning/backlog/y#s|content"},
                          {"key": "planning/backlog/z#s|content"}]}
        m = vm.build_map_model(concepts, [], bodies)
        self.assertEqual(m["groups"][0]["name"], "planning/backlog")

    def test_quote_fragments_carry_no_origin_and_do_not_decide_a_home(self):
        """`quote` 조각은 출처 경로가 없다 — 있는 걸로 치면 전 개념이 한 무리가 된다."""
        concepts = [_c("w#a", "w")]
        bodies = {"w#a": [{"key": "quote"}, {"key": "quote"},
                          {"key": "lib/api/x#s|content"}]}
        m = vm.build_map_model(concepts, [], bodies)
        self.assertEqual(m["groups"][0]["name"], "lib/api")

    def test_a_concept_with_no_traceable_origin_is_named_as_such(self):
        concepts = [_c("w#a", "w"), _c("w#b", "w")]
        bodies = {"w#a": [{"key": "quote"}], "w#b": [{"key": "lib/api/x#s|content"}]}
        m = vm.build_map_model(concepts, [], bodies)
        homeless = [g for g in m["groups"] if g["name"] == vm.NO_ORIGIN][0]
        self.assertEqual([c["anchor"] for c in homeless["children"]], ["w#a"])

    def test_scope_still_wins_when_the_corpus_declares_one(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("kms#a", "p/t/kms")]
        bodies = {"inv#a": [{"key": "planning/x#s|content"}]}
        self.assertEqual(vm.build_map_model(concepts, [], bodies)["axis"], "scope")


class TestWeight(unittest.TestCase):
    """칸 크기가 같으면 지도가 아니라 표다 — 양을 눈으로 읽게 무게를 모델이 낸다."""

    def test_weight_is_relative_to_the_biggest_node(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("kms#b", "p/t/kms")]
        bodies = {"inv#a": [{"key": f"k{i}"} for i in range(10)], "kms#b": [{"key": "z"}]}
        m = vm.build_map_model(concepts, [], bodies)
        w = {a["name"]: a["weight"] for g in m["groups"] for a in g["children"]}
        self.assertEqual(w["inv"], 1.0)
        self.assertLess(w["kms"], 1.0)
        self.assertGreater(w["kms"], 0.0)

    def test_a_node_with_no_fragments_still_has_a_floor(self):
        """조각 0인 갈래를 0폭으로 그리면 사라진다 — 비었다는 사실이 지도의 값어치다."""
        concepts = [_c("inv#a", "p/t/inv"), _c("kms#b", "p/t/kms")]
        bodies = {"inv#a": [{"key": "k"}]}
        m = vm.build_map_model(concepts, [], bodies)
        kms = [a for g in m["groups"] for a in g["children"] if a["name"] == "kms"][0]
        self.assertGreater(kms["weight"], 0.0)

    def test_all_equal_sizes_give_all_equal_weights(self):
        concepts = [_c("inv#a", "p/t/inv"), _c("kms#b", "p/t/kms")]
        bodies = {"inv#a": [{"key": "k"}], "kms#b": [{"key": "z"}]}
        m = vm.build_map_model(concepts, [], bodies)
        ws = {a["weight"] for g in m["groups"] for a in g["children"]}
        self.assertEqual(ws, {1.0})

    def test_the_biggest_group_comes_first_so_the_eye_lands_there(self):
        concepts = [_c("a#1", "p/aaa/a"), _c("b#1", "p/zzz/b"), _c("b#2", "p/zzz/b")]
        m = vm.build_map_model(concepts, [], {})
        self.assertEqual([g["name"] for g in m["groups"]], ["zzz", "aaa"],
                         "알파벳이 아니라 크기 순 — 눈이 큰 데 먼저 닿아야 한다")

    def test_weight_compares_across_groups_not_only_inside_one(self):
        """무리마다 따로 재면 작은 무리의 칸이 큰 무리의 칸보다 커 보인다(실측: 작은 무리의
        칸이 몇 배 큰 무리의 칸보다 컸다). 한 코퍼스 안에서는 한 자로 잰다."""
        concepts = [_c("inv#a", "p/big/inv"), _c("m#a", "p/small/meadow")]
        bodies = {"inv#a": [{"key": f"k{i}"} for i in range(80)],
                  "m#a": [{"key": f"z{i}"} for i in range(12)]}
        m = vm.build_map_model(concepts, [], bodies)
        w = {a["name"]: a["weight"] for g in m["groups"] for a in g["children"]}
        self.assertEqual(w["inv"], 1.0)
        self.assertLess(w["meadow"], 0.3, "12/80 — 작은 갈래는 작게 보여야 한다")
