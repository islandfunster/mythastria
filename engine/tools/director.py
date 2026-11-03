"""GUEST-DIRECTOR-01 (GM 2026-10-21: "Yes, that's a good plan"; names from DECISIONS 2026-10-20 GUEST DIRECTOR): on this
one PC the showrunner (the campaign's owner) hands the GM console to a guest director (or a special guest director)
for a session or a fight, with only the GM controls the showrunner ticks, and takes it back at any time.

The service enforces it: while a guest directs, a GM-only request for a control the showrunner kept is refused (the
route and its grant are in GUARDS; a route a guest always keeps is in OPEN, with why). Players' own choices are never guarded. The state lives in memory only: restarting
the simulator service gives the console back to the showrunner (the way back if a take-back code is forgotten).
"""
import hashlib, re, secrets, threading

GRANTS = {                                       # what the showrunner can hand over, in the order the page shows it
    "fights": "Run fights and scenes (start and restart, Remix Live, lineups, changes mid-fight, traps, hazards, The Stage, the party's day)",
    "undo": "Undo (players' requests and the GM's Undo step)",
    "reveal": "Reveal the map and fog to the players",  # a page lock only: the reveal lives in the browser, no request to refuse
    "notes": "Write GM map notes",
    "maps": "Import and make maps (map paint and the atlas too)",
    "prep": "Remix Prep (adventures, saved remixes, one-shots, spell clarifications)",
    "players": "Let players in (approve, refuse, remove)",          # JOIN-01
    "market": "Run the market (shops, gold, approving carts)",      # MARKET-01
    "flavor": "Flavor (looks, and the players' requests for them)",  # FLAVOR-01
}
DEFAULT = ["fights", "undo", "reveal"]
NAME = re.compile(r"^[^\x00-\x1f<>]{1,40}$")
SHOWRUNNER = "showrunner"                        # a need no grant meets: moving the GM role itself
STAGE_DIRECTOR = ("spotlight", "pause", "resume", "stop", "newsession")   # sim/stage.py: only the Director does these


def _unless(need, *reads):
    """The route needs `need`, except for its read ops (the guest's pages still load)."""
    return lambda req: None if req.get("op") in reads else need


# route -> grant; a function of the request where only some requests to the route are GM-only
GUARDS = {
    "/api/live/new": "fights",
    "/api/live/act": lambda req: "undo" if req.get("op") in ("undo_approve", "undo_refuse") else None,
    "/api/live/ruling": "undo",                                  # GM 2026-10-24: ruling an Ask the GM request
    "/api/live/undo": "undo",                                    # GM-UNDO-01: the GM's Undo step
    "/api/live/freeze": "fights",                                # GM 2026-10-24: freezing the fight (End the adventure)
    "/api/live/control": "fights",                               # GM 2026-10-24: the GM plays a character
    "/api/live/reaction-mode": "fights",                         # OA-AUTO-01: Auto mode for the players' Reactions
    "/api/live/fly": "fights", "/api/live/light": "fights", "/api/live/srd": "fights", "/api/live/panic": "fights",
    "/api/live/scene": "fights", "/api/live/timer": "fights", "/api/live/social": "fights", "/api/live/sight": "fights",
    "/api/live/mount-mode": "fights",
    "/api/live/traps": _unless("fights", "catalog"), "/api/live/hazards": _unless("fights", "catalog"),
    "/api/stage": lambda req: "fights" if req.get("seat") == "GM" and isinstance(req.get("cmd"), dict)
                  and req["cmd"].get("op") in STAGE_DIRECTOR else None,    # the rest are anyone's: join, discuss, applaud
    "/api/party": lambda req: "fights" if req.get("op", "get") != "get" else None,
    "/api/adventures/day": lambda req: "fights" if req.get("op", "state") != "state" else None,
    "/api/adventures/downtime": lambda req: "fights" if req.get("op", "state") not in ("state", "plan") else None,
    "/api/chat/model": lambda req: "fights" if req.get("op") in ("load", "clear") else None,
    "/api/lineups": lambda req: "fights" if req.get("op") in ("save", "delete") else None,
    "/api/notes/save": "notes",
    "/api/import-map": "maps", "/api/import-map/draft": "maps", "/api/terrain-battle": "maps", "/api/site-map": "maps",
    "/api/map_paint/save": "maps",
    "/api/atlas/save": "maps", "/api/atlas/delete": "maps", "/api/atlas/move": "maps", "/api/atlas/import": "maps",
    "/api/atlas/project": "maps",
    "/api/remix/propose": "prep", "/api/remix/apply": "prep", "/api/remix/remove": "prep", "/api/remix/proof/start": "prep",
    "/api/adventures/load": "prep", "/api/adventures/unload": "prep",
    "/api/oneshot": _unless("prep", "setup", "list", "get", "map"),
    "/api/prep": lambda req: "prep" if req.get("op") == "save" else None,
    "/api/spells/clarify": "prep",
    "/api/seats": lambda req: "players" if req.get("op", "state") != "state" else None,
    "/api/market": lambda req: "market" if req.get("op", "state") not in ("state", "view", "catalog", "template") else None,
    "/api/rules/monitor": lambda req: "fights" if req.get("op", "state") not in ("state", "model") else None,   # RULES-MONITOR-01
    "/api/flavor/save": "flavor", "/api/flavor/rule": "flavor",
    "/api/dm": lambda req: SHOWRUNNER if req.get("op", "state") != "state" else None,   # DM-SWAP-01: the role itself
}

# Every other GM route, and why a guest keeps it; test_director.py fails on a route in neither list.
OPEN = {
    "/api/director": "hand over and take back: the take-back code is its own guard",
    "/api/live/state": "reads", "/api/stage/state": "reads", "/api/chat/log": "reads", "/api/messages": "reads",
    "/api/flavor": "reads", "/api/map_paint": "reads", "/api/spells": "reads", "/api/remix": "reads", "/api/live/aim": "reads",
    "/api/notes": "reads: the control kept is writing them, and the map draws them",
    "/api/remix/catalog": "reads", "/api/remix/state": "reads", "/api/remix/traps": "reads", "/api/remix/proof/status": "reads",
    "/api/adventures/state": "reads", "/api/adventures/plan": "reads", "/api/adventures/check": "changes nothing",
    "/api/adventures/check-status": "reads", "/api/terrain-battle/suggest": "reads", "/api/site-map/model": "reads",
    "/api/atlas/list": "reads", "/api/atlas/get": "reads", "/api/atlas/export": "reads",
    "/api/new": "the Simulator's own recordings", "/api/step": "the Simulator's own recordings",
    "/api/live/reaction": "a player's choice at the hotseat", "/api/live/stealth": "a player's choice at the hotseat",
    "/api/live/initiative": "a player's choice at the hotseat",
    "/api/chat": "everyone's", "/api/chat/share": "everyone's", "/api/roll": "everyone's",
    "/api/characters": "players' own sheets, and the browser keeps its own copy of the roster",
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
        title = "special guest director" if g["special"] else "guest director"
        if need == SHOWRUNNER:
            raise ValueError("%s (%s) can't do that: only the showrunner moves the GM role. The showrunner can take the console back."
                             % (g["name"], title))
        if need and need not in g["grants"]:
            raise ValueError("%s (%s) can't do that: the showrunner kept \"%s\". The showrunner can take the console back."
                             % (g["name"], title, GRANTS[need]))
