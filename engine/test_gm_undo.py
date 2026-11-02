"""GM-UNDO-01, the Panic Button and the turn timer (GM 2026-11-01): the GM's stop, rewind and clock, on real fights.
  py -3 -m unittest test_gm_undo
"""
import hashlib, sys, tempfile, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import live_play
import market
import sim_service

SEAT = {"name": "Ann", "character": "Lyra", "hints": "off"}
GM_LINES = ("The GM takes back", "The GM froze", "The GM unfroze")


def sheet(name, cls, spells):
    return {"name": name, "classes": [{"name": cls, "level": 5}], "species": "Human",
            "abilities": {"str": 12, "dex": 14, "con": 14, "int": 12, "wis": 10, "cha": 18},
            "combat": {"hp_max": 38, "ac": 14, "speed": 30, "attack_bonus": 7, "damage_count": 1, "damage_die": 8, "damage_bonus": 0, "reach": 60},
            "equipment": ["Dagger"], "spells": spells, "features": []}


FIGHT = {"scenario": "test/live_spells.json", "members": [], "characters": [sheet("Lyra", "Wizard", ["Fire Bolt", "Shield"]), sheet("Bran", "Fighter", [])],
         "seed": 1, "rounds": 8}


class Table(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = sim_service.Service()
        self.s.market = market.Market(Path(self.tmp.name) / "market.json")
        code, out = self.s.live_new(dict(FIGHT))
        self.assertEqual(code, 200, out)

    def tearDown(self):
        f = self.s.live
        if f:
            f.quit()
            f.thread.join(30)
        self.tmp.cleanup()

    @property
    def f(self):
        return self.s.live

    def act(self, op, cast=True, **k):
        """A choice, with every Reaction it asks on the way answered, as another player's screen would."""
        f, got = self.f, []
        cmd = dict(op=op, actor=f.waiting, revision=f.revision, fight_id=f.fight_id, **k)
        t = threading.Thread(target=lambda: got.append(self.s.live_act(cmd)))
        t.start()
        while t.is_alive():
            q = f.reactions.view()
            if q:
                self.s.live_reaction({"n": q["n"], "cast": cast})
            time.sleep(0.002)
        t.join()
        return got[0]

    def foes(self):
        return [c for c in self.f.snapshot(1 << 30)["state"]["combatants"] if not c.get("pc") and (c.get("hp") or 0) > 0]

    def step_up(self):
        """A real move: next to a foe, when the turn's movement reaches one."""
        foes, reach = self.foes(), self.f.snapshot(1 << 30)["offers"].get("reach") or []
        for r in reach:
            if r[0] >= 0 and r[1] >= 0 and any(max(abs(r[0] - c["x"]), abs(r[1] - c["y"])) == 1 for c in foes):
                return self.act("move", x=r[0], y=r[1])

    def attack(self):
        """A real attack, dice and all, on a foe in reach."""
        ids = {c["id"] for c in self.foes()}
        for a in self.f.snapshot(1 << 30)["offers"].get("attacks") or []:
            near = [i for i in a.get("targets") or [] if i in ids]
            if near:
                return self.act("attack", weapon=a["key"], target=near[0])

    def end_turn(self, cast=True):
        return self.act("end", cast)

    def now(self):
        """The whole fight as it stands, the place the dice have reached included; the GM's own lines aside."""
        f = self.f
        snap = f.snapshot(0)
        keep = {k: snap.get(k) for k in ("waiting", "round", "state", "offers", "gm_control", "door_states", "hazards", "layers", "lights", "reaction", "traps", "done")}
        keep["log"] = [e["text"] for e in snap["log"] if not e["text"].startswith(GM_LINES)]
        keep["dice"] = hashlib.sha1(repr(f.sim.rng.getstate()).encode()).hexdigest()
        return keep

    def play(self, turns):
        """Real turns; what the fight was at each length of the timeline."""
        seen = {0: self.now()}
        for _ in range(turns):
            if self.f.done:
                break
            self.step_up()
            seen[len(self.s.timeline)] = self.now()
            self.attack()
            seen[len(self.s.timeline)] = self.now()
            self.end_turn()
            seen[len(self.s.timeline)] = self.now()
        return seen

    def undo(self):
        code, out = self.s.live_undo({})
        self.assertEqual(code, 200, out)
        self.assertIsNone(out["stopped"])
        return out


class Undo(Table):
    def test_every_step_goes_back_to_what_it_was(self):
        seen = self.play(4)
        steps = [e["label"] for e in self.s.timeline]
        self.assertGreater(sum(1 for e in self.s.timeline if e["kind"] == "creature"), 3, steps)
        self.assertGreater(sum(1 for e in self.s.timeline if e["kind"] == "choice"), 3, steps)
        self.assertTrue(any(a.get("name") == "live_act" and a["req"]["op"] != "end" and b["label"] == "a Reaction answered"
                            for a, b in zip(self.s.timeline, self.s.timeline[1:])), steps)   # a choice that stopped for a Reaction
        matched = 0
        while self.s.timeline:
            n = len(self.s.timeline)
            out = self.undo()
            self.assertEqual((out["timeline"]["steps"], out["undone"]), (n - 1, steps[n - 1]))
            self.assertTrue(self.f.frozen)
            if n - 1 in seen:
                self.assertEqual(self.now(), seen[n - 1], "at step %d" % (n - 1))
                matched += 1
        self.assertGreater(matched, 6)
        code, out = self.s.live_undo({})
        self.assertEqual(code, 409)
        self.assertIn("Nothing to undo", out["refused"])

    def test_going_on_from_a_creature_gives_the_same_fight(self):
        while self.s.timeline[-1:] == [] or self.s.timeline[-1]["kind"] != "creature":
            self.play(1)
        before, steps = self.now(), len(self.s.timeline)
        self.undo()
        self.assertTrue(self.f.held and self.f.frozen)
        self.assertIsNone(self.f.waiting)
        self.s.live_freeze({"frozen": False})
        self.f.wait_ready(30)
        self.assertEqual(self.now(), before)
        self.assertEqual(len(self.s.timeline), steps)

    def test_the_same_choices_give_the_same_dice(self):
        self.step_up()
        ready = self.now()
        code, out = self.attack()
        self.assertTrue(out.get("ok"), out)
        before = self.now()
        self.assertNotEqual(before["dice"], ready["dice"])
        self.undo()
        self.assertEqual(self.now(), ready)
        self.s.live_freeze({"frozen": False})
        self.attack()
        self.assertEqual(self.now(), before)

    def test_a_reaction_is_asked_again(self):
        for _ in range(12):
            self.end_turn()
            if any(e["label"] == "a Reaction answered" for e in self.s.timeline) or self.f.done:
                break
        at = next(i for i, e in enumerate(self.s.timeline) if e["label"] == "a Reaction answered")
        while len(self.s.timeline) > at:
            self.undo()
        q = self.f.reactions.view()
        self.assertEqual((q["spell"], self.s.timeline[-1]["kind"]), ("Shield", "creature"))
        code, out = self.s.live_reaction({"n": q["n"], "cast": False})
        self.assertEqual(code, 200, out)

    def test_a_replay_keeps_the_fight_and_starts_each_screens_log_again(self):
        fight_id = self.f.fight_id
        revision = self.f.revision
        self.act("dodge")
        self.undo()
        self.assertEqual((self.f.fight_id, self.f.rewinds), (fight_id, 1))
        self.assertGreater(self.f.revision, revision)
        self.assertEqual(self.f.snapshot(1 << 30)["rewinds"], 1)
        self.assertTrue(any("The GM takes back" in e["text"] for e in self.f.snapshot(0)["log"]))

    def test_a_new_fight_has_its_own_timeline(self):
        self.play(1)
        self.assertTrue(self.s.timeline)
        self.s.live_new(dict(FIGHT))
        self.assertEqual(self.s.timeline, [])
        self.assertEqual(self.s.live_undo({})[0], 409)

    def test_a_rewind_is_no_end_of_the_fight_for_the_adventures_day(self):
        self.act("dodge")
        ended = []
        self.f.on_done = ended.append
        self.undo()
        self.assertEqual(ended, [])

    def test_bags_and_switches_go_back_with_the_fight(self):
        self.s.market._load()["purses"]["lyra"] = {"name": "Lyra", "cp": 500, "bag": []}
        self.s.fight_start["purses"] = {"lyra": {"name": "Lyra", "cp": 900, "bag": []}}
        self.s.live_social({"off": True})
        self.assertTrue(self.s.social_off)
        self.undo()
        self.assertEqual(self.s.market._load()["purses"]["lyra"]["cp"], 900)
        self.assertFalse(self.s.social_off)
        self.assertFalse(self.f.actions.lore.off)

    def test_a_refused_choice_is_no_step(self):
        out = self.act("move", x=9999 % 500, y=499)
        self.assertFalse(out[1].get("ok"))
        self.assertEqual(self.s.timeline, [])

    def test_the_players_see_no_replay(self):
        self.s.rewinding = True
        code, out = self.s.live_state({})
        self.assertEqual((out["ok"], out["rewinding"]), (False, True))
        self.assertIn("a moment", self.act("end")[1]["refused"])
        self.s.rewinding = False


class Answers(unittest.TestCase):
    def fight(self, **k):
        return SimpleNamespace(replaying=True, done=False, reactions=SimpleNamespace(view=lambda: None), **k)

    def test_a_replay_goes_on_past_a_choice_that_stops_for_a_reaction(self):
        f = self.fight()
        f.reactions.view = lambda: {"n": 1}
        reply = live_play.queue.Queue()
        self.assertTrue(live_play.LiveFight.answer(f, reply, 5)["ok"])

    def test_no_choice_outlives_its_fight(self):
        f = self.fight()
        f.done = True
        out = live_play.LiveFight.answer(f, live_play.queue.Queue(), 5)
        self.assertEqual((out["ok"], out["status"]), (False, 409))


class Panic(Table):
    def setUp(self):
        super().setUp()
        self.s.monitor = SimpleNamespace(on=True, switch=lambda on: setattr(self.s.monitor, "on", on))

    def test_it_holds_everything_and_resume_gives_it_back(self):
        code, out = self.s.live_panic({"on": True})
        self.assertEqual((code, out["panic"]), (200, True))
        self.assertTrue(self.f.frozen)
        self.assertFalse(self.s.monitor.on)
        self.s.live_panic({"on": False})
        self.assertFalse(self.f.frozen)
        self.assertTrue(self.s.monitor.on)

    def test_the_players_door_refuses_and_says_so(self):
        self.s.live_panic({"on": True})
        for route in ("/api/live/act", "/api/live/reaction", "/api/chat", "/api/roll", "/api/flavor/ask", "/api/stage", "/api/live/control"):
            code, out = self.s.seat_request(route, {}, SEAT)
            self.assertEqual((code, out["panic"]), (423, True), route)
            self.assertEqual(out["refused"], "The GM has stopped the game.")
        code, out = self.s.seat_request("/api/live/state", {}, SEAT)
        self.assertEqual((code, out["panic"]), (200, True))
        self.assertNotIn("timeline", out)

    def test_a_fight_frozen_before_stays_frozen(self):
        self.s.live_freeze({"frozen": True})
        self.s.live_panic({"on": True})
        self.s.live_panic({"on": False})
        self.assertTrue(self.f.frozen)

    def test_a_monitor_that_was_off_stays_off(self):
        self.s.monitor.on = False
        self.s.live_panic({"on": True})
        self.s.live_panic({"on": False})
        self.assertFalse(self.s.monitor.on)

    def test_only_resume_lifts_it(self):
        self.s.live_panic({"on": True})
        self.assertEqual(self.s.live_freeze({"frozen": False})[0], 409)
        code, out = self.s.live_new(dict(FIGHT))
        self.assertEqual(code, 409)
        self.assertIn("Resume", out["error"])

    def test_undo_works_while_stopped(self):
        self.act("dodge")
        self.s.live_panic({"on": True})
        self.assertTrue(self.undo()["panic"])
        self.assertTrue(self.f.frozen)
        self.s.live_panic({"on": False})
        self.assertFalse(self.f.frozen)
        self.assertIsNotNone(self.f.waiting)

    def test_panic_is_said_with_no_fight_too(self):
        f, self.s.live = self.s.live, None
        self.s.live_panic({"on": True})
        code, out = self.s.live_state({})
        self.assertEqual((code, out["panic"]), (404, True))
        self.s.live = f
        self.s.live_panic({"on": False})


class Timer(Table):
    def test_it_counts_each_turn(self):
        snap = self.f.snapshot(1 << 30)
        self.assertTrue(snap["turn_timer"])
        self.assertLess(snap["turn_seconds"], 30)
        self.f.turn_began -= 90
        self.assertGreaterEqual(self.f.snapshot(1 << 30)["turn_seconds"], 90)
        self.end_turn()
        self.assertLess(self.f.snapshot(1 << 30)["turn_seconds"], 30)

    def test_a_frozen_fights_clock_waits(self):
        self.f.freeze(True)
        held = self.f.turn_clock()
        self.f.turn_began -= 0                                    # the clock reads the moment of the freeze
        time.sleep(1.1)
        self.assertEqual(self.f.turn_clock(), held)
        self.f.freeze(False)
        self.assertLessEqual(self.f.turn_clock(), held + 1)

    def test_the_gm_turns_it_off_and_on(self):
        code, out = self.s.live_timer({"on": False})
        self.assertEqual((code, out["live"]["turn_timer"]), (200, False))
        self.s.live_new(dict(FIGHT))
        self.assertFalse(self.f.snapshot(1 << 30)["turn_timer"])
        self.s.live_timer({"on": True})
        self.assertTrue(self.f.snapshot(1 << 30)["turn_timer"])

    def test_it_is_on_or_off_only(self):
        with self.assertRaises(ValueError):
            self.s.live_timer({"on": "yes"})


class Doors(unittest.TestCase):
    def test_the_gms_tools_are_never_on_the_players_door(self):
        for route in ("/api/live/panic", "/api/live/undo", "/api/live/timer"):
            self.assertNotIn(route, sim_service.DOOR_ROUTES)


if __name__ == "__main__":
    unittest.main()
