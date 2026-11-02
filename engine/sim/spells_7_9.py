"""SPELLS-7-9 (GM 2026-10-28: "Make the SRD 5.2.1 spells of levels 7, 8 and 9 that matter in a fight into Cast
buttons"): six spells in Play live, each checked before anything is spent and watched by the rules referee. Three more
are lasting areas, in sim/spell_zones.py: Conjure Celestial, Incendiary Cloud and Earthquake.

  Arcane Sword (7)        90 ft, Concentration, up to 1 minute; a miniature sword worth 250+ GP at hand: a spectral sword
                          appears within 5 ft of a creature (the square next to it nearest the caster) and makes a melee
                          spell attack, 4d12 + the spellcasting modifier Force; on later turns a Bonus Action moves it up
                          to 30 ft and attacks again (Swing the sword). The sword and its target stay within the 90 ft.
  Dominate Monster (8)    60 ft, a creature you can see, Concentration, up to 1 hour: Wisdom save (Advantage when you or
                          your allies are fighting it) or Charmed; whenever it takes damage it saves again, the spell
                          ending on a success. On your turn you order it (no action): attack a creature (Order: attack),
                          or stand down; with no order it attacks no one on your side.
  Holy Aura (8)           Self, a 30-foot Emanation, Concentration, up to 1 minute; a reliquary worth 1,000+ GP at hand:
                          you and your side within 30 ft have Advantage on all saving throws, and other creatures have
                          Disadvantage on attack rolls against them; a Fiend or an Undead that hits one with a melee
                          attack: Constitution save or Blinded until the end of its next turn.
  Mind Blank (8)          a willing creature you touch, 24 hours (the fight): Immunity to Psychic damage and the Charmed
                          condition (a Charmed one is free of it).
  Time Stop (9)           Self: you take 1d4 + 1 more turns in a row (Time Stop: next turn), no time passing for the
                          others; the spell ends when something you do on them affects another creature (its damage, a
                          condition it gives), and ending the turn gives up the turns left.
  Storm of Vengeance (9)  1 mile, a cloud of 300-foot radius, Concentration, up to 1 minute: each creature under it when it
                          appears (your side too): Constitution save or 2d6 Thunder and Deafened for the duration. At the
                          start of each of your later turns: 2 acid rain, 4d6 Acid each; 3 six bolts on six of your foes
                          under it, Dexterity save, 10d6 Lightning, half on a success; 4 hail, 2d6 Bludgeoning each;
                          5-10 freezing rain, 1d6 Cold each, and the area is Difficult Terrain and Heavily Obscured.

Each effect is a condition or a mark held as the spell's own record (gm_rules: "Charmed" and "Deafened" by the caster's
Concentration, Party.control; the marks "Holy Aura" and "Mind Blank"), so Dispel and
the Combat Tracker see them.
Not here (the GM rules them, Ask the GM): Storm of Vengeance's wind and its ban on ranged weapon attacks; a creature the
game plays casting these.
"""
import math, re

import more_spells as ms
import requirements as rq

SPELLS = {
    "Arcane Sword": dict(level=7, time="action", shape="creature", range_ft=90, concentration=True, appearance="arcane",
                         rounds=10, cost=("miniature sword", 250),
                         rider="a spectral sword: melee spell attack, 4d12 + your modifier Force; later turns: a Bonus "
                               "Action moves it up to 30 ft and attacks again"),
    "Dominate Monster": dict(level=8, time="action", shape="creature", range_ft=60, concentration=True, appearance="arcane",
                             rounds=600, save=("wis", "Wisdom"),
                             rider="Wisdom save or Charmed: it obeys your orders; it saves again whenever it takes damage"),
    "Holy Aura": dict(level=8, time="action", shape="self", range_ft=0, concentration=True, appearance="radiant",
                      rounds=10, cost=("reliquary", 1000),
                      rider="your side within 30 ft: Advantage on saves, attacks against them at Disadvantage; a Fiend or "
                            "Undead hitting one in melee: Constitution save or Blinded"),
    "Mind Blank": dict(level=8, time="action", shape="creature", range_ft=5, touch=True, appearance="arcane", helps=True,
                       rider="Immunity to Psychic damage and the Charmed condition for 24 hours"),
    "Time Stop": dict(level=9, time="action", shape="self", range_ft=0, appearance="arcane",
                      rider="you take 1d4 + 1 more turns in a row; it ends if you affect another creature"),
    "Storm of Vengeance": dict(level=9, time="action", shape="sphere", radius_ft=300, range_ft=5280, concentration=True,
                               appearance="lightning", rounds=10, save=("con", "Constitution"),
                               rider="everyone under it: Constitution save or 2d6 Thunder and Deafened; acid, lightning, "
                                     "hail and freezing rain on your later turns"),
}
OPS = ("arcane_sword", "dominate_order", "dominate_stand", "time_stop_turn")
HOLY, BLANK, DOMINATED = "Holy Aura", "Mind Blank", "Dominate Monster"
MINE = {HOLY, BLANK, "Charmed", "Deafened"}
SWORD_FT, AURA_FT, STORM_TURNS = 30, 30, 10


def known(c):
    return [n for n in SPELLS if ms.has_spell(c, n)]


def of(sim):
    st = getattr(sim, "_spells_7_9", None)
    if st is None:
        st = sim._spells_7_9 = Spells79(sim)
    ms.ACTIVE = sim
    return st


def gm(sim):
    return getattr(sim, "gm_rules", None)


def info(sim, t, name):
    g = gm(sim)
    return (g.cond.get(t) or {}).get(name) if g else None


def _roll(rng, expr):
    return sum(rng.randint(1, int(d)) for n, d in re.findall(r"(\d+)d(\d+)", expr) for _ in range(int(n)))


class Spells79:
    def __init__(self, sim):
        self.sim = sim
        self.sword = {}                   # caster -> {"at": (x, y), "serial": the turn it was cast or last swung}
        self.order = {}                   # dominated creature -> the creature it was ordered to attack (None: stand down)
        self.master = {}                  # dominated creature -> its caster
        self.stop = {}                    # caster -> Time Stop's turns left
        self.storm = {}                   # caster -> {"zone": its map zone, "round": cast, "done": the last round played}
        self.blind = {}                   # creature -> turn ends left of Holy Aura's Blinded
        self.immune = {}                  # creature -> its damage immunities before Mind Blank

    @property
    def fight(self):
        return self.sim.live

    @property
    def party(self):
        return self.sim.party

    def name(self, i):
        return self.sim.by_id(i)["name"]

    def rnd(self):
        return int(self.sim.S.round() or 0)

    def serial(self):
        return int(self.sim.S.turnSerial or 0)

    def units(self):
        return self.sim.sc.get("units", 5)

    # ------------------------------------------------------------------ the cards
    def needs(self, me, name, slot=None, time=None):
        s = SPELLS[name]
        out = ms.cast_needs(self.fight, me, name, s["level"], time or s["time"], slot)
        if s.get("cost") and self.fight and (self.fight.turn_state or {}).get("id") == me:
            out.append(self.component(me, name)[0])
        return out

    def component(self, me, name):
        """A Material component with a cost, not consumed (a spellcasting focus can't stand in for it): an item in the
        bag that is that thing and worth that much ("Reliquary (1,000 GP)", or the Market's price)."""
        noun, gp = SPELLS[name]["cost"]
        bag = self.fight.items.bag(me)
        have = [b for b in bag.entries() if int(b.get("qty", 0)) > 0 and self.worth(b, noun) >= gp]
        return rq.need("a %s worth %d+ GP at hand" % (noun, gp), bool(have),
                       "%s needs a %s worth %d+ GP; %s has none in the bag (a spellcasting focus can't stand in for a "
                       "component with a cost)." % (name, noun, gp, self.name(me)), rq.LINKS["market"]), have

    @staticmethod
    def worth(entry, noun):
        name = str(entry.get("name") or entry.get("item") or "")
        if noun.lower() not in name.lower():
            return 0
        m = re.search(r"(\d[\d,]*)\s*GP", name, re.I)
        if m:
            return int(m.group(1).replace(",", ""))
        try:
            import market
            item = market.load_catalog(market.CATALOG).get(entry.get("item"))
            return int(item["cost_cp"]) // 100 if item else 0
        except Exception:
            return 0

    def check_target(self, me, name, s, tid):
        sim, party = self.sim, self.party
        o = sim.by_id(tid)
        if o is None or not any(c["id"] == tid for c in sim.sc["combatants"]):
            raise ms.EffectError("Choose a creature for %s." % name)
        if sim.down(tid):
            raise ms.EffectError("%s is down." % o["name"])
        if name in ("Arcane Sword", "Dominate Monster") and tid == me:
            raise ms.EffectError("%s takes another creature, not the caster." % name)
        if name == "Mind Blank":
            if tid != me and party.side(tid) != party.side(me):
                raise ms.EffectError("Mind Blank takes a willing creature: %s is not one (a foe)." % o["name"])
            if info(sim, tid, BLANK):
                raise ms.EffectError("%s already has Mind Blank." % o["name"])
        if name == "Dominate Monster" and (info(sim, tid, "Charmed") or {}).get("spell") == DOMINATED:
            raise ms.EffectError("%s is already dominated." % o["name"])
        ms.in_range(self.fight, me, tid, s["range_ft"], name, sight=name != "Mind Blank")
        return o

    def offers(self, me):
        c, out = self.sim.by_id(me), []
        for name in known(c):
            s = SPELLS[name]
            e = ms.card(self.fight, me, name, s, self.needs(me, name), **({"helps": True} if s.get("helps") else {}))
            if e["ready"] and s["shape"] == "creature":
                e["targets"], e["refused"] = ms.targets_of(self.fight, me, lambda t: self.check_target(me, name, s, t))
            if c.get("metamagic"):
                import live_sorcery
                e["metamagic"] = live_sorcery.of(self.fight).options(me, name, self.meta_entry(name))
            out.append(e)
        return out

    @staticmethod
    def meta_entry(name):
        """The fields Metamagic reads (sim/live_sorcery.py): its time, range, Concentration, a save it forces."""
        s = SPELLS[name]
        return dict(s, save=bool(s.get("save")), twin=False)

    def adjust_offers(self, me, out):
        """Swing the sword, order the dominated creature, Time Stop's next turn."""
        acts, fight = out.setdefault("actions", []), self.fight
        if me in self.sword and self.party.concentrates(me) == "Arcane Sword":
            ready, rows = rq.check(self.sword_needs(me))
            ok, no = ms.targets_of(fight, me, lambda t: self.sword_target(me, t))
            acts.append({"op": "arcane_sword", "label": "Arcane Sword: move it and attack", "time": "bonus",
                         "ready": ready and bool(ok), "why": rq.first_why(rows) or ("" if ok else "No creature for the sword."),
                         "targets": ok, "refused": no})
        for t in self.dominated(me):
            ok, no = ms.targets_of(fight, me, lambda x: self.order_target(me, t, x))
            acts.append({"op": "dominate_order", "label": "Dominate Monster: %s, attack" % self.name(t), "time": "free",
                         "ready": bool(ok), "why": "" if ok else "No creature to attack.", "targets": ok, "refused": no,
                         "creature": t})
            acts.append({"op": "dominate_stand", "label": "Dominate Monster: %s, stand down" % self.name(t), "time": "free",
                         "ready": True, "creature": t})
        if self.stop.get(me):
            acts.append({"op": "time_stop_turn", "label": "Time Stop: take your next turn (%d left)" % self.stop[me],
                         "time": "free", "ready": True})

    # ------------------------------------------------------------------ casting
    def cast(self, me, cmd):
        name = cmd["spell"]
        fight, party, sim = self.fight, self.party, self.sim
        s, plan = ms.metamagic(fight, me, name, self.meta_entry(name), cmd)   # Quickened, Distant, Extended, Subtle
        ms.check(self.needs(me, name, cmd.get("slot"), s["time"]))
        c = sim.by_id(me)
        if name == "Storm of Vengeance":
            return self.cast_storm(me, c, s, plan, cmd)
        tids = []
        if s["shape"] == "creature":
            t = cmd.get("target", (cmd.get("targets") or [None])[0])
            if t is None:
                raise ms.EffectError("Choose a creature for %s." % name)
            self.check_target(me, name, s, t)
            tids = [t]
        if name == "Time Stop" and self.stop.get(me):
            raise ms.EffectError("%s is already in a Time Stop." % c["name"])
        dis = []
        if (plan or {}).get("heighten"):
            import live_sorcery
            dis = live_sorcery.of(fight).heightened(me, tids, cmd)
        lv = ms.spend(fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, name, plan, heightened=dis)
        if s.get("concentration"):
            party.start_concentration(me, name)
        held = getattr(self, name.lower().replace(" ", "_"))(me, c, tids, lv, dis)
        if s.get("concentration"):
            if held:
                party.control[me] = {"spell": name, "targets": set(held)}
            else:
                party.holds_no_one(me, name, "affects no one")
            ms.extended(fight, me, name, plan)
        x, y = party.pos(tids[0] if tids else me)
        return {"spell": name, "appearance": s["appearance"], "from": list(party.pos(me)), "targets": list(tids),
                "shape": "circle", "origin": [x, y], "radius_ft": AURA_FT if name == HOLY else 5}

    def arcane_sword(self, me, c, tids, lv, dis):
        t = tids[0]
        self.sword[me] = {"at": self.spot(me, t, None), "serial": self.serial()}
        self.sim.say("dice", "%s casts Arcane Sword (a level %d slot, Concentration): a spectral sword appears at (%d, %d), "
                             "beside %s" % (c["name"], lv, self.sword[me]["at"][0], self.sword[me]["at"][1], self.name(t)))
        self.swing(me, c, t)
        return [me]                                              # the sword is the caster's (held while it concentrates)

    def dominate_monster(self, me, c, tids, lv, dis):
        sim, g, t = self.sim, gm(self.sim), tids[0]
        dc = self.party.spell_dc(c)
        fighting = self.party.side(t) != self.party.side(me)
        sim.say("dice", "%s casts Dominate Monster (a level %d slot, Concentration): DC %d Wisdom save for %s%s" % (
            c["name"], lv, dc, self.name(t), " (Advantage: you are fighting it)" if fighting else ""))
        if g.cond_immune(t, "Charmed"):
            sim.say("dice", "%s is immune to the Charmed condition" % self.name(t))
            return []
        if g.condition_save(t, "wis", dc, "Dominate Monster", adv="you are fighting it" if fighting else False,
                            dis="Heightened Spell" if t in dis else False):
            return []
        g.add(t, "Charmed", "(%s's Dominate Monster: it obeys %s's orders)" % (c["name"], c["name"]), by=me, spell=DOMINATED,
              save="wis", dc=dc)                                 # gm_rules.hurt: damage from another, the save again
        self.order[t], self.master[t] = None, me
        return [t] if info(sim, t, "Charmed") else []

    def holy_aura(self, me, c, tids, lv, dis):
        self.sim.say("dice", "%s casts Holy Aura (a level %d slot, Concentration): a 30-ft aura of holy light; %s's side "
                             "within it has Advantage on saving throws, and attacks against them have Disadvantage" % (
                                 c["name"], lv, c["name"]))
        gm(self.sim).add(me, HOLY, "(30-ft aura: Advantage on saves, attacks against them at Disadvantage)", by=me,
                         spell=HOLY)
        return [me]

    def mind_blank(self, me, c, tids, lv, dis):
        t = tids[0]
        self.sim.say("dice", "%s casts Mind Blank on %s (a level %d slot): Immunity to Psychic damage and the Charmed "
                             "condition for 24 hours" % (c["name"], self.name(t), lv))
        gm(self.sim).add(t, BLANK, "(%s's Mind Blank: Immunity to Psychic damage and Charmed)" % c["name"], by=me,
                         spell="Mind Blank")
        return tids

    def time_stop(self, me, c, tids, lv, dis):
        n = self.sim.rng.randint(1, 4) + 1
        self.stop[me] = n
        self.sim.say("dice", "%s casts Time Stop (a level %d slot): 1d4 + 1 = %d turns in a row; no time passes for the "
                             "others (it ends if %s affects another creature)" % (c["name"], lv, n, c["name"]))
        return []

    # ------------------------------------------------------------------ Arcane Sword
    def spot(self, me, t, start):
        """The square for the sword: within 5 ft of the target (it hovers, so it may share a space), within 90 ft of the
        caster, nearest the caster; from `start`, within 30 ft of it too. None: no such square."""
        party, gr = self.party, gm(self.sim)
        tx, ty = party.pos(t)
        half = (gr.span(t) - 1) / 2
        cx, cy = party.pos(me)
        best = None
        for x in range(int(math.floor(tx - half)) - 1, int(math.ceil(tx + half)) + 2):
            for y in range(int(math.floor(ty - half)) - 1, int(math.ceil(ty + half)) + 2):
                if max(abs(x - tx), abs(y - ty)) - half > 1.01:
                    continue
                if max(abs(x - cx), abs(y - cy)) * self.units() > SPELLS["Arcane Sword"]["range_ft"] + 0.01:
                    continue
                if start and max(abs(x - start[0]), abs(y - start[1])) * self.units() > SWORD_FT + 0.01:
                    continue
                d = max(abs(x - cx), abs(y - cy))
                if best is None or d < best[0]:
                    best = (d, (x, y))
        return best[1] if best else None

    def swing(self, me, c, t):
        sim, party = self.sim, self.party
        mod = int(c.get("spell_mod", 0))
        mode = sim.attack_mode_for(me, t)
        sim.say("dice", "%s's Arcane Sword attacks %s: a melee spell attack, 4d12 + %d Force" % (c["name"], self.name(t), mod))
        res = sim.S.pcAttack(me, t, c.get("spell_atk", 5), 20, "4d12", mod, mode, 0, 4 if me in party.blessed else 0, "",
                             "force", False, True)
        sim.settle()
        return res

    def sword_needs(self, me):
        fight, sw = self.fight, self.sword.get(me) or {}
        return [rq.able(fight, me), rq.bonus_free(fight, me, "the Arcane Sword"),
                rq.need("a later turn", sw.get("serial") != self.serial(),
                        "The sword attacks again on a later turn than the one it was cast.")]

    def sword_target(self, me, t):
        if t == me or self.sim.down(t):
            raise ms.EffectError("Not a creature for the sword.")
        ms.in_range(self.fight, me, t, SPELLS["Arcane Sword"]["range_ft"], "Arcane Sword")
        if self.spot(me, t, self.sword[me]["at"]) is None:
            raise ms.EffectError("The sword moves only 30 ft: %s is too far from it." % self.name(t))
        return t

    # ------------------------------------------------------------------ Dominate Monster
    def dominated(self, me):
        g = gm(self.sim)
        return [t for t, conds in (g.cond.items() if g else ()) if (conds.get("Charmed") or {}).get("spell") == DOMINATED
                and conds["Charmed"].get("by") == me and not self.sim.down(t)]

    def order_target(self, me, t, x):
        if x in (t, me) or self.sim.down(x):
            raise ms.EffectError("Not a creature to attack.")
        return x

    def on_hurt(self, src, tid, amount, kinds=""):
        """Dominate Monster: "Whenever the target takes damage, it repeats the save" (damage from another creature:
        gm_rules.hurt's repeat save for a Charmed creature; from its master: here). Time Stop ends when the caster hurts
        another creature."""
        if not amount:
            return
        if src in self.stop and src != tid and self.stop[src]:
            self.end_stop(src, "%s's damage reached %s" % (self.name(src), self.name(tid)))
        rec = info(self.sim, tid, "Charmed") or {}
        if rec.get("spell") != DOMINATED or self.sim.down(tid):
            return
        g, me = gm(self.sim), rec["by"]
        if src == me and g.condition_save(tid, "wis", rec.get("dc", 10), "Dominate Monster (its master hurt it)",
                                          adv="you are fighting it"):
            g.remove(tid, "Charmed", "saved")

    def plan_filter(self, source, opponents, combatants):
        """A dominated creature the game plays: its order's creature only (an ally of its own too); with no order, no
        one on its master's side."""
        cid = str(source).split(".")[-1]
        rec = info(self.sim, cid, "Charmed") or {}
        if rec.get("spell") != DOMINATED:
            return opponents
        want = self.order.get(cid)
        if want and not self.sim.down(want):
            return [p for p in combatants if str(p).split(".")[-1] == want]
        side = self.party.side(rec["by"])
        return [p for p in opponents if self.party.side(str(p).split(".")[-1]) != side]

    # ------------------------------------------------------------------ Holy Aura
    def in_aura(self, t):
        """The caster whose Holy Aura covers t now (t on its side within 30 ft), or None."""
        party = self.party
        if party is None:
            return None
        for o in self.sim.sc["combatants"]:
            q = o["id"]
            if party.concentrates(q) == HOLY and info(self.sim, q, HOLY) and party.side(q) == party.side(t) \
                    and (q == t or party.dist(q, t) <= AURA_FT + 0.01):
                return q
        return None

    def save_mod(self, t, ability):
        return (0, "Holy Aura") if self.in_aura(t) else (0, "")

    def attack_mode(self, src, tgt):
        if self.party.side(src) != self.party.side(tgt) and self.in_aura(tgt):
            return False, True, "[Holy Aura]"
        return False, False, ""

    def hit_redirect(self, src, tgt):
        """Holy Aura: a Fiend's or an Undead's hit on a creature in it; once the attack is over, if it was a melee one,
        the attacker saves (Constitution) or is Blinded."""
        q = self.in_aura(tgt)
        kind = str(self.sim.by_id(src).get("type") or "").lower()
        if q and re.search(r"fiend|undead", kind):
            self.sim.later.append(lambda: self.holy_blind(src, q))
        return ""

    def holy_blind(self, src, q):
        sim, g = self.sim, gm(self.sim)
        last = sim.S.lastAttack or {}
        if last.get("ranged") or last.get("src") != src or sim.down(src) or g.has(src, "Blinded"):
            return
        dc = self.party.spell_dc(sim.by_id(q))
        if g.condition_save(src, "con", dc, "Holy Aura (a melee hit on its holy light)"):
            return
        g.add(src, "Blinded", "(%s's Holy Aura, until the end of its next turn)" % self.name(q), by=q)
        self.blind[src] = 2 if sim.S.num(src, "active") == 1 else 1

    # ------------------------------------------------------------------ Mind Blank
    def rule_immune(self, t, name):
        return "Mind Blank" if name.lower() == "charmed" and info(self.sim, t, BLANK) else ""

    # ------------------------------------------------------------------ Time Stop
    def next_turn(self, me):
        """Time Stop: the caster's next turn in a row (a new turn: its Action, Bonus Action, Reaction and movement, a
        spell slot again); the round doesn't move on."""
        fight, sim, party = self.fight, self.sim, self.party
        if not self.stop.get(me):
            raise ms.EffectError("%s has no Time Stop turn left." % self.name(me))
        self.stop[me] -= 1
        S = sim.S
        S.turnSerial += 1
        S.setValue(me, "reaction", 0)
        party.turn_start(me)
        c = sim.by_id(me)
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        fight.turn_state.update({"movement": speed, "speed": speed, "action_used": False, "attacks_left": 0,
                                 "sneak_used": False, "attacks_made": 0})
        ms.live_turn_start(fight, me)
        sim.say("turn", "Time Stop: %s takes another turn (%d left); no time passes for the others" % (c["name"], self.stop[me]))
        return {"ok": True, "result": "time_stop_turn", "left": self.stop[me]}

    def end_stop(self, me, why):
        if self.stop.pop(me, None):
            self.sim.say("dice", "%s's Time Stop ends: %s" % (self.name(me), why))

    # ------------------------------------------------------------------ Storm of Vengeance
    def cast_storm(self, me, c, s, plan, cmd):
        fight, party, sim = self.fight, self.party, self.sim
        x, y = ms.square(cmd, "Storm of Vengeance")
        ms.point_in_range(fight, me, x, y, s["range_ft"], "Storm of Vengeance")
        lv = ms.spend(fight, me, s["time"], s["level"], cmd.get("slot"))
        ms.pay_metamagic(fight, me, "Storm of Vengeance", plan)
        party.start_concentration(me, "Storm of Vengeance")
        layers = getattr(sim, "layers", None)
        if layers is not None:
            layers.sweep()
            layers.n += 1
            n = layers.n
        else:
            n = max([int(z.get("n") or 0) for z in sim.env.zones] + [0]) + 1
        r = s["radius_ft"] / self.units()
        z = {"id": "storm-of-vengeance-%d" % n, "n": n, "spell": "Storm of Vengeance", "owner": me, "circle": [x, y, r],
             "origin": [x, y], "radius_ft": s["radius_ft"], "appearance": "lightning", "layer": "air", "darkness": False,
             "stinking": False, "kind": "spell_area", "level": "none", "veil": "none", "cast_round": self.rnd(),
             "ends_round": self.rnd() + s["rounds"] * (2 if plan and "Extended Spell" in plan["metas"] else 1),
             "rect": [int(math.floor(x - r)), int(math.floor(y - r)), int(math.ceil(x + r)), int(math.ceil(y + r))]}
        sim.env.zones.append(z)
        party.__dict__.setdefault("gm_concentration", {})[me] = "Storm of Vengeance"
        party.__dict__.setdefault("layer_zone", {})[me] = n
        self.storm[me] = {"zone": z, "round": self.rnd(), "done": self.rnd()}
        under = self.under(z)
        dc = party.spell_dc(c)
        sim.say("dice", "%s casts Storm of Vengeance (a level %d slot, Concentration): a storm cloud of 300-ft radius over "
                        "(%d, %d); DC %d Constitution save for each creature under it: %s" % (
                            c["name"], lv, x, y, dc, ", ".join(self.name(t) for t in under) or "none"))
        g, held = gm(sim), []
        for t in under:
            if g.condition_save(t, "con", dc, "Storm of Vengeance"):
                continue
            dmg = _roll(sim.rng, "2d6")
            sim.say("dice", "%s fails: 2d6 = %d Thunder, and Deafened" % (self.name(t), dmg))
            sim.S.pcDamage(me, t, "", dmg, False, "thunder")
            sim.settle(0.2)
            if not sim.down(t):
                g.add(t, "Deafened", "(%s's Storm of Vengeance)" % c["name"], by=me, spell="Storm of Vengeance")
                held.append(t)
        if held:
            party.control[me] = {"spell": "Storm of Vengeance", "targets": set(held)}
        ms.extended(fight, me, "Storm of Vengeance", plan)
        return {"spell": "Storm of Vengeance", "appearance": "lightning", "from": list(party.pos(me)), "targets": under,
                "shape": "circle", "origin": [x, y], "radius_ft": s["radius_ft"], "lasting": True}

    def alive_storm(self, me):
        st = self.storm.get(me)
        if st and (self.party.concentrates(me) != "Storm of Vengeance" or st["zone"] not in self.sim.env.zones):
            self.storm.pop(me, None)
            return None
        return st

    def under(self, z):
        cx, cy, r = z["circle"]
        return [o["id"] for o in self.sim.sc["combatants"] if not self.sim.down(o["id"])
                and math.hypot(self.party.pos(o["id"])[0] - cx, self.party.pos(o["id"])[1] - cy) <= r + 0.01]

    def storm_turn(self, me):
        """The start of each of the caster's later turns: the storm's turn 2 to 10 (by the rounds since it was cast)."""
        st = self.alive_storm(me)
        if not st or st["done"] >= self.rnd():
            return
        st["done"] = self.rnd()
        k = self.rnd() - st["round"] + 1
        if k < 2 or k > STORM_TURNS:
            return
        sim, z, c = self.sim, st["zone"], self.sim.by_id(me)
        under = self.under(z)
        if k == 3:
            dc = self.party.spell_dc(c)
            cx, cy = z["origin"]
            foes = sorted([t for t in under if self.party.side(t) not in (self.party.side(me), "neutral")],
                          key=lambda t: math.hypot(self.party.pos(t)[0] - cx, self.party.pos(t)[1] - cy))[:6]
            sim.say("dice", "%s's Storm of Vengeance, turn 3: lightning bolts strike %s (DC %d Dexterity save, 10d6 "
                            "Lightning, half on a success)" % (c["name"], ", ".join(self.name(t) for t in foes) or "no one", dc))
            for t in foes:
                dmg = _roll(sim.rng, "10d6")
                ok = gm(sim).condition_save(t, "dex", dc, "Storm of Vengeance (10d6 = %d Lightning, half on a success)" % dmg)
                sim.S.pcDamage(me, t, "", dmg // 2 if ok else dmg, False, "lightning")
                sim.settle(0.2)
            return
        dice, kind, what = {2: ("4d6", "acid", "acidic rain"), 4: ("2d6", "bludgeoning", "hailstones")}.get(
            k, ("1d6", "cold", "gusts and freezing rain"))
        if k == 5:
            z.update(kind="obscured", level="heavy", veil="heavy")   # Heavily Obscured until the spell ends
        sim.say("dice", "%s's Storm of Vengeance, turn %d: %s, %s %s on each creature under the cloud%s" % (
            c["name"], k, what, dice, kind.capitalize(), "; the area is Difficult Terrain and Heavily Obscured" if k >= 5 else ""))
        for t in under:
            dmg = _roll(sim.rng, dice)
            sim.say("dice", "%s takes %s = %d %s" % (self.name(t), dice, dmg, kind.capitalize()))
            sim.S.pcDamage(me, t, "", dmg, False, kind)
            sim.settle(0.2)

    def difficult_cells(self, me=None):
        out = set()
        for caster in list(self.storm):
            st = self.alive_storm(caster)
            if not st or self.rnd() - st["round"] + 1 < 5:
                continue
            import sim_messages
            board = sim_messages.map_part(self.sim.sc)
            cx, cy, r = st["zone"]["circle"]
            out |= {(x, y) for x in range(board["cols"]) for y in range(board["rows"]) if math.hypot(x - cx, y - cy) <= r + 0.01}
        return out

    # ------------------------------------------------------------------ actions (more_spells.act)
    def act(self, me, cmd):
        op, fight, sim = cmd["op"], self.fight, self.sim
        if op == "time_stop_turn":
            return self.next_turn(me)
        if op in ("dominate_order", "dominate_stand"):
            t = cmd.get("creature")
            mine = self.dominated(me)
            if t is None and len(mine) == 1:
                t = mine[0]
            if t not in mine:
                raise ms.EffectError("%s dominates no such creature." % self.name(me))
            if op == "dominate_stand":
                self.order[t] = None
                sim.say("turn", "%s orders %s (telepathy, no action): stand down" % (self.name(me), self.name(t)))
                return {"ok": True, "result": op}
            x = cmd.get("target")
            if x is None:
                raise ms.EffectError("Pick the creature it attacks.")
            self.order_target(me, t, x)
            self.order[t] = x
            sim.say("turn", "%s orders %s (telepathy, no action): attack %s" % (self.name(me), self.name(t), self.name(x)))
            return {"ok": True, "result": op}
        # arcane_sword: the Bonus Action, the sword moves up to 30 ft and attacks again
        if me not in self.sword or self.party.concentrates(me) != "Arcane Sword":
            raise ms.EffectError("%s holds no Arcane Sword." % self.name(me))
        ms.check(self.sword_needs(me))
        t = cmd.get("target")
        if t is None:
            raise ms.EffectError("Pick the creature the sword attacks.")
        self.sword_target(me, t)
        c = sim.by_id(me)
        ref = getattr(fight, "referee", None)
        import contextlib
        with (ref.watch(me, "Arcane Sword", {"target": t, "free": "the sword's attack on a later turn", "time": "bonus"})
              if ref else contextlib.nullcontext()):
            self.party.use_bonus(me)
            at = self.spot(me, t, self.sword[me]["at"])
            self.sword[me] = {"at": at, "serial": self.serial()}
            sim.say("turn", "%s moves the Arcane Sword to (%d, %d) (Bonus Action)" % (c["name"], at[0], at[1]))
            res = self.swing(me, c, t)
        return {"ok": True, "result": res}

    # ------------------------------------------------------------------ what the conditions change
    def condition_changed(self, t, name):
        sim, S = self.sim, self.sim.S
        rec = info(sim, t, name)
        if name == BLANK:
            c = sim.by_id(t)
            if rec:
                was = str(c.get("damageimmunities") or "")
                self.immune[t] = was
                dmg, _, conds = was.partition(";")
                now = ", ".join(x for x in (dmg.strip(), "psychic") if x) + (";" + conds if conds else "")
                c["damageimmunities"] = now
                S.setField(t, "damageimmunities", now)
                if gm(sim).has(t, "Charmed"):
                    gm(sim).remove(t, "Charmed", "Mind Blank: Immunity to the Charmed condition")
            elif t in self.immune:
                c["damageimmunities"] = self.immune.pop(t)
                S.setField(t, "damageimmunities", c["damageimmunities"])
        elif name == "Charmed" and not rec and t in self.master:   # Dominate Monster ends on it
            self.order.pop(t, None)
            self.party.spell_target_gone(self.master.pop(t), t)
        rec = rec or {}
        by = rec.get("by")
        if by in self.stop and by != t and self.stop[by]:            # Time Stop: a condition it gave another creature
            self.end_stop(by, "%s now has the %s condition" % (self.name(t), name))

    # ------------------------------------------------------------------ turns
    def live_turn_start(self, me):
        self.storm_turn(me)

    def creature_turn_start(self, me):
        self.storm_turn(me)
        return ""

    def turn_ended(self, me):
        if self.stop.get(me):
            self.end_stop(me, "the turn ended with %d turn%s left" % (self.stop[me], "" if self.stop[me] == 1 else "s"))
        self.stop.pop(me, None)
        if me in self.blind:
            self.blind[me] -= 1
            if self.blind[me] <= 0:
                self.blind.pop(me)
                if gm(self.sim).has(me, "Blinded"):
                    gm(self.sim).remove(me, "Blinded", "Holy Aura's blindness ends")


# ---------------------------------------------------------------------- the hooks (sim/more_spells.py)
def _st(sim):
    return getattr(sim, "_spells_7_9", None)


def condition_changed(sim, t, name):
    st = _st(sim)
    if st:
        st.condition_changed(t, name)


def live_turn_start(fight, me):
    st = _st(fight.sim)
    if st:
        st.live_turn_start(me)


def creature_turn_start(sim, me):
    st = _st(sim)
    return st.creature_turn_start(me) if st else ""


def turn_ended(sim, me):
    st = _st(sim)
    if st:
        st.turn_ended(me)


def on_hurt(sim, src, tid, amount, kinds=""):
    st = _st(sim)
    if st:
        st.on_hurt(src, tid, amount, kinds)


def save_mod(sim, t, ability):
    st = _st(sim)
    return st.save_mod(t, ability) if st else (0, "")


def attack_mode(sim, src, tgt):
    st = _st(sim)
    return st.attack_mode(src, tgt) if st else (False, False, "")


def rule_immune(sim, t, name):
    st = _st(sim)
    return st.rule_immune(t, name) if st else ""


def hit_redirect(sim, src, tgt):
    st = _st(sim)
    return st.hit_redirect(src, tgt) if st else ""


def difficult_cells(sim, me=None):
    st = _st(sim)
    return st.difficult_cells(me) if st else set()


def adjust_offers(fight, me, out):
    st = _st(fight.sim)
    if st:
        st.adjust_offers(me, out)


def plan_filter(sim, source, me, opponents, combatants):
    st = _st(sim)
    return st.plan_filter(source, opponents, combatants) if st else opponents
