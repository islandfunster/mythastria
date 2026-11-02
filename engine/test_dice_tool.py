"""DICE-TOOL-01: free dice rolls outside the mechanics (sim/dice_tool.py), the shared cases for ports
(sim/dice_cases.json), and fairness of the secure dice the service uses."""
import json, random, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim")]
import dice_tool as D  # noqa: E402


class SharedCases(unittest.TestCase):
    def test_every_case(self):
        data = json.loads((ROOT / "sim" / "dice_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(data["format"], D.CASES_FORMAT)
        for case in data["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(D.run_case(case), [])


class Rolls(unittest.TestCase):
    def test_every_face_comes_up_and_nothing_else(self):
        rng = random.Random(7)
        seen = set()
        for _ in range(2000):
            r = D.roll("1d20", lambda s: rng.randint(1, s))
            seen.add(r["total"])
        self.assertEqual(seen, set(range(1, 21)))

    def test_a_dice_source_out_of_range_is_refused(self):
        with self.assertRaises(D.DiceError):
            D.roll("1d6", lambda s: 7)

    def test_labels_are_cut_and_never_executed(self):
        r = D.roll("1d4", lambda s: 1, "GM", "<b>" + "x" * 100)
        self.assertEqual(len(r["label"]), D.MAX_LABEL)
        self.assertTrue(r["text"].startswith("GM rolls 1d4 (<b>"))       # the page shows text, never HTML

    def test_text_that_is_not_a_string_is_refused(self):
        for bad in (None, 20, ["1d20"]):
            with self.assertRaises(D.DiceError):
                D.parse(bad)


if __name__ == "__main__":
    unittest.main()
