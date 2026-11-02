"""RELEASE-01: play reads the SRD numbers from the file that ships with Mythastria, never from outside its folder.
  py -3 -m unittest test_srd_records
"""
import json, sys, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]
import bestiary_catalog as bc
import encounter_tuner as tuner
import run_sim


class Shipped(unittest.TestCase):
    def test_every_creature_is_there(self):
        records = bc.srd_records()
        self.assertGreater(len(records), 330)
        self.assertEqual(len({r["name"] for r in records}), len(records))

    def test_it_holds_numbers_and_defenses_not_stat_block_text(self):
        allowed = {"cr", "xp", "hd", "abilities", "damageimmunities", "damageresistances", "damagevulnerabilities"}
        for r in bc.srd_records():
            self.assertLessEqual(set(r["fields"]), allowed, r["name"])

    def test_play_never_opens_the_module(self):
        with mock.patch.object(bc, "load_srd", side_effect=AssertionError("read from outside")):
            run_sim._SRD_DEFENSES = None
            sc = run_sim.srd_defenses({"combatants": [{"name": "Ghost 1"}]})
            stats = tuner.srd_stats()
        self.assertIn("Necrotic", sc["combatants"][0]["damageimmunities"])
        self.assertIn("wis_save", sc["combatants"][0])
        self.assertEqual(stats["Goblin Warrior"]["xp"], 50)

    def test_an_encounter_has_its_xp(self):
        sc = json.loads((ROOT / "sim" / "scenarios" / "test" / "live_keep.json").read_text(encoding="utf-8"))
        self.assertEqual(tuner.rate(sc, tuner.srd_stats(), 4, 5)["xp"], 500)


if __name__ == "__main__":
    unittest.main()
