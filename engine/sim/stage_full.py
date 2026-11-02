"""STAGE-01 slice 2: the rest of the Stage (GM 2026-10-20: "go ahead and write code for stage to finish it. We'll save it
to be added later. It should be tested by ai first ... It doesn't need to be attached to the game.").

Stage is controls only (GM 2026-10-20: "really only need the buttons ... The acting will be done through third party
audio-visual systems"): this module holds what the buttons do; no speech, text generation or microphone control.

Simple and without judging (GM 2026-10-20: "Let's leave out discussion. It can lead to hard feelings. The simple vote
is enough. Like a nomination!" and "notes is just a silent demerit that affects future spotlight voting opportunities
for everyone. Several notes means it's not a good time for getting carried away and nobody judges. But also the
spotlight stays off until the GM (Director, Show Runner) turns it back on. No questions asked."). This replaces the
earlier design of reviewed notes and a binding vote about a player.

Built on sim/stage.py (slice 1: Join/Leave, ON AIR, Discussion welcome, applause, the Director's timer), which stays as
it is; the table's service still uses only slice 1. This module adds:
- the agreed spotlight timer: each player on the Stage suggests a length, the Director settles the median (rounded to
  30 s); cue() is a gentle "time cue", never a cutoff;
- Stage moments (footlights): marked by the spotlight holder or the Director, once per spotlight segment (pause and
  resume do not add one), at most three lit per session, reset each session, history kept; applause fills no light;
- next-scene invitations: cues for Stage-in players with no moment this session; the invitee accepts or passes;
- nominations for the next spotlight: the Director opens a round, everyone at the table except the Director nominates
  one player on the Stage (not themselves), secretly and once; the most nominated is named, without anyone's count; a
  tie or no nomination leaves the choice to the Director, who still gives the spotlight;
- silent notes: a note names nobody and says nothing aloud; nobody sees who sent one, not even the Director; when
  several different people have sent one (3, or 2 at a table of three) the spotlight rests: no spotlight, invitation
  or nomination until the Director turns it back on, which starts the count afresh with no questions asked;
- rewards recorded for the GM (recognition, a title, Heroic Inspiration offered); Stage itself changes no character.
A GM who also plays uses a separate player seat (GM 2026-10-20: "If DMs chooses to participate as a player, then they
should stay cognizant of their separate roles"): the Director seat never nominates or sends a note; the player seat
has no Director buttons.

TEST SETTINGS (POLICY): the numbers above are the AI rehearsal's settings, for the GM to approve or change.

Same conventions as slice 1: plain JSON state, every call gets `now`, commands {"id", "user", "op", ...}, a retried id
does nothing twice, `director` is decided by the host and never by the command. apply() returns (ok, public text or
None, private text for the commander or None). view() shows a seat what it may see.
"""
import copy

import stage

POLICY = {
    "version": "stage-test-settings/2 (AI rehearsal; for the GM to approve or change)",
    "spotlight_seconds": None,          # settled by agree_timer
    "timer_round": 30,
    "timer_range": [30, 900],
    "footlights": 3,
    "rest_after": 3,                    # different people's notes that rest the spotlight (2 at a table of three)
    "rewards": {"recognition": "recognition", "title": "a title", "heroic_inspiration": "Heroic Inspiration"},
}
SLICE_ONE = ("join", "leave", "discuss", "applaud", "spotlight", "pause", "resume", "stop", "newsession")


def new():
    st = stage.new()
    st.update(policy=copy.deepcopy(POLICY), proposals={}, spot_n=0, moments=[], invitations=[], rounds=[],
              notes={"count": 0, "from": []}, resting=False, rewards=[], counter=0)
    return st


def _name(st, user):
    return stage._name(st, user)


def _names(st, users):
    names = [_name(st, u) for u in users]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _on_stage(st, user):
    return bool((st["participants"].get(user) or {}).get("stage"))


def _open_round(st):
    return next((r for r in st["rounds"] if r["state"] == "open"), None)


def rest_after(st):
    return max(2, min(st["policy"]["rest_after"], len(st["participants"]) - 1))


def footlights(st, user):
    lit = sum(1 for m in st["moments"] if m["who"] == user and m["session"] == st["session"])
    return min(lit, st["policy"]["footlights"])


def invite_cues(st):
    """Stage-in players with no moment this session: the Director may offer them the next scene (never automatic)."""
    if st["resting"]:
        return []
    had = {m["who"] for m in st["moments"] if m["session"] == st["session"]}
    return sorted(u for u in st["participants"] if _on_stage(st, u) and u not in had)


def cue(st, now):
    """A gentle time cue once the agreed length is reached; it changes nothing."""
    s, limit = st["spotlight"], st["policy"].get("spotlight_seconds")
    if not limit or not s["holder"] or stage.elapsed(st, now) < limit:
        return None
    return ("Time cue: %s's spotlight has reached the agreed %s. The Director decides what comes next."
            % (_name(st, s["holder"]), stage.fmt(limit)))


def _rest(st, now):
    s = st["spotlight"]
    stage._close(st, now)
    s.update(holder=None, discussion=False, elapsed=0)
    s["revision"] += 1
    st["resting"] = True
    r = _open_round(st)
    if r:
        r["state"] = "set aside"


def apply(st, cmd, now, director=False):
    if not isinstance(cmd, dict) or not cmd.get("id") or not cmd.get("user") or not cmd.get("op"):
        return False, None, "Malformed Stage command."
    if cmd["id"] in st["seen"]:
        return True, None, None
    op, user, pol = cmd["op"], cmd["user"], st["policy"]

    def done(pub=None, priv=None):
        st["seen"].append(cmd["id"])
        return True, pub, priv

    def refuse(text):
        return False, None, text

    resting = "Stage: the spotlight rests for now; the Director turns it back on."

    # --- slice 1, which the resting spotlight pauses ----------------------------------------------------------------
    if op in SLICE_ONE:
        if st["resting"] and op in ("spotlight", "resume"):
            return refuse(resting)
        ok, pub, priv = stage.apply(st, cmd, now, director)
        if ok and op == "spotlight":
            st["spot_n"] += 1
        if ok and op == "newsession":
            st["proposals"] = {}
            if not st["resting"]:
                st["notes"] = {"count": 0, "from": []}
        return ok, pub, priv

    # --- the agreed timer --------------------------------------------------------------------------------------------
    if op == "propose_timer":
        if not _on_stage(st, user):
            return refuse("Stage: the spotlight length is for the players on the Stage to suggest.")
        secs = cmd.get("seconds")
        lo, hi = pol["timer_range"]
        if not isinstance(secs, int) or isinstance(secs, bool) or not lo <= secs <= hi:
            return refuse("Stage: suggest a spotlight length between %s and %s." % (stage.fmt(lo), stage.fmt(hi)))
        st["proposals"][user] = secs
        return done("Stage: %s suggests a spotlight of %s." % (_name(st, user), stage.fmt(secs)))
    if op == "agree_timer":
        if not director:
            return refuse("Stage: only the Director settles the timer.")
        vals = sorted(st["proposals"].values())
        if not vals:
            return refuse("Stage: nobody has suggested a length yet.")
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        step = pol["timer_round"]
        pol["spotlight_seconds"] = int(round(median / step) * step)
        return done("Stage: the table agrees a spotlight of %s (the median of %d suggestions; a gentle cue, never a "
                    "cutoff)." % (stage.fmt(pol["spotlight_seconds"]), len(vals)))

    # --- Stage moments and invitations -------------------------------------------------------------------------------
    if op == "moment":
        who = cmd.get("to") if director and cmd.get("to") else user
        if who != st["spotlight"]["holder"]:
            return refuse("Stage: a Stage moment belongs to the player holding the spotlight.")
        if not _on_stage(st, who):
            return refuse("Stage: %s is not on the Stage." % _name(st, who))
        if any(m["who"] == who and m["segment"] == st["spot_n"] and m["session"] == st["session"] for m in st["moments"]):
            return refuse("Stage: this spotlight already has its moment.")
        st["moments"].append({"who": who, "segment": st["spot_n"], "session": st["session"], "at": now})
        return done("Stage: a Stage moment for %s (footlights %d of %d)." % (_name(st, who), footlights(st, who),
                                                                            pol["footlights"]))
    if op == "invite":
        if not director:
            return refuse("Stage: only the Director offers a scene.")
        if st["resting"]:
            return refuse(resting)
        to = cmd.get("to")
        if not _on_stage(st, to):
            return refuse("Stage: invitations are for players on the Stage.")
        if any(i["to"] == to and i["state"] == "open" for i in st["invitations"]):
            return refuse("Stage: %s already has an open invitation." % _name(st, to))
        st["invitations"].append({"to": to, "session": st["session"], "state": "open", "at": now})
        return done("Stage: the Director offers %s the next scene." % _name(st, to))
    if op in ("accept", "pass"):
        inv = next((i for i in st["invitations"] if i["to"] == user and i["state"] == "open"), None)
        if not inv:
            return refuse("Stage: there is no invitation for you.")
        inv["state"] = "accepted" if op == "accept" else "passed"
        return done("Stage: %s %s" % (_name(st, user), "accepts the next scene." if op == "accept"
                                      else "passes this time, and that is fine."))

    # --- nominations for the next spotlight --------------------------------------------------------------------------
    if op == "open_nominations":
        if not director:
            return refuse("Stage: only the Director opens nominations.")
        if st["resting"]:
            return refuse(resting)
        if _open_round(st):
            return refuse("Stage: nominations are already open.")
        st["counter"] += 1
        st["rounds"].append({"id": "r%d" % st["counter"], "session": st["session"], "state": "open", "votes": {},
                             "winner": None, "tied": [], "at": now})
        return done("Stage: nominations are open for the next spotlight. Nominate one player on the Stage (not "
                    "yourself); nominations are secret.")
    if op == "nominate":
        r = _open_round(st)
        if not r or r["id"] != cmd.get("round"):
            return refuse("Stage: no nominations are open.")
        if director or user not in st["participants"]:
            return refuse("Stage: the players nominate; the Director runs the round.")
        to = cmd.get("to")
        if to == user:
            return refuse("Stage: nominate someone else.")
        if not _on_stage(st, to):
            return refuse("Stage: nominate a player who is on the Stage.")
        if user in r["votes"]:
            return refuse("Stage: your nomination is already in.")
        r["votes"][user] = to
        return done("Stage: %d nomination%s in." % (len(r["votes"]), " is" if len(r["votes"]) == 1 else "s are"),
                    "Stage: you nominated %s (secret)." % _name(st, to))
    if op == "close_nominations":
        if not director:
            return refuse("Stage: only the Director closes nominations.")
        r = _open_round(st)
        if not r or r["id"] != cmd.get("round"):
            return refuse("Stage: no nominations are open.")
        count = {}
        for to in r["votes"].values():
            count[to] = count.get(to, 0) + 1
        r["state"] = "closed"
        if not count:
            return done("Stage: no nominations this time; the Director chooses.")
        top = max(count.values())
        best = sorted(u for u, n in count.items() if n == top)
        if len(best) == 1:
            r["winner"] = best[0]
            return done("Stage: the table nominates %s for the next spotlight." % _name(st, best[0]))
        r["tied"] = best
        return done("Stage: %s are nominated equally; the Director chooses between them." % _names(st, best))

    # --- silent notes ------------------------------------------------------------------------------------------------
    if op == "note":
        if user not in st["participants"] or director:
            return refuse("Stage: notes are for the players.")
        if any(k in cmd for k in ("about", "to", "text", "account")):
            return refuse("Stage: a note names nobody and says nothing; just send it.")
        n = st["notes"]
        if not st["resting"] and user not in n["from"]:
            n["from"].append(user)
            n["count"] = len(n["from"])
            if n["count"] >= rest_after(st):
                _rest(st, now)
                return done("Stage: the spotlight rests for now. The Director will turn it back on.",
                            "Stage: noted, silently.")
        return done(None, "Stage: noted, silently.")
    if op == "lights_on":
        if not director:
            return refuse("Stage: only the Director turns the spotlight back on.")
        if not st["resting"]:
            return refuse("Stage: the spotlight is not resting.")
        st["resting"] = False
        st["notes"] = {"count": 0, "from": []}
        return done("Stage: the spotlight is back on.")

    # --- rewards (for the GM; never applied here) --------------------------------------------------------------------
    if op == "reward":
        if not director:
            return refuse("Stage: rewards are the GM's.")
        kind, to = cmd.get("kind"), cmd.get("to")
        why = (cmd.get("text") or "").strip()[:200] if isinstance(cmd.get("text"), str) else ""
        if kind not in pol["rewards"] or to not in st["participants"] or not why:
            return refuse("Stage: a reward is recognition, a title or Heroic Inspiration, for someone, with a reason.")
        st["rewards"].append({"to": to, "kind": kind, "text": why, "session": st["session"], "at": now,
                              "applied": False})
        if kind == "title":
            return done("Stage: %s earns the title \"%s\"." % (_name(st, to), why))
        if kind == "recognition":
            return done("Stage: recognition for %s: %s" % (_name(st, to), why))
        return done("Stage: the Director offers %s Heroic Inspiration for %s. The GM grants it through the character "
                    "rules (SRD 5.2.1: one at a time; a spare can go to a character who lacks it); Stage itself "
                    "changes no character." % (_name(st, to), why))
    return refuse("Stage: unknown command.")


def view(st, user, director=False, now=0):
    """What one seat may see: never who sent a silent note (nobody sees that) or anyone else's nomination."""
    r = st["rounds"][-1] if st["rounds"] else None
    v = {"session": st["session"], "on_air": stage.on_air(st, now), "cue": cue(st, now), "resting": st["resting"],
         "spotlight_seconds": st["policy"]["spotlight_seconds"],
         "participants": [{"user": u, "name": p["name"], "stage": bool(p.get("stage")), "footlights": footlights(st, u)}
                          for u, p in sorted(st["participants"].items())],
         "accolades": [dict(a) for a in st["accolades"] if a["session"] == st["session"]],
         "invitations": [dict(i) for i in st["invitations"] if i["to"] == user and i["state"] == "open"],
         "round": ({"id": r["id"], "state": r["state"], "count": len(r["votes"]), "mine": r["votes"].get(user),
                    "winner": r["winner"], "tied": list(r["tied"])} if r else None)}
    if director:
        v["invite_cues"] = invite_cues(st)
        v["rewards"] = [dict(x) for x in st["rewards"]]
    return v
