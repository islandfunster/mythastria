"""REMIX-01 R1 (GM 2026-10-20: "write the Remix design proposal first, then build the encounter description and
dialogue routes for one map"): tools/remix_spec.py checks an encounter description (docs/development/REMIX.md) against
its map. The first one: Seven Isles, the bell cove (maps/isle_of_echoes/bell_cove.encounters.json)."""
import os
import copy, importlib.util, json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import remix_spec

MASTER = Path(os.environ.get("MYTHASTRIA_FG_DIR") or Path(os.environ.get("APPDATA", "")) / "SmiteWorks" / "Fantasy Grounds") / "AI_Adventures" / "seven_isles"
BELL = MASTER / "maps" / "isle_of_echoes" / "bell_cove.encounters.json"


def bell_map():
    sys.path.insert(0, str(MASTER / "tools"))
    spec = importlib.util.spec_from_file_location("bell_cove", MASTER / "maps" / "isle_of_echoes" / "bell_cove.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.SPEC


@unittest.skipUnless(BELL.is_file(), "Seven Isles master not on this PC")
class BellCove(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desc = json.loads(BELL.read_text(encoding="utf-8"))
        cls.map = bell_map()

    def problems(self, desc):
        return remix_spec.check(desc, self.map)

    def test_the_bell_cove_description_passes_against_its_map(self):
        self.assertEqual(self.problems(self.desc), [])

    def test_it_says_what_it_is_for_and_how_hard_it_measured(self):
        e = self.desc["encounters"][0]
        self.assertTrue(e["story_job"]["locked"])
        self.assertIn(e["difficulty"]["measured"]["plays_as"], remix_spec.PLAYS_AS)
        self.assertTrue((MASTER / e["difficulty"]["measured"]["report"]).is_file())
        self.assertGreaterEqual(len(e["routes"]), 3)
        self.assertGreaterEqual(len({r["approach"] for r in e["routes"]}), 3)          # different kinds of ways through

    def broken(self, change):
        d = copy.deepcopy(self.desc); change(d["encounters"][0]); return " | ".join(self.problems(d))

    def test_no_talking_to_a_creature_that_cannot_talk(self):
        def parley_crab(e):
            e["routes"][0]["approach"], e["routes"][0]["who"] = "parley", ["Giant Crab"]
        self.assertIn("Intelligence", self.broken(parley_crab))

    def test_dcs_stay_in_the_rules_range(self):
        def dc(e):
            r = next(r for r in e["routes"] if "check" in r); r["check"]["dc"] = 40
        self.assertIn("DC", self.broken(dc))

    def test_the_locked_story_job_is_required(self):
        self.assertIn("story_job", self.broken(lambda e: e["story_job"].update(locked=[])))

    def test_a_route_that_skips_a_clue_room_says_where_the_clue_is(self):
        def skip(e):
            r = e["routes"][0]; r["bypasses"] = ["EC-BC-03"]; r.pop("clue_elsewhere", None)
        self.assertIn("clue", self.broken(skip))

    def test_unknown_approach_and_missing_outcomes(self):
        self.assertIn("approach", self.broken(lambda e: e["routes"][0].update(approach="teleport")))
        self.assertIn("failure", self.broken(lambda e: e["routes"][0].pop("failure")))

    def test_the_creatures_must_match_the_map(self):
        def count(e):
            e["original"][0]["count"] += 1
        self.assertIn("map", self.broken(count))


class Format(unittest.TestCase):
    def test_an_empty_description_lists_what_is_missing(self):
        out = " | ".join(remix_spec.check({"format": "remix-encounters/1", "encounters": [{}]}))
        for part in ("room", "story_job", "original", "difficulty", "routes"):
            self.assertIn(part, out)

    def test_the_format_is_named(self):
        self.assertIn("format", " | ".join(remix_spec.check({"encounters": []})))


class Events(unittest.TestCase):
    """GM 2026-10-20: "underground island rooms and caverns can have traps and events that fill them partially or fully
    with water." An encounter description can list events (a flood) Remix may use as a difficulty lever."""
    FLOOD = {"id": "sluice-breaks", "kind": "flood", "trigger": "A character pulls the rusted lever, or round 3 begins.",
             "stages": [{"round": 1, "area": "the lower hall", "depth": "shallow"},
                        {"round": 3, "area": "the lower hall", "depth": "deep"},
                        {"round": 5, "area": "the whole room", "depth": "full"}],
             "counter": {"how": "Close the sluice gate", "check": {"ability": "Strength", "skill": "Athletics", "dc": 15}},
             "favours": ["swimmers", "creatures that do not breathe"],
             "remix": "Harder: the first stage starts at round 1 and the room fills by round 3. Easier: it stops at shallow."}

    def base(self, events):
        return {"format": "remix-encounters/1", "encounters": [{"room": "X-01", "events": events}]}

    def problems(self, events):
        return " | ".join(p for p in remix_spec.check(self.base(events)) if "event" in p)

    def test_a_complete_flood_passes(self):
        self.assertEqual(self.problems([self.FLOOD]), "")

    def test_a_flood_needs_stages_in_order_with_known_depths_and_a_way_out(self):
        self.assertIn("depth", self.problems([dict(self.FLOOD, stages=[{"round": 1, "area": "a", "depth": "soggy"}])]))
        self.assertIn("order", self.problems([dict(self.FLOOD, stages=list(reversed(self.FLOOD["stages"])))]))
        self.assertIn("counter", self.problems([{k: v for k, v in self.FLOOD.items() if k != "counter"}]))
        self.assertIn("kind", self.problems([dict(self.FLOOD, kind="volcano")]))
        bad = dict(self.FLOOD, counter={"how": "x", "check": {"ability": "Strength", "dc": 99}})
        self.assertIn("DC", self.problems([bad]))


if __name__ == "__main__":
    unittest.main()
