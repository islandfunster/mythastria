"""GM 2026-10-24 (docs/development/ADVENTURE_PILLARS_PLAN.md, steps 1 and 2): "not all creatures are automatically
hostiles, especially not intelligent or social creatures"; "The scene should have the hostility selected in the
creatures and change it depending on the actions of the party"; "Morale should also be part of the prep along-side
hostility". Attitude and morale for each creature in a live fight, by rules the engine applies and the GM overrides.

Attitude (SRD 5.2.1 Rules Glossary: Attitude, Friendly, Indifferent, Hostile, Influence): a monster has a starting
attitude toward the player characters; "Indifferent is the default attitude of a monster".
- Where a creature's starting attitude comes from, most specific first: the GM's prep for its group (Remix Prep) > the
  attitude written on the creature in the map (an adventure's narrative) > the GM's prep for this encounter > the
  adventure pack's default for this encounter > the GM's default for the level > the pack's default for the level > the
  map's side as written (a map written as a fight: its foes Hostile, its non-player allies Friendly and with the party)
  > the creature's nature (mindless or a predator of instinct: Hostile; anything that thinks for itself: Indifferent)
  > Indifferent.
- Sides follow from attitudes: Hostile creatures fight (side "foe"); Indifferent and Friendly ones stay out of the
  fight (side "neutral": they take no turns and nobody's AI targets them) until provoked, or, Friendly, until the GM
  has them join the party (side "friend": the bridge plays them as an allied NPC).
- What the party does changes them, each change logged with its reason, and the GM can set any attitude at any time:
  an attack, a harmful spell, a Grapple or Shove, or damage on a creature makes it and its group Hostile (Calm
  Emotions, SRD: indifference "ends if the target takes damage or witnesses its allies taking damage"); a helpful spell
  on it moves it one step friendlier. Influence, a gift or a kept promise is the GM's ruling (Ask the GM, GM 2026-11-01).

Morale (prepped beside attitude; the SRD leaves it to the GM): a group fights to the end, or flees, surrenders or
bargains when it is below half (or a quarter) of its Hit Points, when its leader is out of the fight, or when it is
outnumbered two to one. The engine only suggests ("the bandits are below half and their captain is down: they may
surrender"); the GM accepts (they surrender, flee or parley: out of the fight) or has them fight on. A creature without
a rule fights on. A fight can end with no winner: a surrender, a flight, a truce or the party's retreat; the scene goes
on as social or exploration.

Every GM choice is checked here first (sim/requirements.py), with the reason when it can't be taken.
"""
import queue
import re

import requirements as rq
import social_pack

ATTITUDES = ("Hostile", "Indifferent", "Friendly")
SIDE = {"Hostile": "foe", "Indifferent": "neutral", "Friendly": "neutral"}
RULES = {"fight": "fights to the end", "flee": "flees", "surrender": "surrenders", "bargain": "bargains"}
WHEN = {"half": "below half its Hit Points", "quarter": "below a quarter of its Hit Points",
        "leader": "its leader is out of the fight", "outnumbered": "outnumbered two to one"}
STATUS = {"surrendered": "surrendered", "fled": "fled", "parley": "stopped to bargain"}
# GM 2026-10-25 (ruling P3): what a successful Influence urged, and the attitude that follows
URGES = {"stand_down": ("stand down", "Indifferent"), "help": ("help us", "Friendly"), "other": ("something else", None)}
# SRD 5.2.1 spells that only help their target: cast on a creature, one step friendlier (the plan's "aid")
HELPFUL = {"Aid", "Bless", "Cure Wounds", "Enhance Ability", "Freedom of Movement", "Greater Restoration", "Guidance",
           "Heal", "Healing Word", "Heroism", "Lesser Restoration", "Longstrider", "Mass Cure Wounds",
           "Mass Healing Word", "Prayer of Healing", "Protection from Energy", "Protection from Evil and Good",
           "Protection from Poison", "Remove Curse", "Resistance", "Sanctuary", "Shield of Faith", "Spare the Dying",
           "Warding Bond"}
PREDATOR = re.compile(r"\b(bite|claws?|talons?|tentacles?|sting|constrict|engulf|pseudopod|swallow|gore|tusks?)\b", re.I)


class AttitudeError(ValueError):
    pass


def kind(c):
    """A creature's kind: its SRD name, else its name without the number ("Bandit 2" -> Bandit)."""
    return c.get("srd_name") or re.sub(r"\s+\d+$", "", str(c.get("name") or "")).strip()


def nature(c):
    """(attitude, why) when nothing is written or prepped. GM 2026-10-25 (ruling P1, "DM does with prep"): no guess
    from the creature: the SRD 5.2.1 default, Indifferent ("Indifferent is the default attitude of a monster"); the GM
    preps attitudes in Remix Prep, or switches on the optional Social rules pack (sim/social_pack.py)."""
    return "Indifferent", "nothing prepped: the SRD's default attitude of a monster"


def nature_guess(c):
    """The engine's earlier rule of thumb (before ruling P1), kept for reference: mindless (an Ooze, or Undead or
    Construct of Intelligence 6 or lower) or a predator of instinct (Intelligence 4 or lower, with a bite, claws or the
    like): Hostile; anything else: Indifferent."""
    t = str(c.get("type") or "").lower()
    i = c.get("int", (c.get("abilities") or {}).get("int"))
    if i is None:
        return "Indifferent", "nothing written about it: the SRD's default attitude of a monster"
    i = int(i)
    if "ooze" in t or (("undead" in t or "construct" in t) and i <= 6):
        return "Hostile", "mindless (%s, Intelligence %d)" % (t.split(" (")[0].title() or "creature", i)
    if i <= 4 and any(PREDATOR.search(str(a.get("name") or "")) for a in c.get("actions") or []):
        return "Hostile", "a predator of instinct (Intelligence %d)" % i
    return "Indifferent", "it thinks for itself (Intelligence %d): the SRD's default attitude of a monster" % i


def check_attitude(value, what="An attitude"):
    return rq.need("an attitude", value in ATTITUDES, "%s is Friendly, Indifferent or Hostile." % what)


def check_morale(m, kinds=()):
    """The needs a prepped morale rule must meet: {"rule": fight|flee|surrender|bargain, "when": [half, quarter,
    leader, outnumbered], "leader": a creature kind in the encounter}."""
    if m is None:
        return [rq.need("a morale rule", True)]
    if not isinstance(m, dict):
        return [rq.need("a morale rule", False, "A morale rule is a rule and when it breaks.")]
    rule, when = m.get("rule", "fight"), m.get("when") or []
    needs = [rq.need("a morale rule", rule in RULES, "Morale is: fights to the end, flees, surrenders or bargains."),
             rq.need("when it breaks", isinstance(when, list) and all(w in WHEN for w in when),
                     "Morale breaks below half or a quarter of its Hit Points, when its leader is out, or outnumbered.")]
    if rule in RULES and rule != "fight":
        needs.append(rq.need("a moment it breaks", bool(when), "%s when? Choose at least one moment (below half its "
                                                              "Hit Points, its leader out, outnumbered)." % RULES[rule].capitalize()))
    if isinstance(when, list) and "leader" in when:
        leader = m.get("leader")
        needs.append(rq.need("its leader", isinstance(leader, str) and leader in kinds,
                             "Name its leader: one of the creatures in this encounter (%s)." % ", ".join(sorted(kinds))
                             if kinds else "Name its leader."))
    return needs


def check_prep(prep, kinds=()):
    """Every need a prep record meets (Remix Prep's save): ready, rows."""
    needs = []
    for lv, a in ((prep.get("levels") or {}).items()):
        needs.append(rq.need("a level", str(lv).isdigit() and 1 <= int(lv) <= 20, "Levels are 1 to 20."))
        needs.append(check_attitude(a, "Level %s's default" % lv))
    sc = prep.get("scenario") or {}
    if sc.get("attitude") is not None:
        needs.append(check_attitude(sc["attitude"], "The encounter's default"))
    for k, g in (sc.get("groups") or {}).items():
        needs.append(rq.need("a creature of this encounter", not kinds or k in kinds,
                             "%s is not in this encounter." % k))
        if g.get("attitude") is not None:
            needs.append(check_attitude(g["attitude"], "%s's attitude" % k))
        needs += check_morale(g.get("morale"), kinds)
        if (g.get("morale") or {}).get("leader") == k:
            needs.append(rq.need("another leader", False, "%s can't be its own leader." % k))
    return rq.check(needs)


def starting(c, prep=None, level=None, optional=None):
    """(attitude, where it comes from, joined): the most specific source first (the module docstring). GM 2026-10-25:
    with the optional Social rules pack on (optional {"social": true}), the pack's disposition for the creature (its
    faction, else its Intelligence and type: sim/social_pack.py) comes after everything written or prepped and before
    the map's side as written."""
    prep = prep or {}
    sc, pack = prep.get("scenario") or {}, prep.get("pack") or {}
    group = (sc.get("groups") or {}).get(c.get("group") or kind(c)) or {}
    lv = str(level) if level is not None else None
    for value, source in ((group.get("attitude"), "the GM's prep for this group"),
                          (c.get("attitude"), "written into the adventure for this creature"),
                          (sc.get("attitude"), "the GM's prep for this encounter"),
                          (pack.get("encounter"), "the adventure's default for this encounter"),
                          ((prep.get("levels") or {}).get(lv), "the GM's default for level %s" % lv),
                          ((pack.get("levels") or {}).get(lv), "the adventure's default for level %s" % lv)):
        if value in ATTITUDES:
            return value, source, value == "Friendly" and c.get("side") == "friend"
    if social_pack.on(optional or prep.get("optional")):
        d = social_pack.disposition(c)
        return d["attitude"], "the Social rules pack: " + d["why"], False
    if c.get("side") == "foe":
        return "Hostile", "the map as written: a fight", False
    if c.get("side") == "friend":
        return "Friendly", "the map as written: with the party", True
    a, why = nature(c)
    return a, "its nature: " + why, False


def apply(sc, prep=None, level=None):
    """Set each creature's starting attitude, group, morale and side in a scenario (before the simulator is built, so
    the Combat Tracker starts with the right sides). Returns the creatures' rows."""
    groups = ((prep or {}).get("scenario") or {}).get("groups") or {}
    optional = sc.get("optional_rules") or (prep or {}).get("optional")
    rows = []
    for c in sc.get("combatants") or []:
        if c.get("pc"):
            continue
        a, source, joined = starting(c, prep, level, optional)
        c["pack_item"] = social_pack.disposition(c)["item"]      # the asterisk's link on the GM's screen
        c["group"] = c.get("group") or kind(c)
        m = (groups.get(c["group"]) or {}).get("morale") or c.get("morale")
        if m:
            c["morale"] = m
        c.update(attitude=a, attitude_from=source, joined=joined, side="friend" if joined else SIDE[a])
        rows.append({"id": c["id"], "name": c["name"], "attitude": a, "from": source})
    return rows


def morale_text(m):
    if not m or m.get("rule", "fight") == "fight":
        return "fights to the end"
    when = [WHEN[w].replace("its leader", "its leader (%s)" % m.get("leader")) if w == "leader" else WHEN[w]
            for w in m.get("when") or []]
    return "%s when %s" % (RULES[m["rule"]], " or ".join(when))


class Attitudes:
    """The attitudes and morale of one live fight. Every change runs on the simulator's thread: the service hands the
    GM's choices over with submit(), and the fight applies them in drain() (between turns, or while a character's turn
    waits)."""

    def __init__(self, fight):
        self.fight, sim = fight, fight.sim
        self.rows, self.log, self.cards = {}, [], []
        self.n = self.card_n = 0
        self.answered = {}                       # group -> the triggers the GM already answered
        self.ended = self.outcome = None
        self.gmq = queue.Queue()
        for c in sim.sc["combatants"]:
            if c.get("pc"):
                continue
            if "attitude" not in c or "attitude_from" not in c:
                apply({"combatants": [c], "optional_rules": sim.sc.get("optional_rules")})
            self.add(c)
        sim.attitudes = self

    def add(self, c):
        """A creature's row: at the start, or one that joins later (sim/live_add.py)."""
        self.rows[c["id"]] = {"attitude": c["attitude"], "from": c["attitude_from"], "group": c["group"],
                              "joined": bool(c.get("joined")), "status": None, "morale": c.get("morale"),
                              "hostile_once": c["attitude"] == "Hostile",
                              "pack": social_pack.disposition(c)}
        # the Combat Tracker's side too (a fight built before its attitudes were set; before the fight's thread runs)
        self.fight.sim.set_side(c["id"], c["side"])

    @property
    def sim(self):
        return self.fight.sim

    # ------------------------------------------------------------------ reading
    def attitude(self, cid):
        r = self.rows.get(cid)
        return r["attitude"] if r else None

    def in_fight(self, cid):
        """A creature that fights: Hostile (or joined with the party), not surrendered, fled or bargaining, not down."""
        r = self.rows.get(cid)
        return bool(r) and not r["status"] and not self.sim.down(cid) and (r["attitude"] == "Hostile" or r["joined"])

    def held(self, cid):
        """GM 2026-10-27 (the spell-effects merge): a creature kept out of the fight only by a lasting spell, which brings
        it back Hostile when it ends (or when damage ends it): Calm Emotions' indifference (SRD 5.2.1: "the creature's
        attitude returns to normal" when the spell ends), or a Suggestion to stop fighting (Indifferent) or to stop
        fighting and leave (fleeing, until it is off the map). Its fight is not over while it is held."""
        r = self.rows.get(cid)
        gm = getattr(self.sim, "gm_rules", None)
        if not r or gm is None or r["joined"] or r.get("gone") or self.sim.down(cid):
            return False
        cond = gm.cond.get(cid) or {}
        if "Calmed" in cond and r["attitude"] == "Indifferent" and not r["status"]:
            return True
        want = (cond.get("Charmed") or {}).get("suggestion")
        return (want == "Stop fighting and leave" and r["status"] == "fled"
                or want == "Stop fighting" and r["attitude"] == "Indifferent" and not r["status"])

    def held_any(self):
        return any(self.held(i) for i in self.rows)

    def sits_out(self, cid):
        """Why this creature takes no turn now, or None."""
        r = self.rows.get(cid)
        if not r or self.sim.down(cid):
            return None
        name = self.sim.by_id(cid)["name"]
        if r["status"]:
            return "%s has %s: it takes no part in the fight" % (name, STATUS[r["status"]])
        if r["attitude"] != "Hostile" and not r["joined"]:
            return "%s is %s: it keeps out of the fight unless provoked" % (name, r["attitude"])
        return None

    def party(self, cid):
        """The party's side: the player characters and the creatures that joined them."""
        c = self.sim.by_id(cid)
        return bool(c.get("pc")) or bool((self.rows.get(cid) or {}).get("joined"))

    def hp(self, cid):
        st = self.sim.S.state(cid)
        return max(0, int(st[1]) - int(st[0])), int(st[1])

    def view(self, gm=True):
        """What the table shows: each creature's attitude (and, for the GM, where it came from and its morale), the
        changes, the GM's morale suggestions and how the fight ended."""
        out = []
        for cid, r in self.rows.items():
            e = {"id": cid, "name": self.sim.by_id(cid)["name"], "attitude": r["attitude"], "status": r["status"],
                 "joined": r["joined"]}
            if gm:
                e.update({"from": r["from"], "group": r["group"], "morale": morale_text(r["morale"])})
                p = r.get("pack") or {}                  # GM 2026-10-25: the Social rules pack's item for the asterisk
                e["pack"] = {"attitude": p.get("attitude"), "why": p.get("why"), "item": p.get("item"),
                             "creature": social_pack.anchor(kind(self.sim.by_id(cid)))}
            out.append(e)
        v = {"creatures": out, "changes": list(self.log[-40:]), "outcome": self.outcome}
        if gm:
            v["cards"] = [dict(c) for c in self.cards]
        return v

    # ------------------------------------------------------------------ changing (the simulator's thread)
    def _say(self, text):
        self.sim.say("scene", text)

    def _side(self, cid):
        r, c = self.rows[cid], self.sim.by_id(cid)
        side = "friend" if r["joined"] and not r["status"] else "neutral" if r["status"] else SIDE[r["attitude"]]
        if c.get("side") != side:
            c["side"] = side
            self.sim.set_side(cid, side)

    def set(self, cid, to, why, by="rule"):
        r = self.rows[cid]
        before = r["attitude"]
        if before == to and not (to == "Hostile" and r["status"]):
            return False
        r["attitude"], r["from"] = to, ("the GM: " if by == "GM" else "") + why
        if to == "Hostile":
            r["hostile_once"], r["status"] = True, None              # a provoked surrender or parley is off
            r["joined"] = False
        elif to != "Friendly":
            r["joined"] = False
        self._side(cid)
        self.n += 1
        name = self.sim.by_id(cid)["name"]
        self.log.append({"n": self.n, "id": cid, "name": name, "from": before, "to": to, "why": why, "by": by})
        self._say("%s: %s -> %s (%s%s)" % (name, before, to, why, "; the GM" if by == "GM" else ""))
        return True

    def group_of(self, cid):
        g = self.rows[cid]["group"]
        return [i for i, r in self.rows.items() if r["group"] == g]

    def provoke(self, src, tid, why):
        """An attack, a harmful spell, a Grapple or Shove, or damage from the party: it and its group turn Hostile."""
        if tid not in self.rows or not self.party(src) or self.party(tid):
            return
        r = self.rows[tid]
        if r["attitude"] == "Hostile" and not r["status"]:
            return
        who, name = self.sim.by_id(src)["name"], self.sim.by_id(tid)["name"]
        self.set(tid, "Hostile", "%s by %s" % (why, who))
        for o in self.group_of(tid):
            if o != tid and not self.sim.down(o) and (self.rows[o]["attitude"] != "Hostile" or self.rows[o]["status"]):
                self.set(o, "Hostile", "its ally %s %s by %s" % (name, why, who))

    def hurt(self, src, tid):
        if src and src in {c["id"] for c in self.sim.sc["combatants"]}:
            self.provoke(src, tid, "hurt")

    def step(self, cid, n, why, by="rule"):
        """n steps friendlier (n < 0: less friendly), within Hostile..Friendly."""
        r = self.rows[cid]
        i = max(0, min(2, ATTITUDES.index(r["attitude"]) + n))
        return self.set(cid, ATTITUDES[i], why, by)

    def follow_urge(self, tid, wants, why, by="rule"):
        to = URGES[wants][1]
        if to and self.rows[tid]["attitude"] != to:
            self.set(tid, to, "%s (%s)" % (why, URGES[wants][0]), by)

    def after_choice(self, me, cmd):
        """A player's choice went through: what it does to the creatures' attitudes."""
        op = cmd.get("op")
        tids = [t for t in [cmd.get("target")] + list(cmd.get("targets") or []) if t in self.rows]
        if op in ("attack", "grapple", "shove") or (op == "use_item" and tids):
            for t in tids:
                self.provoke(me, t, {"attack": "attacked", "grapple": "grappled", "shove": "shoved"}.get(op, "attacked"))
        elif op == "cast":
            spell = cmd.get("spell")
            for t in tids:
                if spell in HELPFUL:
                    if not self.rows[t]["joined"]:
                        self.step(t, 1, "%s helped it (%s)" % (self.sim.by_id(me)["name"], spell))
                else:
                    self.provoke(me, t, "targeted with %s" % spell)
        self.check_morale()

    # ------------------------------------------------------------------ morale
    def check_morale(self):
        """Open a suggestion for each group whose prepped morale breaks now (once per new reason)."""
        if self.ended:
            return
        groups = {}
        for cid, r in self.rows.items():
            groups.setdefault(r["group"], []).append(cid)
        party = [c["id"] for c in self.sim.sc["combatants"] if self.party(c["id"]) and not self.sim.down(c["id"])]
        fighting = [i for i in self.rows if self.in_fight(i) and not self.rows[i]["joined"]]
        for g, members in groups.items():
            m = next((self.rows[i]["morale"] for i in members if self.rows[i]["morale"]), None)
            standing = [i for i in members if self.in_fight(i) and not self.rows[i]["joined"]]
            if not m or m.get("rule", "fight") == "fight" or not standing:
                continue
            hps = [self.hp(i) for i in members if self.rows[i]["hostile_once"]]
            left, full = sum(h[0] for h in hps), sum(h[1] for h in hps) or 1
            why = {}
            when = m.get("when") or []
            if "quarter" in when and left * 4 <= full:
                why["quarter"] = "below a quarter of %s Hit Points (%d of %d)" % ("its" if len(members) == 1 else "their", left, full)
            elif "half" in when and left * 2 <= full:
                why["half"] = "below half %s Hit Points (%d of %d)" % ("its" if len(members) == 1 else "their", left, full)
            if "leader" in when and m.get("leader"):
                lead = [i for i, r in self.rows.items() if kind(self.sim.by_id(i)) == m["leader"] or r["group"] == m["leader"]]
                if lead and not any(self.in_fight(i) for i in lead):
                    why["leader"] = "%s leader (%s) is out of the fight" % ("its" if len(members) == 1 else "their", m["leader"])
            if "outnumbered" in when and fighting and len(party) >= 2 * len(fighting):
                why["outnumbered"] = "outnumbered %d to %d" % (len(party), len(fighting))
            new = set(why) - self.answered.get(g, set())
            if not new:
                continue
            self.cards = [c for c in self.cards if c["group"] != g or c.get("kind") == "urge"]
            self.card_n += 1
            names = [self.sim.by_id(i)["name"] for i in standing]
            text = "%s: %s. Prepped morale: %s %s." % (
                g if len(members) > 1 else names[0], "; ".join(why.values()),
                "they" if len(standing) > 1 else "it", {"flee": "may flee", "surrender": "may surrender",
                                                        "bargain": "may offer to bargain"}[m["rule"]])
            self.cards.append({"n": self.card_n, "group": g, "rule": m["rule"], "why": sorted(why), "members": standing,
                               "names": names, "text": text})
            self._say(GM_ONLY + text)

    def answer(self, n, accept):
        card = next((c for c in self.cards if c["n"] == n), None)
        ready, rows = rq.check([rq.need("an open morale suggestion", card is not None,
                                        "That morale suggestion is no longer open.")])
        if not ready:
            raise AttitudeError(rq.first_why(rows))
        self.cards.remove(card)
        self.answered[card["group"]] = self.answered.get(card["group"], set()) | set(card["why"])
        if not accept:
            self._say("The GM rules %s fight on." % card["group"])
            return
        status = {"surrender": "surrendered", "flee": "fled", "bargain": "parley"}[card["rule"]]
        for cid in card["members"]:
            if self.in_fight(cid):
                self.set_status(cid, status, "morale: " + ", ".join(WHEN[w] for w in card["why"]))

    def set_status(self, cid, status, why, by="rule"):
        r, name = self.rows[cid], self.sim.by_id(cid)["name"]
        r["status"] = status
        self._side(cid)
        self.n += 1
        self.log.append({"n": self.n, "id": cid, "name": name, "from": r["attitude"], "to": r["attitude"],
                         "status": status, "why": why, "by": by})
        self._say("%s %s (%s%s)" % (name, {"surrendered": "surrenders", "fled": "flees the fight (it runs for the "
                                           "map's edge)", "parley": "stops fighting and offers to bargain",
                                           None: "fights again"}[status], why, "; the GM" if by == "GM" else ""))

    def flee_turn(self, cid):
        """GM 2026-10-25 (ruling P11): a creature that fled takes the Dash action each turn toward the nearest edge of the
        map (double its Speed); each character whose reach it leaves may make an Opportunity Attack before it does (the
        simulator's reaction window). On an edge square it leaves the map. True when it took a turn."""
        import sim_messages
        sim, r = self.sim, self.rows[cid]
        if r.get("gone") or sim.down(cid):
            return False
        c, s = sim.by_id(cid), sim.S
        board = sim_messages.map_part(sim.sc)
        cols, rows = board["cols"], board["rows"]
        edge = lambda q: q[0] <= 0 or q[1] <= 0 or q[0] >= cols - 1 or q[1] >= rows - 1
        to_edge = lambda q: min(q[0], q[1], cols - 1 - q[0], rows - 1 - q[1])
        st = s.state(cid)
        here = (int(round(st[2])), int(round(st[3])))
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        name = c["name"]
        if not edge(here):
            best, _, _ = sim._route_search(cid, 2 * speed)
            occupied = sim.occupied_cells(cid)
            spots = [q for q in best if q not in occupied]
            if not spots:
                self._say("%s tries to flee but can't move" % name)
                return True
            goal = min(spots, key=lambda q: (to_edge(q), best[q][0]))
            path = best[goal][1]
            self._say("%s flees: it takes the Dash action toward the edge of the map (Opportunity Attacks allowed)" % name)
            walked = sim.npc_walk(cid, path, stop=lambda: r["status"] != "fled")
            if sim.down(cid):
                return True
            if r["status"] != "fled":                            # GM 2026-10-27: an Opportunity Attack's damage ended
                self._say("%s stops fleeing where it stands (its action went on the Dash)" % name)   # the Suggestion
                return True
            here = tuple(path[walked]) if walked < len(path) else goal
        if edge(here):
            r["gone"] = True
            self._say("%s leaves the map: it has fled the fight" % name)
            s.move(cid, -100, -100)                              # off the board (the pages draw nothing below -50)
        return True

    # ------------------------------------------------------------------ the end of the fight
    def over(self):
        """The fight ends: the GM ended it, or nobody who ever fought is still fighting (down, surrendered, fled or no
        longer Hostile). A scene where nobody was ever Hostile goes on until the GM ends it. GM 2026-10-27: not while a
        lasting spell (Calm Emotions, Suggestion) is all that keeps a foe out of it (held): the spell may end."""
        if self.ended:
            return True
        once = [i for i, r in self.rows.items() if r["hostile_once"]]
        return bool(once) and not any(self.in_fight(i) and not self.rows[i]["joined"] or self.held(i) for i in self.rows)

    def finish(self):
        """The outcome line, once (the fight is over)."""
        if self.outcome:
            return self.outcome
        if self.ended in ("truce", "retreat", "end"):
            self.outcome = {"truce": "Truce: the fight ends with no winner. The scene goes on (social or exploration).",
                            "retreat": "The party retreats: the fight ends with no winner. The scene goes on.",
                            "end": "The GM ends the scene."}[self.ended]
        else:
            down, gone, calm = [], {}, []
            for i, r in self.rows.items():
                if not r["hostile_once"] or r["joined"]:
                    continue
                name = self.sim.by_id(i)["name"]
                if self.sim.down(i):
                    down.append(name)
                elif r["status"]:
                    gone.setdefault(r["status"], []).append(name)
                else:
                    calm.append(name)
            if not gone and not calm:
                self.outcome = "The party wins: every hostile creature is down."
            else:
                parts = ["%s %s" % (", ".join(v), STATUS[k]) for k, v in gone.items()]
                parts += ["%s stood down (no longer Hostile)" % ", ".join(calm)] if calm else []
                self.outcome = "%s: %s. The scene goes on (social or exploration)." % (
                    "The party wins" if down else "The fight ends with no winner", "; ".join(parts))   # play-test 2026-11-02
        self._say(self.outcome)
        return self.outcome

    # ------------------------------------------------------------------ the GM's choices
    def needs(self, cmd):
        """The needs a GM choice must meet before it is applied."""
        op, cid = cmd.get("op"), cmd.get("creature")
        known = cid in self.rows
        needs = [rq.need("the fight still on", not self.ended and not self.fight.done, "The fight is over.")]
        if op in ("attitude", "join", "leave", "status"):
            needs.append(rq.need("a creature of this fight", known, "Choose a creature (not a character) in this fight."))
        if op == "attitude":
            needs.append(check_attitude(cmd.get("attitude")))
        if op == "join" and known:
            needs.append(rq.need("a Friendly creature", self.rows[cid]["attitude"] == "Friendly",
                                 "Only a Friendly creature joins the party (%s is %s)." % (
                                     self.sim.by_id(cid)["name"], self.rows[cid]["attitude"])))
            needs.append(rq.need("not down", not self.sim.down(cid), "%s is down." % self.sim.by_id(cid)["name"]))
        if op == "status":
            needs.append(rq.need("a status", cmd.get("status") in list(STATUS) + ["fighting"],
                                 "A creature surrenders, flees, bargains or fights again."))
            if known and cmd.get("status") == "fighting":
                needs.append(rq.need("a Hostile creature", self.rows[cid]["attitude"] == "Hostile",
                                     "Only a Hostile creature fights: set its attitude to Hostile."))
        if op == "morale":
            needs.append(rq.need("an open morale suggestion", any(c["n"] == cmd.get("n") and c.get("kind") != "urge"
                                                                  for c in self.cards),
                                 "That morale suggestion is no longer open."))
        if op == "urge":
            needs.append(rq.need("an open Influence question", any(c["n"] == cmd.get("n") and c.get("kind") == "urge"
                                                                   for c in self.cards),
                                 "That Influence question is already answered."))
            needs.append(rq.need("what was urged", cmd.get("wants") in URGES, "Stand down, help us, or something else."))
        scenes = getattr(self.fight, "scenes", None)
        if op in ("truce", "retreat") and scenes and scenes.in_scene():      # GM 2026-10-26 (sim/scenes.py)
            needs.append(rq.need("a fight on", False, "No fight is on (%s): there is nothing to call off." %
                                 scenes.view(gm=False)["label"].lower()))
        if op == "truce":
            needs.append(rq.need("someone fighting the party", any(self.in_fight(i) and not self.rows[i]["joined"]
                                                                   for i in self.rows),
                                 "Nobody is fighting the party: there is nothing to call a truce on."))
        if op not in ("attitude", "join", "leave", "status", "morale", "urge", "truce", "retreat", "end"):
            needs.append(rq.need("a GM choice", False, "The GM sets an attitude, has a Friendly creature join or "
                                                       "leave, answers a morale suggestion, calls a truce, has the "
                                                       "party retreat, or ends the scene."))
        return needs

    def do(self, cmd):
        """Apply a GM choice (the simulator's thread)."""
        ready, rows = rq.check(self.needs(cmd))
        if not ready:
            raise AttitudeError(rq.first_why(rows))
        op, cid, why = cmd.get("op"), cmd.get("creature"), str(cmd.get("why") or "").strip()[:120]
        if op == "attitude":
            if not self.set(cid, cmd["attitude"], why or "the GM's ruling", by="GM"):
                raise AttitudeError("%s is already %s." % (self.sim.by_id(cid)["name"], cmd["attitude"]))
        elif op in ("join", "leave"):
            self.rows[cid]["joined"] = op == "join"
            self._side(cid)
            self._say("%s %s (the GM)" % (self.sim.by_id(cid)["name"], "joins the party" if op == "join"
                                          else "leaves the party's side"))
        elif op == "status":
            st = None if cmd["status"] == "fighting" else cmd["status"]
            self.set_status(cid, st, why or "the GM's ruling", by="GM")
        elif op == "morale":
            self.answer(cmd["n"], bool(cmd.get("accept")))
        elif op == "urge":                                       # GM 2026-10-25 (ruling P3)
            card = next(c for c in self.cards if c["n"] == cmd["n"])
            self.cards.remove(card)
            if card["creature"] in self.rows:
                self.follow_urge(card["creature"], cmd["wants"], "%s's Influence (%s) succeeded" % (card["who"], card["skill"]),
                                 by="GM")
        elif op == "truce":
            for i in list(self.rows):
                if self.in_fight(i) and not self.rows[i]["joined"]:
                    self.set(i, "Indifferent", why or "a truce", by="GM")
            self.ended = "truce"
        elif op in ("retreat", "end"):
            self.ended = op
        self.check_morale()
        if getattr(self.fight, "scenes", None):                 # GM 2026-10-26: the scene's suggestions follow at once
            self.fight.scenes.refresh_cards()
        return {"ok": True}

    def submit(self, cmd, timeout=30):
        """From the service's thread: hand a GM choice to the fight and wait for its answer."""
        ready, rows = rq.check(self.needs(cmd))
        if not ready:
            return {"ok": False, "refused": rq.first_why(rows)}
        reply = queue.Queue()
        self.gmq.put((cmd, reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "refused": "The fight did not answer: try again."}

    def drain(self):
        """On the simulator's thread: apply the GM's waiting choices. True when one was applied."""
        did = False
        while True:
            try:
                cmd, reply = self.gmq.get_nowait()
            except queue.Empty:
                return did
            try:
                out = self.do(cmd)
                did = True
            except AttitudeError as e:
                out = {"ok": False, "refused": str(e)}
            except Exception as e:                              # shown to the GM, never hidden
                out = {"ok": False, "refused": "%s: %s" % (type(e).__name__, e)}
            reply.put(out)

    def refuse_waiting(self):
        """The fight is over: answer any GM choice still waiting."""
        while True:
            try:
                _, reply = self.gmq.get_nowait()
            except queue.Empty:
                return
            reply.put({"ok": False, "refused": "The fight is over."})


GM_ONLY = "Morale (for the GM): "


def player_view(snap):
    """A seat's cut of the scene (after table_seats.player_view): the attitudes of the creatures the party sees (what
    the characters can tell from how they act), no prep sources, morale rules or the GM's morale suggestions."""
    if not isinstance(snap, dict) or not isinstance(snap.get("scene"), dict):
        return snap
    out, scene = dict(snap), snap["scene"]
    seen = {c.get("id") for c in ((snap.get("state") or {}).get("combatants") or [])}
    keep = lambda e: e.get("id") in seen
    out["scene"] = {"creatures": [{k: e[k] for k in ("id", "name", "attitude", "status", "joined")}
                                  for e in scene.get("creatures") or [] if keep(e)],
                    "changes": [dict(e) for e in scene.get("changes") or [] if keep(e)], "outcome": scene.get("outcome")}
    out["log"] = [e for e in snap.get("log") or [] if not str(e.get("text", "")).startswith(GM_ONLY)]
    return out
