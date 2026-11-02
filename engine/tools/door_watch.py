"""CHEAT-LOG-01 (GM 2026-11-02: "A tool for the logs should find cheaters"; "let's do the cheater log tool"): what the players'
door refused, by seat, for the GM's Players dialog. The engine rolls the dice and checks every choice, so a tampered screen
can't cheat quietly: all it can do is ask for what it may not have, and those refusals are kept here.

Three sorts of refusal. Timing (a stale click, a frozen fight, the creatures acting) happens to honest players all the time
and isn't kept. Against the rules (out of reach, no slot left) can be an honest mistake, so it counts only when it piles up.
Not allowed (another's character, a GM route, a GM's answer) is something the table's own screen never sends.

A refusal is a reason to look, never proof: the GM decides. In memory only, like the door log: a restart forgets it, and the
table's notice says so. Names only, never an address.
"""
import re, threading, time
from collections import deque

KEEP, SHOWN = 500, 12                                             # lines kept in all, lines shown per player
RULE_LOOK, RULE_WINDOW = 8, 600                                   # against the rules: 8 in 10 minutes is worth a look
NOT_ALLOWED, AGAINST_RULES = "not allowed", "against the rules"
QUIET = {"/api/join", "/api/live/state", "/api/live/aim", "/api/chat/log", "/api/stage/state", "/api/notes", "/api/flavor", "/api/map_paint"}
TIMING = re.compile(r"stale|creatures are acting|frozen|fight is over|no fight|no live fight|initiative is being rolled|"
                    r"gm is playing|no longer open|already answered|taking the fight back|been taken back|simulator did not answer", re.I)
FORBIDDEN = re.compile(r"only the gm|each player rolls|the gm calls|plays .*wait for that turn|not yours|someone else", re.I)


def sort_of(route, code, out):
    """The sort of refusal this answer is, or None when there's nothing to keep."""
    if (code == 200 and out.get("ok") is not False) or route in QUIET or code == 429 or out.get("panic") or out.get("no_seat") or out.get("notice"):
        return None
    why = str(out.get("refused") or out.get("error") or "")
    if TIMING.search(why):
        return None
    if FORBIDDEN.search(why) or code == 403 or (code == 400 and route.startswith("/api/live/")):
        return NOT_ALLOWED
    return AGAINST_RULES


def what_of(route, req):
    words = [route.rsplit("/", 1)[-1], req.get("op"), req.get("spell")]
    return " ".join(str(w)[:40] for w in dict.fromkeys(words) if w)


class Watch:
    def __init__(self, clock=time.time):
        self.lock = threading.Lock()
        self.clock = clock
        self.lines = deque(maxlen=KEEP)

    def note(self, who, route, req, code, out):
        sort = sort_of(route, code, out)
        if sort and who:
            self.add(who, sort, what_of(route, req), str(out.get("refused") or out.get("error") or "")[:160])

    def add(self, who, sort, what, why):
        with self.lock:
            self.lines.append({"t": int(self.clock()), "who": who, "sort": sort, "what": what, "why": why})

    def clear(self):
        with self.lock:
            self.lines.clear()

    def view(self):
        """Per player, the most to look at first."""
        with self.lock:
            lines, now = list(self.lines), self.clock()
        out = {}
        for e in reversed(lines):
            w = out.setdefault(e["who"], {"who": e["who"], "not_allowed": 0, "against_rules": 0, "lately": 0, "lines": []})
            w["not_allowed" if e["sort"] == NOT_ALLOWED else "against_rules"] += 1
            w["lately"] += e["sort"] == AGAINST_RULES and now - e["t"] <= RULE_WINDOW
            if len(w["lines"]) < SHOWN:
                w["lines"].append(e)
        for w in out.values():
            w["look"] = bool(w["not_allowed"]) or w.pop("lately") >= RULE_LOOK
        return sorted(out.values(), key=lambda w: (not w["look"], -w["not_allowed"], -w["against_rules"], w["who"]))
