"""ADVENTURE-01 (2026-10-21): the loaded adventures are remembered (sim/adventures/loaded.json) and loaded again when the
service starts; the Adventure page reads a loaded pack's places in the manifest's order. A small pack made here."""
import json, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import sim_service


def make_pack(library):
    pack = library / "tiny"
    (pack / "scenarios").mkdir(parents=True)
    (pack / "encounters").mkdir()
    for key, name in (("gate", "First Isle - The gate (test map)"), ("hall", "First Isle - The hall (test map)")):
        (pack / "scenarios" / (key + ".json")).write_text(json.dumps({"name": name, "combatants": []}), encoding="utf-8")
    (pack / "encounters" / "hall.json").write_text(json.dumps({"encounters": [
        {"room": "H-1", "name": "Rats", "level": 2, "party_size": 4, "original": [{"srd": "Rat", "count": 3}],
         "story_job": {"locked": ["The hall is old."], "open": ["The rats are hungry."]}}]}), encoding="utf-8")
    (pack / "adventure.json").write_text(json.dumps({"format": "mythastria-adventure/1", "id": "tiny", "name": "Tiny",
        "encounters": {"hall": {"scenario": "scenarios/hall.json", "description": "encounters/hall.json"},
                       "gate": {"scenario": "scenarios/gate.json"}}}), encoding="utf-8")


class AdventureState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.library = Path(self.tmp.name) / "library"
        make_pack(self.library)
        self.state = Path(self.tmp.name) / "adventures" / "loaded.json"

    def tearDown(self):
        self.tmp.cleanup()

    def service(self):
        s = sim_service.Service(adventure_packs=str(self.library))
        s.adventure_state = self.state
        return s

    def test_load_is_remembered_and_restored(self):
        s = self.service()
        self.assertEqual(s.remix_request("/api/adventures/load", {"pack": "tiny"})[0], 200)
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8")), {"loaded": ["tiny"]})
        again = self.service()
        self.assertEqual(again.restore_adventures(), (["tiny"], []))
        self.assertIn("pack/tiny/hall.json", again.available_scenarios())

    def test_unload_is_remembered(self):
        s = self.service()
        s.remix_request("/api/adventures/load", {"pack": "tiny"})
        s.remix_request("/api/adventures/unload", {"pack": "tiny"})
        again = self.service()
        self.assertEqual(again.restore_adventures(), ([], []))
        self.assertNotIn("pack/tiny/hall.json", again.available_scenarios())

    def test_a_pack_that_is_gone_is_reported(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text(json.dumps({"loaded": ["missing"]}), encoding="utf-8")
        done, problems = self.service().restore_adventures()
        self.assertEqual(done, [])
        self.assertEqual(len(problems), 1)

    def test_no_state_file_means_nothing_remembered(self):
        s = sim_service.Service(adventure_packs=str(self.library))
        s.remix_request("/api/adventures/load", {"pack": "tiny"})
        self.assertFalse(self.state.exists())
        self.assertEqual(s.restore_adventures(), ([], []))

    def test_plan_in_manifest_order(self):
        s = self.service()
        self.assertRaises(ValueError, s.remix_request, "/api/adventures/plan", {"pack": "tiny"})
        s.remix_request("/api/adventures/load", {"pack": "tiny"})
        plan = s.remix_request("/api/adventures/plan", {"pack": "tiny"})[1]
        self.assertEqual([p["key"] for p in plan["places"]], ["hall", "gate"])
        hall, gate = plan["places"]
        self.assertEqual((hall["isle"], hall["place"], hall["scenario"]), ("First Isle", "The hall", "pack/tiny/hall.json"))
        self.assertEqual(hall["encounters"][0]["creatures"], ["Rat x3"])
        self.assertEqual(hall["encounters"][0]["story"], ["The hall is old.", "The rats are hungry."])
        self.assertEqual(gate["encounters"], [])


if __name__ == "__main__":
    unittest.main()
