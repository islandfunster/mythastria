"""CHEAT-LOG-01: what the players' door refused, by player, for the GM.
  py -3 -m unittest test_door_watch
"""
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import door_watch as dw
import sim_service
import table_seats

ACT ="/api/live/act"


class Sorts(unittest.TestCase):
    def test_timing_is_never_kept(self):
        for why in ("Stale: the fight has moved on.", "The creatures are acting; wait for a character's turn.", "The fight is over.",
                    "The GM has frozen the fight; it goes on when the GM unfreezes it.", "Initiative is being rolled: roll yours in the popup first.",
                    "The GM is playing Lyra now.", "That Reaction question is no longer open.", "The GM is taking the fight back; a moment."):
            self.assertIsNone(dw.sort_of(ACT, 409, {"ok": False, "refused": why}), why)

    def test_a_good_answer_and_a_read_are_never_kept(self):
        self.assertIsNone(dw.sort_of(ACT, 200, {"ok": True}))
        self.assertIsNone(dw.sort_of("/api/live/state", 404, {"ok": False, "error": "No live fight: start one."}))

    def test_a_stop_a_closed_seat_and_a_slow_down_are_not_cheating(self):
        self.assertIsNone(dw.sort_of(ACT, 423, {"ok": False, "panic": True, "refused": "The GM has stopped the game."}))
        self.assertIsNone(dw.sort_of(ACT, 403, {"ok": False, "no_seat": True, "error": "Your seat is closed"}))
        self.assertIsNone(dw.sort_of(ACT, 429, {"ok": False, "slow_down": True, "error": "Slow down"}))

    def test_what_the_screen_never_sends_is_not_allowed(self):
        for code, why in ((409, "Ann plays Lyra: wait for that turn."), (400, "Only the GM answers an undo."), (409, "Each player rolls for their own character."),
                          (403, "The GM calls stealth checks and rolls Perception."), (400, "A choice is one of attack, move, with the revision it answers.")):
            self.assertEqual(dw.sort_of(ACT, code, {"ok": False, "error": why}), dw.NOT_ALLOWED, why)

    def test_a_rule_refused_can_be_a_mistake(self):
        self.assertEqual(dw.sort_of(ACT, 200, {"ok": False, "refused": "Goblin is 45 ft away: out of Dagger's reach (5 ft)."}), dw.AGAINST_RULES)


class Lists(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.w = dw.Watch(lambda: self.now)

    def rule(self, who="Ann"):
        self.w.note(who, ACT, {"op": "attack"}, 200, {"ok": False, "refused": "out of reach"})

    def test_one_mistake_is_no_reason_to_look(self):
        self.rule()
        row = self.w.view()[0]
        self.assertEqual((row["who"], row["against_rules"], row["look"]), ("Ann", 1, False))

    def test_a_pile_is(self):
        for _ in range(8):
            self.rule()
        self.assertTrue(self.w.view()[0]["look"])

    def test_old_mistakes_dont_pile_up(self):
        for _ in range(7):
            self.rule()
        self.now += 700
        self.rule()
        self.assertFalse(self.w.view()[0]["look"])

    def test_one_forbidden_ask_is(self):
        self.w.note("Ben", ACT, {"op": "undo_approve"}, 400, {"ok": False, "error": "Only the GM answers an undo."})
        self.rule()
        self.assertEqual([r["who"] for r in self.w.view()], ["Ben", "Ann"])
        self.assertTrue(self.w.view()[0]["look"])

    def test_the_line_says_what_and_why(self):
        self.w.note("Ann", ACT, {"op": "cast", "spell": "Fireball"}, 200, {"ok": False, "refused": "No level 3 slot."})
        self.assertEqual({k: self.w.view()[0]["lines"][0][k] for k in ("what", "why")}, {"what": "act cast Fireball", "why": "No level 3 slot."})

    def test_no_name_no_line(self):
        self.w.note(None, ACT, {"op": "attack"}, 200, {"ok": False, "refused": "out of reach"})
        self.assertEqual(self.w.view(), [])

    def test_it_keeps_no_address_or_ticket(self):
        self.w.note("Ann", ACT, {"op": "move", "ticket": "secret-ticket", "x": 1}, 200, {"ok": False, "refused": "too far"})
        self.assertNotIn("secret-ticket", str(self.w.view()))

    def test_the_list_is_bounded(self):
        for _ in range(dw.KEEP + 50):
            self.rule()
        row = self.w.view()[0]
        self.assertEqual((row["against_rules"], len(row["lines"])), (dw.KEEP, dw.SHOWN))


class Service(unittest.TestCase):
    def test_the_gm_sees_and_clears_it(self):
        s = sim_service.Service()
        s.door_watch.add("Ann", dw.NOT_ALLOWED, "panic", "A GM route.")
        self.assertEqual(s.seats_gm({"op": "state"})[1]["watch"][0]["who"], "Ann")
        self.assertEqual(s.seats_gm({"op": "watch_clear"})[1]["watch"], [])

    def test_a_seat_has_a_name_for_its_ticket_only(self):
        s = sim_service.Service()
        s.seats.seats[table_seats._hash("t1")] = {"name": "Ann"}
        self.assertEqual(s.seats.name_for("t1"), "Ann")
        for ticket in ("nope", None, 7, "x" * 200):
            self.assertIsNone(s.seats.name_for(ticket))

    def test_it_is_not_a_players_route(self):
        self.assertNotIn("/api/seats", sim_service.DOOR_ROUTES)


if __name__ == "__main__":
    unittest.main()
