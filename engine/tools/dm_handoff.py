"""DM-SWAP-01 (GM 2026-10-25: "There is only one Mythastria ... You can also request a DM key and when receiving that,
your screen becomes the full DM version and the original DM becomes a player, except he also has a take back button on
his player screen"; asked, chose: the current GM approves each request; the old GM plays one of his own player
characters, even one he was not playing, or watches; the stand-in key stays beside this).

The swap, at the table:
1. A seated player asks to be the GM (players' door, POST /api/dm {op: "ask"}). One request waits at a time.
2. The owning GM (the GM door, this PC) sees it and approves, choosing the character he will play (one not held by a
   player's seat) or none, or refuses it.
3. The player's screen claims the role (op "claim"): it gets a GM session cookie, the same cookie the stand-in key gives,
   so the players' door serves it the full GM console (every request logged like a stand-in's).
4. Meanwhile the GM door is the old GM's player screen: its GM requests are refused, its table requests go through as a
   seat named "GM" playing the chosen character (Service.handed_request), and its pages open as the players' view.
5. Take back (GM door, op "take_back") ends the new GM's session at once; the new GM may also give it back (op "give_back").
Nothing is kept on disk: a restart ends a swap (the GM door is the GM again)."""
import hashlib, secrets, threading, time


def _h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Handoff:
    def __init__(self, clock=time.time):
        self.lock = threading.Lock()
        self.clock = clock
        self.asked = None          # {"seat", "character", "since"}: the waiting request
        self.refused = {}          # seat name -> the GM's reason (shown once to that seat)
        self.held = None           # {"to", "character" (the old GM's), "since", "cookie": hash or None}
        self.last = None           # how the last swap ended, for the screens: {"to", "why", "at"}

    # ------------------------------------------------------------------ what each side sees
    def active(self):
        return self.held is not None

    def view(self):
        with self.lock:
            return {"asked": dict(self.asked) if self.asked else None,
                    "held": {k: v for k, v in self.held.items() if k != "cookie"} if self.held else None,
                    "last": dict(self.last) if self.last else None}

    def old_dm_seat(self):
        """The GM door while the role is handed over: a seat named GM playing the character he chose (or none)."""
        with self.lock:
            return {"name": "GM", "character": (self.held or {}).get("character") or "", "hints": "off"}

    # ------------------------------------------------------------------ a seated player (players' door)
    def player(self, seat, req):
        op = req.get("op", "state")
        with self.lock:
            now = self.clock()
            name = seat["name"]
            if op == "ask":
                if self.held:
                    raise ValueError("%s is the GM now." % self.held["to"])
                if self.asked and self.asked["seat"] != name:
                    raise ValueError("%s has already asked to be the GM; the GM answers one request at a time." % self.asked["seat"])
                self.asked = {"seat": name, "character": seat.get("character") or "", "since": int(now)}
                self.refused.pop(name, None)
            elif op == "cancel":
                if self.asked and self.asked["seat"] == name:
                    self.asked = None
            elif op != "state":
                raise ValueError("op is ask, cancel, state or claim.")
            mine = self.held and self.held["to"] == name
            return {"ok": True, "asked": bool(self.asked and self.asked["seat"] == name),
                    "granted": bool(mine and not self.held["cookie"]), "dm": self.held["to"] if self.held else None,
                    "refused": self.refused.pop(name, None) if op == "state" else None}

    def claim(self, seat):
        """The approved seat takes the role: a new GM session cookie (its secret), once."""
        with self.lock:
            if not self.held or self.held["to"] != seat["name"]:
                raise ValueError("The GM has not handed the role to %s." % seat["name"])
            if self.held["cookie"]:
                raise ValueError("%s has already taken the GM role." % seat["name"])
            secret = secrets.token_urlsafe(32)
            self.held["cookie"] = _h(secret)
            return secret

    def check(self, cookie):
        """The new GM's seat name while the swap holds and this is its session cookie, else None."""
        if not isinstance(cookie, str) or not cookie:
            return None
        with self.lock:
            if self.held and self.held["cookie"] and secrets.compare_digest(self.held["cookie"], _h(cookie)):
                return self.held["to"]
            return None

    def give_back(self, cookie):
        with self.lock:
            if self.held and self.held["cookie"] and isinstance(cookie, str) and secrets.compare_digest(self.held["cookie"], _h(cookie)):
                self.last = {"to": self.held["to"], "why": "given back", "at": int(self.clock())}
                self.held = None
                return True
            return False

    # ------------------------------------------------------------------ the owning GM (GM door)
    def gm(self, req, characters):
        """op state | approve {character: one of `characters` or ""} | refuse {reason} | take_back."""
        op = req.get("op", "state")
        with self.lock:
            now = self.clock()
            if op == "approve":
                if self.held:
                    raise ValueError("%s is the GM now: take it back first." % self.held["to"])
                if not self.asked:
                    raise ValueError("No one is asking to be the GM.")
                character = req.get("character") or ""
                if character and character not in characters:
                    raise ValueError("Play one of your own characters (%s), or none to watch." % (", ".join(characters) or "none free"))
                self.held = {"to": self.asked["seat"], "character": character, "since": int(now), "cookie": None}
                self.asked = None
            elif op == "refuse":
                if not self.asked:
                    raise ValueError("No one is asking to be the GM.")
                reason = req.get("reason") or ""
                if not isinstance(reason, str) or len(reason) > 200:
                    raise ValueError("A reason is up to 200 characters.")
                self.refused[self.asked["seat"]] = reason or "The GM keeps the role for now."
                self.asked = None
            elif op == "take_back":
                if not self.held:
                    raise ValueError("You are the GM already.")
                self.last = {"to": self.held["to"], "why": "taken back", "at": int(now)}
                self.held = None
            elif op != "state":
                raise ValueError("op is state, approve, refuse or take_back.")
        return dict(self.view(), ok=True, characters=list(characters))
