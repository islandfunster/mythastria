"""GM 2026-10-25 ("make all DM parts only accessible if they are given a key by the current DM. No adventure page, no
remix, etc."): without the stand-in key the players' door serves only the players' pages.
  py -m unittest test_door_pages
"""
import json, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim")]
import sim_service

# MYTHASTRIA_TABLE: another dist folder (a worktree's) instead of the main one
TABLE = Path(os.environ.get("MYTHASTRIA_TABLE") or Path(__file__).resolve().parent.parent / "isles-table" / "dist")


def go(path, query=None, table=None):
    return sim_service.door_page(path, query or {}, table)


class DoorPages(unittest.TestCase):
    def test_the_players_pages_are_served(self):
        for path in ("/join.html", "/stage.html", "/rules-social.html", "/donate.html", "/play-ui.mjs", "/site.css", "/table-notice.json"):
            self.assertIsNone(go(path), path)
        self.assertIsNone(go("/play.html", {"view": ["player"]}))

    def test_an_actions_reply_hides_a_creatures_numbers(self):
        import table_seats
        snap = {"state": {"combatants": [{"name": "Goblin Warrior 3"}, {"name": "Mara", "pc": True}]}}
        out = table_seats.player_lines(["Mara attacks Goblin Warrior 3: d20 4 +5 = 9 vs AC 15 -> miss",
                                        "Mara deals 3 damage to Goblin Warrior 3 (7/10 HP left)",
                                        "Goblin Warrior 2 deals 3 damage to Mara (28/31 HP left)"], snap)
        self.assertNotIn("AC 15", out[0])
        self.assertNotIn("7/10", out[1])
        self.assertIn("28/31", out[2])

    def test_a_seat_never_sees_a_creatures_planning(self):
        import table_seats
        snap = {"state": {"combatants": [{"name": "Mara", "pc": True}]},
                "log": [{"n": 1, "kind": "bridge", "text": "ai-npc-turn offered to Guard 2: move 30 ft"}, {"n": 2, "kind": "chat", "text": "Guard 2 moves 30 ft."}]}
        self.assertEqual([e["n"] for e in table_seats.player_view(snap, "Mara")["log"]], [2])

    def test_every_gm_page_goes_to_the_join_page(self):
        for page in ("adventure", "oneshot", "remix", "characters", "replay", "region", "spells", "docs", "training", "index",
                     "standin"):                                       # GM 2026-10-28: no stand-in key
            self.assertEqual(go("/%s.html" % page), "/join.html", page)
        self.assertEqual(go("/"), "/join.html")
        self.assertEqual(go("/play.html"), "/play.html?view=player")      # the GM console becomes the players' view
        self.assertEqual(go("/recordings/any.json"), "/join.html")

    @unittest.skipUnless(TABLE.is_dir(), "the Isles Table folder is not on this PC")
    def test_case_and_trailing_dots_do_not_slip_past(self):
        for path in ("/REMIX.HTML", "/remix.html.", "/./adventure.html", "/maps/../remix.html", "/Recordings/x.json"):
            self.assertEqual(go(path, table=TABLE), "/join.html", path)
        self.assertIsNone(go("/JOIN.html", table=TABLE))


class PlayerPackage(unittest.TestCase):
    """PLAYER-PACKAGE-01: without the stand-in key, a page, script or stylesheet only from the player package's list."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.table = root / "dist"
        (root / "player-client").mkdir()
        self.table.mkdir()
        for f in ("join.html", "play.html", "play-ui.mjs", "site.css", "remix-panel.mjs", "seats-ui.mjs", "notes.json"):
            (self.table / f).write_text("x", encoding="utf-8")
        self.list = root / "player-client" / "files.json"
        self.list.write_text(json.dumps({"files": ["join.html", "play.html", "play-ui.mjs", "site.css"]}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_package_is_served_and_the_dm_tools_are_not(self):
        for path in ("/join.html", "/play-ui.mjs", "/site.css", "/notes.json"):
            self.assertIsNone(go(path, table=self.table), path)
        self.assertIsNone(go("/play.html", {"view": ["player"]}, table=self.table))
        for path in ("/remix-panel.mjs", "/SEATS-UI.MJS", "/seats-ui.mjs.", "/missing.js"):
            self.assertIs(go(path, table=self.table), False, path)

    def test_no_list_serves_no_code(self):
        self.list.unlink()
        self.assertIs(go("/play-ui.mjs", table=self.table), False)
        self.assertEqual(go("/join.html", table=self.table), "/join.html")
        self.assertIsNone(go("/notes.json", table=self.table))

    @unittest.skipUnless(TABLE.parent.joinpath("player-client", "files.json").is_file(), "no player package list yet")
    def test_the_real_package_leaves_out_the_dm_tools(self):
        for f in ("remix-panel.mjs", "director-ui.mjs", "map-picker.mjs", "seats-ui.mjs", "dm-swap-ui.mjs",
                  "adventure-ui.mjs", "rules-monitor-ui.mjs"):
            self.assertIs(go("/" + f, table=TABLE), False, f)
        self.assertIsNone(go("/play-ui.mjs", table=TABLE))
        self.assertIsNone(go("/rules-monitor.css", table=TABLE))   # play.html links it on every page
