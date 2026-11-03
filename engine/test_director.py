"""GUEST-DIRECTOR-01: what a guest director may do. The walk over the GM routes is what keeps this honest: a new GM route
fails here until it is in director.GUARDS or director.OPEN, so a new GM control can't slip past a guest's limits."""
import re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import director  # noqa: E402

SERVICE = (ROOT / "tools" / "sim_service.py").read_text(encoding="utf-8")
ROUTE = re.compile(r'"(/api/[a-z0-9_\-/]+)"')


def gm_routes():
    """Every route the GM door answers: the dispatcher, the Remix and adventure routes it passes on, the atlas's."""
    start = SERVICE.index("service.director.check(route, req)")
    door = SERVICE[start:SERVICE.index("return Handler", start)]
    start = SERVICE.index("def remix_request")
    remix = SERVICE[start:SERVICE.index("    def ", start + 10)]
    routes = set(ROUTE.findall(door + remix))
    atlas = re.search(r"ATLAS_ROUTES = \(([^)]*)\)", SERVICE).group(1)
    routes |= {"/api/atlas/" + w for w in re.findall(r'"(\w+)"', atlas)}
    return {r for r in routes if not r.endswith("/")}


class Routes(unittest.TestCase):
    def test_the_walk_finds_the_dispatcher(self):
        found = gm_routes()
        for route in ("/api/live/fly", "/api/director", "/api/remix/apply", "/api/adventures/load", "/api/atlas/save"):
            self.assertIn(route, found)

    def test_every_gm_route_is_guarded_or_open_with_a_reason(self):
        self.assertEqual(sorted(gm_routes() - set(director.GUARDS) - set(director.OPEN)), [])

    def test_no_route_is_listed_that_does_not_exist(self):
        self.assertEqual(sorted((set(director.GUARDS) | set(director.OPEN)) - gm_routes()), [])

    def test_a_route_is_never_both(self):
        self.assertEqual(sorted(set(director.GUARDS) & set(director.OPEN)), [])

    def test_every_guard_names_a_real_grant(self):
        for route, need in director.GUARDS.items():
            if not callable(need):
                self.assertIn(need, director.GRANTS, route)


class Guest(unittest.TestCase):
    def guest(self, grants=(), code=""):
        d = director.Director()
        d.hand({"name": "Pat", "grants": list(grants), "code": code})
        return d

    def refused(self, d, route, **req):
        with self.assertRaisesRegex(ValueError, "can't do that"):
            d.check(route, req)

    def test_the_showrunner_is_never_refused(self):
        director.Director().check("/api/live/fly", {"op": "creature"})

    def test_nothing_granted_refuses_what_used_to_get_through(self):
        d = self.guest()
        for route, req in (("/api/live/fly", {"op": "announce"}), ("/api/live/traps", {"op": "place"}),
                           ("/api/live/hazards", {"op": "weather"}), ("/api/live/light", {}), ("/api/live/srd", {}),
                           ("/api/live/panic", {}), ("/api/live/scene", {}), ("/api/live/undo", {}), ("/api/live/timer", {}),
                           ("/api/oneshot", {"op": "publish"}), ("/api/prep", {"op": "save"}), ("/api/flavor/save", {}),
                           ("/api/flavor/rule", {}), ("/api/map_paint/save", {}), ("/api/site-map", {}),
                           ("/api/chat/model", {"op": "load"}), ("/api/dm", {"op": "approve"}),
                           ("/api/adventures/day", {"op": "long"}), ("/api/spells/clarify", {}),
                           ("/api/atlas/project", {"action": "delete"}), ("/api/party", {"op": "save"})):
            with self.subTest(route=route):
                self.refused(d, route, **req)

    def test_each_grant_opens_its_own_controls_only(self):
        d = self.guest(["fights"])
        d.check("/api/live/fly", {"op": "announce"})
        d.check("/api/adventures/day", {"op": "long"})
        self.refused(d, "/api/flavor/save")
        d = self.guest(["flavor", "undo", "prep", "maps"])
        for route, req in (("/api/flavor/save", {}), ("/api/live/undo", {}), ("/api/oneshot", {"op": "save"}), ("/api/map_paint/save", {})):
            d.check(route, req)
        self.refused(d, "/api/live/panic")

    def test_read_ops_stay_open_so_pages_load(self):
        d = self.guest()
        for route, req in (("/api/live/traps", {"op": "catalog"}), ("/api/live/hazards", {"op": "catalog"}),
                           ("/api/oneshot", {"op": "setup"}), ("/api/oneshot", {"op": "list"}), ("/api/prep", {"op": "state"}),
                           ("/api/adventures/day", {}), ("/api/adventures/downtime", {"op": "plan"}), ("/api/party", {}),
                           ("/api/chat/model", {"op": "state"}), ("/api/dm", {"op": "state"})):
            d.check(route, req)

    def test_players_own_choices_stay_open(self):
        d = self.guest()
        for route, req in (("/api/live/act", {"op": "attack"}), ("/api/live/reaction", {}), ("/api/live/stealth", {}),
                           ("/api/live/initiative", {}), ("/api/stage", {"seat": "Pat", "cmd": {"op": "spotlight"}}),
                           ("/api/stage", {"seat": "GM", "cmd": {"op": "applaud"}})):
            d.check(route, req)

    def test_the_stage_directors_commands_are_kept(self):
        self.refused(self.guest(), "/api/stage", seat="GM", cmd={"op": "spotlight"})
        self.guest(["fights"]).check("/api/stage", {"seat": "GM", "cmd": {"op": "spotlight"}})

    def test_the_gm_role_never_moves_whatever_is_granted(self):
        d = self.guest(director.GRANTS)
        for op in ("approve", "refuse", "take_back"):
            with self.assertRaisesRegex(ValueError, "only the showrunner"):
                d.check("/api/dm", {"op": op})

    def test_flavor_is_handed_only_when_ticked(self):
        self.assertNotIn("flavor", director.DEFAULT)
        self.assertIn("flavor", [c["id"] for c in director.Director().view()["choices"]])

    def test_take_back_with_a_code(self):
        d = self.guest(code="owl")
        for code in ("", "cat"):
            with self.assertRaisesRegex(ValueError, "not the take-back code"):
                d.take_back({"code": code})
        self.assertIsNone(d.take_back({"code": "owl"})["directing"])

    def test_take_back_without_a_code(self):
        self.assertIsNone(self.guest().take_back({})["directing"])

    def test_one_guest_at_a_time(self):
        with self.assertRaisesRegex(ValueError, "Pat is directing"):
            self.guest().hand({"name": "Sam", "grants": []})


if __name__ == "__main__":
    unittest.main()
