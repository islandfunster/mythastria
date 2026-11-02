"""VIEW-01 (GM 2026-10-20: "map imports from Dungeondraft and similar tools"; "not their code, of course"): our own reader
for the published Universal VTT format (.dd2vtt / .uvtt), tools/map_import.py, turning a file into a Mythastria map."""
import base64, json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import map_import as mi


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def sample(**over):
    u = {"format": 0.3,
         "resolution": {"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 6, "y": 4}, "pixels_per_grid": 64},
         "line_of_sight": [[{"x": 0, "y": 0}, {"x": 6, "y": 0}, {"x": 6, "y": 4}]],
         "objects_line_of_sight": [[{"x": 3, "y": 2}, {"x": 3, "y": 4}]],
         "portals": [{"position": {"x": 3, "y": 1}, "bounds": [{"x": 3, "y": 0}, {"x": 3, "y": 2}], "rotation": 0,
                      "closed": True, "freestanding": False}],
         "environment": {"baked_lighting": False, "ambient_light": "202020ff"},
         "lights": [{"position": {"x": 1.5, "y": 1.5}, "range": 4, "intensity": 1, "color": "ffeeccff", "shadows": True}],
         "image": base64.b64encode(PNG).decode()}
    u.update(over)
    return u


class Convert(unittest.TestCase):
    lib = {"Goblin": {"name": "Goblin", "hp": 7, "ac": 15, "speed": "30 ft.", "actions": [{"id": "1", "name": "Scimitar"}],
                      "xp": 50, "cr": "1/4", "source": "x", "init": 10}}

    def convert_cells(self, cells):
        return mi.convert(sample(resolution={"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 7, "y": 5},
                                             "pixels_per_grid": 64}), name="Squares", party_at=(1, 1), creature="Goblin",
                          count=1, foes_at=(5, 3), lib=self.lib, cells=cells)

    def convert(self, u=None, **kw):
        args = dict(name="Bell Cove Remade!", party_at=(1, 1), creature="Goblin", count=2, foes_at=(4, 2), lib=self.lib)
        args.update(kw)
        return mi.convert(u or sample(), **args)

    def test_walls_doors_lights_light_and_picture(self):
        sc, image, ext = self.convert()
        walls = [w for w in sc["walls"] if not w.get("door")]
        self.assertIn([[-0.5, -0.5], [5.5, -0.5]], [w["points"] for w in walls])         # grid units -> square edges
        self.assertIn([[2.5, 1.5], [2.5, 3.5]], [w["points"] for w in walls])            # objects block sight too
        door = next(w for w in sc["walls"] if w.get("door"))
        self.assertEqual(door["points"], [[2.5, -0.5], [2.5, 1.5]])
        self.assertNotIn(door["id"], sc["open_doors"])                                   # closed
        self.assertEqual(sc["lighting"]["ambient"], "dark")
        light = sc["lighting"]["lights"][0]
        self.assertEqual((light["x"], light["y"], light["dim_ft"], light["bright_ft"]), (1.0, 1.0, 20, 10))
        self.assertEqual((image, ext), (PNG, "png"))
        self.assertEqual(sc["background"], {"src": "maps/imported/bell_cove_remade.png", "cols": 6, "rows": 4})

    def test_party_and_creatures_where_the_gm_said(self):
        sc, _, _ = self.convert()
        pcs = [c for c in sc["combatants"] if c.get("pc")]
        foes = [c for c in sc["combatants"] if c.get("side") == "foe"]
        self.assertEqual([c["name"] for c in pcs], mi.PARTY)
        self.assertEqual((pcs[0]["x"], pcs[0]["y"]), (1, 1))
        self.assertEqual([(c["name"], c["x"], c["y"]) for c in foes][:1], [("Goblin 1", 4, 2)])
        self.assertEqual(len(foes), 2)
        self.assertEqual(len({(c["x"], c["y"]) for c in sc["combatants"]}), len(sc["combatants"]))   # no two on a square
        self.assertEqual(sc["aware"], [c["id"] for c in foes])

    def test_bright_maps_open_doors_and_offsets(self):
        u = sample(environment={"baked_lighting": True, "ambient_light": "ffffffff"}, resolution={
            "map_origin": {"x": 2, "y": 1}, "map_size": {"x": 6, "y": 4}, "pixels_per_grid": 64})
        u["portals"][0]["closed"] = False
        sc, _, _ = self.convert(u)
        self.assertEqual(sc["lighting"]["ambient"], "bright")
        door = next(w for w in sc["walls"] if w.get("door"))
        self.assertIn(door["id"], sc["open_doors"])
        self.assertEqual(door["points"], [[0.5, -1.5], [0.5, 0.5]])                     # the map origin is subtracted

    def test_bad_files_are_refused_with_a_reason(self):
        for bad, why in ((sample(resolution={}), "resolution"), (sample(image="bm90IGFuIGltYWdl"), "picture"),
                         (sample(resolution={"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 900, "y": 4}, "pixels_per_grid": 64}), "size"),
                         ("not a dict", "Universal VTT")):
            with self.assertRaises(mi.ImportError_) as e:
                mi.convert(bad, name="x", party_at=(1, 1), creature="Goblin", count=1, foes_at=(4, 2), lib=self.lib)
            self.assertIn(why, str(e.exception))
        with self.assertRaises(mi.ImportError_):
            self.convert(creature="Tarrasque")                                           # not a known creature
        with self.assertRaises(mi.ImportError_):
            self.convert(party_at=(40, 1))                                               # off the map

    def test_the_table_gets_the_picture(self):
        import sim_messages
        sc, _, _ = self.convert()
        self.assertEqual(sim_messages.map_part(sc)["background"], sc["background"])

    def test_slugs_are_safe(self):
        self.assertEqual(mi.slug("../../Evil Map!!"), "evil_map")
        self.assertEqual(mi.slug("???"), "map")

    def test_write_puts_the_files_in_their_folders(self):
        sc, image, ext = self.convert()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            name = mi.write(sc, image, ext, scenarios_dir=Path(a), table_dir=Path(b))
            self.assertEqual(name, "imported/bell_cove_remade.json")
            self.assertTrue((Path(a) / "imported" / "bell_cove_remade.json").is_file())
            self.assertEqual((Path(b) / "maps" / "imported" / "bell_cove_remade.png").read_bytes(), PNG)


def room(cols=7, rows=5, door=None):
    """A 7 x 5 map: a ring of wall squares round a 5 x 3 floor; with door=(x, y): a wall column at x=3 and its doorway."""
    wall = [[x, y] for y in range(rows) for x in range(cols) if x in (0, cols - 1) or y in (0, rows - 1)]
    doors = []
    if door:
        wall += [[3, y] for y in range(1, rows - 1) if (3, y) != tuple(door)]
        doors = [list(door)]
    return {"wall": wall, "door": doors}


class Squares(unittest.TestCase):
    """MAP RULE (GM 2026-10-20: walls "a minimum of 5 feet wide"; "this is a rule for map building") and the grid tools
    (GM: "maps will need a grid aligment tool ... the grid will need to be created by hand by a survey tool"): an
    imported map's walls are the squares the GM paints (drafted first), never thin lines."""

    def test_walls_follow_the_painted_squares(self):
        walls = mi.cell_walls(7, 5, room()["wall"], [])
        self.assertEqual(sorted(w["points"] for w in walls), sorted([
            [[0.5, 0.5], [5.5, 0.5]], [[0.5, 3.5], [5.5, 3.5]],          # the floor's top and bottom edges
            [[0.5, 0.5], [0.5, 3.5]], [[5.5, 0.5], [5.5, 3.5]]]))         # its left and right edges

    def test_a_doorway_square_carries_the_door(self):
        walls = mi.cell_walls(7, 5, room(door=(3, 2))["wall"], [[3, 2]])
        door = [w for w in walls if w.get("door")]
        self.assertEqual([d["points"] for d in door], [[[2.5, 1.5], [2.5, 2.5]]])    # across the doorway, on its west face
        plain = [w["points"] for w in walls if not w.get("door")]
        self.assertNotIn([[2.5, 1.5], [2.5, 2.5]], plain)
        self.assertNotIn([[3.5, 1.5], [3.5, 2.5]], plain)                              # its east face opens on the floor

    def test_the_rule_is_checked(self):
        self.assertEqual(mi.rule_problems(7, 5, room()["wall"], []), [])
        open_edge = [c for c in room()["wall"] if c != [0, 2]]
        self.assertIn("floor on the map's edge", " ".join(mi.rule_problems(7, 5, open_edge, [])))
        self.assertIn("not in a wall", " ".join(mi.rule_problems(7, 5, room()["wall"], [[2, 2]])))
        self.assertIn("no floor", " ".join(mi.rule_problems(3, 3, [[x, y] for x in range(3) for y in range(3)], [])))

    def test_a_dungeondraft_file_is_drafted_into_squares(self):
        u = sample(line_of_sight=[[{"x": 1, "y": 1}, {"x": 5, "y": 1}, {"x": 5, "y": 3}, {"x": 1, "y": 3}, {"x": 1, "y": 1}],
                                  [{"x": 3, "y": 1}, {"x": 3, "y": 2}]],
                   objects_line_of_sight=[],
                   portals=[{"bounds": [{"x": 3, "y": 2}, {"x": 3, "y": 3}], "closed": True}])
        d = mi.draft(u)
        self.assertEqual((d["cols"], d["rows"]), (6, 4))
        wall = {tuple(c) for c in d["wall"]}
        self.assertTrue({(0, 0), (5, 0), (0, 3), (5, 3), (0, 1)} <= wall)            # outside the outer wall: rock
        self.assertNotIn((1, 1), wall)                                                 # inside: floor
        self.assertIn((3, 1), wall)                                                    # a line wall becomes a square
        self.assertEqual(d["door"], [[3, 2]])                                          # and a door its doorway
        self.assertTrue(d["notes"])

    def test_painted_squares_make_the_map(self):
        sq = room(door=(3, 2))
        sc, _, _ = Convert().convert_cells(sq)
        self.assertEqual(sorted(sc["wall_cells"]), sorted(sq["wall"]))
        self.assertEqual([w["id"] for w in sc["walls"] if w.get("door")], ["door 1"])
        self.assertEqual(sc["open_doors"], [])
        with self.assertRaises(mi.ImportError_) as e:
            Convert().convert_cells({"wall": [c for c in sq["wall"] if c != [0, 2]], "door": sq["door"]})
        self.assertIn("edge", str(e.exception))

    def test_a_picture_alone_with_the_gms_grid(self):
        grid = {"px": 64, "ox": 32, "oy": 16, "width": 32 + 64 * 7 + 10, "height": 16 + 64 * 5 + 40}
        sc, image, ext = mi.convert_picture(PNG, grid, room(door=(3, 2)), name="Hand Drawn", party_at=(1, 1),
                                            creature="Goblin", count=1, foes_at=(5, 3), lib=Convert.lib, ambient="dark")
        self.assertEqual((sc["background"]["cols"], sc["background"]["rows"]), (7, 5))
        self.assertEqual((sc["background"]["x"], sc["background"]["y"]), (-0.5, -0.25))   # the picture's corner in squares
        self.assertAlmostEqual(sc["background"]["w"], 490 / 64)
        self.assertEqual(sc["lighting"], {"ambient": "dark", "lights": []})
        self.assertEqual(ext, "png")
        for bad in ({"px": 3}, {"px": 64, "ox": -1}, {"px": 64, "width": 64 * 300, "height": 64}):
            with self.assertRaises(mi.ImportError_):
                mi.convert_picture(PNG, dict(grid, **bad), room(), name="x", party_at=(1, 1), creature="Goblin",
                                   count=1, foes_at=(5, 3), lib=Convert.lib, ambient="dark")


class Plays(unittest.TestCase):
    def test_an_imported_map_plays_in_the_simulator(self):
        import creature_threat, encounter_tuner
        lib = creature_threat.library()
        sc, _, _ = mi.convert(sample(environment={"baked_lighting": True, "ambient_light": "ffffffff"}), name="tiny",
                              party_at=(0, 1), creature="Skeleton", count=1, foes_at=(5, 1), lib=lib)
        sc = encounter_tuner.with_party(sc, mi.PARTY, 1)
        r = encounter_tuner.simulate(sc, [1], 3, instant=True)
        self.assertEqual(r["runs"], 1)
        self.assertEqual(r["issues"], 0)


if __name__ == "__main__":
    unittest.main()
