"""SPELL-EFFECTS-01 group 2 (GM 2026-10-26): summoned and conjured creatures in Play live, by SRD 5.2.1 (levels 1-3).
Summon Beast is not in SRD 5.2.1; Conjure Animals there is a pack of spirits, an area that moves (sim/spell_zones.py).

- Find Steed (level 2, Action, 30 ft): an Otherworldly Steed (its own stat block in the spell: AC 10 + the slot's level,
  5 + 10 Hit Points a slot level, Speed 60 ft and Fly 60 ft from a level 4 slot, Otherworldly Slam with the caster's
  spell attack, 1d8 + the slot's level Radiant (Celestial), Psychic (Fey) or Necrotic (Fiend)), Large, in an unoccupied
  space within range. It shares the caster's Initiative count (its turn comes right after the caster's), is a controlled
  mount while the caster rides it (sim/map_layers.py), and otherwise the game plays it as an ally. A new casting replaces
  the steed; it disappears at 0 Hit Points or when the caster dies.
- Find Familiar (1 hour or Ritual: never cast in a fight): a character with the spell has its familiar from before the
  fight, waiting in its pocket dimension; a Magic action calls it to an unoccupied space within 30 ft (the form chosen
  the first time: Bat, Cat, Frog, Hawk, Lizard, Octopus, Owl, Rat, Raven, Spider or Weasel, a Celestial, Fey or Fiend),
  and another dismisses it. It rolls its own Initiative and acts on its own turn; it can't attack. It obeys its caster
  (telepathy, no action): "follow" (it keeps beside the caster and takes the Dodge action, the default) or "help" (it
  goes beside the creature named and takes the Help action: the next attack an ally makes against it has Advantage).
  At 0 Hit Points it disappears until the spell is cast again.
- Animate Dead (1 minute: SRD 5.2.1 Longer Casting Times, the Action on each of the caster's turns for 10 rounds, with
  Concentration; broken, the spell fails and no slot is spent): a dead Small or Medium Humanoid within 10 ft rises as a
  Zombie on the caster's side (its own Initiative). On each of its turns the caster can take a Bonus Action to command
  every creature it made this way within 60 ft: attack a creature (until it drops) or guard (the Dodge action). With no
  command it takes the Dodge action and stays where it is. Undead the GM puts in a lineup with "animated_by": the
  caster's id obey the same commands.

How a creature joins the fight (_join) and leaves it (_leave) is the one place that knows the fight state: today the
stand-in FG's Combat Tracker (the Test lab's "add an encounter" path, after which the bridge syncs it); FG-EXIT-01's
FightState takes it there too. Its turns: creature_turn_start (the familiar's, an uncommanded undead's) and plan_filter
(the one creature a commanded undead attacks).
"""
import copy, re

import more_spells as ms
import requirements as rq

FORMS = ("Bat", "Cat", "Frog", "Hawk", "Lizard", "Octopus", "Owl", "Rat", "Raven", "Spider", "Weasel")
KINDS = ("Celestial", "Fey", "Fiend")
SLAM = {"Celestial": "radiant", "Fey": "psychic", "Fiend": "necrotic"}
SPELLS = {
    "Find Steed": dict(level=2, time="action", shape="sphere", radius_ft=5, range_ft=30, appearance="radiant",
                       choices=list(KINDS), upcast=True,
                       rider="an Otherworldly Steed (Large) on your Initiative; a controlled mount while you ride it"),
    "Find Familiar": dict(level=1, time="action", shape="sphere", radius_ft=5, range_ft=30, appearance="arcane",
                          choices=list(FORMS), call=True,
                          rider="your familiar (cast as a Ritual before the fight) comes from its pocket dimension: "
                                "a Magic action, no spell slot; it can't attack"),
    "Animate Dead": dict(level=3, time="action", shape="creature", range_ft=10, appearance="shadow",
                         rider="1 minute: your Action on each of 10 turns (Concentration), then the corpse rises as a "
                               "Zombie; a Bonus Action commands your undead"),
}
OPS = ("familiar_dismiss", "familiar_help", "familiar_follow", "command_undead", "command_guard")
CASTING = "Animate Dead (casting)"
TURNS = 10                                   # 1 minute


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_summons", None)
    if st is None:
        st = sim._summons = Summons(sim)
    ms.ACTIVE = sim
    return st


def library():
    import srd_library
    return srd_library.load()


def _clean(c):
    """A stat block as the fight takes it (plain fields; actions without their nested parts)."""
    c = copy.deepcopy(c)
    for k in ("gm_text", "played", "text", "made", "source", "xp", "cr"):
        c.pop(k, None)
    c["actions"] = [{k: v for k, v in a.items() if not isinstance(v, (dict, list))} for a in c.get("actions") or []]
    return c


class Summons:
    def __init__(self, sim):
        self.sim = sim
        self.made = {}            # creature id -> {"by", "spell", "kind": steed / familiar / undead, "order"}
        self.familiar = {}        # caster -> {"form", "type", "hp", "id", "out": on the map}
        self.steed = {}           # caster -> steed id
        self.casting = {}         # caster -> {"corpse", "actions", "slot"}
        self.n = 0
        self.battles = 0
        for c in sim.sc["combatants"]:                           # undead the GM put in the lineup for a caster
            if c.get("animated_by"):
                self.made[c["id"]] = {"by": c["animated_by"], "spell": "Animate Dead", "kind": "undead", "order": None}

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    def name(self, i):
        return self.sim.by_id(i)["name"]

    # ------------------------------------------------------------------ joining and leaving the fight
    def new_id(self):
        taken = {c["id"] for c in self.sim.sc["combatants"]}
        while True:
            self.n += 1
            i = "id-%05d" % (900 + self.n)
            if i not in taken:
                return i

    def _join(self, c):
        """Put a creature into the running fight. Today the stand-in FG's Combat Tracker, through the Test lab's "add an
        encounter" path: Sim.on_battle adds it, then the bridge syncs it so its turns are planned."""
        sim = self.sim
        S = getattr(sim, "S", None)
        if S is not None and hasattr(S, "addCombatant"):         # FG-EXIT-01: the Python fight state (sim/fight_state.py)
            S.addCombatant(c)
            for a in c.get("actions") or []:
                S.addAction(c["id"], a)
            sim.sc["combatants"].append(c)
            return
        raise RuntimeError("Summons need the Python fight state (sim.S).")

    def _leave(self, cid):
        """Take a creature out of the fight (a dismissed familiar)."""
        sim = self.sim
        S = getattr(sim, "S", None)
        if hasattr(S, "removeCombatant"):                        # FG-EXIT-01: the Python fight state
            S.removeCombatant(cid)
        else:
            getattr(S, "combatants", {}).pop(cid, None)
        sim.sc["combatants"][:] = [o for o in sim.sc["combatants"] if o["id"] != cid]

    def free_space(self, x, y, size=1):
        """True when the size x size squares from (x, y) hold no standing creature."""
        sim = self.sim
        for o in sim.sc["combatants"]:
            if sim.down(o["id"]):
                continue
            ox, oy = self.party.pos(o["id"])
            n = sim.size_sq(o["id"])
            x0, y0 = ox - (n - 1) / 2, oy - (n - 1) / 2
            if x0 < x + size - 0.01 and x < x0 + n - 0.01 and y0 < y + size - 0.01 and y < y0 + n - 0.01:
                return False
        if size > 1 and self.party.walled((x, y), (x + size - 1, y + size - 1)):
            return False
        return True

    def initiative(self, after=None, block=None):
        """(init result, init bonus): right after `after` on its count (Find Steed), else a d20 roll (its own)."""
        s = self.sim.S
        if after is not None:
            return int(s.getField(after, "initresult") or 10), float(s.getField(after, "init") or 0) - 0.5
        bonus = int((block or {}).get("init", 10)) - 10
        return self.sim.rng.randint(1, 20) + bonus, bonus

    # ------------------------------------------------------------------ the cards
    def needs(self, me, name, slot=None):
        s = SPELLS[name]
        if s.get("call"):                                        # Find Familiar: a Magic action, no slot
            needs = ms.cast_needs(self.fight, me, name, 0, "action")
            fam = self.familiar.get(me) or {}
            needs.append(rq.need("the familiar away", not fam.get("out"), "%s's familiar is already here." % self.name(me)))
            needs.append(rq.need("the familiar able to come", fam.get("hp", 1) > 0,
                                 "%s's familiar dropped to 0 Hit Points: it comes back when the spell is cast again "
                                 "(after the fight)." % self.name(me)))
            return needs
        needs = ms.cast_needs(self.fight, me, name, s["level"], s["time"], slot)
        if name == "Animate Dead":
            needs.append(rq.need("not casting it already", me not in self.casting,
                                 "%s is casting Animate Dead already." % self.name(me)))
        return needs

    def offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in known(c):
            s = dict(SPELLS[name])
            fam = self.familiar.get(me)
            if name == "Find Familiar" and fam:
                s["choices"] = [fam["form"]]                     # the form chosen the first time
            e = ms.card(self.fight, me, name, s, self.needs(me, name))
            if name == "Find Familiar":
                e["call"] = True
                e["slots_ok"] = []
            if name == "Find Steed":
                e["summoned"] = True                             # the page: "a square", not a Sphere
            if name == "Animate Dead":
                e["upcast"] = False
                if e["ready"]:
                    e["targets"], e["refused"] = ms.targets_of(self.fight, me, lambda t: self.corpse(me, t))
            if c.get("metamagic") and name == "Find Steed":
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, s)
            out.append(e)
        return out

    def adjust_offers(self, me, out):
        """The familiar's and the undead's buttons on the caster's sheet."""
        acts = out.setdefault("actions", [])
        fam = self.familiar.get(me)
        if fam and fam.get("out"):
            ready, rows = rq.check([rq.able(self.fight, me), rq.action_free(self.fight, me, "dismissing the familiar")])
            acts.append({"op": "familiar_dismiss", "label": "Dismiss the familiar (Magic action)", "ready": ready,
                         "why": rq.first_why(rows)})
            ok, no = ms.targets_of(self.fight, me, lambda t: self.help_target(me, t))
            acts.append({"op": "familiar_help", "label": "Familiar: help against a foe", "ready": bool(ok),
                         "why": "" if ok else "No foe for the familiar to help against.", "targets": ok, "refused": no,
                         "time": "free"})
            acts.append({"op": "familiar_follow", "label": "Familiar: follow me", "ready": True, "time": "free"})
        if self.undead(me):
            ready, rows = rq.check(self.command_needs(me))
            ok, no = ms.targets_of(self.fight, me, lambda t: self.attack_target(me, t))
            acts.append({"op": "command_undead", "label": "Command your undead: attack", "time": "bonus",
                         "ready": ready and bool(ok), "why": rq.first_why(rows) or ("" if ok else "No creature to attack."),
                         "targets": ok, "refused": no})
            acts.append({"op": "command_guard", "label": "Command your undead: guard", "time": "bonus",
                         "ready": ready, "why": rq.first_why(rows)})
        if me in self.casting:
            out["casting"] = {"spell": "Animate Dead", "turns": self.casting[me]["actions"], "of": TURNS}

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        if name == "Find Steed":
            return self.find_steed(me, cmd)
        if name == "Find Familiar":
            return self.call_familiar(me, cmd)
        return self.animate_dead(me, cmd)

    def place(self, me, cmd, name, size=1, rng=None):
        x, y = ms.square(cmd, name)
        ms.point_in_range(self.fight, me, x, y, rng or SPELLS[name]["range_ft"], name)
        if not self.free_space(x, y, size):
            raise ms.EffectError("%s needs an unoccupied space%s there." % (name, " (Large: 2 by 2 squares from it)" if size > 1 else ""))
        return x, y

    def find_steed(self, me, cmd):
        fight, sim, party = self.fight, self.sim, self.party
        s, plan = ms.metamagic(fight, me, "Find Steed", dict(SPELLS["Find Steed"]), cmd)   # Quickened: the Bonus Action
        ms.check(ms.cast_needs(fight, me, "Find Steed", 2, s["time"], cmd.get("slot")))
        kind = cmd.get("choice") or KINDS[0]
        if kind not in KINDS:
            raise ms.EffectError("Find Steed: a Celestial, Fey or Fiend steed.")
        x, y = self.place(me, cmd, "Find Steed", size=2, rng=s["range_ft"])
        c = sim.by_id(me)
        lv = ms.spend(fight, me, s["time"], 2, cmd.get("slot"))
        ms.pay_metamagic(fight, me, "Find Steed", plan)
        old = self.steed.get(me)
        if old and not sim.down(old):                            # "the steed is replaced by the new one"
            self.vanish(old, "replaced by a new steed")
        sid = self.new_id()
        init, bonus = self.initiative(after=me)
        atk = int(c.get("spell_atk") or (party.spell_dc(c) - 8))
        dmg = SLAM[kind]
        steed = {"id": sid, "name": "Otherworldly Steed (%s)" % kind, "side": c.get("side", "friend"),
                 "x": x + 0.5, "y": y + 0.5, "hp": 5 + 10 * lv, "ac": 10 + lv,
                 "speed": "60 ft., Fly 60 ft." if lv >= 4 else "60 ft.", "space": 10, "size": "large", "type": kind,
                 "senses": "Passive Perception 11", "int": 6, "wis_mod": 1, "init": init, "init_bonus": bonus,
                 "str_save": 4, "dex_save": 1, "con_save": 2, "int_save": -2, "wis_save": 1, "cha_save": -1,
                 "trained_mount": True, "summoned_by": me,
                 "actions": [{"id": "id-00001", "name": "Otherworldly Slam", "atk": atk, "atktype": "melee", "reach": 5,
                              "dmg": "1d8+%d" % lv, "dmgtype": dmg,
                              "desc": "Melee Attack Roll: +%d, reach 5 ft. Hit: 1d8 + %d %s damage." % (atk, lv, dmg.capitalize())}]}
        sim.say("dice", "%s casts Find Steed (a level %d slot): an Otherworldly Steed (%s; AC %d, %d HP) appears at (%d, %d), "
                "on %s's Initiative count" % (c["name"], lv, kind, steed["ac"], steed["hp"], x, y, c["name"]))
        self._join(steed)
        self.made[sid] = {"by": me, "spell": "Find Steed", "kind": "steed", "order": None}
        self.steed[me] = sid
        return {"spell": "Find Steed", "appearance": "radiant", "shape": "circle", "origin": [x + 0.5, y + 0.5],
                "radius_ft": 5, "targets": [], "from": list(party.pos(me)), "summoned": sid}

    def call_familiar(self, me, cmd):
        fight, sim, party = self.fight, self.sim, self.party
        if cmd.get("metamagic"):
            raise ms.EffectError("Calling a familiar is a Magic action, not casting a spell: no Metamagic.")
        ms.check(self.needs(me, "Find Familiar"))
        fam = self.familiar.get(me) or {}
        form = fam.get("form") or cmd.get("choice") or "Owl"
        if form not in FORMS:
            raise ms.EffectError("Find Familiar: a Bat, Cat, Frog, Hawk, Lizard, Octopus, Owl, Rat, Raven, Spider or Weasel.")
        x, y = self.place(me, cmd, "Find Familiar")
        c = sim.by_id(me)
        t = fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0                  # a Magic action
        block = _clean(library()[form])
        fid = fam.get("id") or self.new_id()
        init, bonus = self.initiative(block=block)
        kind = fam.get("type") or (cmd.get("kind") if cmd.get("kind") in KINDS else "Fey")
        block.update(id=fid, name="%s's %s" % (c["name"], form.lower()), side=c.get("side", "friend"), x=x, y=y,
                     init=init, init_bonus=bonus, type=kind, summoned_by=me, actions=[], familiar=True)
        if fam.get("hp") is not None:
            block["wounds"] = max(0, block["hp"] - fam["hp"])
        sim.say("turn", "%s calls the familiar from its pocket dimension (a Magic action; Find Familiar was cast as a Ritual "
                "before the fight): %s %s (%s) at (%d, %d), Initiative %d; it can't attack" % (
                    c["name"], "an" if form[0] in "AEIOU" else "a", form, kind, x, y, init))
        self._join(block)
        self.made[fid] = {"by": me, "spell": "Find Familiar", "kind": "familiar", "order": {"do": "follow"}}
        self.familiar[me] = {"form": form, "type": kind, "id": fid, "out": True, "hp": fam.get("hp", block["hp"])}
        return {"spell": "Find Familiar", "appearance": "arcane", "shape": "circle", "origin": [x, y], "radius_ft": 5,
                "targets": [], "from": list(party.pos(me)), "summoned": fid,
                "_cmd": {"free": "the familiar answers its call (Find Familiar was cast as a Ritual before the fight)"}}

    def corpse(self, me, tid):
        """Animate Dead: a dead Small or Medium Humanoid within 10 ft (bones are not on the map)."""
        sim, o = self.sim, self.sim.by_id(tid)
        if not sim.down(tid) or o.get("pc"):
            raise ms.EffectError("Animate Dead needs a corpse: %s is not one." % o["name"])
        if "humanoid" not in str(o.get("type", "")).lower():
            raise ms.EffectError("Animate Dead raises a Humanoid's corpse; %s is not one." % o["name"])
        import map_layers
        if map_layers.size_of(o) not in ("small", "medium"):
            raise ms.EffectError("Animate Dead raises a Small or Medium Humanoid.")
        if o.get("raised"):
            raise ms.EffectError("%s's corpse was raised already." % o["name"])
        if self.party.dist(me, tid) > 10.01:
            raise ms.EffectError("%s's corpse is %d ft away: out of range (10 ft)." % (o["name"], round(self.party.dist(me, tid))))
        return o

    def animate_dead(self, me, cmd):
        """Starting the minute's casting (SRD 5.2.1 Longer Casting Times): the Action now and on each turn after."""
        fight, party = self.fight, self.party
        if cmd.get("metamagic"):
            raise ms.EffectError("Metamagic on Animate Dead (a 1-minute casting): ask the GM.")
        ms.check(self.needs(me, "Animate Dead", cmd.get("slot")))
        tid = cmd.get("target")
        if tid is None:
            raise ms.EffectError("Choose a corpse for Animate Dead.")
        self.corpse(me, tid)
        t = fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0
        party.start_concentration(me, CASTING)
        party.__dict__.setdefault("gm_concentration", {})[me] = CASTING
        self.casting[me] = {"corpse": tid, "actions": 1, "slot": cmd.get("slot")}
        self.sim.say("turn", "%s begins casting Animate Dead on %s's corpse: 1 minute, the Action on each of %d turns with "
                     "Concentration; the slot is spent when it is done (1 of %d)" % (self.name(me), self.name(tid), TURNS, TURNS))
        x, y = party.pos(tid)
        return {"spell": "Animate Dead", "appearance": "shadow", "shape": "circle", "origin": [x, y], "radius_ft": 5,
                "targets": [], "from": list(party.pos(me)),
                "_cmd": {"free": "a 1-minute casting: its slot is spent when it is done"}}

    def keep_casting(self, me):
        """The caster's turn: the minute goes on (its Action), or failed (Concentration broken), or is done."""
        job = self.casting.get(me)
        if not job:
            return
        party, sim = self.party, self.sim
        if party.concentrates(me) != CASTING:
            self.casting.pop(me)
            sim.say("dice", "%s's Animate Dead fails: the Concentration broke (no spell slot spent)" % self.name(me))
            return
        t = self.fight.turn_state
        t["action_used"], t["attacks_left"] = True, 0
        job["actions"] += 1
        if job["actions"] < TURNS:
            sim.say("turn", "%s keeps casting Animate Dead (the Action): %d of %d" % (self.name(me), job["actions"], TURNS))
            return
        self.casting.pop(me)
        party.end_concentration(me)
        pool = party.pools.get(me) or [party.slots.get(me, 0)]
        if sum(pool[2:]) <= 0:
            sim.say("dice", "%s finishes Animate Dead with no spell slot of level 3 or higher left: it fails" % self.name(me))
            return
        lv = party.spend_slot(me, max(3, int(job.get("slot") or 3)))
        self.raise_dead(me, job["corpse"], lv)

    def raise_dead(self, me, corpse, lv):
        sim, party = self.sim, self.party
        body = sim.by_id(corpse)
        body["raised"] = True
        block = _clean(library()["Zombie"])
        zid = self.new_id()
        init, bonus = self.initiative(block=block)
        x, y = party.pos(corpse)
        block.update(id=zid, name="Zombie (%s)" % body["name"], side=sim.by_id(me).get("side", "friend"), x=x, y=y,
                     init=init, init_bonus=bonus, animated_by=me)
        sim.say("dice", "%s finishes Animate Dead (a level %d slot): %s's corpse rises as a Zombie under %s's control "
                "(Initiative %d)" % (self.name(me), lv, body["name"], self.name(me), init))
        self._join(block)
        self.made[zid] = {"by": me, "spell": "Animate Dead", "kind": "undead", "order": None}
        return zid

    # ------------------------------------------------------------------ orders
    def undead(self, me):
        here = {o["id"] for o in self.sim.sc["combatants"]}
        return [i for i, m in self.made.items() if m["by"] == me and m["kind"] == "undead" and i in here and not self.sim.down(i)]

    def command_needs(self, me):
        party = self.party
        near = [i for i in self.undead(me) if party.dist(me, i) <= 60.01]
        return [rq.able(self.fight, me), rq.bonus_free(self.fight, me, "commanding the undead"),
                rq.need("an undead within 60 ft", bool(near), "None of %s's undead is within 60 ft." % self.name(me))]

    def attack_target(self, me, tid):
        if tid == me or tid in self.made or self.sim.down(tid):
            raise ms.EffectError("Not a creature to attack.")
        if self.party.side(tid) == self.party.side(me):
            raise ms.EffectError("%s is an ally." % self.name(tid))
        return tid

    def help_target(self, me, tid):
        if self.sim.down(tid) or self.party.side(tid) == self.party.side(me):
            raise ms.EffectError("The familiar helps against a foe.")
        return tid

    def act(self, me, cmd):
        op, fight, party = cmd["op"], self.fight, self.party
        if op == "familiar_dismiss":
            ms.check([rq.able(fight, me), rq.action_free(fight, me, "dismissing the familiar")])
            fam = self.familiar.get(me)
            if not fam or not fam.get("out"):
                raise ms.EffectError("%s's familiar is not here." % self.name(me))
            t = fight.turn_state
            t["action_used"], t["attacks_left"] = True, 0
            fam["hp"] = party.hp_left(fam["id"])
            self.sim.say("turn", "%s dismisses the familiar to its pocket dimension (a Magic action)" % self.name(me))
            self._leave(fam["id"])
            fam["out"] = False
            return {"ok": True, "result": op}
        if op in ("familiar_help", "familiar_follow"):
            fam = self.familiar.get(me)
            if not fam or not fam.get("out"):
                raise ms.EffectError("%s's familiar is not here." % self.name(me))
            if op == "familiar_help":
                if cmd.get("target") is None:
                    raise ms.EffectError("Pick the foe the familiar helps against.")
                self.help_target(me, cmd["target"])
                self.made[fam["id"]]["order"] = {"do": "help", "target": cmd["target"]}
                said = "help against %s" % self.name(cmd["target"])
            else:
                self.made[fam["id"]]["order"] = {"do": "follow"}
                said = "follow"
            self.sim.say("turn", "%s tells the familiar (telepathy, no action): %s" % (self.name(me), said))
            return {"ok": True, "result": op}
        ms.check(self.command_needs(me))                         # command_undead, command_guard
        tid = cmd.get("target") if op == "command_undead" else None
        if op == "command_undead" and tid is None:
            raise ms.EffectError("Pick the creature your undead attack.")
        order = {"do": "attack", "target": self.attack_target(me, tid)} if tid is not None else {"do": "guard"}
        party.use_bonus(me)
        near = [i for i in self.undead(me) if party.dist(me, i) <= 60.01]
        for i in near:
            self.made[i]["order"] = dict(order)
        self.sim.say("turn", "%s commands %s (Bonus Action): %s" % (
            self.name(me), ", ".join(self.name(i) for i in near),
            "attack %s" % self.name(tid) if tid is not None else "guard (the Dodge action)"))
        return {"ok": True, "result": op}

    # ------------------------------------------------------------------ their turns
    def creature_turn_start(self, me):
        """A summoned creature's turn: the familiar's (follow, or Help), an undead's with no command (Dodge). Returns why
        its turn is over, or "" (the game plays it: a steed, a commanded undead)."""
        m = self.made.get(me)
        if not m or self.sim.down(me):
            return ""
        sim = self.sim
        if m["kind"] == "familiar":
            return self.familiar_turn(me, m)
        if m["kind"] == "undead":
            order = m.get("order") or {}
            if order.get("do") == "attack" and not sim.down(order["target"]):
                return ""
            if order.get("do") == "attack":                      # its task is complete: it waits for a new command
                m["order"] = order = None
            sim.by_id(me)["dodging"] = True
            return ("no command from %s: it takes the Dodge action and stays where it is" % self.name(m["by"]) if not order
                    else "%s's command: it guards (the Dodge action)" % self.name(m["by"]))
        return ""

    def walk_to(self, me, goal, near=5):
        """Move the creature along its cheapest route to within `near` ft of `goal`'s square (its fastest Speed)."""
        sim, party = self.sim, self.party
        c = sim.by_id(me)
        speed = max([int(n) for n in re.findall(r"\d+", str(c.get("speed", "30")))] or [30])
        best, _, start = sim._route_search(me, speed)
        occupied = sim.occupied_cells(me)
        gx, gy = party.pos(goal)
        u = sim.sc.get("units", 5)
        if max(abs(start[0] - gx), abs(start[1] - gy)) * u <= near:
            return 0
        spots = [q for q in best if q not in occupied and max(abs(q[0] - gx), abs(q[1] - gy)) * u <= near]
        if not spots:
            spots = sorted((q for q in best if q not in occupied),
                           key=lambda q: (max(abs(q[0] - gx), abs(q[1] - gy)), best[q][0]))[:1]
        if not spots:
            return 0
        goal_sq = min(spots, key=lambda q: best[q][0])
        return sim.npc_walk(me, best[goal_sq][1])

    def familiar_turn(self, me, m):
        sim, gm = self.sim, self.sim.gm_rules
        order = m.get("order") or {"do": "follow"}
        name = self.name(me)
        if order["do"] == "help" and not sim.down(order["target"]):
            tid = order["target"]
            self.walk_to(me, tid)
            if sim.down(me):
                return True
            if self.party.dist(me, tid) <= 5.01:
                gm.__dict__.setdefault("helped", {})[tid] = me
                return "it takes the Help action: the next attack an ally makes against %s has Advantage" % self.name(tid)
            return "it can't reach %s this turn" % self.name(tid)
        self.walk_to(me, m["by"])
        if sim.down(me):
            return True
        sim.by_id(me)["dodging"] = True
        return "it keeps beside %s and takes the Dodge action (a familiar can't attack)" % self.name(m["by"])

    def live_turn_start(self, me):
        self.keep_casting(me)

    def vanish(self, cid, why):
        """A summoned creature disappears (its token stays, fallen, as a marker)."""
        sim = self.sim
        m = self.made.get(cid)
        if not m or m.get("gone"):
            return
        m["gone"] = True
        hp = self.party.hp_left(cid)
        if hp > 0:
            sim.S.pcDamage(m["by"], cid, "", hp, False, "force")
            sim.settle()
        sim.say("dice", "%s disappears (%s)" % (self.name(cid), why))

    def on_hurt(self, src, tid, amount, kinds=""):
        m = self.made.get(tid)
        if m and self.sim.down(tid) and not m.get("gone"):
            m["gone"] = True
            if m["kind"] == "familiar":
                fam = self.familiar.get(m["by"])
                if fam:
                    fam["hp"], fam["out"] = 0, False
            if m["kind"] in ("familiar", "steed"):
                self.sim.say("dice", "%s drops to 0 Hit Points and disappears" % self.name(tid))
        c = self.sim.by_id(tid)
        if c.get("pc") and self.party.deaths.get(tid, {}).get("dead"):     # "or if you die": the steed goes
            sid = self.steed.get(tid)
            if sid and not self.sim.down(sid):
                self.vanish(sid, "its caster died")

    # ------------------------------------------------------------------ the planner's list
    def plan_filter(self, source, opponents):
        cid = str(source).split(".")[-1]
        order = (self.made.get(cid) or {}).get("order") or {}
        if order.get("do") != "attack":
            return opponents
        want = [p for p in opponents if str(p).split(".")[-1] == order["target"]]
        return want or opponents


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def creature_turn_start(sim, me):
    return of(sim).creature_turn_start(me) if getattr(sim, "_summons", None) else ""


def live_turn_start(fight, me):
    if getattr(fight.sim, "_summons", None):
        of(fight.sim).live_turn_start(me)


def adjust_offers(fight, me, out):
    of(fight.sim).adjust_offers(me, out)


def on_hurt(sim, src, tid, amount, kinds=""):
    if getattr(sim, "_summons", None):
        of(sim).on_hurt(src, tid, amount, kinds)


def plan_filter(sim, source, me, opponents, combatants):
    st = getattr(sim, "_summons", None)
    return st.plan_filter(source, opponents) if st else opponents
