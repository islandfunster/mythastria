"""REMIX-01, Add a creature (GM 2026-10-21: "Training doesn't have a way to populate the combat table"): the quick remix
(tools/remix.py) adds SRD 5.2.1 creatures to a map's fight on free floor near the foe start or a clicked square."""
import copy, json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import remix, creature_threat

DEN = ROOT / "sim" / "scenarios" / "test/goblin_den_2024.json"


class AddCreature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = creature_threat.library()

    def setUp(self):
        self.sc = json.loads(DEN.read_text(encoding="utf-8"))

    def added(self, out, name):
        return [c for c in out["combatants"] if remix.base_name(c["name"]) == name]

    def test_two_wolves_join_the_goblins_near_the_foe_start(self):
        before = copy.deepcopy(self.sc)
        out = remix.apply(self.sc, {"seed": 1, "add": [{"name": "Wolf", "count": 2}]}, self.lib)
        self.assertEqual(self.sc, before)                       # the map itself never changes
        wolves = self.added(out, "Wolf")
        self.assertEqual([w["name"] for w in wolves], ["Wolf 1", "Wolf 2"])
        self.assertTrue(all(w["side"] == "foe" and w["x"] > 5.5 for w in wolves))   # the goblins' side of the wall
        squares = [(round(c["x"]), round(c["y"])) for c in out["combatants"]]
        self.assertEqual(len(squares), len(set(squares)))
        self.assertEqual(len(self.added(out, "Goblin Warrior")), 2)

    def test_a_clicked_square_and_a_change_together(self):
        out = remix.apply(self.sc, {"changes": [{"from": "Goblin Warrior", "to": "Wolf", "count": 2}],
                                    "add": [{"name": "Wolf", "count": 1, "at": [3, 3]}]}, self.lib)
        wolves = self.added(out, "Wolf")
        self.assertEqual(sorted(w["name"] for w in wolves), ["Wolf 1", "Wolf 2", "Wolf 3"])
        self.assertIn((3, 3), [(w["x"], w["y"]) for w in wolves])

    def test_refusals(self):
        for bad in ({"add": [{"name": "Not A Creature", "count": 1}]}, {"add": [{"name": "Wolf", "count": 0}]},
                    {"add": [{"name": "Wolf", "count": 13}]}, {"add": [{"name": "Wolf", "count": 1, "at": [99, 1]}]},
                    {"add": [{"name": "Wolf", "count": 12}, {"name": "Wolf", "count": 12}]}, {"add": []}):
            with self.assertRaises(ValueError):
                remix.apply(self.sc, bad, self.lib)

    def test_the_offer_says_where_added_creatures_start(self):
        self.assertEqual(remix.foe_start(self.sc), [10, 2])   # MAP RULE 2026-10-24: the thick-walled den


if __name__ == "__main__":
    unittest.main()
