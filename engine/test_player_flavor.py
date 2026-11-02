"""PLAYER-FLAVOR-01 (the Player Client Plan, item 7): a player asks for a look for a creature they control; the GM approves it.
  py -3 -m unittest test_player_flavor
"""
import sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
import sim_service
import table_flavor as tf

ROOM, HERO, OWL = "Test room", "Lyra", "Familiar (Owl)"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "flavor.json"
        self.store = tf.FlavorStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, value, actor=HERO, character=HERO):
        return self.store.ask("Ann", character, actor, ROOM, value)


class Requests(Store):
    def test_a_look_waits_and_changes_nothing(self):
        self.ask({"name": "Moon Singer"})
        state, rev = self.store.get()
        self.assertEqual((state["entries"], rev), ({}, 0))
        self.assertEqual([a["actor"] for a in self.store.waiting()[0]], [HERO])

    def test_a_players_requests_are_theirs_alone(self):
        self.ask({"name": "Moon Singer"})
        self.assertEqual(len(self.store.waiting("lyra")[0]), 1)
        self.assertEqual(self.store.waiting("Bran")[0], [])

    def test_a_request_is_looks_only(self):
        for field in ("hp", "ac", "speed", "attacks", "share", "paint_until"):
            with self.assertRaises(ValueError, msg=field):
                self.ask({"name": "Moon Singer", field: 99})
        self.assertEqual(self.store.waiting()[0], [])

    def test_paint_goes_with_the_request(self):
        pic = "data:image/webp;base64,AAAA"
        self.assertEqual(self.ask({"paint": pic, "mask": pic, "paint_on": "p1-1"})["paint"], pic)
        with self.assertRaises(ValueError):
            self.ask({"paint": "https://example.com/picture.png"})

    def test_a_footnote_is_for_the_table(self):
        self.assertTrue(self.ask({"description": "Hums to the moon."})["share"])
        self.assertNotIn("share", self.ask({"name": "Moon Singer"}))

    def test_a_new_request_replaces_the_one_before(self):
        self.ask({"name": "First"})
        self.ask({"name": "Second"})
        asks = self.store.waiting()[0]
        self.assertEqual([a["flavor"]["name"] for a in asks], ["Second"])

    def test_each_change_moves_the_requests_revision(self):
        marks = [self.store.waiting()[1]]
        self.ask({"name": "One"})
        marks.append(self.store.waiting()[1])
        self.store.rule(HERO, False)
        marks.append(self.store.waiting()[1])
        self.assertEqual(len(set(marks)), 3)

    def test_requests_survive_a_restart(self):
        self.ask({"name": "Moon Singer"})
        again = tf.FlavorStore(self.path)
        self.assertEqual(again.waiting()[0][0]["flavor"]["name"], "Moon Singer")
        again.rule(HERO, True)
        self.assertEqual(tf.FlavorStore(self.path).get()[0]["entries"][tf.actor_key(tf.EVERY_MAP, HERO)]["name"], "Moon Singer")


class Answers(Store):
    def seen(self, names=(HERO,), room="Another room"):
        return tf.player_view(self.store.get()[0], room, names)["entries"]

    def test_approved_every_player_sees_it_on_every_map(self):
        self.ask({"name": "Moon Singer", "description": "Hums to the moon.", "role": "pet"})
        self.assertEqual(self.seen(), {})
        state, rev = self.store.rule(HERO, True)
        self.assertEqual(rev, 1)
        self.assertEqual(self.store.waiting()[0], [])
        shown = self.seen()[tf.actor_key(tf.EVERY_MAP, HERO)]
        self.assertEqual((shown["name"], shown["description"], shown["role"]), ("Moon Singer", "Hums to the moon.", "pet"))

    def test_approved_it_replaces_the_look_kept_for_this_map(self):
        here = tf.actor_key(ROOM, HERO)
        self.store.save({"version": 1, "entries": {here: {"name": "Old"}}}, 0)
        self.ask({"name": "New"})
        entries = self.store.rule(HERO, True)[0]["entries"]
        self.assertNotIn(here, entries)
        self.assertEqual(entries[tf.actor_key(tf.EVERY_MAP, HERO)]["name"], "New")

    def test_refused_the_old_look_stays_and_nothing_is_kept(self):
        every = tf.actor_key(tf.EVERY_MAP, HERO)
        self.store.save({"version": 1, "entries": {every: {"name": "Old"}}}, 0)
        self.ask({"name": "New"})
        state, rev = self.store.rule(HERO, False)
        self.assertEqual((state["entries"][every]["name"], rev), ("Old", 1))
        self.assertEqual(self.store.waiting()[0], [])

    def test_the_original_look_can_be_asked_for(self):
        every = tf.actor_key(tf.EVERY_MAP, HERO)
        self.store.save({"version": 1, "entries": {every: {"name": "Old"}}}, 0)
        self.ask({})
        self.assertNotIn(every, self.store.rule(HERO, True)[0]["entries"])

    def test_a_footnote_the_gm_kept_private_stays_private(self):
        every = tf.actor_key(tf.EVERY_MAP, HERO)
        self.store.save({"version": 1, "entries": {every: {"name": "Old", "description": "Secretly a spy."}}}, 0)
        self.ask({"name": "New"})
        kept = self.store.rule(HERO, True)[0]["entries"][every]
        self.assertEqual((kept["name"], kept["description"]), ("New", "Secretly a spy."))
        self.assertNotIn("description", self.seen()[every])

    def test_an_answer_counts_once(self):
        self.ask({"name": "New"})
        self.store.rule(HERO, True)
        with self.assertRaises(ValueError):
            self.store.rule(HERO, False)


class Door(Store):
    def setUp(self):
        super().setUp()
        everyone = [{"id": "a", "name": HERO, "pc": True}, {"id": "b", "name": "Bran", "pc": True},
                    {"id": "c", "name": OWL, "side": "friend"}, {"id": "d", "name": "Goblin Warrior 1", "side": "foe"}]
        sim = SimpleNamespace(sc={"combatants": everyone}, _summons=SimpleNamespace(made={"c": {"by": "a", "kind": "familiar"}}))
        self.service = sim_service.Service.__new__(sim_service.Service)
        self.service.flavor, self.service.live_scenario = self.store, {"map": {"name": ROOM}}
        self.service.live = SimpleNamespace(sim=sim, snapshot=lambda since: {"state": {"combatants": everyone}})
        self.lyra, self.bran = {"name": "Ann", "character": HERO}, {"name": "Ben", "character": "Bran"}

    def test_a_player_controls_their_character_and_what_it_summoned(self):
        self.assertEqual(self.service.flavor_own(self.lyra), [HERO, OWL])
        self.assertEqual(self.service.flavor_own(self.bran), ["Bran"])
        self.assertEqual(self.service.flavor_own({"name": "Cy", "character": ""}), [])

    def test_a_look_for_another_creature_is_refused(self):
        for actor in ("Bran", "Goblin Warrior 1", None):
            code, out = self.service.flavor_ask(self.lyra, {"actor": actor, "flavor": {"name": "Mine now"}})
            self.assertEqual((code, out["ok"]), (403, False), actor)
        self.assertEqual(self.store.waiting()[0], [])

    def test_only_the_asker_is_told_a_look_is_pending(self):
        code, out = self.service.flavor_ask(self.lyra, {"actor": OWL, "flavor": {"name": "Hoot"}})
        self.assertEqual(code, 200)
        mine = self.service.flavor_player(self.lyra, {})[1]["mine"]
        self.assertEqual(mine, {"actors": [HERO, OWL], "pending": {OWL: {"name": "Hoot"}}})
        other = self.service.flavor_player(self.bran, {})[1]
        self.assertEqual(other["mine"]["pending"], {})
        self.assertNotIn("Hoot", str(other))

    def test_a_seat_hears_when_its_request_is_answered(self):
        self.service.flavor_ask(self.lyra, {"actor": HERO, "flavor": {"name": "New"}})
        mark = self.service.flavor_player(self.lyra, {})[1]["rev"]
        self.assertTrue(self.service.flavor_player(self.lyra, {"rev": mark})[1]["unchanged"])
        self.store.rule(HERO, False)
        self.assertEqual(self.service.flavor_player(self.lyra, {"rev": mark})[1]["mine"]["pending"], {})

    def test_the_gm_gets_the_requests_only_when_they_changed(self):
        self.service.flavor_ask(self.lyra, {"actor": HERO, "flavor": {"name": "New"}})
        out = self.service.flavor_gm({})[1]
        self.assertEqual(out["asks"][0]["seat"], "Ann")
        self.assertNotIn("asks", self.service.flavor_gm({"asks_rev": out["asks_rev"]})[1])

    def test_only_the_gm_can_answer(self):
        self.assertIn("/api/flavor/ask", sim_service.DOOR_ROUTES)
        self.assertNotIn("/api/flavor/rule", sim_service.DOOR_ROUTES)
        self.assertNotIn("/api/flavor/save", sim_service.DOOR_ROUTES)
        self.assertGreaterEqual(sim_service.DOOR_BODY["/api/flavor/ask"], 2 * tf.MAX_PAINT + 4096)


if __name__ == "__main__":
    unittest.main()
