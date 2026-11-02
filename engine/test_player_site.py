"""PLAYER-SITE-01 (GM 2026-10-28: the player client is a hosted HTML site): the players' door answers the hosted site's
pages (CORS) and no other site; the hosted site never reaches the stand-in key, and no seat asks to be the GM.
  py -m unittest test_player_site
"""
import http.client, json, sys, threading, unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim")]
import sim_service

SITE = "https://players.example"


class PlayerSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = sim_service.Service()
        cls.door = sim_service.ExclusiveServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        cls.port = cls.door.server_address[1]
        cls.door.RequestHandlerClass = sim_service.make_players_door(cls.svc, cls.port, None, (), (SITE + "/",))
        threading.Thread(target=cls.door.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.door.shutdown()
        cls.door.server_close()

    def ask(self, method, path, origin=None, body=None, headers=()):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers)
        if origin:
            h["Origin"] = origin
        if body is not None:
            h["Content-Type"] = "application/json"
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        r.read()
        c.close()
        return r.status, r.getheader("Access-Control-Allow-Origin")

    def test_the_hosted_site_may_ask(self):
        status, allow = self.ask("OPTIONS", "/api/join", SITE, headers={"Access-Control-Request-Method": "POST"})
        self.assertEqual((status, allow), (204, SITE))
        status, allow = self.ask("POST", "/api/join", SITE, {"op": "status", "ask": "none"})
        self.assertEqual(allow, SITE)
        self.assertNotEqual(status, 403)

    def test_any_other_site_is_refused(self):
        for method, body, headers in (("OPTIONS", None, {"Access-Control-Request-Method": "POST"}), ("POST", {"op": "status"}, {})):
            status, allow = self.ask(method, "/api/join", "https://elsewhere.example", body, headers)
            self.assertEqual((status, allow), (403, None), method)

    def test_no_stand_in_key_and_no_dm_request_from_the_player_client(self):
        self.assertEqual(self.ask("POST", "/api/standin", SITE, {"op": "state"})[0], 403)
        self.assertEqual(self.ask("POST", "/api/dm", SITE, {"op": "ask"})[0], 403)
        self.assertEqual(self.ask("POST", "/api/dm", None, {"op": "ask"})[0], 403)


if __name__ == "__main__":
    unittest.main()
