"""ONE-SHOT-01 and ON-THE-FLY-01 (GM 2026-11-02): a one-shot written as a real adventure pack, and the GM's changes to a running
fight. Real fights on real maps.
  py -3 -m unittest test_one_shot
"""
import json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]
import market
import one_shot
import sim_service
import test_gm_undo as undo


def doc(**more):
    return dict({"title": "The Mill", "level": 3, "premise": "The mill stopped.", "hook": "The miller asks for help.",
                 "locations": [{"name": "Old Mill", "map": "test/live_keep.json", "read_aloud": "Dust hangs in the air.",
                                "gm_text": "The stones are stuck.",
                                "creatures": [{"name": "Goblin Warrior", "count": 2},
                                              {"name": "Commoner", "count": 1, "attitude": "Friendly", "who": "Marta the miller", "wants": "Her mill back"}],
                                "puzzles": [{"name": "The stone wheel", "text": "Three marks on a wheel.", "hint": "Water first.", "solution": "River, wheel, stone."}]}]}, **more)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.s = sim_service.Service(adventure_packs=str(t / "library"))
        (t / "library").mkdir()
        self.s.one_shots_dir = t / "one_shots"
        self.s.market = market.Market(t / "market.json")

    def tearDown(self):
        if self.s.live:
            self.s.live.quit()
            self.s.live.thread.join(30)
        self.tmp.cleanup()

    def os(self, **req):
        return self.s.one_shot(req)


class Writing(Base):
    def test_a_one_shot_is_kept_on_this_pc(self):
        code, out = self.os(op="save", doc=doc())
        self.assertEqual(code, 200)
        self.assertEqual(self.os(op="get", id=out["doc"]["id"])[1]["doc"]["title"], "The Mill")
        self.assertEqual(self.os(op="list")[1]["one_shots"][0]["places"], 1)

    def test_two_with_one_title_stay_apart(self):
        a, b = self.os(op="save", doc=doc())[1]["doc"], self.os(op="save", doc=doc())[1]["doc"]
        self.assertNotEqual(a["id"], b["id"])

    def test_it_refuses_in_plain_words(self):
        with self.assertRaisesRegex(ValueError, "title"):
            self.os(op="save", doc=doc(title=""))
        with self.assertRaisesRegex(ValueError, "library"):
            self.os(op="save", doc=doc(locations=[{"name": "A", "creatures": [{"name": "Beholder"}]}]))

    def test_a_puzzle_has_no_dice(self):
        d = self.os(op="save", doc=doc())[1]["doc"]
        p = d["locations"][0]["puzzles"][0]
        self.assertEqual(set(p), {"name", "text", "hint", "solution"})

    def test_every_location_needs_a_map_to_publish(self):
        with self.assertRaisesRegex(ValueError, "needs a map"):
            self.os(op="publish", doc=doc(locations=[{"name": "Nowhere"}]))


class Pack(Base):
    def setUp(self):
        super().setUp()
        self.pid = self.os(op="publish", doc=doc())[1]["pack"]
        self.plan = self.s.packs.plan(self.pid)
        self.place = self.plan["places"][0]

    def test_it_is_an_ordinary_pack_and_loaded(self):
        self.assertIn(self.pid, self.s.packs.loaded)
        self.assertEqual(self.plan["name"], "The Mill (One-shot)")
        self.assertEqual(self.plan["lore"]["premise"], ["The mill stopped.", "The miller asks for help."])
        self.assertIn(self.place["scenario"], self.s.available_scenarios())

    def test_the_gms_notes_reach_the_adventure_page(self):
        n = self.place["notes"]
        self.assertEqual(n["read_aloud"], "Dust hangs in the air.")
        self.assertEqual(n["puzzles"][0]["solution"], "River, wheel, stone.")
        self.assertEqual(n["people"][0]["name"], "Marta the miller")

    def test_the_map_keeps_its_file_and_the_party_marks(self):
        sc = self.s.raw_scenario(self.place["scenario"])
        original = json.loads((sim_service.SCENARIOS / "test/live_keep.json").read_text(encoding="utf-8"))
        names = [c["name"] for c in sc["combatants"] if not c.get("pc")]
        self.assertEqual(sorted(names), ["Goblin Warrior 1", "Goblin Warrior 2", "Marta the miller"])
        self.assertEqual(len([c for c in sc["combatants"] if c.get("pc")]), len([c for c in original["combatants"] if c.get("pc")]))
        self.assertTrue(any(not c.get("pc") and c["name"] not in names for c in original["combatants"]))

    def test_people_to_talk_to_start_by_the_party(self):
        sc = self.s.raw_scenario(self.place["scenario"])
        hero = next(c for c in sc["combatants"] if c.get("pc"))
        marta = next(c for c in sc["combatants"] if c["name"] == "Marta the miller")
        self.assertLessEqual(max(abs(hero["x"] - marta["x"]), abs(hero["y"] - marta["y"])), 3)

    def test_a_crowd_leaves_the_party_room(self):
        d = doc()
        d["id"], d["locations"][0]["creatures"] = "crowd", [{"name": "Commoner", "count": 6, "attitude": "Indifferent"}]
        pid = self.os(op="publish", doc=d)[1]["pack"]
        sc = self.s.raw_scenario(self.s.packs.plan(pid)["places"][0]["scenario"])
        hero = next(c for c in sc["combatants"] if c.get("pc"))
        self.assertFalse(any(max(abs(hero["x"] - c["x"]), abs(hero["y"] - c["y"])) <= 1 for c in sc["combatants"] if not c.get("pc")))

    def test_it_plays(self):
        code, out = self.s.live_new(dict(undo.FIGHT, scenario=self.place["scenario"]))
        self.assertEqual(code, 200, out)
        rows = {r["name"]: r["attitude"] for r in self.s.live.attitudes.view()["creatures"]}
        self.assertEqual(rows["Marta the miller"], "Friendly")
        self.assertEqual(rows["Goblin Warrior 1"], "Hostile")

    def test_republishing_replaces_it_and_the_loaded_copy(self):
        d = self.os(op="list")[1]["one_shots"][0]["id"]
        changed = dict(self.os(op="get", id=d)[1]["doc"], title="The Mill")
        changed["locations"][0]["read_aloud"] = "New words."
        self.os(op="publish", doc=changed)
        self.assertEqual(self.s.packs.plan(self.pid)["places"][0]["notes"]["read_aloud"], "New words.")

    def test_it_never_replaces_an_adventure_it_did_not_write(self):
        folder = self.s.packs.directory / self.pid
        m = json.loads((folder / "adventure.json").read_text(encoding="utf-8"))
        m.pop("one_shot")
        (folder / "adventure.json").write_text(json.dumps(m), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "isn't a one-shot"):
            self.os(op="publish", doc=self.os(op="get", id=self.os(op="list")[1]["one_shots"][0]["id"])[1]["doc"])


class Traps(Base):
    def test_a_trap_goes_on_the_map(self):
        d = doc()
        import traps
        kind, t = next(iter(traps.TRAPS.items()))
        d["locations"][0]["traps"] = [{"kind": kind, "band": list(t["bands"])[0], "squares": [[6, 6]]}]
        pid = self.os(op="publish", doc=d)[1]["pack"]
        sc = self.s.raw_scenario(self.s.packs.plan(pid)["places"][0]["scenario"])
        self.assertEqual(sc["traps"][0]["kind"], kind)


class Generate(Base):
    def test_without_a_model_it_says_so(self):
        with self.assertRaisesRegex(ValueError, "Load a model in Chat"):
            self.os(op="generate", field="premise", doc={"title": "X"})

    def test_with_a_model_it_writes_that_field(self):
        self.s.model_loaded, self.s.llm_url, self.s.llm_model = True, "http://127.0.0.1:1234/v1", "m"
        with mock.patch("chat_model.complete", return_value="A storm is coming.") as asked:
            out = self.os(op="generate", field="read_aloud", doc={"title": "X", "premise": "P"}, place={"name": "Dock"}, idea="fog")[1]
        self.assertEqual(out["text"], "A storm is coming.")
        self.assertNotIn("max_tokens", asked.call_args[1], "a thinking model spends a short limit before it writes (play-test 2026-11-02)")
        words = asked.call_args[0][0][1]["content"]
        self.assertIn("Dock", words)
        self.assertIn("fog", words)

    def test_it_asks_for_invented_names(self):
        self.assertIn("Don't use any published setting", one_shot.prompt("premise", {"title": "X"})[0]["content"])


class NoOneLeftOut(unittest.TestCase):
    def test_a_crowded_start_still_seats_the_whole_party(self):
        import run_sim, copy as cp
        raw = json.loads((sim_service.SCENARIOS / "test/live_keep.json").read_text(encoding="utf-8"))
        hero = next(c for c in raw["combatants"] if c.get("pc"))
        for n, (dx, dy) in enumerate((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
            raw["combatants"].append({"id": "x%d" % n, "name": "Crowd %d" % n, "side": "neutral", "x": hero["x"] + dx, "y": hero["y"] + dy, "hp": 4, "ac": 10})
        raw["combatants"] = [c for c in raw["combatants"] if not c.get("pc") or c is hero]
        team = {"Mage %d" % n: cp.deepcopy(__import__("test_rulings_ask_gm").HERO) for n in range(4)}
        sc = run_sim.apply_party(raw, "srd_pregens", 5, extra=team)
        rock = {tuple(p) for p in sc.get("wall_cells") or []}
        placed = [c for c in sc["combatants"] if str(c["name"]).startswith("Mage")]
        self.assertEqual(len(placed), 4)
        self.assertFalse([c["name"] for c in placed if (c["x"], c["y"]) in rock])


class OnTheFly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = sim_service.Service()
        self.s.market = market.Market(Path(self.tmp.name) / "market.json")
        self.assertEqual(self.s.live_new(dict(undo.FIGHT))[0], 200)

    def tearDown(self):
        self.s.live.quit()
        self.s.live.thread.join(30)
        self.tmp.cleanup()

    def names(self):
        return [c["name"] for c in self.s.live.sim.sc["combatants"]]

    def settled(self):
        self.s.live.settle()

    def test_a_creature_joins_without_a_new_fight(self):
        f, fid = self.s.live, self.s.live.fight_id
        code, out = self.s.live_fly({"op": "creature", "name": "Wolf", "count": 2})
        self.assertEqual(code, 200, out)
        self.assertIs(self.s.live, f)
        self.assertEqual(f.fight_id, fid)
        self.assertEqual(out["made"], ["Wolf 1", "Wolf 2"])
        self.assertIn("Wolf 2", self.names())

    def test_it_lands_on_the_square_asked(self):
        sc = self.s.live.sim.sc
        taken = {(int(c["x"]), int(c["y"])) for c in sc["combatants"]} | {tuple(p) for p in sc.get("wall_cells") or []}
        spot = next([x, y] for x in range(2, 20) for y in range(2, 20) if (x, y) not in taken)
        self.s.live_fly({"op": "creature", "name": "Wolf", "at": spot})
        wolf = next(c for c in sc["combatants"] if c["name"] == "Wolf 1")
        self.assertEqual([int(wolf["x"]), int(wolf["y"])], spot)

    def test_rock_is_refused(self):
        rock = (self.s.live.sim.sc.get("wall_cells") or [None])[0]
        if rock:
            code, out = self.s.live_fly({"op": "creature", "name": "Wolf", "at": list(rock)})
            self.assertEqual(code, 409)
            self.assertIn("rock", out["refused"])

    def test_an_attitude_comes_with_it(self):
        self.s.live_fly({"op": "creature", "name": "Commoner", "attitude": "Friendly"})
        row = next(r for r in self.s.live.attitudes.view()["creatures"] if r["name"] == "Commoner 1")
        self.assertEqual(row["attitude"], "Friendly")

    def test_a_hostile_one_takes_a_turn(self):
        self.s.live_fly({"op": "creature", "name": "Wolf"})
        f = self.s.live
        for _ in range(12):
            self.settled()
            if f.done or any("Wolf 1" in e["text"] and "join" not in e["text"] for e in f.snapshot(0)["log"]):
                break
            if f.waiting:
                self.s.live_act(dict(op="end", actor=f.waiting, revision=f.revision, fight_id=f.fight_id))
        self.assertTrue(any("Wolf 1" in e["text"] and "join" not in e["text"] for e in f.snapshot(0)["log"]))

    def test_the_gms_words_reach_the_log(self):
        code, out = self.s.live_fly({"op": "announce", "text": "The wheel  turns."})
        self.assertEqual(code, 200)
        self.assertIn("GM: The wheel turns.", "\n".join(e["text"] for e in self.s.live.snapshot(0)["log"]))

    def test_the_gms_words_reach_a_seat_even_naming_someone_unseen(self):
        import table_seats
        f = self.s.live
        hidden = next(c["name"] for c in f.sim.sc["combatants"] if not c.get("pc"))
        self.s.live_fly({"op": "announce", "text": "%s waves from the far bank." % hidden})
        self.s.live.settle()
        snap = dict(f.snapshot(0))
        sight = dict(snap.get("party_sight") or {}, creatures=[])
        snap["party_sight"] = sight
        snap["tracker"] = dict(snap.get("tracker") or {}, sight={})
        seen = table_seats.player_view(snap, "Lyra") if hasattr(table_seats, "player_view") else None
        self.assertIsNotNone(seen)
        self.assertTrue(any(hidden in e["text"] for e in seen["log"]))

    def test_the_gm_can_set_an_ac_for_this_fight(self):
        f = self.s.live
        c = next(x for x in f.sim.sc["combatants"] if x.get("pc"))
        code, out = self.s.live_fly({"op": "ac", "target": c["id"], "ac": 23, "why": "Mage Armor"})
        self.assertEqual(code, 200, out)
        self.assertEqual(int(f.sim.S.getField(c["id"], "ac")), 23)
        self.assertIn("(Mage Armor)", "\n".join(e["text"] for e in f.snapshot(0)["log"]))
        self.assertEqual(self.s.live_undo({})[0], 200)
        self.assertNotEqual(int(self.s.live.sim.S.getField(c["id"], "ac")), 23)

    def test_the_gm_can_heal_a_creature(self):
        f = self.s.live
        c = next(x for x in f.sim.sc["combatants"] if x.get("pc"))
        f.sim.S.damage(c["id"], 5) if hasattr(f.sim.S, "damage") else f.sim.S.setField(c["id"], "wounds", 5)
        code, out = self.s.live_fly({"op": "heal", "target": c["id"], "hp": 3})
        self.assertEqual(code, 200, out)
        self.assertIn("regains 3 HP", "\n".join(e["text"] for e in f.snapshot(0)["log"]))

    def test_the_gm_can_give_temporary_hit_points(self):
        c = next(x for x in self.s.live.sim.sc["combatants"] if x.get("pc"))
        code, out = self.s.live_fly({"op": "temp", "target": c["id"], "hp": 10})
        self.assertEqual(code, 200, out)
        self.assertEqual(self.s.live.sim.S.getField(c["id"], "sim_temp_hp"), 10)

    def test_the_gm_can_call_a_check_in_a_fight(self):
        c = next(x for x in self.s.live.sim.sc["combatants"] if x.get("pc"))
        code, out = self.s.live_fly({"op": "check", "target": c["id"], "ability": "str", "dc": 15})
        self.assertEqual(code, 200, out)
        self.assertIn("vs DC 15", "\n".join(e["text"] for e in self.s.live.snapshot(0)["log"]))

    def test_only_the_dying_can_be_stabilized(self):
        c = next(x for x in self.s.live.sim.sc["combatants"] if x.get("pc"))
        code, out = self.s.live_fly({"op": "stabilize", "target": c["id"]})
        self.assertEqual(code, 409)
        self.assertIn("isn't dying", out["refused"])

    def test_undo_takes_a_creature_back(self):
        self.s.live_fly({"op": "creature", "name": "Wolf"})
        self.assertEqual(self.s.timeline[-1]["label"], "an on-the-fly change")
        code, out = self.s.live_undo({})
        self.assertEqual(code, 200, out)
        self.assertNotIn("Wolf 1", self.names())

    def test_a_replay_keeps_it(self):
        self.s.live_fly({"op": "creature", "name": "Wolf"})
        f = self.s.live
        self.settled()
        self.s.live_act(dict(op="dodge", actor=f.waiting, revision=f.revision, fight_id=f.fight_id))
        self.assertEqual(self.s.live_undo({})[0], 200)
        self.assertIn("Wolf 1", self.names())

    def test_it_is_the_gms_alone(self):
        self.assertNotIn("/api/live/fly", sim_service.DOOR_ROUTES)
        self.assertNotIn("/api/oneshot", sim_service.DOOR_ROUTES)


if __name__ == "__main__":
    unittest.main()
