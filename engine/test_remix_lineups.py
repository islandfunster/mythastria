"""Remix Live, creature lineups (2026-10-21): the GM saves the creatures of a fight by name and loads them onto any map.
The service keeps them (sim/lineups/lineups.json); only SRD 5.2.1 library creatures, on saving and on loading."""
import json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import remix, creature_threat, sim_service

DEN = ROOT / "sim" / "scenarios" / "test/goblin_den_2024.json"


class Lineups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = creature_threat.library()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = sim_service.Service()
        self.service.lineups_file = Path(self.tmp.name) / "lineups" / "lineups.json"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, **req):
        return self.service.lineups(req)[1]

    def test_save_list_load_delete(self):
        self.assertEqual(self.call(op="list")["lineups"], [])
        out = self.call(op="save", name=" Wolf pack ", creatures=[{"name": "Wolf", "count": 1}, {"name": "Wolf", "count": 1},
                                                                   {"name": "Goblin Warrior", "count": 2}])
        [saved] = out["lineups"]
        self.assertEqual((saved["name"], saved["creatures"], saved["missing"]),
                         ("Wolf pack", [{"name": "Wolf", "count": 2}, {"name": "Goblin Warrior", "count": 2}], []))
        self.assertEqual(saved["xp"], 2 * self.lib["Wolf"]["xp"] + 2 * self.lib["Goblin Warrior"]["xp"])
        self.assertTrue(self.service.lineups_file.is_file())
        self.call(op="save", name="wolf PACK", creatures=[{"name": "Wolf", "count": 3}])     # the same name replaces it
        self.assertEqual(self.call(op="load", name="Wolf pack")["lineup"]["creatures"], [{"name": "Wolf", "count": 3}])
        self.assertEqual(self.call(op="delete", name="wolf pack")["lineups"], [])
        with self.assertRaises(ValueError):
            self.call(op="load", name="Wolf pack")

    def test_only_srd_library_creatures_are_saved(self):
        for bad in ([{"name": "Not A Creature", "count": 1}], [{"name": "Wolf", "count": 13}], [{"name": "Wolf", "count": 0}],
                    [], [{"name": n, "count": 1} for n in list(self.lib)[:13]],
                    [{"name": "Wolf", "count": 12}, {"name": "Goblin Warrior", "count": 12}, {"name": "Bandit", "count": 1}]):
            with self.assertRaises(ValueError):
                self.call(op="save", name="Bad", creatures=bad)
        for bad_name in ("", "x" * 41, "../up", None):
            with self.assertRaises(ValueError):
                self.call(op="save", name=bad_name, creatures=[{"name": "Wolf", "count": 1}])
        self.assertEqual(self.call(op="list")["lineups"], [])

    def test_a_name_no_longer_in_the_library_is_refused_on_loading(self):
        self.service.lineups_file.parent.mkdir(parents=True)
        self.service.lineups_file.write_text(json.dumps({"lineups": [
            {"name": "Old", "creatures": [{"name": "Wolf", "count": 1}, {"name": "Gone Beast", "count": 2}]}]}), encoding="utf-8")
        self.assertEqual(self.call(op="list")["lineups"][0]["missing"], ["Gone Beast"])
        with self.assertRaisesRegex(ValueError, "Gone Beast is no longer in the SRD 5.2.1 creature library"):
            self.call(op="load", name="Old")

    def test_a_lineup_replaces_another_maps_creatures(self):
        """What the panel sends after Load with Replace: every map kind to 0, the lineup's kinds added."""
        sc = json.loads(DEN.read_text(encoding="utf-8"))
        kinds = remix.encounter(sc, self.lib, 4, 1)["kinds"]
        lineup = remix.check_lineup([{"name": "Wolf", "count": 2}], self.lib)
        out = remix.apply(sc, {"seed": 1, "changes": [{"from": k["name"], "to": k["name"], "count": 0} for k in kinds],
                               "add": lineup}, self.lib)
        self.assertEqual(sorted(c["name"] for c in remix.foes(out)), ["Wolf 1", "Wolf 2"])


if __name__ == "__main__":
    unittest.main()
