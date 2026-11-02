"""GM 2026-10-23 (the SRD parts still to build, step 1: "do 1-4 here tonight"): the Study action in a live fight,
SRD 5.2.1 (Playing the Game, Actions; Rules Glossary: Study), every prerequisite checked first (sim/requirements.py), with
the reason when one is missing. GM 2026-11-01 ("All social are ASK the GM"; "Keep the social buttons, but allow the GM to
disable them. They require an action after all."): each Influence button spends the Action and goes to the GM with its
skill (no roll here); the GM's switch turns the buttons off.

- Study (Action): an Intelligence check to recall what the character knows about a creature it can see; the skill by
  the creature's type (the Areas of Knowledge table: Arcana for Aberrations, Constructs, Elementals, Fey and
  Monstrosities; History for Giants and Humanoids; Nature for Beasts, Dragons, Oozes and Plants; Religion for
  Celestials, Fiends and Undead). The SRD leaves the DC and what is learned to the GM: here the DC is 15 (Medium, the
  SRD's typical DCs) and a success tells its damage vulnerabilities, resistances and immunities and its condition
  immunities, which the whole party then knows (Party.known: the computer-played heroes stop wasting damage on it).
  Traps get their own Study (sim/traps.py, another session).
"""
import requirements as rq
import social_pack

STUDY_DC = 15
INFLUENCE = {"deception": "Deception", "intimidation": "Intimidation", "performance": "Performance",
             "persuasion": "Persuasion", "animal_handling": "Animal Handling"}
LORE = {"aberration": "Arcana", "construct": "Arcana", "elemental": "Arcana", "fey": "Arcana", "monstrosity": "Arcana",
        "giant": "History", "humanoid": "History", "beast": "Nature", "dragon": "Nature", "ooze": "Nature", "plant": "Nature",
        "celestial": "Religion", "fiend": "Religion", "undead": "Religion"}


class LoreError(ValueError):
    pass


def creature_type(c):
    t = str(c.get("type") or "").lower()
    return next((k for k in LORE if k in t), None)


def mod(score):
    return (int(score) - 10) // 2


def check_bonus(c, ability, skill):
    """The character's ability check with that skill: the modifier, + PB when proficient, + PB again with Expertise."""
    score = (c.get("abilities") or {}).get(ability)
    if score is None:
        score = {"cha": 10, "wis": 10 + 2 * int(c.get("wis_mod", 0) or 0), "int": 10}.get(ability, 10)
    pb = 2 + (int(c.get("level", 1) or 1) - 1) // 4
    prof = skill in (c.get("skills") or [])
    expert = skill in (c.get("expertise") or [])
    return mod(score) + (pb if prof else 0) + (pb if expert else 0), prof


class Lore:
    def __init__(self, fight):
        self.fight = fight
        self.off = False                                         # the GM's switch: the Influence buttons off

    @property
    def sim(self):
        return self.fight.sim

    def set_off(self, off):
        """The GM's switch (every screen redraws it and the buttons, as Auto Reactions does)."""
        f = self.fight
        with f.lock:
            self.off = bool(off)
            f.revision += 1
            f._publish_locked()
        self.sim.say("note", "The GM turns the Influence buttons %s." % ("off" if self.off else "on"))

    def seen(self, me, tid, what):
        t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
        ok = t is not None and tid != me and not self.sim.down(tid) and self.sim.sees(me, tid)
        return rq.need("a creature you can see", ok, "%s: choose another creature you can see." % what if t is None or tid == me
                       else "%s cannot see %s." % (self.sim.by_id(me)["name"], t["name"]) if not self.sim.down(tid) else
                       "%s is down." % t["name"]), t

    def needs(self, me, op, tid, mode=None):
        what = "Study" if op == "study" else "Influence"
        sight, t = self.seen(me, tid, what)
        needs = [rq.able(self.fight, me), rq.action_free(self.fight, me, what), sight]
        if op == "study" and t is not None:
            needs.append(rq.need("a creature the Areas of Knowledge cover", creature_type(t) is not None,
                                 "%s's type (%s) is not in the Areas of Knowledge table." % (t["name"], t.get("type") or "unknown")))
        if op == "influence":
            needs.append(rq.need("the Influence buttons on", not self.off, "The GM has turned the Influence buttons off."))
            needs.append(rq.need("an interaction", mode in INFLUENCE, "Choose how: deceive, intimidate, amuse or persuade (or "
                                                                      "Animal Handling for a Beast or Monstrosity)."))
            if t is not None and mode == "animal_handling":
                needs.append(rq.need("a Beast or Monstrosity", creature_type(t) in ("beast", "monstrosity"),
                                     "Animal Handling coaxes a Beast or Monstrosity; %s is not one." % t["name"]))
            if t is not None and mode in INFLUENCE and social_pack.on(self.sim.sc.get("optional_rules")):
                why = social_pack.influence_refusal(t, mode)   # GM 2026-10-25: the optional Social rules pack
                needs.append(rq.need("a creature that can be urged that way", why is None, why or ""))
        return needs

    def offers(self, me):
        """Study and Influence entries for the sheet: the creatures each can take now, and why not for the others."""
        out = []
        others = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me]
        for op, label, modes in (("study", "Study", [None]), ("influence", "Influence", list(INFLUENCE))):
            for mode in modes:
                ok, no = [], {}
                for o in others:
                    ready, rows = rq.check(self.needs(me, op, o, mode))
                    (ok.append(o) if ready else no.__setitem__(o, rq.first_why(rows)))
                base = self.needs(me, op, None, mode)[:2]
                if op == "influence":
                    base = base + [rq.need("the Influence buttons on", not self.off, "The GM has turned the Influence buttons off.")]
                ready, rows = rq.check(base)
                e = {"op": op, "label": label if not mode else "%s (%s)" % (label, INFLUENCE[mode]), "bonus": False,
                     "ready": ready, "targets": ok, "refused": no}
                if mode:
                    e["mode"] = mode
                if not ready:
                    e["why"] = rq.first_why(rows)
                out.append(e)
        return out

    def do(self, me, cmd):
        op, tid, mode = cmd.get("op"), cmd.get("target"), cmd.get("mode")
        ready, rows = rq.check(self.needs(me, op, tid, mode))
        if not ready:
            raise LoreError(rq.first_why(rows))
        c, t, turn = self.sim.by_id(me), self.sim.by_id(tid), self.fight.turn_state
        turn["action_used"], turn["attacks_left"] = True, 0
        if op == "influence":                                    # no roll here: the GM rules it, even after the turn
            urge, what = str(cmd.get("urge") or "").strip()[:120], "Influence (%s)" % INFLUENCE[mode]
            n = self.fight.add_ask(me, c["name"], "action", what, [tid], t["name"] + (": " + urge if urge else ""))
            self.sim.say("turn", "%s uses %s on %s (Action)%s: the GM rules it (request %d)" % (
                c["name"], what, t["name"], ' "%s"' % urge if urge else "", n))
            return "action"
        say = lambda text: self.sim.say("dice", text)
        rng = self.sim.rng
        kind = creature_type(t)
        skill = LORE[kind]
        bonus, prof = check_bonus(c, "int", skill)
        d20 = rng.randint(1, 20)
        total = d20 + bonus
        import martial_high                                  # MARTIAL-HIGH: Tactical Mind, Stroke of Luck
        if total < STUDY_DC and martial_high.lucky(self.sim.party, me):
            say("%s Studies %s: Intelligence (%s) d20 %d %+d = %d vs DC %d" % (c["name"], t["name"], skill, d20, bonus, total, STUDY_DC))
            total = martial_high.luck_check(self.sim.party, me, total, STUDY_DC, "Intelligence (%s)" % skill, bonus)
            d20 = total - bonus
        ok = total >= STUDY_DC
        say("%s Studies %s (Action): Intelligence (%s) d20 %d %+d = %d vs DC %d -> %s" % (
            c["name"], t["name"], skill, d20, bonus, total, STUDY_DC, "recalls it" if ok else "recalls nothing useful"))
        if ok:
            self.reveal(me, tid, t)
        return "action"

    def reveal(self, me, tid, t):
        party, say = self.sim.party, lambda text: self.sim.say("dice", text)
        parts = []
        for field, what in (("damagevulnerabilities", "vulnerable"), ("damageresistances", "resistant"),
                            ("damageimmunities", "immune")):
            kinds = [k.strip().lower() for k in str(t.get(field) or "").split(";")[0].split(",") if k.strip()]
            for k in kinds:
                party.known[(party.kind(tid), k)] = what
            if kinds:
                parts.append("%s to %s" % (what.capitalize(), ", ".join(kinds)))
        cond = str(t.get("conditionimmunities") or "").strip()
        if cond:
            parts.append("immune to the %s condition%s" % (cond, "s" if "," in cond else ""))
        say("%s knows about %s: %s" % (self.sim.by_id(me)["name"], t["name"],
                                       "; ".join(parts) if parts else "no damage it shrugs off, nothing it resists"))
