"""JOIN-01 (GM 2026-10-21: "let's work on the handshaking protocol to connect players with the main DM engine"; asked,
chose "over the internet" and "GM approves each"): how a player's page joins the GM's engine and is recognised.
The protocol: docs/development/JOIN_PROTOCOL.md.

A player asks (name, character) at the players' door with the GM's invite code (GM 2026-10-21, on the internet:
players join only with an invite the GM issues); the GM approves or refuses; an approved player gets a seat ticket, and every players'-door request names its seat by that ticket only. What a seat may see is cut here
(player_view) before anything leaves the service. In memory only, like the guest director: restarting the service
closes the door and forgets every request and seat.
"""
import hashlib, re, secrets, threading, time

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]{0,39}$")         # as sim_service.SEAT
CHARACTER = re.compile(r"^[^\x00-\x1f<>]{0,40}$")
RESERVED = {"gm", "director", "showrunner"}
MAX_WAITING, MAX_SEATS = 8, 12
# HINTS-01 (GM 2026-10-22: "Hints are opt-in"): a seat's turn hints. Every seat starts Off; only its player turns them
# on (Suggestions come with step H7). sim/live_hints.py builds them; player_view keeps them for that seat only.
HINT_LEVELS = ("off", "reminders")
# HINTS-01 step H3 (GM 2026-10-28: "Build H3"; docs/development/LLM_PLAYTESTER_AND_HINTS.md "Levels, per seat"): the GM's
# table cap and a limit per seat, each the highest level allowed. The GM can lower a seat's level, never raise it: only
# the player turns hints on, within both. In memory, like the seats: a restart sets the cap back to players choose.
HINT_WORDS = {"off": "Off", "reminders": "Reminders"}
ASK_TTL = 600                                                     # an unanswered request lapses after 10 minutes
AWAY = 15                                                          # no check-in for 15 s: shown as away
BEAT = 5                                                           # the join page checks in every 5 s


class WrongInvite(ValueError):
    """An invite code that is not the GM's current one (BETA-B: counted against the visitor at the door)."""


class NoSeat(Exception):
    """The ticket names no seat (never given, removed, left, or the service restarted)."""


class NoticeNeeded(Exception):
    """The seat accepted an older notice than the table's current one (JOIN-01 notice, GM 2026-10-22)."""


def accepted(notice, version):
    """JOIN-01 notice (GM 2026-10-22: privacy notice and age; chose 18+ only): the page's acceptance of the current
    notice (dist/table-notice.json), both boxes ticked. Only the version and the time are kept, with the seat."""
    if not version:
        return None                                                # no notice file: nothing to accept
    if not isinstance(notice, dict):
        raise ValueError("Read and accept the table's notice first.")
    if notice.get("version") != version:
        raise ValueError("The table's notice changed: read it again (reload the page).")
    if notice.get("adult") is not True:
        raise ValueError("This table is for adults only (18 or older).")
    if notice.get("accept") is not True:
        raise ValueError("Read and accept the notice and table rules first.")
    return version


def new_invite():
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


def _hash(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _same(a, b):
    return (a or "").strip().casefold() == (b or "").strip().casefold()


class Seats:
    def __init__(self, clock=time.time, notice=lambda: None):
        self.lock = threading.Lock()
        self.clock = clock
        self.notice = notice                                       # the current notice version (None: no notice)
        self.open = False                                          # the GM opens the door; closed at every start
        self.invite = None                                         # the code in the GM's invite link; new at each opening
        self.asks = {}                                             # id -> request
        self.seats = {}                                            # ticket hash -> seat
        self.cap = HINT_LEVELS[-1]                                 # H3: the table cap (the highest: players choose)

    # ------------------------------------------------------------------ H3: hint levels
    @staticmethod
    def _lower(a, b):
        return min(a, b, key=HINT_LEVELS.index)

    def hint_limit(self, seat):
        """The highest hint level this seat may choose now: the table cap and the seat's own limit."""
        return self._lower(self.cap, seat.get("hints_limit", HINT_LEVELS[-1]))

    def _clamp(self, seat):
        """Lower the seat's level to what it may have (never raise it)."""
        seat["hints"] = self._lower(seat.get("hints", "off"), self.hint_limit(seat))

    # ------------------------------------------------------------------ checks
    @staticmethod
    def _name(name):
        if not isinstance(name, str) or not NAME.match(name.strip()) or name.strip().casefold() in RESERVED:
            raise ValueError("A player's name is letters, digits, spaces, ' and - (up to 40); GM is the GM's.")
        return name.strip()

    @staticmethod
    def _character(character):
        character = "" if character is None else character
        if not isinstance(character, str) or not CHARACTER.match(character):
            raise ValueError("A character's name is up to 40 characters.")
        return character.strip()

    def _lapse(self, now):
        for k in [k for k, a in self.asks.items() if a["answer"] is None and now - a["at"] > ASK_TTL]:
            del self.asks[k]

    def _taken(self, name=None, character=None, but=None):
        """The seat or waiting request that already has this name or character."""
        for s in list(self.seats.values()) + [a for a in self.asks.values() if a["answer"] is None]:
            if s is but:
                continue
            if name and _same(s["name"], name):
                return "%s is already at the table or asking." % s["name"]
            if character and _same(s["character"], character):
                return "%s already plays %s." % (s["name"], s["character"])
        return None

    # ------------------------------------------------------------------ the player's side (players' door)
    def player(self, req):
        op = req.get("op")
        if op in ("beat", "leave", "accept", "hints"):
            seat = self.seat_for(req.get("ticket"))
            if op == "leave":
                with self.lock:
                    self.seats = {k: s for k, s in self.seats.items() if s is not seat}
                return {"ok": True, "left": True}
            current = self.notice()
            if op == "accept":                                     # a new notice version: the seated player accepts again
                with self.lock:
                    seat.update(notice=accepted(req.get("notice"), current), accepted_at=int(self.clock()))
            if op == "hints":                                      # HINTS-01: the player's own switch (Off / Reminders)
                if req.get("level") not in HINT_LEVELS:
                    raise ValueError("Hints are %s." % " or ".join(HINT_LEVELS))
                with self.lock:
                    top = self.hint_limit(seat)                    # H3: within the GM's table cap and seat limit
                    if HINT_LEVELS.index(req["level"]) > HINT_LEVELS.index(top):
                        raise ValueError("The GM has set hints to %s %s." % (
                            HINT_WORDS[top], "for the whole table" if top == self.cap else "for you"))
                    seat["hints"] = req["level"]
            return {"ok": True, "seat": self._seat_view(seat, self.clock()), "open": self.open, "beat": BEAT,
                    "notice_ok": seat.get("notice") == current}
        if op == "ask":
            return self.ask(req)
        ask, key = req.get("ask"), req.get("key")
        if op not in ("wait", "cancel"):
            raise ValueError("op is ask, wait, cancel, beat, accept, hints or leave.")
        with self.lock:
            self._lapse(self.clock())
            a = self.asks.get(ask) if isinstance(ask, str) else None
            if not a or not isinstance(key, str) or not secrets.compare_digest(_hash(key), a["key"]):
                return {"ok": True, "status": "gone", "text": "That request is no longer waiting; ask again."}
            if op == "cancel":
                del self.asks[ask]
                return {"ok": True, "status": "cancelled"}
            if a["answer"] is None:
                return {"ok": True, "status": "waiting", "open": self.open}
            del self.asks[ask]                                     # an answer is given once
            if a["answer"] == "refused":
                return {"ok": True, "status": "refused", "reason": a["reason"]}
            return {"ok": True, "status": "approved", "ticket": a["ticket"], "seat": {"name": a["name"], "character": a["character"]}}

    def ask(self, req):
        name, character, invite = self._name(req.get("name")), self._character(req.get("character")), req.get("invite")
        notice = accepted(req.get("notice"), self.notice())
        with self.lock:
            now = self.clock()
            self._lapse(now)
            if not self.open:
                raise ValueError("The GM has not opened the door for players yet.")
            if not isinstance(invite, str) or not self.invite or not secrets.compare_digest(invite.strip().upper(), self.invite):
                raise WrongInvite("That invite code is not the GM's current one; ask the GM for the invite link.")
            if sum(1 for a in self.asks.values() if a["answer"] is None) >= MAX_WAITING:
                raise ValueError("Too many players are waiting; try again in a minute.")
            taken = self._taken(name, character)
            if taken:
                raise ValueError(taken)
            ask, key = secrets.token_urlsafe(12), secrets.token_urlsafe(24)
            self.asks[ask] = {"id": ask, "name": name, "character": character, "at": now, "key": _hash(key),
                              "answer": None, "reason": "", "ticket": None, "notice": notice}
        return {"ok": True, "status": "waiting", "ask": ask, "key": key, "beat": BEAT}

    def seat_for(self, ticket):
        """The seat a ticket names (any request with it counts as a check-in); NoSeat when there is none."""
        if not isinstance(ticket, str) or not 0 < len(ticket) <= 100:
            raise NoSeat()
        with self.lock:
            seat = self.seats.get(_hash(ticket))
            if not seat:
                raise NoSeat()
            seat["seen"] = self.clock()
            return seat

    def name_for(self, ticket):
        """The name of the seat a ticket names, or None: no check-in (CHEAT-LOG-01)."""
        if not isinstance(ticket, str) or not 0 < len(ticket) <= 100:
            return None
        with self.lock:
            return (self.seats.get(_hash(ticket)) or {}).get("name")

    def check_notice(self, seat):
        """NoticeNeeded while the seat's accepted notice is not the current one."""
        if seat.get("notice") != self.notice():
            raise NoticeNeeded()

    # ------------------------------------------------------------------ the GM's side (GM door)
    def gm(self, req, characters=()):
        op = req.get("op", "state")
        with self.lock:
            now = self.clock()
            self._lapse(now)
            if op == "door":
                if not isinstance(req.get("open"), bool):
                    raise ValueError("open is true or false.")
                if req["open"] and not self.open:
                    self.invite = new_invite()                     # closing and opening again makes the old link useless
                self.open = req["open"]
            elif op == "invite":
                self.invite = new_invite()
            elif op in ("approve", "refuse"):
                a = self.asks.get(req.get("ask")) if isinstance(req.get("ask"), str) else None
                if not a or a["answer"] is not None:
                    raise ValueError("That request is no longer waiting.")
                if op == "refuse":
                    reason = req.get("reason") or ""
                    if not isinstance(reason, str) or len(reason) > 200:
                        raise ValueError("A reason is up to 200 characters.")
                    a.update(answer="refused", reason=reason.strip())
                else:
                    character = self._character(req["character"]) if "character" in req else a["character"]
                    taken = self._taken(None, character, but=a)
                    if taken:
                        raise ValueError(taken)
                    if len(self.seats) >= MAX_SEATS:
                        raise ValueError("The table has %d seats; remove one first." % MAX_SEATS)
                    ticket = secrets.token_urlsafe(32)
                    a.update(answer="approved", character=character, ticket=ticket)
                    self.seats[_hash(ticket)] = {"name": a["name"], "character": character, "since": now, "seen": now,
                                                 "notice": a["notice"], "accepted_at": int(a["at"]), "hints": "off"}
            elif op in ("remove", "assign"):
                seat = next((s for s in self.seats.values() if _same(s["name"], req.get("name"))), None)
                if not seat:
                    raise ValueError("No player of that name is seated.")
                if op == "remove":
                    self.seats = {k: s for k, s in self.seats.items() if s is not seat}
                else:
                    character = self._character(req.get("character"))
                    taken = self._taken(None, character, but=seat)
                    if taken:
                        raise ValueError(taken)
                    seat["character"] = character
            elif op == "hints_cap":                                # H3: the table cap
                if req.get("level") not in HINT_LEVELS:
                    raise ValueError("The table cap is %s." % " or ".join(HINT_LEVELS))
                self.cap = req["level"]
                for s in self.seats.values():
                    self._clamp(s)
            elif op == "hints_limit":                              # H3: one seat's limit (lowers its level, never raises)
                seat = next((s for s in self.seats.values() if _same(s["name"], req.get("name"))), None)
                if not seat:
                    raise ValueError("No player of that name is seated.")
                if req.get("level") not in HINT_LEVELS:
                    raise ValueError("A seat's limit is %s." % " or ".join(HINT_LEVELS))
                seat["hints_limit"] = req["level"]
                self._clamp(seat)
            elif op != "state":
                raise ValueError("op is state, door, invite, approve, refuse, remove, assign, hints_cap or hints_limit.")
            return {"ok": True, "open": self.open, "invite": self.invite if self.open else None, "characters": list(characters),
                    "notice": self.notice(), "hints_cap": self.cap,
                    "asks": [{"ask": a["id"], "name": a["name"], "character": a["character"], "waited": int(now - a["at"]),
                              "notice": a["notice"]}
                             for a in sorted(self.asks.values(), key=lambda a: a["at"]) if a["answer"] is None],
                    "seats": [self._seat_view(s, now) for s in sorted(self.seats.values(), key=lambda s: s["since"])]}

    def _seat_view(self, s, now):
        ago = int(now - s["seen"])
        return {"name": s["name"], "character": s["character"], "connected": ago <= AWAY, "seen_ago": ago,
                "notice": s.get("notice"), "accepted_at": s.get("accepted_at"), "hints": s.get("hints", "off"),
                # H3: the highest level it may choose now, and the GM's limit for this seat alone
                "hints_max": self.hint_limit(s), "hints_limit": s.get("hints_limit", HINT_LEVELS[-1])}


# ---------------------------------------------------------------------- what a seat may see
def player_view(snap, character, hints="off", watching=False):
    """A live snapshot cut for one seat: the player characters and the creatures the party sees now; log lines naming a
    creature it does not see are left out; the waiting character's offers only for the seat that plays it, with its
    turn hints (HINTS-01) only when that seat's level is Reminders.
    GM 2026-10-25 ("When a player joins as watch only, nothing can be seen or shown. They need to automatically get all
    the player's views"): a watching seat (no character) gets each player character's offers on its turn too, marked
    watching (read only: the door refuses a watcher's choices), without its hints."""
    if not isinstance(snap, dict):
        return snap
    out = dict(snap)
    sight = snap.get("party_sight") or {}
    seen = set(sight.get("creatures") or [])
    state = snap.get("state")
    if isinstance(state, dict):
        everyone = state.get("combatants") or []
        mine_id = next((c.get("id") for c in everyone if c.get("pc") and character and _same(c.get("name"), character)), None)
        # SIGHT-01 (GM 2026-10-27: "which creatures can be seen according to each player's vision by each player"): a
        # seat whose character stands sees what that character sees (sim/combat_tracker.py: the engine's sight, and the
        # GM's picks); a watcher, or a seat whose character is down, sees what the party sees
        own = ((snap.get("tracker") or {}).get("sight") or {}).get(mine_id)
        if own is not None:
            seen = set(own)
        keep = [c for c in everyone if c.get("pc") or c.get("id") in seen]
        # MAP-LAYERS-01 (GM 2026-10-24): an Invisible creature only for a seat whose own character sees it (Truesight,
        # Blindsight); the seat's own Invisible character stays (the page draws it faded)
        invisible, seen_by = set(sight.get("invisible") or []), sight.get("seen_by") or {}
        keep = [c for c in keep if c.get("id") not in invisible or c.get("id") == mine_id
                or c.get("id") in (seen_by.get(mine_id) or [])]
        kept = {c.get("id") for c in keep}
        if isinstance(snap.get("party_sight"), dict):          # never another character's sight or an unseen id
            out["party_sight"] = dict({k: v for k, v in sight.items() if k != "seen_by"},
                                      invisible=[i for i in invisible if i in kept],
                                      creatures=[c.get("id") for c in keep if not c.get("pc")])   # SIGHT-01: this seat's own, for its page
        if isinstance(snap.get("layers"), dict):
            out["layers"] = dict(snap["layers"], mounts=[m for m in snap["layers"].get("mounts") or []
                                                         if m.get("rider") in kept and m.get("mount") in kept])
        unseen = [c.get("name") for c in everyone if c not in keep and c.get("name")]
        # GM 2026-10-27 ("cut creatures' exact Hit Points at the players' door so a player's browser only gets the words"):
        # a creature (not a party member) comes with its health in words, never its Hit Points
        out["state"] = dict(state, combatants=[c if c.get("pc") else health_only(c) for c in keep])
        if state.get("active") is not None and state["active"] not in {c.get("id") for c in keep}:
            out["state"]["active"] = None
        out["log"] = [hp_words(e, {c.get("name") for c in everyone if not c.get("pc")})   # GM 2026-10-27: no creature HP
                      for e in snap.get("log") or [] if (e.get("kind") == "gm" or not any(n in str(e.get("text", "")) for n in unseen))
                      and e.get("kind") not in ("secret", "bridge")]   # goal 15: the GM's own lines (what a creature knows); play-test: its
                                                                 # planning lines (bridge) too; ON-THE-FLY-01: the
                                                                 # GM's words read to the table always arrive, whoever they name
        ids = {c.get("id") for c in keep}                          # a cast's effect: only creatures the party sees
        out["effects"] = [dict(e, effect=dict(e["effect"], targets=[t for t in e["effect"].get("targets") or [] if t in ids]))
                          for e in snap.get("effects") or [] if isinstance(e.get("effect"), dict) and e.get("caster") in ids]
        # GM 2026-10-24 (sim/traps.py): a player's map shows only the traps the party knows (found, gone off, gear)
        out["traps"] = [{k: v for k, v in t.items() if (k != "area" or t.get("rubble")) and k not in ("known_by", "foe_found")}
                        for t in snap.get("traps") or [] if t.get("known")]   # goal 15: never what the creatures know
        # LIGHTS-01 (2026-10-26): a light carried by a creature this seat keeps, or lying on a square the party sees now
        if isinstance(snap.get("lights"), dict):
            now = {tuple(p) for p in sight.get("squares") or [] if isinstance(p, list)}
            out["lights"] = dict(snap["lights"], sources=[l for l in snap["lights"].get("sources") or []
                                                          if (l.get("holder") in kept if l.get("holder") else
                                                              tuple(l.get("at") or ()) in now)])
        mine = next((c for c in keep if c.get("id") == snap.get("waiting")), None)
        control = snap.get("gm_control") or {}                     # GM 2026-10-24: only this seat's own character
        out["gm_control"] = {k: v for k, v in control.items() if k == mine_id}
        out["tracker"] = __import__("combat_tracker").player_cut(snap.get("tracker"), kept)   # COMBAT-TRACKER-01
        if watching and not character and isinstance(snap.get("offers"), dict):   # mine: the waiting creature
            out["offers"] = (dict({k: v for k, v in snap["offers"].items() if k != "hints"}, watching=True)
                             if mine and mine.get("pc") else None)
        elif not (mine and character and _same(mine.get("name"), character)) or control.get(mine_id):
            out["offers"] = None
        elif isinstance(snap.get("offers"), dict) and hints != "reminders":
            out["offers"] = {k: v for k, v in snap["offers"].items() if k != "hints"}
        if isinstance(out.get("offers"), dict):
            out["offers"] = seen_offers(out["offers"], ids)
        # SPELL-BATCH-02: a Reaction asked (Shield, Counterspell): the whole question for the seat that plays that
        # character (mine; not while the GM holds it), only who decides for the others
        r = snap.get("reaction")
        if isinstance(r, dict):
            own = r.get("pc") == mine_id and bool(character) and not control.get(mine_id)
            out["reaction"] = dict(r, mine=True) if own else {"n": r.get("n"), "name": r.get("name"), "spell": r.get("spell")}
        import stealth                                             # STEALTH-01: its own stealth; the group check's own roll
        out["stealth"] = stealth.player_cut(snap.get("stealth"), mine_id if character else None)
        import initiative                                          # INITIATIVE-01: its own roll; who has rolled
        out["initiative"] = initiative.player_cut(snap.get("initiative"), mine_id if character else None)
    else:
        out["log"], out["offers"], out["effects"], out["traps"], out["gm_control"] = [], None, [], [], {}
        out["reaction"] = None
        out["stealth"] = None
        out["initiative"] = None
        out["tracker"] = None
        out.pop("lights", None)                                    # LIGHTS-01
    if isinstance(snap.get("hazards"), dict):                  # HAZARDS-01: the ice and water show; what it holds does not
        out["hazards"] = {"weather": snap["hazards"].get("weather") or [],
                          "zones": [{k: v for k, v in z.items() if k != "holds"} for z in snap["hazards"].get("zones") or []]}
    return out


def health(hp, top):
    """SRD 5.2.1 Rules Glossary, Bloodied: half its Hit Points or fewer. The words a player gets for a creature's health."""
    hp, top = max(0, int(hp or 0)), max(1, int(top or 1))
    return "down" if hp <= 0 else "unhurt" if hp >= top else "Bloodied" if hp * 2 <= top else "hurt"


SCALE = {"unhurt": 4, "hurt": 3, "Bloodied": 1, "down": 0}       # out of 4: the word, as numbers the pages can draw


def health_only(c):
    """A creature for a seat: its health in words, and its Hit Points replaced by the word's place on a scale of 4 (the
    pages' checks need numbers; these say no more than the word). Its real Hit Points and its AC are never sent
    (GM 2026-10-27: "cut creatures' AC at the players' door too")."""
    word = "down" if c.get("down") else health(c.get("hp"), c.get("hp_max"))
    return dict({k: v for k, v in c.items() if k not in ("temp_hp", "ac", "ac_why")}, hp=SCALE[word], hp_max=4, ac=None, health=word)


_HP_LEFT = re.compile(r"(damage to (.+?)) \((\d+)/(\d+) HP left\)")
_FOCUS = re.compile(r"(concentrates on (.+?)) \(\d+ HP left\)")
_VS_AC = re.compile(r" vs AC \d+")


def hp_words(entry, creatures):
    """A log line for a seat: a creature's "(7/17 HP left)" becomes "(hurt)", and an attack on a creature loses its
    "vs AC 15" (the roll and hit or miss stay); the party's own numbers stay."""
    text = str(entry.get("text", ""))
    new = _HP_LEFT.sub(lambda m: "%s (%s)" % (m.group(1), health(m.group(3), m.group(4))) if m.group(2) in creatures else m.group(0), text)
    new = _FOCUS.sub(lambda m: m.group(1) if m.group(2) in creatures else m.group(0), new)
    if any("attacks %s" % n in new for n in creatures):
        new = _VS_AC.sub("", new)
    return entry if new == text else dict(entry, text=new)


def player_lines(lines, snap):
    """An action's own result lines for a seat, by the log's rule: no creature's exact HP or AC (play-test 2026-11-02: the
    reply to a player's attack carried them, though the table's log did not)."""
    names = {c.get("name") for c in ((snap or {}).get("state") or {}).get("combatants") or [] if not c.get("pc")}
    return [hp_words({"text": x}, names)["text"] if isinstance(x, str) else x for x in lines]


def seen_offers(offers, ids):
    """INVISIBILITY-01 (2026-10-26): a seat's offers name only the creatures its map keeps. A creature left out (an
    Invisible one its character can't see) is neither a legal target nor a refused one there: the targets and the
    reasons of each attack, spell and action, and the creatures to mount."""
    def cut(e):
        if not isinstance(e, dict):
            return e
        e = dict(e)
        for k in ("targets", "distant_targets"):
            if isinstance(e.get(k), list):
                e[k] = [t for t in e[k] if t in ids]
        if isinstance(e.get("refused"), dict):
            e["refused"] = {t: why for t, why in e["refused"].items() if t in ids}
        return e
    out = {k: [cut(e) for e in v] if isinstance(v, list) else v for k, v in offers.items()}
    if isinstance(out.get("mount"), dict) and isinstance(out["mount"].get("candidates"), list):
        out["mount"] = dict(out["mount"], candidates=[m for m in out["mount"]["candidates"] if m.get("target") in ids])
    if isinstance(out.get("hints"), dict):                     # HINTS-01 H4-H6: the facts name seen creatures only
        h = dict(out["hints"])
        if isinstance(h.get("attacks"), dict):
            h["attacks"] = {k: {t: f for t, f in row.items() if t in ids} for k, row in h["attacks"].items()}
        r = h.get("reach")
        if isinstance(r, dict):
            squares = {}
            for sq, f in (r.get("squares") or {}).items():
                f = {k: [i for i in f.get(k) or [] if i in ids] for k in ("near", "oa")}
                if f["near"] or f["oa"]:
                    squares[sq] = f
            h["reach"] = {"foes": {i: ft for i, ft in (r.get("foes") or {}).items() if i in ids}, "squares": squares}
        out["hints"] = h
    return out


def player_scenario(scenario):
    """The scenario without the dice seed and Remix's GM text."""
    if not isinstance(scenario, dict):
        return scenario
    return {k: v for k, v in scenario.items() if k not in ("seed", "remix")}


# BETA-B (GM 2026-10-22: a blind playability test; testers see only the players' pages): what a player reads is game
# words, never the machinery. Messages from the rules (a refusal, a log line) keep their sense; only these words change.
_WORDS = [(re.compile(r"\s*\((?:see )?SRD 5\.2\.1[^)]*\)"), ""), (re.compile(r"\bSRD 5\.2\.1\b|\bSRD\b"), "the rules"),
          (re.compile(r"\s*/api/[\w/-]+"), ""),
          (re.compile(r"\b(simulator service|simulator|service|engine)\b", re.I), lambda m: "Table" if m.group(0)[0].isupper() else "table")]
_TEXT_KEYS = {"error", "refused", "reason", "text", "lines", "why", "label"}


def player_words(obj, key=None):
    """A door answer with game words in its messages; the chat (players' own words) is left as written."""
    if isinstance(obj, str):
        if key not in _TEXT_KEYS:
            return obj
        for pattern, repl in _WORDS:
            obj = pattern.sub(repl, obj)
        return obj
    if isinstance(obj, list):
        return [player_words(x, key) for x in obj]
    if isinstance(obj, dict):
        return {k: v if k == "chat" else player_words(v, k) for k, v in obj.items()}
    return obj


def player_notes(notes):
    return [n for n in notes or [] if isinstance(n, dict) and n.get("show_players")]
