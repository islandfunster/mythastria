"""MAPGEN-02 (GM 2026-10-26: goal 19, "Indoor maps and dungeons from your preferences", "in LM Studio"): the site maps
(tools/site_maps.py). The model's design is given here, so no model runs: the design check, the builder, the map check
(walls whole squares, doors in walls, every room walked to, passages a square wide), the files and the service route."""
import copy, json, random, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import site_maps as M  # noqa: E402
import map_import  # noqa: E402

LIB = {"Goblin Warrior": {"hp": 10, "ac": 15, "speed": "30 ft.", "space": 5, "size": "Small", "init": 12},
       "Ogre": {"hp": 68, "ac": 11, "speed": "40 ft.", "space": 10, "size": "Large", "init": 8}}

DESIGN = {"name": "The Hollow Bell", "summary": "An old bell-founders' vault, now held by goblins.", "entrance": "R1", "lair": "R6",
          "rooms": [
              {"id": "R1", "name": "Gate", "level": 1, "purpose": "entrance", "size": "small", "shape": "built", "description": "A rusted gate.", "features": ["brazier"]},
              {"id": "R2", "name": "Guard post", "level": 1, "purpose": "guardroom", "size": "small", "shape": "built", "description": "Dice on a table.", "features": ["table", "chair", "weapon_rack"]},
              {"id": "R3", "name": "Casting hall", "level": 1, "purpose": "hall", "size": "large", "shape": "built", "description": "A huge cracked bell.", "features": ["bell", "anvil", "brazier", "pool"]},
              {"id": "R4", "name": "Store", "level": 1, "purpose": "storage", "size": "medium", "shape": "built", "description": "Crates.", "features": ["crate", "barrel", "sacks"]},
              {"id": "R5", "name": "Drip cave", "level": 2, "purpose": "cavern", "size": "medium", "shape": "natural", "description": "Water drips.", "features": ["stalagmite", "mushrooms"]},
              {"id": "R6", "name": "Boss den", "level": 2, "purpose": "lair", "size": "medium", "shape": "natural", "description": "Bones and a throne.", "features": ["throne", "bones", "chest"]}],
          "connections": [
              {"from": "R1", "to": "R2", "kind": "door", "length": "short"},
              {"from": "R2", "to": "R3", "kind": "archway", "length": "long"},
              {"from": "R3", "to": "R4", "kind": "locked door", "length": "short"},
              {"from": "R4", "to": "R1", "kind": "door", "length": "long"},
              {"from": "R3", "to": "R5", "kind": "stairs", "length": "short"},
              {"from": "R5", "to": "R6", "kind": "archway", "length": "short"}]}


def prefs(**kw):
    return M.check_prefs(dict({"kind": "dungeon", "levels": 2, "seed": 3}, **kw))


def built(design=DESIGN, **kw):
    p = prefs(**kw)
    d, fixes = M.check_design(copy.deepcopy(design), p)
    return M.build(d, p, "Goblin Warrior", 4, LIB, model="test", where="Place 4"), d, fixes


def random_design(seed):
    """A design such as a model might send: 4-15 rooms on 1-3 levels, joined any old way (some rooms left out)."""
    r = random.Random(seed)
    levels = r.randint(1, 3)
    rooms = [{"id": "R%d" % (i + 1), "name": "Room %d" % (i + 1), "level": 1 if i == 0 else r.randint(1, levels),
              "purpose": r.choice(M.PURPOSES), "size": r.choice(list(M.ROOM_SIZES)), "shape": r.choice(("built", "natural")),
              "description": "A room.", "features": r.sample(M.FEATURES, r.randint(0, 6))} for i in range(r.randint(4, 15))]
    links = []
    for i in range(1, len(rooms)):
        if r.random() < .85:
            j = r.randrange(i)
            links.append({"from": rooms[j]["id"], "to": rooms[i]["id"], "kind": r.choice(M.LINKS), "length": r.choice(("short", "long"))})
    for _ in range(r.randint(0, 3)):
        a, b = r.sample(rooms, 2)
        links.append({"from": a["id"], "to": b["id"], "kind": r.choice(M.LINKS), "length": "long"})
    return {"name": "Site %d" % seed, "summary": "", "entrance": "R1", "lair": rooms[-1]["id"], "rooms": rooms,
            "connections": links}, levels


class Design(unittest.TestCase):
    def test_a_good_design_is_kept_as_it_is(self):
        d, fixes = M.check_design(copy.deepcopy(DESIGN), prefs())
        self.assertEqual(fixes, [])
        self.assertEqual((d["entrance"], d["lair"], d["levels"], len(d["rooms"]), len(d["connections"])), ("R1", "R6", 2, 6, 6))

    def test_what_is_changed_is_said(self):
        raw = copy.deepcopy(DESIGN)
        raw["rooms"].append({"id": "R7", "name": "Lost room", "level": 2, "purpose": "empty", "size": "small",
                             "shape": "built", "description": "Dust.", "features": ["throne", "a dragon"]})
        raw["connections"] += [{"from": "R6", "to": "R99", "kind": "door", "length": "short"},
                               {"from": "R1", "to": "R5", "kind": "door", "length": "short"}]
        d, fixes = M.check_design(raw, prefs())
        text = " ".join(fixes)
        self.assertIn("R6 - R99 names no room", text)
        self.assertIn("R1 and R5 are on different levels: they are joined by stairs", text)
        self.assertIn("Room R7 (Lost room) had no way in on its level: Mythastria added a passage", text)
        self.assertEqual(next(r for r in d["rooms"] if r["id"] == "R7")["features"], ["throne"])

    def test_repeated_features_and_a_pool_room(self):
        """Seen from gemma-4-12b-qat on 2026-10-27: six beds in a small alcove; a room for a spring with no pool."""
        raw = copy.deepcopy(DESIGN)
        raw["rooms"][3]["features"] = ["bed"] * 6
        raw["rooms"][4]["purpose"] = "pool"
        d, fixes = M.check_design(raw, prefs())
        self.assertEqual(d["rooms"][3]["features"], ["bed", "bed"])
        self.assertIn("pool", d["rooms"][4]["features"])
        self.assertIn("Room R4 listed the same feature again and again; each is kept at most twice.", fixes)
        self.assertIn("Room R5 is a pool: it has one.", fixes)
        self.assertEqual(M.build(d, prefs(), "Goblin Warrior", 4, LIB)[1]["zones"][0]["kind"], "water")

    def test_nothing_usable_is_an_error_never_a_scripted_map(self):
        for raw in (None, [], {}, {"rooms": []}, {"rooms": [{"id": "R1", "name": "Alone", "level": 1}]}):
            with self.assertRaises(M.SiteMapError) as e:
                M.check_design(raw, prefs())
            self.assertIn("nothing usable", str(e.exception))

    def test_levels_are_joined_by_stairs(self):
        raw = copy.deepcopy(DESIGN)
        raw["connections"] = [c for c in raw["connections"] if c["kind"] != "stairs"]
        raw["rooms"][4]["level"] = 5
        d, fixes = M.check_design(raw, prefs())
        self.assertIn("Room R5 was on level 5; it is on level 2.", fixes)
        self.assertTrue(any(c["kind"] == "stairs" for c in d["connections"]))
        self.assertTrue(any(f.startswith("Level 2 had no stairs down to it") for f in fixes))

    def test_the_preferences(self):
        for bad in ({"kind": "castle"}, {"levels": 4}, {"seed": 0}, {"theme": "x" * 301}, {"colour": "red"}):
            with self.assertRaises(M.SiteMapError):
                M.check_prefs(bad)
        msgs = M.prompt(prefs(theme="a drowned  bell foundry", kind="ruin"), M.check_context({"terrain": "hills", "river": True}))
        self.assertIn("Design a ruin: 7 to 10 rooms in all, on 2 levels.", msgs[1]["content"])
        self.assertIn("hills terrain, a temperate climate, a river nearby", msgs[1]["content"])
        self.assertIn("a drowned bell foundry", msgs[1]["content"])
        self.assertIn("original names only", msgs[0]["content"])


class Builder(unittest.TestCase):
    def test_every_level_passes_the_map_check(self):
        levels, d, _ = built()
        self.assertEqual([sc["site"]["level"] for sc in levels], [1, 2])
        for sc in levels:
            self.assertEqual(M.check_map(sc), [], sc["map_name"])
            self.assertEqual(sc["lighting"]["ambient"], "dark")
            self.assertTrue(sc["wall_cells"], "walls are squares, drawn as stone that fades past the edge")
        self.assertEqual(levels[0]["map_name"], "Place 4, map 3: The Hollow Bell, level 1")
        self.assertEqual(levels[0]["site"]["start"], "R1")
        self.assertEqual(levels[1]["site"]["start"], "R5", "level 2 starts where the stairs come down")
        self.assertEqual(levels[1]["site"]["creatures_in"], "R6", "the creatures wait in the model's lair")
        self.assertEqual(levels[1]["ground"], "dry", "natural caverns")
        self.assertEqual(levels[0]["ground"], "stone")

    def test_doors_sit_in_walls_and_locked_doors_are_locked(self):
        sc = built()[0][0]
        wall = set(map(tuple, sc["wall_cells"]))
        cols, rows = max(w[0] for w in wall) + 1, max(w[1] for w in wall) + 1
        kinds = [d["kind"] for d in sc["doorways"]]
        self.assertEqual(kinds.count("locked door"), 2, "both ends of the locked link")
        self.assertEqual(len(sc["locked_doors"]), 2)
        door_walls = [w for w in sc["walls"] if w.get("door")]
        self.assertEqual(len(door_walls), kinds.count("door") + kinds.count("locked door"))
        for d in sc["doorways"]:
            self.assertIsNotNone(map_import._door_face(tuple(d["square"]), wall, cols, rows), d)

    def test_every_room_is_walked_to(self):
        for sc in built()[0]:
            wall = set(map(tuple, sc["wall_cells"]))
            cols, rows = max(w[0] for w in wall) + 1, max(w[1] for w in wall) + 1
            floor = {(x, y) for x in range(cols) for y in range(rows)} - wall
            pc = next(c for c in sc["combatants"] if c.get("pc"))
            reach = M._walk(floor, (pc["x"], pc["y"]), floor)
            for r in sc["rooms"]:
                self.assertTrue(M._inside(r["rect"]) & set(reach), r["name"])
            foe = next(c for c in sc["combatants"] if not c.get("pc"))
            self.assertIn((foe["x"], foe["y"]), reach)

    def test_props_lights_stairs_notes_and_ceilings(self):
        one, two = built()[0]
        kinds = [p["kind"] for p in one["props"]]
        self.assertIn("bell", kinds); self.assertIn("weapon_rack", kinds)
        self.assertIn("The way in, from outside", [p["label"] for p in one["props"]])
        self.assertIn("Stairs down to level 2: Drip cave", [p["label"] for p in one["props"]])
        self.assertIn("Stairs up to level 1: Casting hall", [p["label"] for p in two["props"]])
        self.assertEqual(len(one["lighting"]["lights"]), 2, "two braziers")
        self.assertEqual(one["zones"][0]["kind"], "water", "the hall's pool")
        self.assertEqual({n["id"] for n in one["notes"]}, {"room-R1", "room-R2", "room-R3", "room-R4"})
        self.assertFalse(any(n["show_players"] for n in one["notes"]), "the GM's notes")
        self.assertIn("A huge cracked bell.", [c["description"] for c in one["ceilings"]])
        wall = set(map(tuple, one["wall_cells"]))
        for p in one["props"]:
            self.assertNotIn((p["x"], p["y"]), wall)

    def test_the_same_number_gives_the_same_map_another_number_another(self):
        a, b, c = built(seed=3)[0][0], built(seed=3)[0][0], built(seed=4)[0][0]
        self.assertEqual(a, b)
        self.assertNotEqual(a["wall_cells"], c["wall_cells"])

    def test_a_large_creature_fits(self):
        p = prefs()
        d, _ = M.check_design(copy.deepcopy(DESIGN), p)
        levels = M.build(d, p, "Ogre", 2, LIB)
        self.assertEqual(M.check_map(levels[1]), [])

    def test_many_designs_all_build_and_pass(self):
        for seed in range(1, 41):
            raw, levels = random_design(seed)
            p = M.check_prefs({"levels": levels, "seed": seed, "kind": "cave"})
            d, _ = M.check_design(raw, p)
            for sc in M.build(d, p, "Goblin Warrior", 4, LIB):
                self.assertEqual(M.check_map(sc), [], "design %d, %s" % (seed, sc["map_name"]))
                wall = set(map(tuple, sc["wall_cells"]))
                cols, rows = max(w[0] for w in wall) + 1, max(w[1] for w in wall) + 1
                self.assertLessEqual(max(cols, rows), M.MAX_SIDE)


class Check(unittest.TestCase):
    """check_map() refuses what breaks the rules: it is not a rubber stamp."""
    def setUp(self):
        self.sc = copy.deepcopy(built()[0][0])
        self.wall = set(map(tuple, self.sc["wall_cells"]))

    def test_a_line_wall_between_floor_squares(self):
        r = self.sc["rooms"][2]["rect"]                                 # the large hall: a line across its floor
        self.sc["walls"].append({"id": "thin", "points": [[r[0] + 1.5, r[1] - 0.5], [r[0] + 1.5, r[1] + 1.5]]})
        self.assertIn("Wall thin is a line between two floor squares: walls are whole squares.", M.check_map(self.sc))

    def test_a_room_nobody_can_reach(self):
        r = self.sc["rooms"][0]["rect"]                                 # wall up the gate's doorways and passages
        for d in self.sc["doorways"]:
            x, y = d["square"]
            if r[0] - 1 <= x <= r[2] + 1 and r[1] - 1 <= y <= r[3] + 1:
                self.wall.add((x, y))
        self.sc["wall_cells"] = sorted(map(list, self.wall))
        self.sc["doorways"] = [d for d in self.sc["doorways"] if tuple(d["square"]) not in self.wall]
        out = " ".join(M.check_map(self.sc))
        self.assertIn("cannot be walked to from the start", out)

    def test_squares_touching_only_at_a_corner_are_no_passage(self):
        cols, rows = max(w[0] for w in self.wall) + 1, max(w[1] for w in self.wall) + 1
        x, y = 1, 1                                                     # a floor square in the rock, corner to corner with nothing
        self.wall.discard((x, y)); self.wall.discard((x + 1, y + 1))
        self.sc["wall_cells"] = sorted(map(list, self.wall))
        self.assertIn("cannot be walked to", " ".join(M.check_map(self.sc)))
        self.assertLess(x + 1, cols); self.assertLess(y + 1, rows)

    def test_floor_on_the_edge_and_a_door_not_in_a_wall(self):
        self.wall.discard((0, 5))
        self.sc["wall_cells"] = sorted(map(list, self.wall))
        r = self.sc["rooms"][2]["rect"]
        self.sc["doorways"].append({"square": [r[0] + 1, r[1] + 1], "kind": "door"})
        out = " ".join(M.check_map(self.sc))
        self.assertIn("on the map's edge", out)
        self.assertIn("is not in a wall", out)


class Files(unittest.TestCase):
    def test_written_into_the_folder_tree(self):
        import scenario_folders
        levels = built()[0]
        with tempfile.TemporaryDirectory() as tmp:
            names = M.write(levels, "Isles campaign", "North Vale", "Place 4", Path(tmp) / "sites")
            self.assertEqual(names, ["sites/isles_campaign/north_vale/place_4_the_hollow_bell_3_level_1.json",
                                     "sites/isles_campaign/north_vale/place_4_the_hollow_bell_3_level_2.json"])
            self.assertEqual(scenario_folders.folder_of(names[0]), ["Region sites", "Isles Campaign", "North Vale"])
            self.assertEqual((Path(tmp) / "sites" / ".gitignore").read_text(), "*\n", "made at the table, not in git")
            sc = json.loads((Path(tmp) / names[1]).read_text(encoding="utf-8"))
            self.assertEqual(sc["site"]["level"], 2)


class Model(unittest.TestCase):
    """The model's side, with no model: what is sent, and what the GM is told when it fails."""
    def test_only_a_model_on_this_pc(self):
        with self.assertRaises(M.SiteMapError) as e:
            M.ask_model(prefs(), M.check_context({}), llm_url="https://api.example.com/v1")
        self.assertIn("not on this PC", str(e.exception))

    def _reply(self, content, finish="stop"):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return json.dumps({"model": "gemma", "choices": [{"message": {"content": content}, "finish_reason": finish}],
                                            "usage": {"prompt_tokens": 500, "completion_tokens": 900}}).encode()
        sent = []

        def fake(req, timeout=None):
            sent.append(json.loads(req.data.decode()))
            return R()
        return fake, sent

    def test_the_request_and_a_good_reply(self):
        fake, sent = self._reply("```json\n" + json.dumps(DESIGN) + "\n```")
        real, M.urlopen = M.urlopen, fake
        try:
            raw, facts = M.ask_model(prefs(), M.check_context({"terrain": "mountains"}))
        finally:
            M.urlopen = real
        self.assertEqual(raw["name"], "The Hollow Bell")
        self.assertEqual((facts["model"], facts["completion_tokens"]), ("gemma", 900))
        body = sent[0]
        self.assertEqual(body["model"], M.MODEL)
        self.assertEqual(body["seed"], 3)
        self.assertEqual(body["response_format"]["json_schema"]["schema"], M.DESIGN_SCHEMA)

    def test_a_reply_that_is_not_a_design(self):
        for content, finish, words in (("I cannot help with that.", "stop", "not a JSON design"),
                                       ('{"name": "The', "length", "ran out of room")):
            fake, _ = self._reply(content, finish)
            real, M.urlopen = M.urlopen, fake
            try:
                with self.assertRaises(M.SiteMapError) as e:
                    M.ask_model(prefs(), M.check_context({}))
            finally:
                M.urlopen = real
            self.assertIn("The model gave nothing usable", str(e.exception))
            self.assertIn(words, str(e.exception))

    def test_no_server(self):
        def down(req, timeout=None):
            raise M.URLError("connection refused")
        real, M.urlopen = M.urlopen, down
        try:
            with self.assertRaises(M.SiteMapError) as e:
                M.ask_model(prefs(), M.check_context({}))
        finally:
            M.urlopen = real
        self.assertIn("is not answering", str(e.exception))
        self.assertIn("LM Studio", str(e.exception))


class Route(unittest.TestCase):
    def test_the_service_route(self):
        import sim_service as S
        service = S.Service()
        with tempfile.TemporaryDirectory() as tmp:
            service.scenarios_dir, service.notes_dir = Path(tmp) / "scenarios", Path(tmp) / "notes"
            asked = []
            service.site_designer = lambda p, c: (asked.append((p, c)) or (copy.deepcopy(DESIGN), {"model": "stand-in"}))
            S.creature_names()["Goblin Warrior"]                       # the real library: the route checks the creature
            code, out = service.site_map({"prefs": {"kind": "dungeon", "levels": 2, "seed": 9}, "context": {"terrain": "hills"},
                                          "creature": "Goblin Warrior", "count": 3, "project": "Campaign", "region": "Vale",
                                          "place": "Place 2"})
            self.assertEqual(code, 200)
            self.assertEqual(out["scenarios"][0], "sites/campaign/vale/place_2_the_hollow_bell_9_level_1.json")
            self.assertEqual((out["levels"], out["rooms"], out["fixes"]), (2, 6, []))
            self.assertEqual(asked[0][1]["terrain"], "hills")
            notes = json.loads(service._notes_file({"map": "Place 2, map 9: The Hollow Bell, level 1"}).read_text(encoding="utf-8"))
            self.assertEqual(len(notes["notes"]), 4)
            service.site_designer = lambda p, c: ({"rooms": []}, {"model": "stand-in"})
            with self.assertRaises(ValueError) as e:
                service.site_map({"prefs": {}, "creature": "Goblin Warrior", "count": 3})
            self.assertIn("nothing usable", str(e.exception))
            service.llm_url = "http://127.0.0.1:9/v1"                  # nothing listens on the discard port
            code, out = service.site_model({})
            self.assertFalse(out["ready"])
            self.assertIn("start LM Studio", out["why"])


if __name__ == "__main__":
    unittest.main()
