"""STAGE-01 in the simulator (GM 2026-10-19: Stage is not in FG; it lives in the simulator and is ported from there to the
future engines). sim/stage.py is the reference; sim/stage_cases.json holds the language-neutral cases a port must pass.
Checks for slice 1 (STAGE01_Tooling_Brief_Claude.md): Join/Leave keeps identity; ON AIR / Discussion welcome; only the
holder toggles discussion and the timer is untouched; a handover closes discussion and refuses stale toggles; retries do
nothing twice; applause and accolades are public and award nothing; only the Director controls the spotlight."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sim"))
import stage  # noqa: E402

CASES = json.loads((ROOT / "sim" / "stage_cases.json").read_text(encoding="utf-8"))


class Cases(unittest.TestCase):
    def test_the_reference_passes_every_shared_case(self):
        self.assertEqual(CASES["format"], stage.CASES_FORMAT)
        for case in CASES["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(stage.run_case(case), [])

    def test_a_wrong_answer_is_caught(self):
        case = json.loads(json.dumps(CASES["cases"][1]))
        case["steps"][3]["expect"] = 61
        self.assertEqual(len(stage.run_case(case)), 1)


class State(unittest.TestCase):
    def test_the_state_is_plain_json_and_keeps_history(self):
        st = stage.new()
        stage.apply(st, {"id": "1", "user": "ann", "op": "join", "name": "Ann"}, 0)
        stage.apply(st, {"id": "2", "user": "ann", "op": "applaud", "to": "bob", "reason": "nice"}, 1)
        stage.apply(st, {"id": "3", "user": "ann", "op": "leave"}, 2)
        again = json.loads(json.dumps(st))
        self.assertEqual(again, st)
        self.assertEqual((st["participants"]["ann"]["stage"], len(st["accolades"])), (False, 1))

    def test_the_command_cannot_make_itself_the_director(self):
        st = stage.new()
        ok, _, priv = stage.apply(st, {"id": "1", "user": "bob", "op": "spotlight", "to": "bob", "director": True}, 0)
        self.assertFalse(ok)
        self.assertIsNone(st["spotlight"]["holder"])

    def test_no_character_fields_anywhere(self):
        text = (ROOT / "sim" / "stage.py").read_text(encoding="utf-8").lower()
        for word in ("wounds", "hptotal", "\"xp\"", "inspiration\"", "charsheet", "spell"):
            self.assertNotIn(word, text, word)


if __name__ == "__main__":
    unittest.main()
