"""GM 2026-10-28 ("I don't want any of the test characters. I only want to use characters saved in the saved characters
tab"): Simulator fights (POST /api/new) fights with the saved characters' sheets, each at its own level.
  py -3 -m unittest test_saved_only
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import sim_messages, sim_service  # noqa: E402
from test_encounter_check import RANGER  # noqa: E402

DEN = ROOT / "sim" / "scenarios" / "test" / "goblin_den_2024.json"


class SimulatorFights(unittest.TestCase):
    def test_the_service_hands_the_saved_characters_to_the_recording(self):
        seen = {}

        def recorder(scenario, members, level, items, rounds, seed, extra=None):
            seen.update(members=members, level=level, extra=extra)
            return sim_messages.record(str(DEN), members, level, items, 1, seed, extra)
        code, out = sim_service.Service(recorder).new({"scenario": "test/goblin_den_2024.json", "characters": [RANGER],
                                                       "rounds": 1, "seed": 1})
        self.assertEqual((code, out["ok"]), (200, True), out)
        self.assertEqual((seen["members"], seen["level"], list(seen["extra"])), ([], 5, ["Imported"]))
        self.assertEqual([c["name"] for c in out["messages"][1]["combatants"] if c.get("pc")], ["Imported"])

    def test_without_characters_it_asks_for_the_party(self):
        with self.assertRaisesRegex(ValueError, "Choose the party"):              # SRD-EDITION-01: no test characters
            sim_service.Service(lambda *a: []).new({"scenario": "test/goblin_den_2024.json"})


if __name__ == "__main__":
    unittest.main()
