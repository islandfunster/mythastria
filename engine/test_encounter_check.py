"""ENCOUNTER-CHECK-01 (GM 2026-10-28, tools/encounter_check.py): before a game the GM checks that the adventure's
encounters are winnable for the table's saved characters: a few simulated fights each, a verdict and the risk.
  py -3 -m unittest test_encounter_check
"""
import json, sys, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import encounter_check as ec, sim_service  # noqa: E402

RANGER = {"name": "Imported", "classes": [{"name": "Ranger", "level": 5}], "species": "Wood Elf",
          "abilities": {"str": 12, "dex": 18, "con": 14, "int": 10, "wis": 14, "cha": 8},
          "combat": {"hp_max": 44, "ac": 15, "speed": 35, "attack_bonus": 7, "damage_count": 1, "damage_die": 8,
                     "damage_bonus": 4, "reach": 5},
          "equipment": ["Longbow", "Shortsword"], "spells": ["Hunter's Mark", "Cure Wounds"], "features": ["Favored Enemy"]}
DEN = json.loads((ROOT / "sim" / "scenarios" / "test" / "goblin_den_2024.json").read_text(encoding="utf-8"))


def res(won, lost=0, timeout=0, dead=0, drops=0.0, stuck=0):
    return {"runs": won + lost + timeout, "won": won, "lost": lost, "timeout": timeout, "dead": dead,
            "drops_per_run": drops, "stuck": stuck, "avg_rounds": 3.0}


class Verdict(unittest.TestCase):
    def test_the_bands(self):
        self.assertEqual(ec.verdict(res(5)), "winnable")
        self.assertEqual(ec.verdict(res(5, drops=1.2)), "risky")
        self.assertEqual(ec.verdict(res(4, lost=1)), "risky")
        self.assertEqual(ec.verdict(res(5, dead=1)), "risky")
        self.assertEqual(ec.verdict(res(2, lost=3)), "deadly")
        self.assertEqual(ec.verdict(res(1, timeout=4)), "not rated")
        self.assertEqual(ec.verdict(res(0, lost=5, stuck=2)), "deadly")       # a stuck creature hides no clear result


class Job(unittest.TestCase):
    def test_each_encounter_gets_a_row_and_a_failure_is_said(self):
        def runner(payload):
            if payload["raw"] == "bad":
                raise RuntimeError("no map")
            return res(5)
        checks = ec.Checks(runner)
        job = checks.start([{"scenario": "a", "place": "A", "raw": {}}, {"scenario": "b", "place": "B", "raw": "bad"}],
                           [], 5, {"Imported": {}})
        for _ in range(100):
            if checks.view(job["id"])["status"] != "running":
                break
            time.sleep(0.05)
        out = checks.view(job["id"])
        self.assertEqual((out["status"], out["done"], out["of"]), ("complete", 2, 2))
        self.assertEqual([(r["place"], r["verdict"]) for r in out["results"]], [("A", "winnable"), ("B", "not rated")])
        self.assertIn("no map", out["results"][1]["error"])

    def test_the_service_needs_the_saved_characters(self):
        with self.assertRaisesRegex(ValueError, "saved characters"):
            sim_service.Service().check_encounters({"pack": "x", "characters": []})


class Fights(unittest.TestCase):
    def test_a_saved_character_fights_in_its_own_process(self):
        extra = sim_service.Service.saved_characters({"characters": [RANGER]}, [])
        r = ec.run_one({"raw": DEN, "party": list(extra), "level": 5, "extra": extra, "seeds": [1, 2], "rounds": 10})
        self.assertEqual(r["runs"], 2)
        self.assertGreater(r["won"] + r["lost"] + r["drops"], 0, r)                # the party is there and fights
        self.assertEqual(r["won"] + r["lost"] + r["timeout"], 2)
        self.assertIn(ec.verdict(r), ("winnable", "risky", "deadly", "not rated"))


if __name__ == "__main__":
    unittest.main()
