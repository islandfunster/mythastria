"""RULES-MONITOR-01 (GM 2026-10-28: "Watch every action"; design: the "Mythastria: LLM-Assisted Rules Engine
Architecture" doc): a local model (LM Studio) reads every action of a live fight beside play and says whether the engine
followed the SRD 5.2.1 rules, with what should have happened when it thinks not. GM decisions the same day: one model,
LM Studio; it runs during live play; "If lm studio doesn't find a resolution, I'll ask claude to fix it" (the GM's panel
copies an action for Claude).

What it never does: change a result, hold up a turn, or speak to the players. It is a second pair of eyes beside the
Referee (sim/referee.py), which stays parser only (GM 2026-10-22: "No, parser only"). Each action waits in a short
queue; when the model falls behind (about 5 s a check with Gemma 4 12B, thinking off), the oldest waiting action is
skipped and counted. Results are kept in memory for this run of Mythastria (the last 100), newest last.

An action: a player's choice in Play live (move, attack, cast, a class action...), or a creature's whole turn. What the
model reads: the actor, the fight log lines the action wrote, and the SRD text it involves (the spell cast, the
creature's stat-block actions).
"""
import collections, json, re, threading, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
WAITING = 3                         # actions waiting at most; an older one is skipped
KEEP = 100                          # results kept
MAX_LINES, MAX_TEXT = 40, 3500      # what one check sends (Gemma 4 12B loads with 8,192 tokens of context)
VERDICTS = ("ok", "question", "break")


class MonitorError(ValueError):
    pass


GUIDE = """You watch a D&D fight run by a rules engine under the SRD 5.2.1 rules (the 2024 rules). You get one action:
who acted, the fight log lines it wrote, and the SRD text it involves. Say whether the engine followed the rules.
- verdict "ok": nothing in the log breaks the rules.
- verdict "break": the log shows a clear rule break (wrong range, too many targets, a save or damage the text doesn't
  give, an action it had no right to take, a condition that shouldn't be there...).
- verdict "question": something looks doubtful but the log doesn't show enough to be sure.
Dice results are random and fine; judge only what the log shows; never invent rules. Use the SRD text given.
The SRD text sent covers only the spell cast and a creature's stat block. Class features, feats, species traits and
the Weapon Mastery properties (Cleave, Graze, Nick, Push, Sap, Slow, Topple, Vex; the log writes them as "feat:" lines)
are SRD rules too: never call one non-SRD because its text is missing; say "question" if you doubt how it was used.
Every creature may take the actions every creature has (Attack, Dash, Disengage, Dodge, Help, Hide, Influence, Magic,
Ready, Search, Study, Utilize) and move up to its Speed, besides its stat block's own actions. A creature that only
moves made no attack.
A stat block's "Hit: 5 (1d6 + 2) Slashing damage" gives the average (5) and the dice: the engine rolls the dice, so any
total they can make (3 to 8 here) is right; a Critical Hit rolls the dice twice."""
GUIDE += """
Return JSON only: {"verdict": "ok"|"question"|"break", "comment": "one or two sentences", "resolution": "what the SRD
says should have happened instead (empty when ok)", "quote": "the exact SRD words you rely on (empty when none)"}."""

SCHEMA = {"type": "object", "required": ["verdict", "comment", "resolution", "quote"],
          "properties": {"verdict": {"type": "string", "enum": list(VERDICTS)}, "comment": {"type": "string"},
                         "resolution": {"type": "string"}, "quote": {"type": "string"}}}


def _plain(s):
    s = str(s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(s.split())


def messages(rec):
    texts = "\n\n".join("%s:\n%s" % (t["name"], t["text"]) for t in rec["srd"])[:MAX_TEXT]
    lines = "\n".join(rec["lines"][-MAX_LINES:])
    return [{"role": "system", "content": GUIDE},
            {"role": "user", "content": "Actor: %s\nAction: %s\n\nFight log:\n%s\n\nSRD text:\n%s"
             % (rec["actor"], rec["action"], lines, texts or "(none: judge from the general rules)")}]


def check_local(url):
    host = (urlparse(url or "").hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise MonitorError("Refused: %s is not on this PC. Only a local model server watches the rules." % url)
    return url.rstrip("/")


def ask_model(msgs, llm_url, model, timeout=60):
    """One request to LM Studio, thinking off (thinking on ran out of 4,096 tokens before answering, 2026-10-28).
    Returns (the object it sent, facts about the call)."""
    base = check_local(llm_url)
    payload = {"model": model, "messages": msgs, "temperature": 0, "max_tokens": 600, "stream": False,
               "reasoning_effort": "none",
               "response_format": {"type": "json_schema", "json_schema": {"name": "ruling", "schema": SCHEMA, "strict": False}}}
    req = Request(base + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
                  headers={"Content-Type": "application/json"})
    started = time.time()
    try:
        with urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode())
    except HTTPError as e:
        raise MonitorError("LM Studio answered HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200]))
    except (URLError, TimeoutError, OSError) as e:
        raise MonitorError("No local model answers at %s (start LM Studio's server with %s loaded)." % (base, model))
    except ValueError:
        raise MonitorError("LM Studio sent something that is not JSON.")
    choice = (resp.get("choices") or [{}])[0]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", ((choice.get("message") or {}).get("content") or "").strip())
    try:
        out = json.loads(text)
    except ValueError:
        out = None
    if not isinstance(out, dict):
        raise MonitorError("The model's reply was not a JSON ruling.")
    return out, {"model": resp.get("model") or model, "seconds": round(time.time() - started, 1)}


def ruling(raw, rec):
    """The model's reply, checked: a known verdict, short texts, and whether its quote is in the SRD text it was sent."""
    if not isinstance(raw, dict) or raw.get("verdict") not in VERDICTS:
        raise MonitorError("The model gave no verdict.")
    out = {k: str(raw.get(k) or "").strip()[:600] for k in ("comment", "resolution", "quote")}
    out["verdict"] = raw["verdict"]
    if out["quote"]:
        q = _plain(out["quote"]).strip(' ."')
        out["quote_found"] = bool(q) and any(q in _plain("%s: %s" % (t["name"].split(": ")[-1].replace(" (spell)", ""), t["text"]))
                                             for t in rec["srd"])
    # A rule break stands only on SRD words found in the text it was sent (2026-10-28: Gemma's false alarms on Savage
    # Attacker, Potent Cantrip and a Search quoted nothing; a Fireball with no saves did): else it is only doubtful.
    if out["verdict"] == "break" and not out.get("quote_found"):
        out["verdict"], out["unbacked"] = "question", True
    return out


class Monitor:
    """The GM's switch, the queue and the worker thread. ask: messages -> (object, facts); tests give a stand-in."""

    def __init__(self, ask):
        self.ask = ask
        self.on = False
        self.cv = threading.Condition()
        self.waiting = collections.deque()
        self.results, self.rev, self.n, self.skipped = [], 0, 0, 0
        self.status, self.error = "off", None
        self.worker = None

    def switch(self, on):
        with self.cv:
            self.on = bool(on)
            self.status = "watching" if self.on else "off"
            if not self.on:
                self.waiting.clear()
            self.rev += 1
            if self.on and (self.worker is None or not self.worker.is_alive()):
                self.worker = threading.Thread(target=self._work, daemon=True)
                self.worker.start()
            self.cv.notify_all()

    def clear(self):
        with self.cv:
            self.results, self.skipped, self.error = [], 0, None
            self.rev += 1

    def submit(self, rec):
        """An action, from the fight's thread: queued at once, never waited on."""
        if not self.on:
            return
        with self.cv:
            self.n += 1
            rec = dict(rec, n=self.n, when=time.strftime("%H:%M:%S"))
            if len(self.waiting) >= WAITING:
                self.waiting.popleft()
                self.skipped += 1
            self.waiting.append(rec)
            self.rev += 1
            self.cv.notify_all()

    def _work(self):
        while True:
            with self.cv:
                while self.on and not self.waiting:
                    self.cv.wait()
                if not self.on:
                    return
                rec = self.waiting.popleft()
                self.status = "checking %s" % rec["action"]
                self.rev += 1
            try:
                raw, facts = self.ask(messages(rec))
                out, error = dict(rec, **ruling(raw, rec), model=facts), None
            except MonitorError as e:
                out, error = None, str(e)
            except Exception as e:                       # noqa: BLE001 (the monitor never stops a fight)
                out, error = None, "%s: %s" % (type(e).__name__, e)
            with self.cv:
                if out:
                    self.results = (self.results + [out])[-KEEP:]
                self.error = error
                self.status = "watching" if self.on else "off"
                self.rev += 1

    def view(self):
        with self.cv:
            flags = [r for r in self.results if r["verdict"] != "ok"]
            return {"on": self.on, "status": self.status, "error": self.error, "rev": self.rev,
                    "waiting": len(self.waiting), "skipped": self.skipped, "checked": len(self.results),
                    "flags": len(flags), "results": list(reversed(self.results))[:50]}


# ------------------------------------------------------------------ what an action involves (the live fight calls these)
def srd_texts(fight, actor, cmd=None):
    """The SRD text an action involves: the spell cast (the rules the engine reads, the GM's wording when it has one),
    and for a creature its stat-block actions."""
    import spell_rules
    out = []
    spell = (cmd or {}).get("spell")
    if spell:
        s = spell_rules.spell(spell)
        if s:
            out.append({"name": "%s (spell)" % spell, "text": s["text"]})
    c = fight.sim.by_id(actor) or {}
    if not c.get("pc"):
        for a in c.get("actions") or []:
            if a.get("desc"):
                out.append({"name": "%s: %s" % (c.get("name", "?"), a.get("name", "?")), "text": a["desc"]})
    return out


def record(fight, actor, action, start, cmd=None):
    """An action's record from the fight's log since `start` (None when it wrote nothing)."""
    with fight.lock:
        # what happened, not the engine's plan (its "bridge" lines name an attack even for a turn spent moving), the
        # players' retelling of it, or the Referee's own notes
        lines = ["%s: %s" % (e["kind"], e["text"]) for e in fight.log
                 if e["n"] > start and e["kind"] not in ("referee", "bridge", "players")]
    if not lines:
        return None
    c = fight.sim.by_id(actor) or {}
    return {"actor": c.get("name", "?"), "action": action, "lines": lines, "srd": srd_texts(fight, actor, cmd)}
