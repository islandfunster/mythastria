"""THREAT-02 (2026-10-20, GM: "make sure creatures can use our interpreted (homebrew) squeeze rule"): with every SRD
creature in the library, Large and bigger creatures appear on maps built without a hand-placed token: Import map, the
region map's terrain battles and the threat arenas. Their tokens sit as the simulator and the bridge expect (a Large
token on a grid corner: x.5; Huge on a square centre), their whole space free, and they move by the route planner,
the one that knows their space and HR-SQUEEZE, on open ground too (ai_turn._melee_move)."""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import map_import as mi  # noqa: E402

_LIB = None


def lib():
    global _LIB
    if _LIB is None:
        import creature_threat
        _LIB = creature_threat.library()
    return _LIB


def cells(c):
    """The squares a combatant's space covers, from its token centre."""
    s = max(1, int(round(float(c.get("space") or 5) / 5)))
    x0, y0 = c["x"] - (s - 1) / 2, c["y"] - (s - 1) / 2
    assert x0 == int(x0) and y0 == int(y0), (c["name"], c["x"], c["y"])        # on the size's own grid point
    return {(int(x0) + i, int(y0) + j) for i in range(s) for j in range(s)}


def check_spaces(test, sc, blocked=()):
    seen = set()
    for c in sc["combatants"]:
        mine = cells(c)
        test.assertFalse(mine & seen, "%s overlaps another space" % c["name"])
        test.assertFalse(mine & set(blocked), "%s starts in a blocked square" % c["name"])
        seen |= mine


class Spaces(unittest.TestCase):
    def test_free_spaces_for_each_size(self):
        self.assertEqual(mi.spaces((5, 5), 1, 20, 20, set(), 1), [(5, 5)])
        large = mi.spaces((5, 5), 3, 20, 20, {(6, 6)}, 2)
        self.assertEqual(len(large), 3)
        for x, y in large:
            self.assertEqual((x % 1, y % 1), (0.5, 0.5))
        huge = mi.spaces((5, 5), 2, 20, 20, set(), 3)
        self.assertTrue(all(x == int(x) and y == int(y) for x, y in huge))
        self.assertEqual(mi.spaces((0, 0), 1, 1, 1, set(), 2), [])           # a 1x1 map holds no Large creature

    def test_import_map_places_large_creatures_whole(self):
        walls = {(3, 3), (4, 3)}
        sc = mi._scenario("t", 16, 12, [], [], {"ambient": "bright", "lights": []}, None, (1, 1), "Brown Bear", 4,
                          (8, 6), lib(), sorted(walls))
        check_spaces(self, sc, walls)
        self.assertEqual(sum(1 for c in sc["combatants"] if not c.get("pc")), 4)

    def test_terrain_battles_place_large_creatures_in_the_open(self):
        import terrain_battle as T
        for terrain, creature in (("forest", "Brown Bear"), ("hills", "Hill Giant"), ("forest", "Owlbear")):
            sc = T.build(terrain, creature, 3, lib(), seed=3)
            blocked = {(p["x"], p["y"]) for p in sc["props"] if p["kind"] == T.TERRAINS[terrain]["block"][0]}
            check_spaces(self, sc, blocked)

    def test_threat_arenas_place_large_creatures_on_corners(self):
        import creature_threat as ct
        for arena in ct.ARENAS:
            sc = ct.arena_scenario(arena, lib()["Brown Bear"], 2)
            check_spaces(self, sc)


class Fights(unittest.TestCase):
    def test_a_large_creature_reaches_and_attacks_on_open_ground(self):
        import creature_threat as ct, encounter_tuner as tuner, run_sim
        sc = tuner.with_party(ct.arena_scenario("open", lib()["Brown Bear"], 1), ct.PARTY, 1)
        sim = run_sim.Sim(sc, "scripted", True, 1, True, True)
        try:
            sim.run(3, 20)
        finally:
            sim.close()
        text = "\n".join(t for _, t in sim.lines)
        self.assertIn("Brown Bear 1 attacks", text)
        self.assertEqual((sim.stalls, sim.problems, sim.wall_crossings), (0, [], 0))


if __name__ == "__main__":
    unittest.main()
