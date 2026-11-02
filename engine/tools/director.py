"""GUEST-DIRECTOR-01 (GM 2026-10-21: "Yes, that's a good plan"; names from DECISIONS 2026-10-20 GUEST DIRECTOR): on this
one PC the showrunner (the campaign's owner) hands the GM console to a guest director (or a special guest director)
for a session or a fight, with only the GM controls the showrunner ticks, and takes it back at any time.

The service enforces it: while a guest directs, a GM-only request for a control the showrunner kept is refused (the
route and its grant are in GUARDS). Players' own choices are never guarded. The state lives in memory only: restarting
the simulator service gives the console back to the showrunner (the way back if a take-back code is forgotten).
"""
import hashlib, re, secrets, threading

GRANTS = {                                       # what the showrunner can hand over, in the order the page shows it
    "fights": "Start and restart fights (map, party, Remix Live, lineups)",
    "undo": "Approve or refuse players' undos",
    "reveal": "Reveal the map and fog to the players",
    "notes": "Write GM map notes",
    "maps": "Import and make maps",
    "prep": "Remix Prep (adventures and saved remixes)",
    "players": "Let players in (approve, refuse, remove)",          # JOIN-01
    "market": "Run the market (shops, gold, approving carts)",      # MARKET-01
}
DEFAULT = ["fights", "undo", "reveal"]
NAME = re.compile(r"^[^\x00-\x1f<>]{1,40}$")

# route -> grant; a function of the request where only some requests to the route are GM-only
GUARDS = {
    "/api/live/new": "fights",
    "/api/live/act": lambda req: "undo" if req.get("op") in ("undo_approve", "undo_refuse") else None,
    "/api/live/ruling": "undo",                                  # GM 2026-10-24: ruling an Ask the GM request
    "/api/live/freeze": "fights",                                # GM 2026-10-24: freezing the fight (End the adventure)
    "/api/live/control": "fights",                               # GM 2026-10-24: the GM plays a character
    "/api/live/reaction-mode": "fights",                         # OA-AUTO-01: Auto mode for the players' Reactions
    "/api/lineups": lambda req: "fights" if req.get("op") in ("save", "delete") else None,
    "/api/notes/save": "notes",
    "/api/import-map": "maps", "/api/import-map/draft": "maps", "/api/terrain-battle": "maps",
    "/api/remix/propose": "prep", "/api/remix/apply": "prep", "/api/remix/remove": "prep", "/api/remix/proof/start": "prep",
    "/api/adventures/load": "prep", "/api/adventures/unload": "prep",
    "/api/seats": lambda req: "players" if req.get("op", "state") != "state" else None,
    "/api/market": lambda req: "market" if req.get("op", "state") not in ("state", "view", "catalog", "template") else None,
    "/api/rules/monitor": lambda req: "fights" if req.get("op", "state") not in ("state", "model") else None,   # RULES-MONITOR-01
}


class Director:
    def __init__(self):
        self.lock = threading.Lock()
        self.guest = None                        # {"name", "special", "grants", "code": (salt, hash) or None}

    def view(self):
        g = self.guest
        return {"ok": True, "directing": g["name"] if g else None,
                "title": ("Special guest director" if g["special"] else "Guest director") if g else "Showrunner",
                "grants": list(g["grants"]) if g else list(GRANTS), "code": bool(g and g["code"]),
                "choices": [{"id": k, "label": v} for k, v in GRANTS.items()], "default": DEFAULT,
                "note": "Restarting the simulator service gives the console back to the showrunner."}

    def hand(self, req):
        name, special, grants, code = req.get("name"), req.get("special", False), req.get("grants"), req.get("code") or ""
        if not isinstance(name, str) or not NAME.match(name.strip()):
            raise ValueError("A guest director's name is 1-40 characters.")
        if not isinstance(special, bool):
            raise ValueError("special is true or false.")
        if not isinstance(grants, list) or not all(g in GRANTS for g in grants) or len(set(grants)) != len(grants):
            raise ValueError("grants are some of: %s." % ", ".join(GRANTS))
        if not isinstance(code, str) or len(code) > 32:
            raise ValueError("A take-back code is at most 32 characters.")
        with self.lock:
            if self.guest:
                raise ValueError("%s is directing; the showrunner takes it back first." % self.guest["name"])
            salt = secrets.token_bytes(16)
            self.guest = {"name": name.strip(), "special": special, "grants": [g for g in GRANTS if g in grants],
                          "code": (salt, hashlib.sha256(salt + code.encode("utf-8")).digest()) if code else None}
        return self.view()

    def take_back(self, req):
        code = req.get("code") or ""
        with self.lock:
            if not self.guest:
                raise ValueError("The showrunner is already directing.")
            if self.guest["code"]:
                salt, digest = self.guest["code"]
                if not isinstance(code, str) or not secrets.compare_digest(hashlib.sha256(salt + code.encode("utf-8")).digest(), digest):
                    raise ValueError("That is not the take-back code.")
            self.guest = None
        return self.view()

    def request(self, req):
        op = req.get("op", "state")
        if op == "state":
            return self.view()
        if op == "hand":
            return self.hand(req)
        if op == "take_back":
            return self.take_back(req)
        raise ValueError("op is state, hand or take_back.")

    def check(self, route, req):
        """Raise ValueError when a guest directs and the request needs a control the showrunner kept."""
        g = self.guest
        if not g:
            return
        need = GUARDS.get(route)
        need = need(req) if callable(need) else need
        if need and need not in g["grants"]:
            raise ValueError("%s (%s) can't do that: the showrunner kept \"%s\". The showrunner can take the console back."
                             % (g["name"], "special guest director" if g["special"] else "guest director", GRANTS[need]))
