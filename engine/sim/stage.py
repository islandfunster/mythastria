"""STAGE-01 in the simulator (GM 2026-10-19: "let's not include Stage in FG. Let's only install it on the simulator and
hence will be ported to Java, Javascript and/or Rust or Ruby"). The reference implementation of the Stage tools' rules,
with no Fantasy Grounds, no I/O and no clock of its own: every call gets `now` (seconds). The state is plain JSON (dicts,
lists, strings, numbers), so it can be saved, sent to the Isles Table or compared with a port.

Ports are checked against sim/stage_cases.json: each case is a list of commands with the expected answers. A port in
another language passes when it gives the same answers to the same cases (test_stage.py runs them here).

Design: docs/development/STAGE01_Tooling_Brief_Claude.md; player sheet: STAGE01_Session_Zero_Rules.md.
Slice 1: Join/Leave Stage; the spotlight (ON AIR) with its timer; the Dialogue light (an improv invitation to join the scene in character, GM 2026-10-20;
formerly "Discussion welcome"; internally still `discuss` / `discussion`; only the holder toggles it; the
timer keeps running); applause and public accolades; the Director's time report. Not yet: footlights, next-scene
invitations, private notes, the vote (they wait for the GM's settings). Stage never touches characters.

A command: {"id", "user", "op", ...}. `director` is decided by whoever runs the session (the host, the Isles Table's
GM seat), never by the command itself. apply() returns (ok, public text or None, private text or None).
"""
import copy

CASES_FORMAT = "stage-cases/1"


def new():
    return {"participants": {}, "spotlight": {"holder": None, "discussion": False, "revision": 0, "running": False,
                                               "started": None, "elapsed": 0},
            "segments": [], "accolades": [], "seen": [], "session": 1}


def fmt(seconds):
    seconds = max(0, int(seconds + 0.5))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def _name(st, user):
    p = st["participants"].get(user)
    return (p or {}).get("name") or user


def elapsed(st, now):
    s = st["spotlight"]
    return s["elapsed"] + ((now - s["started"]) if s["running"] and s["started"] is not None else 0)


def on_air(st, now):
    s = st["spotlight"]
    if not s["holder"]:
        return "Stage: no one holds the spotlight."
    who = _name(st, s["holder"])
    cue = ("Dialogue · %s's spotlight · join in character" % who) if s["discussion"] else ("ON AIR · %s · Spotlight - please listen" % who)
    return "%s · %s%s" % (cue, fmt(elapsed(st, now)), "" if s["running"] else " (paused)")


def _close(st, now):
    s = st["spotlight"]
    if s["holder"] and s["running"] and s["started"] is not None:
        st["segments"].append({"holder": s["holder"], "from": s["started"], "to": now, "seconds": now - s["started"]})
        s["elapsed"] += now - s["started"]
    s["running"], s["started"] = False, None


def apply(st, cmd, now, director=False):
    if not isinstance(cmd, dict) or not cmd.get("id") or not cmd.get("user") or not cmd.get("op"):
        return False, None, "Malformed Stage command."
    if cmd["id"] in st["seen"]:
        return True, None, None                                   # a retry: already applied, nothing again
    s, op = st["spotlight"], cmd["op"]

    def done(pub=None, priv=None):
        st["seen"].append(cmd["id"])
        return True, pub, priv

    def refuse(text):
        return False, None, text

    if op in ("join", "leave"):
        p = st["participants"].get(cmd["user"]) or {"name": cmd.get("name") or cmd["user"], "stage": None}
        p["name"] = cmd.get("name") or p["name"]
        want = op == "join"
        if p.get("stage") == want:
            return done(None, "Stage: you are already %s." % ("in" if want else "out"))
        p["stage"], p["changed_at"] = want, now
        st["participants"][cmd["user"]] = p
        return done("Stage: %s %s" % (p["name"], "joins the Stage." if want else "leaves the Stage (a regular player, as valid)."))

    if op == "discuss":
        if cmd["user"] != s["holder"]:
            return refuse("Stage: only the player holding the spotlight lights or ends Dialogue.")
        if cmd.get("revision") != s["revision"]:
            return refuse("Stage: the spotlight has changed since; nothing done.")
        want = cmd.get("on") is True
        if s["discussion"] == want:
            return done()
        s["discussion"] = want                                    # the timer is not touched
        s["revision"] += 1
        return done(on_air(st, now))

    if op == "applaud":
        to = cmd.get("to") or ""
        if not to:
            return refuse("Stage: applaud whom?")
        if to == cmd["user"]:
            return refuse("Stage: applause goes to someone else.")
        reason = (cmd.get("reason") or "").strip()[:300]
        kind = "accolade" if reason else "cheer"
        st["accolades"].append({"from": cmd["user"], "to": to, "reason": reason, "at": now, "kind": kind,
                                "session": st["session"]})
        text = "Applause: %s applauds %s" % (_name(st, cmd["user"]), _name(st, to))
        return done(text + (": " + reason if reason else "."))

    if not director:
        return refuse("Stage: only the Director (the GM) does that.")
    if op == "spotlight":
        if not cmd.get("to"):
            return refuse("Stage: spotlight whom?")
        _close(st, now)
        s.update(holder=cmd["to"], discussion=False, elapsed=0, running=True, started=now)
        s["revision"] += 1
        return done(on_air(st, now))
    if op == "pause":
        if not s["holder"] or not s["running"]:
            return refuse("Stage: the timer is not running.")
        _close(st, now); s["revision"] += 1
        return done(on_air(st, now))
    if op == "resume":
        if not s["holder"] or s["running"]:
            return refuse("Stage: nothing to resume.")
        s["running"], s["started"] = True, now; s["revision"] += 1
        return done(on_air(st, now))
    if op == "stop":
        if not s["holder"]:
            return refuse("Stage: no one holds the spotlight.")
        _close(st, now)
        was = _name(st, s["holder"])
        s.update(holder=None, discussion=False, elapsed=0); s["revision"] += 1
        return done("Stage: %s's spotlight ends. Thank you!" % was)
    if op == "newsession":
        _close(st, now)
        s.update(holder=None, discussion=False, elapsed=0); s["revision"] += 1
        st["session"] += 1
        st["segments"] = []
        return done("Stage: a new session begins. Everyone keeps their Stage choice.")
    return refuse("Stage: unknown command.")


def time_report(st, now):
    """The Director's view of spotlight time this session: a cue for sharing the floor, never a verdict."""
    total = {}
    for seg in st["segments"]:
        total[seg["holder"]] = total.get(seg["holder"], 0) + seg["seconds"]
    s = st["spotlight"]
    if s["holder"] and s["running"] and s["started"] is not None:
        total[s["holder"]] = total.get(s["holder"], 0) + now - s["started"]
    lines = sorted((_name(st, u), t) for u, t in total.items())
    out = ["Stage spotlight time this session (a cue, not a score):"]
    out += ["  %s %s" % (n, fmt(t)) for n, t in lines] or ["  nobody has held the spotlight yet"]
    return "\n".join(out)


def status(st, now):
    ins = sorted(p["name"] for p in st["participants"].values() if p.get("stage"))
    outs = sorted(p["name"] for p in st["participants"].values() if not p.get("stage"))
    return "Stage: in: %s; out: %s. %s" % (", ".join(ins) or "nobody", ", ".join(outs) or "nobody", on_air(st, now))


def run_case(case):
    """Play one case from stage_cases.json; returns a list of mismatches (empty: the implementation agrees)."""
    st, problems = new(), []
    for i, step in enumerate(case["steps"]):
        if "cmd" in step:
            got = list(apply(st, copy.deepcopy(step["cmd"]), step["now"], step.get("director", False)))
            want = step["expect"]
            for k, idx in (("ok", 0), ("public", 1), ("private", 2)):
                if k in want and want[k] != got[idx]:
                    problems.append("%s step %d %s: want %r, got %r" % (case["name"], i + 1, k, want[k], got[idx]))
        elif "query" in step:
            q = step["query"]
            got = {"on_air": on_air, "elapsed": elapsed, "time_report": time_report, "status": status}[q](st, step["now"])
            if got != step["expect"]:
                problems.append("%s step %d %s: want %r, got %r" % (case["name"], i + 1, q, step["expect"], got))
    return problems
