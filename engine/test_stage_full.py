"""STAGE-01 slice 2 (GM 2026-10-20: "write code for stage to finish it. We'll save it to be added later. It should be
tested by ai first"): sim/stage_full.py, the rest of the Stage on top of sim/stage.py, not attached to the table yet.
Reworked the same day (GM: "Let's leave out discussion. It can lead to hard feelings. The simple vote is enough. Like a
nomination!" and "notes is just a silent demerit that affects future spotlight voting opportunities for everyone.
Several notes means it's not a good time for getting carried away and nobody judges. But also the spotlight stays off
until the GM (Director, Show Runner) turns it back on. No questions asked."). Checks: the agreed timer and its gentle
cue; Stage moments (footlights) once per segment, applause apart; next-scene invitations; nominations for the next
spotlight (secret, one each, no self-nomination, only Stage players, a tie left to the Director, no counts for the
others); silent notes (name nobody, nobody sees who sent one, several from different people rest the spotlight until
the Director turns it back on); rewards recorded, never applied; retries do nothing twice; no grievance machinery."""
import json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sim"))
import stage_full as sf  # noqa: E402

PLAYERS = ["ann", "bob", "cat", "dan", "eve"]


def table(stage_out=()):
    st, n = sf.new(), [0]

    def do(user, op, now=0, director=False, **kw):
        n[0] += 1
        cmd = dict(kw, id="c%d" % n[0], user=user, op=op)
        return sf.apply(st, cmd, now, director=director)

    for p in PLAYERS:
        do(p, "join", name=p.title())
    for p in stage_out:
        do(p, "leave")
    return st, do


class Timer(unittest.TestCase):
    def test_the_table_agrees_the_median_of_the_proposals_rounded_to_30_seconds(self):
        st, do = table()
        for p, secs in zip(PLAYERS, (120, 180, 150, 240, 100)):
            self.assertTrue(do(p, "propose_timer", seconds=secs)[0])
        ok, pub, _ = do("gm", "agree_timer", director=True)
        self.assertTrue(ok)
        self.assertEqual(st["policy"]["spotlight_seconds"], 150)
        self.assertIn("2:30", pub)

    def test_only_players_on_the_stage_suggest_a_length(self):
        st, do = table(stage_out=("eve",))
        self.assertFalse(do("eve", "propose_timer", seconds=600)[0])
        self.assertTrue(do("ann", "propose_timer", seconds=120)[0])

    def test_only_the_director_settles_it(self):
        st, do = table()
        do("ann", "propose_timer", seconds=120)
        self.assertFalse(do("ann", "agree_timer")[0])

    def test_the_cue_is_gentle_and_changes_nothing(self):
        st, do = table()
        do("ann", "propose_timer", seconds=60)
        do("gm", "agree_timer", director=True)
        do("gm", "spotlight", now=0, director=True, to="ann")
        self.assertIsNone(sf.cue(st, 30))
        before = json.dumps(st, sort_keys=True)
        self.assertIn("Time cue", sf.cue(st, 61))
        self.assertEqual(json.dumps(st, sort_keys=True), before)


class Moments(unittest.TestCase):
    def test_a_segment_counts_once_and_applause_fills_no_light(self):
        st, do = table()
        do("gm", "spotlight", now=0, director=True, to="ann")
        self.assertTrue(do("ann", "moment", now=10)[0])
        self.assertFalse(do("ann", "moment", now=11)[0])
        do("gm", "pause", now=12, director=True)
        do("gm", "resume", now=13, director=True)
        self.assertFalse(do("gm", "moment", now=14, director=True, to="ann")[0])
        do("bob", "applaud", now=15, to="ann", reason="lovely")
        self.assertEqual((sf.footlights(st, "ann"), sf.footlights(st, "bob")), (1, 0))

    def test_footlights_stop_at_three_and_reset_with_a_new_session(self):
        st, do = table()
        for i in range(5):
            do("gm", "spotlight", now=i * 10, director=True, to="ann")
            do("ann", "moment", now=i * 10 + 1)
        self.assertEqual(sf.footlights(st, "ann"), 3)
        do("gm", "newsession", now=100, director=True)
        self.assertEqual(sf.footlights(st, "ann"), 0)
        self.assertEqual(len(st["moments"]), 5)

    def test_invitations_only_for_stage_players_without_a_moment(self):
        st, do = table(stage_out=("eve",))
        do("gm", "spotlight", now=0, director=True, to="ann")
        do("ann", "moment", now=1)
        self.assertEqual(sf.invite_cues(st), ["bob", "cat", "dan"])
        self.assertTrue(do("gm", "invite", director=True, to="bob")[0])
        self.assertFalse(do("gm", "invite", director=True, to="eve")[0])
        self.assertFalse(do("cat", "accept")[0])
        ok, pub, _ = do("bob", "pass")
        self.assertTrue(ok)
        self.assertIn("passes", pub)


class Nominations(unittest.TestCase):
    def setUp(self):
        self.st, self.do = table(stage_out=("eve",))
        ok, pub, _ = self.do("gm", "open_nominations", director=True)
        self.assertTrue(ok)
        self.assertIn("next spotlight", pub)
        self.round = self.st["rounds"][-1]["id"]

    def nominate(self, votes):
        for user, to in votes.items():
            ok, _, priv = self.do(user, "nominate", round=self.round, to=to)
            self.assertTrue(ok, priv)

    def test_the_most_nominated_stage_player_is_named_without_the_others_counts(self):
        self.nominate({"ann": "cat", "bob": "cat", "dan": "ann", "eve": "cat"})
        ok, pub, _ = self.do("gm", "close_nominations", director=True, round=self.round)
        self.assertTrue(ok)
        self.assertIn("Cat", pub)
        self.assertNotIn("Ann", pub)                               # nobody hears how few nominated them
        self.assertEqual(self.st["rounds"][-1]["winner"], "cat")
        self.assertTrue(self.do("gm", "spotlight", director=True, to="cat")[0])   # the Director still gives it

    def test_a_tie_is_left_to_the_director(self):
        self.nominate({"ann": "cat", "bob": "dan", "cat": "dan", "dan": "cat"})
        ok, pub, _ = self.do("gm", "close_nominations", director=True, round=self.round)
        self.assertIn("Cat and Dan", pub)
        self.assertIn("Director", pub)
        self.assertIsNone(self.st["rounds"][-1]["winner"])

    def test_no_nominations_names_nobody(self):
        ok, pub, _ = self.do("gm", "close_nominations", director=True, round=self.round)
        self.assertTrue(ok)
        self.assertIn("no nominations", pub)

    def test_one_secret_nomination_each_for_someone_else_on_the_stage(self):
        self.assertFalse(self.do("ann", "nominate", round=self.round, to="ann")[0])     # not yourself
        self.assertFalse(self.do("ann", "nominate", round=self.round, to="eve")[0])     # Eve is not on the Stage
        self.assertFalse(self.do("ann", "nominate", round=self.round, to="zed")[0])
        ok, pub, priv = self.do("ann", "nominate", round=self.round, to="bob")
        self.assertTrue(ok)
        self.assertNotIn("Bob", pub or "")                          # secret
        self.assertFalse(self.do("ann", "nominate", round=self.round, to="cat")[0])     # final
        self.assertTrue(self.do("eve", "nominate", round=self.round, to="bob")[0])      # Stage-out may nominate
        self.assertFalse(self.do("gm", "nominate", director=True, round=self.round, to="bob")[0])  # the Director runs it

    def test_only_the_director_opens_and_closes_a_round(self):
        self.assertFalse(self.do("ann", "close_nominations", round=self.round)[0])
        self.assertFalse(self.do("ann", "open_nominations")[0])
        self.assertFalse(self.do("gm", "open_nominations", director=True)[0])           # one round at a time
        self.do("gm", "close_nominations", director=True, round=self.round)
        self.assertFalse(self.do("bob", "nominate", round=self.round, to="cat")[0])     # closed

    def test_views_hold_no_one_elses_nomination(self):
        self.nominate({"ann": "cat", "bob": "dan"})
        for seat in ("cat", "dan", "gm"):
            v = json.dumps(sf.view(self.st, seat, director=(seat == "gm")))
            self.assertNotIn("\"votes\"", v)
            self.assertNotIn("\"by\"", v)
        self.assertEqual(sf.view(self.st, "ann")["round"]["mine"], "cat")
        self.assertIsNone(sf.view(self.st, "dan")["round"]["mine"])


class SilentNotes(unittest.TestCase):
    def test_a_note_names_nobody_and_says_nothing_aloud(self):
        st, do = table()
        ok, pub, priv = do("ann", "note")
        self.assertTrue(ok)
        self.assertIsNone(pub)
        self.assertIn("silently", priv)
        self.assertFalse(do("ann", "note", about="bob")[0])          # a note is about nobody
        self.assertEqual(st["notes"]["count"], 1)

    def test_nobody_sees_who_sent_a_note_not_even_the_director(self):
        st, do = table()
        seats = (("cat", False), ("gm", True), ("ann", False))
        before = [sf.view(st, seat, director=d) for seat, d in seats]
        do("ann", "note")
        do("bob", "note")
        self.assertEqual([sf.view(st, seat, director=d) for seat, d in seats], before)   # nothing shows

    def test_several_notes_from_different_people_rest_the_spotlight(self):
        st, do = table()
        do("gm", "spotlight", now=0, director=True, to="bob")
        do("ann", "note", now=5)
        do("ann", "note", now=6)                                    # the same person twice counts once
        do("cat", "note", now=7)
        self.assertEqual(st["spotlight"]["holder"], "bob")
        ok, pub, _ = do("dan", "note", now=8)
        self.assertTrue(ok)
        self.assertIn("rests", pub)
        self.assertNotIn("Bob", pub)                                 # no reason, no name
        self.assertIsNone(st["spotlight"]["holder"])
        self.assertTrue(st["resting"])
        self.assertEqual(st["segments"][-1]["seconds"], 8)          # the time up to then is kept

    def test_while_it_rests_no_spotlight_and_no_nominations_until_the_director_says(self):
        st, do = table()
        for p in ("ann", "cat", "dan"):
            do(p, "note")
        self.assertFalse(do("gm", "spotlight", director=True, to="ann")[0])
        self.assertFalse(do("gm", "open_nominations", director=True)[0])
        self.assertFalse(do("ann", "lights_on")[0])                 # only the Director
        ok, pub, _ = do("gm", "lights_on", director=True)
        self.assertTrue(ok)
        self.assertIn("back on", pub)
        self.assertEqual(st["notes"]["count"], 0)                   # a fresh start, no questions asked
        self.assertTrue(do("gm", "spotlight", director=True, to="ann")[0])

    def test_resting_sets_an_open_round_aside(self):
        st, do = table()
        do("gm", "open_nominations", director=True)
        for p in ("ann", "cat", "dan"):
            do(p, "note")
        self.assertEqual(st["rounds"][-1]["state"], "set aside")

    def test_a_small_table_rests_after_fewer_notes(self):
        st, n = sf.new(), [0]
        for u in ("ann", "bob", "cat"):
            sf.apply(st, {"id": u, "user": u, "op": "join"}, 0)
        sf.apply(st, {"id": "n1", "user": "ann", "op": "note"}, 1)
        sf.apply(st, {"id": "n2", "user": "bob", "op": "note"}, 2)
        self.assertTrue(st["resting"])                              # 3 people at the table: 2 notes are several


class DirectorWhoPlays(unittest.TestCase):
    """GM 2026-10-20: "If DMs chooses to participate as a player, then they should stay cognizant of their separate
    roles." The GM plays through a player seat of their own; the Director seat keeps only the Director's buttons."""

    def test_the_dm_plays_through_a_player_seat_and_the_director_seat_stays_apart(self):
        st, do = table()
        self.assertTrue(do("cam", "join", name="Cam")[0])               # the GM's player seat
        self.assertTrue(do("cam", "propose_timer", seconds=150)[0])
        do("gm", "open_nominations", director=True)
        rid = st["rounds"][-1]["id"]
        self.assertTrue(do("cam", "nominate", round=rid, to="ann")[0])    # as a player
        self.assertFalse(do("gm", "nominate", director=True, round=rid, to="ann")[0])   # never as Director
        self.assertTrue(do("ann", "nominate", round=rid, to="cam")[0])    # and can be nominated
        self.assertTrue(do("cam", "note")[0])
        self.assertFalse(do("gm", "note", director=True)[0])
        self.assertFalse(do("cam", "lights_on")[0])                       # Director buttons only on the Director seat
        self.assertFalse(do("cam", "spotlight", to="cam")[0])


class Retries(unittest.TestCase):
    def test_a_retried_note_or_nomination_does_nothing_twice(self):
        st, do = table()
        sf.apply(st, {"id": "n1", "user": "ann", "op": "note"}, 0)
        sf.apply(st, {"id": "n1", "user": "ann", "op": "note"}, 1)
        self.assertEqual(st["notes"]["count"], 1)
        do("gm", "open_nominations", director=True)
        rid = st["rounds"][-1]["id"]
        cmd = {"id": "v1", "user": "bob", "op": "nominate", "round": rid, "to": "cat"}
        self.assertEqual(sf.apply(st, dict(cmd), 2)[0], True)
        self.assertEqual(sf.apply(st, dict(cmd), 3), (True, None, None))

    def test_slice_one_still_works_through_the_full_rules(self):
        st, do = table()
        ok, pub, _ = do("gm", "spotlight", now=0, director=True, to="ann")
        self.assertIn("ON AIR", pub)
        self.assertFalse(do("bob", "discuss", on=True, revision=st["spotlight"]["revision"])[0])

    def test_the_state_stays_plain_json(self):
        st, do = table()
        do("ann", "note")
        do("gm", "open_nominations", director=True)
        self.assertEqual(json.loads(json.dumps(st)), st)


class NoJudging(unittest.TestCase):
    def test_no_grievance_vote_or_penalty_commands(self):
        st, do = table()
        for op in ("triage", "respond", "open_vote", "ballot", "close_vote"):
            self.assertFalse(do("gm", op, director=True)[0], op)
        text = (ROOT / "sim" / "stage_full.py").read_text(encoding="utf-8").lower()
        for word in ("accused", "grievance", "uphold", "privilege", "demerit against"):
            self.assertNotIn(word, text, word)


class Rewards(unittest.TestCase):
    def test_a_reward_is_recorded_for_the_gm_and_never_applied(self):
        st, do = table()
        self.assertFalse(do("ann", "reward", to="bob", kind="title", text="Bard of the Bell")[0])
        ok, pub, _ = do("gm", "reward", director=True, to="bob", kind="heroic_inspiration", text="the bell speech")
        self.assertTrue(ok)
        self.assertIn("character rules", pub)
        self.assertFalse(do("gm", "reward", director=True, to="bob", kind="gold", text="x")[0])
        self.assertEqual(st["rewards"][0]["applied"], False)

    def test_no_character_fields_anywhere(self):
        text = (ROOT / "sim" / "stage_full.py").read_text(encoding="utf-8").lower()
        for word in ("wounds", "hptotal", "\"xp\"", "charsheet", "spell"):
            self.assertNotIn(word, text, word)


class NotAttached(unittest.TestCase):
    def test_the_table_service_does_not_load_the_full_rules_yet(self):
        text = (ROOT / "tools" / "sim_service.py").read_text(encoding="utf-8")
        self.assertNotIn("stage_full", text)


if __name__ == "__main__":
    unittest.main()
