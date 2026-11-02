"""SIM-MECHANICS-01 (b), 2026-10-18: monster saving-throw effects, played by the simulator as the GM (simulator only;
GM decision 2026-10-18: "Do it in the simulator only for now, as a scripted GM rule; leave the live bridge alone").

The live bridge does not offer Recharge actions or areas; in FG the GM plays them by hand. Here the simulated GM:
- at the start of a creature's turn (before FG tells the bridge), rolls Recharge for a spent breath (1d6, regained on
  the stat block's numbers) and, while it is ready, uses it in place of the creature's turn when the best 15-ft Cone
  from where the creature stands catches at least one character and no ally the damage would harm;
- when such a creature drops to 0 hit points, resolves its Death Burst on every creature in the Emanation.
Area damage is rolled once (SRD 5.2.1); each creature saves on its own: d20 + its save (Danger Sense, Aura of
Protection, Bless, Evasion as the SRD gives them); the damage goes through the fake FG, so Resistance and Immunity
apply. Numbers are the SRD 5.2.1 stat blocks (DNDSRD521BESTIARY); test_gm_rules checks them against the records.
Conditions (SIM-MECHANICS-01 c): _Conditions below."""
import contextlib, math, re

import party as party_mod

SAVE_EFFECTS = {
    "Magma Mephit": {
        "breath": {"name": "Fire Breath", "recharge": 6, "save": "dex", "dc": 11, "shape": "cone", "size": 15,
                   "dmg": "2d6", "type": "fire"},
        "death_burst": {"name": "Death Burst", "save": "dex", "dc": 11, "shape": "emanation", "size": 5,
                        "dmg": "2d6", "type": "fire"}},
    "Steam Mephit": {
        "breath": {"name": "Steam Breath", "recharge": 6, "save": "con", "dc": 10, "shape": "cone", "size": 15,
                   "dmg": "2d4", "type": "fire", "slow": 10},
        "death_burst": {"name": "Death Burst", "save": "dex", "dc": 10, "shape": "emanation", "size": 5,
                        "dmg": "2d4", "type": "fire"}},
    "Magmin": {
        "death_burst": {"name": "Death Burst", "save": "dex", "dc": 11, "shape": "emanation", "size": 10,
                        "dmg": "2d6", "type": "fire"}},
}
ABILITY = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom",
           "cha": "Charisma"}


def dice(rng, expr):
    """'2d4+4', '1d4-1', '3d8' -> total (THREAT-02: the library's damage, minus modifiers too)."""
    m = re.fullmatch(r"(\d+)d(\d+)([+-]\d+)?", str(expr).replace(" ", ""))
    if not m:
        return party_mod.roll(rng, expr)
    return max(0, sum(rng.randint(1, int(m.group(2))) for _ in range(int(m.group(1)))) + int(m.group(3) or 0))


def area_damage(dmg, saved, evasion):
    """Half on a success; Evasion (Rogue 7): none on a success, half on a failure."""
    if evasion:
        return 0 if saved else dmg // 2
    return dmg // 2 if saved else dmg


# ---------------------------------------------------------------------- SIM-MECHANICS-01 (c), 2026-10-18: conditions
# Riders on a monster's hit (SRD 5.2.1 stat blocks; test_conditions checks them against DNDSRD521BESTIARY)
HIT_RIDERS = {
    ("Giant Crab", "Claw"): {"condition": "Grappled", "dc": 11, "max": 2, "max_size": "medium", "range": 5},
    ("Earth Elemental", "Rock Launch"): {"condition": "Prone", "max_size": "large"},
}
# Actions the GM takes at the start of the creature's turn: in place of its turn, or (in_multiattack) before its attacks
TURN_ACTIONS = {
    "Harpy": {"name": "Luring Song", "save": "wis", "dc": 11, "size": 300, "condition": "Charmed",
              "con_save": 1},          # Con 12; the song lasts while the harpy concentrates
    "Doppelganger": {"name": "Unsettling Visage", "recharge": 6, "save": "wis", "dc": 12, "size": 15,
                     "condition": "Frightened", "in_multiattack": True},   # "two Slam attacks and uses Unsettling
                                                                           # Visage if available": its attacks follow
}
SIZES = ["tiny", "small", "medium", "large", "huge", "gargantuan"]
# SIM-MECHANICS-01 (e): conditions that include Incapacitated (SRD 5.2.1); each ends Concentration
INCAPACITATING = ("Incapacitated", "Paralyzed", "Petrified", "Stunned", "Unconscious")
# SIM-MECHANICS-01 (f): attack rolls against them have Advantage; they fail Strength and Dexterity saves (SRD 5.2.1)
HELPLESS = ("Paralyzed", "Petrified", "Stunned", "Unconscious")
CONDITION_NOTES = {"Grappled": "Speed 0; Disadvantage on attacks against anyone but the grappler",
                   "Prone": "Disadvantage on its attacks; attacks within 5 ft have Advantage, from farther Disadvantage",
                   "Charmed": "can't attack its charmer or aim harmful effects at it",   # SPELL-EFFECTS-01 (was the harpy's song)
                   "Incapacitated": "no action, Bonus Action or Reaction; Concentration broken",
                   "Frightened": "Disadvantage on attacks while it sees the source; will not move closer",
                   "Slowed": "Speed reduced",
                   "Burning": "1d4 Fire at the start of each of its turns; an action and Prone put it out",
                   "Restrained": "Speed 0; attacks against it have Advantage, its attacks Disadvantage",
                   "Invisible": "unseen: attacks against it have Disadvantage, its attacks Advantage, unless the other can see it",
                   "Poisoned": "Disadvantage on attack rolls and ability checks",
                   "Blinded": "Disadvantage on its attacks; attacks against it have Advantage",
                   "Paralyzed": "Incapacitated, Speed 0; fails Strength and Dexterity saves; attacks against it have Advantage",
                   "Stunned": "Incapacitated; fails Strength and Dexterity saves; attacks against it have Advantage",
                   "Unconscious": "Incapacitated, Prone; fails Strength and Dexterity saves; attacks against it have Advantage",
                   "Petrified": "Incapacitated, Speed 0; fails Strength and Dexterity saves; attacks against it have Advantage"}
# THREAT-02 step 2: conditions that hold a creature in place (Speed 0)
HELD = ("Grappled", "Restrained", "Paralyzed", "Petrified", "Stunned", "Unconscious")


def size_of(c):
    s = str(c.get("size") or "").lower()
    if s in SIZES:
        return s
    sq = max(1, int(round(float(c.get("space") or 5) / 5)))
    return {1: "medium", 2: "large", 3: "huge"}.get(sq, "gargantuan")


class _Conditions:
    """Mixed into GmRules: conditions on creatures, mirrored as Combat Tracker effects (as FG shows them)."""

    def _init_conditions(self):
        self.cond = {}               # creature -> {condition: info}
        self.singing = set()         # harpies whose Luring Song lasts
        self.song_immune = {}        # harpy -> creatures that saved

    # ------------------------------------------------------------ bookkeeping
    def has(self, t, name):
        info = self.cond.get(t, {}).get(name)
        if info and name == "Grappled":
            g = info["by"]
            if self.sim.down(g) or self.incapacitated(g) or self.ft_between(g, t) > info.get("range", 5):
                self.remove(t, "Grappled", "the grapple ends")
                return False
        return bool(info)

    def add(self, t, name, why="", **info):
        if self.has(t, name):
            return
        feature = self.rule_immune(t, name)
        if feature:                                             # Mindless Rage, Aura of Devotion
            self.sim.say("dice", "%s is immune to the %s condition (%s)" % (self.sim.by_id(t)["name"], name, feature))
            return
        self.cond.setdefault(t, {})[name] = info or {"why": why}   # 2026-10-20: never an empty (falsy) record
        self.sim.S.addEffect(t, name, True)
        self.sim.say("dice", "%s has the %s condition%s (%s)" % (self.sim.by_id(t)["name"], name,
                     " " + why if why else "", CONDITION_NOTES.get(name, name)))
        if name == "Charmed" and info.get("song"):
            self.add(t, "Incapacitated", "while Charmed by the song", by=info["by"])
        if name in INCAPACITATING and self.p:                   # SIM-MECHANICS-01 (e): these include Incapacitated
            self.p.lose_concentration(t, name)
        env = getattr(self.sim, "env", None)
        if env and name in ("Prone", "Incapacitated", "Grappled"):
            self.sim.later.append(lambda: env.lost_flight(t))   # SIM-ENV-02: a flier over a drop falls
        if env and name == "Prone":                              # SIM-ENV-04: Falling Off
            if env.rider_of(t) is not None:                     # MAP-LAYERS-01: an independent mount too
                self.sim.later.append(lambda: env.rider_check(t, "its mount is knocked Prone"))
            elif env.mount_of(t) and info.get("by") != t:
                self.sim.later.append(lambda: env.rider_check(env.mount_of(t), "it is knocked Prone"))
        import more_spells                                       # SPELL-EFFECTS-01: Haste's AC and Speed follow it
        more_spells.condition_changed(self.sim, t, name)

    def remove(self, t, name, why):
        info = self.cond.get(t, {}).pop(name, None)
        if info is None:
            return
        if name == "Grappled" and info.get("whelm"):
            self.sim.S.removeEffect(t, name)
            self.sim.say("dice", "%s is no longer %s (%s)" % (self.sim.by_id(t)["name"], name, why))
            self.remove(t, "Restrained", why)
            return
        self.sim.S.removeEffect(t, name)
        self.sim.say("dice", "%s is no longer %s (%s)" % (self.sim.by_id(t)["name"], name, why))
        if name == "Charmed" and info.get("song"):
            self.remove(t, "Incapacitated", why)
        import more_spells                                       # SPELL-EFFECTS-01: Haste's lethargy when it ends
        more_spells.condition_changed(self.sim, t, name)

    def incapacitated(self, t):
        return any(self.cond.get(t, {}).get(n) for n in INCAPACITATING)

    def auto_fail(self, t, ability):
        """SRD 5.2.1 Paralyzed, Petrified, Stunned, Unconscious: automatic failure on Strength and Dexterity saves."""
        return ability[:3] in ("str", "dex") and any(self.cond.get(t, {}).get(n) for n in HELPLESS)

    def cond_immune(self, t, name):
        """Condition Immunities from the SRD record (FG keeps them after the ";" of the damage immunities), and the ones a
        class feature gives for now (rule_immune)."""
        parts = str(self.sim.by_id(t).get("damageimmunities") or "").split(";")
        return (len(parts) > 1 and name.lower() in parts[1].lower()) or bool(self.rule_immune(t, name))

    def rule_immune(self, t, name):
        """GM 2026-10-23 (the test heroes to the full SRD 5.2.1): a condition a class feature keeps off right now, by name
        of the feature, or "". Mindless Rage (Berserker 6): Charmed and Frightened while the Rage is active. Aura of
        Devotion (Devotion Paladin 7): Charmed, for the Paladin and allies within her Aura of Protection (10 ft) while she
        is not Incapacitated."""
        n, p = name.lower(), self.p
        if n in ("charmed", "frightened") and self.sim.by_id(t).get("mindless_rage") and p and t in getattr(p, "raging", {}):
            return "Mindless Rage"
        if n == "charmed" and p:
            import high_levels                                   # Aura Expansion (Paladin 18): 30 ft
            for q in getattr(p, "aura_ids", ()):
                pal = self.sim.by_id(q)
                if pal.get("aura_devotion") and p.side(q) == p.side(t) and not self.sim.down(q)                         and not self.incapacitated(q) and (q == t or p.dist(q, t) <= high_levels.aura_ft(pal)):
                    return "Aura of Devotion"
        if n == "frightened" and p:                              # GM 2026-10-26: Aura of Courage (Paladin 10)
            import high_levels
            if high_levels.courage(self, t):
                return "Aura of Courage"
        import more_spells                                       # SPELLS-7-9: Mind Blank (Charmed)
        return more_spells.rule_immune(self.sim, t, name)

    def own_luck(self, t, total, dc, label):
        """Dark One's Own Luck (Fiend Warlock 6): after seeing a failed saving throw, +1d10 (Charisma modifier uses per
        Long Rest, once per roll). Used when the d10 can still turn the failure into a success. -> what it adds."""
        c = self.sim.by_id(t)
        if total >= dc or not c.get("own_luck") or dc - total > 10:
            return 0
        luck = getattr(self, "luck", None)
        if luck is None:
            luck = self.luck = {}
        left = luck.setdefault(t, int(c["own_luck"]))
        if left <= 0:
            return 0
        luck[t] = left - 1
        d10 = self.sim.rng.randint(1, 10)
        self.sim.say("dice", "%s calls on Dark One's Own Luck (%s): +1d10 = %d (%d use%s left)" % (
            c["name"], label, d10, luck[t], "" if luck[t] == 1 else "s"))
        return d10

    def antitoxin(self, t, condition):
        """Antitoxin (SRD 5.2.1): Advantage on saves to avoid or end the Poisoned condition for 1 hour."""
        import live_items
        return "Antitoxin" if condition == "Poisoned" and live_items.antitoxin_on(self.p, t) else False

    def indomitable(self, t, total, dc, label, bonus):
        """Indomitable (Fighter 9; SRD 5.2.1): a failed saving throw rolled again with a bonus equal to the Fighter
        level, the new roll kept (1 use per Long Rest; 2 at 13, 3 at 17). bonus: the save's own bonus. -> the total."""
        c = self.sim.by_id(t)
        import martial_high                                      # MARTIAL-HIGH: Heroic Inspiration, Stroke of Luck
        total = martial_high.luck_save(self, t, total, dc, label, bonus)
        total = __import__("epic_boons").fate_save(self, t, total, dc, label)   # EPIC-BOONS-01: Boon of Fate
        if total < dc and c.get("disciplined_survivor"):         # GM 2026-10-28: Disciplined Survivor (Monk 14)
            import monk
            total = monk.survivor(self, t, total, dc, label, bonus)
        if total >= dc or not c.get("indomitable"):
            return total
        used = self.__dict__.setdefault("indomitable_left", {})
        left = used.setdefault(t, int(c["indomitable"]))
        if left <= 0:
            return total
        used[t] = left - 1
        d20, lv = self.sim.rng.randint(1, 20), int(c.get("level", 1) or 1)
        new = d20 + bonus + lv
        self.sim.say("dice", "%s uses Indomitable (%s): the save again, d20 %d %+d + %d (Fighter level) = %d (%d use%s left)" % (
            c["name"], label, d20, bonus, lv, new, used[t], "" if used[t] == 1 else "s"))
        return new

    # ------------------------------------------------------------ SIM-MECHANICS-01 (f): the party's control spells
    def spell_conditions(self, t, caster=None):
        """{condition: info} on t that a party spell holds (info["spell"]), optionally only `caster`'s."""
        return {n: i for n, i in self.cond.get(t, {}).items() if i.get("spell") and (caster is None or i.get("by") == caster)}

    def end_spell_on(self, t, caster, why):
        for n in list(self.spell_conditions(t, caster)):
            self.remove(t, n, why)
        if self.p:
            self.p.spell_target_gone(caster, t)

    def end_spell(self, caster, why, spell=None):
        """The caster's Concentration ended: its spell's conditions end on everyone (spell: only that spell's; a
        non-Concentration spell of the same caster, Blindness/Deafness, keeps going: SPELL-CASTER-01)."""
        for t in list(self.cond):
            for n, info in list(self.spell_conditions(t, caster).items()):
                if spell is None or info.get("spell") == spell:
                    self.remove(t, n, why)

    def end_one_spell_on(self, t, caster, spell, why):
        """SPELL-CASTER-01: one spell ends on one creature (its save, its damage), the caster's others stay."""
        for n, info in list(self.spell_conditions(t, caster).items()):
            if info.get("spell") == spell:
                self.remove(t, n, why)
        if self.p:
            self.p.spell_target_gone(caster, t)

    def spell_turn_ended(self, me):
        """End of an affected creature's turn: Sleep's second save, Hideous Laughter's and Hold Person's repeat saves."""
        for name, info in list(self.spell_conditions(me).items()):
            if name not in self.cond.get(me, {}):
                continue
            spell, caster = info["spell"], info["by"]
            if spell == "Sleep" and name == "Incapacitated" and info.get("stage") == 1:
                if self.condition_save(me, "wis", info["dc"], "Sleep (end of its turn)", dis=info.get("dis", False)):
                    self.end_spell_on(me, caster, "saved against Sleep")
                else:
                    info["stage"] = 2
                    for n in ("Unconscious", "Prone"):
                        self.add(me, n, "(%s's Sleep)" % self.sim.by_id(caster)["name"], by=caster, spell="Sleep")
            elif spell in ("Hideous Laughter", "Hold Person") and name == ("Incapacitated" if spell == "Hideous Laughter" else "Paralyzed"):
                if self.condition_save(me, "wis", info["dc"], "%s (end of its turn)" % spell, dis=info.get("dis", False)):
                    self.end_spell_on(me, caster, "saved against %s" % spell)
            elif info.get("repeat_spell"):                       # SPELL-CASTER-01: Blindness/Deafness, read from its text
                if self.condition_save(me, info["save"], info["dc"], "%s (end of its turn)" % spell, dis=info.get("dis", False)):
                    self.end_one_spell_on(me, caster, spell, "saved against %s" % spell)

    SHAKE_SPELLS = ("Sleep", "Hypnotic Pattern")

    def shakeable(self, t):
        """GM 2026-10-25 (ruling L4): what an action to shake it awake would end, or None. SRD 5.2.1: Spider's Sting and
        Essence of Ether ("the creature wakes up if it takes damage or if another creature takes an action to shake it
        awake"); Sleep ("someone within 5 feet of it takes an action to shake it out of the spell's effect"); Hypnotic
        Pattern ("someone else uses an action to shake the creature out of its stupor")."""
        info = self.cond.get(t, {}).get("Unconscious")
        if info and info.get("shake"):
            return "the poison's sleep"
        for name, info in self.spell_conditions(t).items():
            if info.get("spell") in self.SHAKE_SPELLS:
                return info["spell"]
        return None

    def shake_awake(self, t, by):
        """An action to shake t awake: ends what shakeable(t) names."""
        what = self.shakeable(t)
        who = self.sim.by_id(by)["name"]
        if what == "the poison's sleep":
            self.remove(t, "Unconscious", "%s shakes it awake (an action)" % who)
        elif what:
            caster = next(i["by"] for n, i in self.spell_conditions(t).items() if i.get("spell") == what)
            self.end_one_spell_on(t, caster, what, "%s shakes it out of %s (an action)" % (who, what))
        return what

    def spell_hurt(self, tgt, src=None):
        """Damage: Sleep ends on the creature; Hideous Laughter's save again, with Advantage. GM 2026-10-23: a poison's
        sleep (Essence of Ether, Spider's Sting, Oil of Taggit) ends too: the creature wakes."""
        info = self.cond.get(tgt, {}).get("Unconscious")
        if info and info.get("wakes"):
            self.remove(tgt, "Unconscious", "the damage wakes it")
        for name, info in list(self.spell_conditions(tgt).items()):
            if name not in self.cond.get(tgt, {}):
                continue
            if info["spell"] in ("Sleep", "Turn Undead"):          # (f) slice 4: Turn Undead ends on damage too
                self.end_spell_on(tgt, info["by"], "the damage ends %s" % info["spell"])
            elif info.get("ends_on_hurt"):                       # SPELL-CASTER-01: Hypnotic Pattern
                self.end_one_spell_on(tgt, info["by"], info["spell"], "the damage ends %s" % info["spell"])
            elif info["spell"] == "Hideous Laughter" and name == "Incapacitated":
                d20 = max(self.sim.rng.randint(1, 20), self.sim.rng.randint(1, 20))
                bonus = self.sim.by_id(tgt).get("wis_save", 0)
                ok = d20 + bonus >= info["dc"]
                self.sim.say("dice", "%s Wisdom save against Hideous Laughter (damaged, Advantage): d20 %d %+d = %d vs DC %d -> %s" % (
                    self.sim.by_id(tgt)["name"], d20, bonus, d20 + bonus, info["dc"], "success" if ok else "failure"))
                if ok:
                    self.end_spell_on(tgt, info["by"], "saved against Hideous Laughter")

    def by(self, t, name):
        return (self.cond.get(t, {}).get(name) or {}).get("by")

    # ------------------------------------------------------------ attack rolls (the fake FG asks for every attack)
    def cond_mode(self, src, tgt, rng="", dmgtype="", spell=False, peek=False):
        """(Advantage, Disadvantage, notes, modifier) from conditions, as FG's 5E modAttack reads condition effects, and
        from the environment (SIM-ENV-01: underwater weapons, sunlight, Exhaustion). peek (HINTS-01 H5: the attack hint):
        Help is not used up, and a fifth item, why, gives each Advantage or Disadvantage note its side
        (fight_state.roll_mode)."""
        adv = dis = False
        notes, why = [], []

        def side(a, d, more):                                    # a hook's notes: one side, or "either" when it gave both
            why.extend(("either" if a and d else "adv" if a else "dis", n) for n in more if a or d)
        if self.has(src, "Prone"):
            dis = True; notes.append("[attacker Prone]"); why.append(("dis", "[attacker Prone]"))
        if self.has(tgt, "Prone"):
            if self.ft_between(src, tgt) <= 5:
                adv = True; notes.append("[target Prone, within 5 ft]"); why.append(("adv", "[target Prone, within 5 ft]"))
            else:
                dis = True; notes.append("[target Prone, beyond 5 ft]"); why.append(("dis", "[target Prone, beyond 5 ft]"))
        if self.has(src, "Grappled") and self.by(src, "Grappled") != tgt:
            dis = True; notes.append("[Grappled: not the grappler]"); why.append(("dis", "[Grappled: not the grappler]"))
        if self.cond.get(tgt, {}).get("Restrained"):                # SRD 5.2.1 Restrained
            adv = True; notes.append("[target Restrained]"); why.append(("adv", "[target Restrained]"))
        if self.cond.get(src, {}).get("Restrained"):
            dis = True; notes.append("[attacker Restrained]"); why.append(("dis", "[attacker Restrained]"))
        tc = self.sim.by_id(tgt) or {}                         # LIVE-PLAY-01 slice 3: Dodge (SRD 5.2.1)
        if tc.get("dodging") and not self.incapacitated(tgt) and tc.get("_speed_now", 1) != 0 and self.sim.sees(tgt, src):
            dis = True; notes.append("[Dodge]"); why.append(("dis", "[Dodge]"))
        helper = getattr(self, "helped", {}).get(tgt)            # LIVE-PLAY-01 slice 4: Help (SRD 5.2.1)
        if helper and helper != src and (self.sim.by_id(src) or {}).get("side") == (self.sim.by_id(helper) or {}).get("side"):
            adv = True; notes.append("[Help]"); why.append(("adv", "[Help]"))
            if not peek:
                self.helped.pop(tgt, None)
        if self.has(src, "Frightened") and self.sim.sees(src, self.by(src, "Frightened")):
            dis = True; notes.append("[Frightened]"); why.append(("dis", "[Frightened]"))
        if self.cond.get(src, {}).get("Poisoned"):              # THREAT-02 step 2 (SRD 5.2.1)
            dis = True; notes.append("[attacker Poisoned]"); why.append(("dis", "[attacker Poisoned]"))
        if self.cond.get(src, {}).get("Blinded"):
            dis = True; notes.append("[attacker Blinded]"); why.append(("dis", "[attacker Blinded]"))
        if self.cond.get(tgt, {}).get("Blinded"):
            adv = True; notes.append("[target Blinded]"); why.append(("adv", "[target Blinded]"))
        helpless = [n for n in HELPLESS if self.cond.get(tgt, {}).get(n)]
        if helpless:                                             # SIM-MECHANICS-01 (f)
            adv = True; notes.append("[target %s]" % helpless[0]); why.append(("adv", notes[-1]))
        tadv, tdis, tnotes = self.trait_mode(src, tgt)          # SIM-MECHANICS-01 (d)
        side(tadv, tdis, tnotes)
        mod = 0
        env = getattr(self.sim, "env", None)
        if env:
            eadv, edis, enotes, mod = env.attack_mode(src, tgt, rng, dmgtype, spell)
            side(eadv, edis, enotes[1:] if mod else enotes)     # (Exhaustion's note, first, is the modifier's)
            tadv, tdis, tnotes = tadv or eadv, tdis or edis, tnotes + enotes
            cov = env.cover(src, tgt)                            # SIM-ENV-03: +2 / +5 AC = that much off the roll
            if cov:
                mod -= cov
                tnotes = tnotes + ["[%s Cover: +%d AC]" % ("Half" if cov == 2 else "Three-Quarters", cov)]
        import martial_high                                      # MARTIAL-HIGH: Smite of Protection, Half Cover
        half = martial_high.smite_cover(self, src, tgt)
        if half:
            mod -= half
            tnotes = tnotes + ["[Smite of Protection: Half Cover, +%d AC]" % half]
        outlined = self.cond.get(tgt, {}).get("Outlined")        # SPELL-CASTER-01: Faerie Fire, Starry Wisp
        if outlined and outlined.get("advantage") and self.sim.sees(src, tgt):
            adv = True; notes.append("[target outlined: Faerie Fire]"); why.append(("adv", "[target outlined: Faerie Fire]"))
        import map_layers                                        # MAP-LAYERS-01: "If a creature can somehow see you,
        if self.has(tgt, "Invisible") and not outlined and \
                not map_layers.sees_invisible(self.sim, src, tgt):   # you don't gain this benefit"; SIM-ENV-03: Hide
            tdis = True; tnotes = tnotes + ["[target Invisible]"]; why.append(("dis", "[target Invisible]"))
        if self.has(src, "Invisible") and not map_layers.sees_invisible(self.sim, tgt, src):
            tadv = True; tnotes = tnotes + ["[attacker Invisible]"]; why.append(("adv", "[attacker Invisible]"))
        import more_spells                                       # SPELL-BATCH-01: Bane's -1d4
        smod, snote = more_spells.attack_mod(self.sim, src, tgt)
        if smod:
            mod += smod
            tnotes = tnotes + [snote]
        sadv, sdis, snotes = more_spells.attack_mode(self.sim, src, tgt)   # SPELLS-4-6-FIGHT: the dance, Dispel Evil
        side(sadv, sdis, snotes)
        tadv, tdis, tnotes = tadv or sadv, tdis or sdis, tnotes + snotes    # and Good; SPELLS-7-9: Holy Aura
        return (adv or tadv, dis or tdis, " ".join(notes + tnotes), mod) + ((why,) if peek else ())

    # ------------------------------------------------------------ riders on hits, damage, drops
    def on_hit(self, src, tgt, action, res):
        if res in ("hit", "crit") and not self.sim.down(tgt) or res in ("hit", "crit") and self.kind(src) == "Shadow":
            self.trait_hit(src, tgt, str(action), res)          # SIM-MECHANICS-01 (d)
        rider = HIT_RIDERS.get((self.sim.by_id(src).get("srd_name") or self.kind(src), str(action)))
        if not rider and res in ("hit", "crit") and not self.sim.down(tgt):
            self.save_rider(src, tgt, str(action))               # THREAT-02 step 2: the library's save riders
        if not rider or res not in ("hit", "crit") or self.sim.down(tgt):
            return
        if SIZES.index(size_of(self.sim.by_id(tgt))) > SIZES.index(rider["max_size"]):
            return
        if rider["condition"] == "Grappled":
            held = [t for t in list(self.cond) if (self.cond[t].get("Grappled") or {}).get("by") == src
                    and self.has(t, "Grappled")]
            if len(held) >= rider["max"] or tgt in held:
                return
            self.add(tgt, "Grappled", "(escape DC %d, %s's %s)" % (rider["dc"], self.sim.by_id(src)["name"], action),
                     by=src, dc=rider["dc"], range=rider["range"])
        else:
            self.add(tgt, rider["condition"], "(%s's %s)" % (self.sim.by_id(src)["name"], action), by=src)

    def hurt(self, src, tgt, amount):
        """Damage taken: a charmed creature hurt by anyone but its harpy repeats the save; a singing harpy keeps its
        Concentration with a Constitution save (DC 10 or half the damage)."""
        if amount:
            self.spell_hurt(tgt, src)                            # SIM-MECHANICS-01 (f): Sleep, Hideous Laughter
            import high_levels
            high_levels.abjure_hurt(self, tgt)                   # GM 2026-10-26: damage ends Abjure Foes' Frightened
            import martial_high
            martial_high.knockout_hurt(self, tgt)                # MARTIAL-HIGH: damage ends Knock Out's Unconscious
        if amount and src and src != tgt:                        # INVISIBILITY-01: "deals damage" ends the spell on it
            import invisibility
            invisibility.ends_on(self.sim, src, "it dealt damage")
        if self.p and self.sim.by_id(tgt).get("pc"):
            self.sim.later.append(lambda: self.p.hellish_rebuke(tgt, src))   # (f) slice 3: after the damage settles
            import martial_high                                  # MARTIAL-HIGH: Retaliation (Berserker 10)
            self.sim.later.append(lambda: martial_high.retaliate(self.p, tgt, src))
        if self.sim.by_id(tgt).get("displacement"):
            self.displaced_off.add(tgt)                          # PARTY-ITEMS: until the start of its next turn
        harpy = self.by(tgt, "Charmed")
        if harpy and src != harpy and self.has(tgt, "Charmed"):
            self.repeat_save(tgt, "Charmed", "hurt by another")
        if tgt in self.singing and not self.sim.down(tgt):
            dc = max(10, amount // 2)
            d20 = self.sim.rng.randint(1, 20)
            bonus = TURN_ACTIONS["Harpy"]["con_save"]
            kept = d20 + bonus >= dc
            self.sim.say("dice", "%s Concentration save: d20 %d %+d = %d vs DC %d -> %s" % (
                self.sim.by_id(tgt)["name"], d20, bonus, d20 + bonus, dc, "kept" if kept else "Luring Song ends"))
            if not kept:
                self.end_song(tgt, "its Concentration broke")

    def end_song(self, harpy, why):
        self.singing.discard(harpy)
        for t in [t for t, c in self.cond.items() if (c.get("Charmed") or {}).get("by") == harpy]:
            self.remove(t, "Charmed", "the song ends: " + why)

    def dropped(self, me):
        if me in self.singing:
            self.end_song(me, "the harpy drops")

    # ------------------------------------------------------------ saves
    def condition_save(self, t, save, dc, label, charm=False, dis=False, adv=False, cover=0):
        """dis: Disadvantage on the save (True, or its reason: GM 2026-10-23, Heightened Spell); adv: Advantage (its
        reason: Antitoxin against the Poisoned condition); cover: the +2 / +5 of Half or Three-Quarters Cover on a
        Dexterity save (GM 2026-10-25, ruling S4)."""
        parts, rng = self.save_parts(t, save), self.sim.rng
        if cover and save == "dex":
            parts["bonus"] += cover
        if not adv and parts.get("spell_adv"):                  # SPELL-EFFECTS-01: Haste (Dexterity saves)
            adv = parts["spell_adv"]
        d20 = rng.randint(1, 20)
        rolls = "d20 %d" % d20
        fey = (charm and self.sim.by_id(t).get("fey_ancestry") and "Fey Ancestry") or adv or parts["adv_why"]
        if fey and dis:
            rolls += " (Advantage and Disadvantage cancel)"
        elif fey:
            second = rng.randint(1, 20)
            rolls = "d20 %d/%d (%s: Advantage)" % (d20, second, fey if isinstance(fey, str) else "Advantage")
            d20 = max(d20, second)
        elif dis:
            second = rng.randint(1, 20)
            rolls = "d20 %d/%d (%s: Disadvantage)" % (d20, second, dis if isinstance(dis, str) else "Disadvantage")
            d20 = min(d20, second)
        bless = rng.randint(1, 4) if parts["bless"] else 0
        total = d20 + parts["bonus"] + bless
        total += self.own_luck(t, total, dc, label)
        total = self.indomitable(t, total, dc, label, parts["bonus"] + bless)    # Fighter 9
        import high_levels                                       # group 3: Indomitable Might (Barbarian 18)
        total = high_levels.indomitable_might(self.sim, self.sim.by_id(t), save, total, "Strength save")
        ok = total >= dc
        self.sim.say("dice", "%s %s save against %s: %s %+d%s%s = %d vs DC %d -> %s" % (
            self.sim.by_id(t)["name"], ABILITY[save], label, rolls, parts["bonus"], " +%d Bless" % bless if bless else "",
            " (cover +%d)" % cover if cover and save == "dex" else "", total, dc, "success" if ok else "failure"))
        return self.save_result(t, ok, label)

    def repeat_save(self, t, name, when):
        info = self.cond.get(t, {}).get(name)
        if not info:
            return
        if self.condition_save(t, info["save"], info["dc"], "%s (%s)" % (name, when), charm=name == "Charmed",
                               dis=info.get("dis", False)):
            self.remove(t, name, "saved")

    # ------------------------------------------------------------ actions at the start of a monster's turn
    # ------------------------------------------------------------ SIM-ENV-03: hiding
    def passive_perception(self, i):
        c = self.sim.by_id(i)
        hz = getattr(self.sim, "hazards", None)
        dis = 5 if hz and hz.perception_dis() else 0             # HAZARDS-01: Disadvantage on Perception: -5 passive
        m = re.search(r"Passive Perception (\d+)", str(c.get("senses") or ""))
        if m:
            return int(m.group(1)) - dis
        if c.get("passive_perception"):
            return int(c["passive_perception"]) - dis
        return 10 + int(c.get("wis_mod", 0)) - dis

    def search_for_hidden(self, me):
        """At the start of its turn a creature finds a hidden enemy when its passive Perception reaches the hide total
        (INVISIBILITY-01: never one the Invisibility spell makes Invisible: that is not hiding)."""
        side = self.p.side(me) if self.p else self.sim.by_id(me).get("side")
        import light_sources                                     # LIGHTS-01: Dim Light -5, Darkness: not by sight
        for t in [t for t, c in self.cond.items() if c.get("Invisible") and not c["Invisible"].get("spell")]:
            if (self.p.side(t) if self.p else None) != side and not self.sim.down(me):
                look = light_sources.perception(self.sim, me, t)
                pp = self.passive_perception(me) - (5 if look == "dis" else 0)
                if look != "blind" and pp >= self.cond[t]["Invisible"].get("total", 15):
                    self.remove(t, "Invisible", "found by %s (passive Perception %d%s)" % (
                        self.sim.by_id(me)["name"], pp, ", Dim Light" if look == "dis" else ""))

    def attack_rolled(self, src):
        import invisibility, high_levels, epic_boons             # INVISIBILITY-01: the spell ends on its attack roll
        epic_boons.attack_rolled(self.sim, src)                  # EPIC-BOONS-01: Blink Steps (the computer)
        if not invisibility.ends_on(self.sim, src, "it made an attack roll") and self.has(src, "Invisible") \
                and not high_levels.keeps_hidden(self, src) \
                and not epic_boons.keeps(self.sim, src):          # EPIC-BOONS-01: Merge with Shadows, its own turn
            self.remove(src, "Invisible", "it made an attack roll")

    def hide(self, i, bonus, adv=False, reliable=False, why=""):
        """The Hide action (or a Bonus Action): DC 15 Dexterity (Stealth); the total is the DC to find it."""
        rng = self.sim.rng
        d20 = rng.randint(1, 20)
        rolls = "d20 %d" % d20
        if adv:
            second = rng.randint(1, 20); rolls = "d20 %d/%d (Advantage)" % (d20, second); d20 = max(d20, second)
        if reliable and d20 < 10:
            rolls += " (Reliable Talent: 10)"; d20 = 10
        total = d20 + bonus
        import martial_high                                      # MARTIAL-HIGH: Tactical Mind, Stroke of Luck
        if total < 15 and self.p and martial_high.lucky(self.p, i):
            self.sim.say("dice", "%s tries to hide%s: Dexterity (Stealth) %s %+d = %d vs DC 15" % (
                self.sim.by_id(i)["name"], why, rolls, bonus, total))
            new = martial_high.luck_check(self.p, i, total, 15, "Dexterity (Stealth)", bonus)
            if new != total:
                rolls, total = "%s, now %d" % (rolls, new - bonus), new
        ok = total >= 15
        self.sim.say("dice", "%s tries to hide%s: Dexterity (Stealth) %s %+d = %d vs DC 15 -> %s" % (
            self.sim.by_id(i)["name"], why, rolls, bonus, total, "hidden" if ok else "seen"))
        if ok:
            self.add(i, "Invisible", "(hidden, Stealth %d)" % total, by=i, total=total)
        return ok

    def shadow_stealth(self, me):
        """Shadow Stealth: in Dim Light or Darkness the shadow hides (a Bonus Action), if no enemy sees it."""
        if self.kind(me) != "Shadow" or self.has(me, "Invisible") or self.sim.down(me):
            return
        if self.sim.light_level(me) >= 2:
            return
        side = self.p.side(me)
        if any(self.sim.sees(o["id"], me) for o in self.sim.sc["combatants"]
               if self.p.side(o["id"]) != side and not self.sim.down(o["id"])):
            return
        m = re.search(r"Stealth \+(\d+)", str(self.sim.by_id(me).get("skills") or ""))
        self.hide(me, int(m.group(1)) if m else 0, why=" (Shadow Stealth, Bonus Action)")

    def condition_turn(self, me):
        e = TURN_ACTIONS.get(self.sim.by_id(me).get("srd_name") or self.kind(me))
        if not e:
            return False
        c = self.sim.by_id(me)
        side = self.p.side(me)
        if e["name"] == "Luring Song":
            if me in self.singing:
                return False
            immune = self.song_immune.setdefault(me, set())
            targets = [o["id"] for o in self.sim.sc["combatants"] if o.get("pc") and self.p.side(o["id"]) != side
                       and not self.sim.down(o["id"]) and o["id"] not in immune and not self.has(o["id"], "Charmed")
                       and self.ft_between(me, o["id"]) <= e["size"]]
            if not targets:
                return False
            self.singing.add(me)
            self.sim.say("dice", "%s sings its Luring Song (the simulator as GM; Concentration): DC %d Wisdom save for %s" % (
                c["name"], e["dc"], ", ".join(self.sim.by_id(t)["name"] for t in targets)))
            for t in targets:
                if self.condition_save(t, "wis", e["dc"], "Luring Song", charm=True):
                    immune.add(t)
                else:
                    self.add(t, "Charmed", "(%s's Luring Song)" % c["name"], by=me, song=True, save="wis", dc=e["dc"])
            return True
        # Unsettling Visage: Recharge 6
        if not self.ready(me):
            d6 = self.sim.rng.randint(1, 6)
            self.charged[me] = d6 >= e["recharge"]
            self.sim.say("dice", "%s %s, Recharge %d: rolls %d -> %s" % (
                c["name"], e["name"], e["recharge"], d6, "regained" if self.charged[me] else "not yet"))
            if not self.charged[me]:
                return False
        targets = [o["id"] for o in self.sim.sc["combatants"] if self.p.side(o["id"]) != side
                   and not self.sim.down(o["id"]) and self.ft_between(me, o["id"]) <= e["size"]
                   and self.sim.sees(o["id"], me) and not self.has(o["id"], "Frightened")]
        if not targets:
            return False
        self.charged[me] = False
        self.sim.say("dice", "%s uses %s (Recharge %d; the simulator as GM): DC %d Wisdom save for %s" % (
            c["name"], e["name"], e["recharge"], e["dc"], ", ".join(self.sim.by_id(t)["name"] for t in targets)))
        for t in targets:
            if not self.condition_save(t, "wis", e["dc"], e["name"]):
                self.add(t, "Frightened", "(%s's %s)" % (c["name"], e["name"]), by=me, save="wis", dc=e["dc"])
        return not e.get("in_multiattack")

    # ------------------------------------------------------------ Whelm (Water Elemental, SRD 5.2.1)
    def whelm_turn(self, me):
        """Start of the elemental's turn: 2d8 to those it holds; then Whelm (Recharge 4-6) on up to two Medium or smaller
        creatures next to it (the simulator's reading of "in the elemental's space": it flows over them). True: its
        action was Whelm."""
        if self.kind(me) != "Water Elemental" or self.sim.down(me):
            return False
        g = self.sim.S
        held = [t for t in list(self.cond) if (self.cond[t].get("Grappled") or {}).get("whelm") == me and self.has(t, "Grappled")]
        for t in held:
            self.sim.say("dice", "%s is crushed inside %s: 2d8 Bludgeoning" % (self.sim.by_id(t)["name"], self.sim.by_id(me)["name"]))
            g.pcDamage(me, t, "2d8", 0, False, "bludgeoning")
            self.sim.settle(0.2)
        key = ("whelm", me)
        if not self.charged.get(key, True):
            d6 = self.sim.rng.randint(1, 6)
            self.charged[key] = d6 >= 4
            self.sim.say("dice", "%s Whelm, Recharge 4-6: rolls %d -> %s" % (
                self.sim.by_id(me)["name"], d6, "regained" if self.charged[key] else "not yet"))
            if not self.charged[key]:
                return False
        side = self.p.side(me)
        room = 2 - len(held)
        near = [o["id"] for o in self.sim.sc["combatants"] if self.p.side(o["id"]) != side and not self.sim.down(o["id"])
                and self.ft_between(me, o["id"]) <= 5 and SIZES.index(size_of(o)) <= SIZES.index("medium")
                and o["id"] not in held]
        targets = near[:room]
        if not targets:
            return False
        self.charged[key] = False
        dmg = party_mod.roll(self.sim.rng, "4d8+4")
        self.sim.say("dice", "%s uses Whelm (Recharge 4-6; the simulator as GM): DC 15 Strength save, 4d8 + 4 = %d "
                     "Bludgeoning on %s" % (self.sim.by_id(me)["name"], dmg, ", ".join(self.sim.by_id(t)["name"] for t in targets)))
        e = {"save": "str", "dc": 15, "type": "bludgeoning"}
        for t in targets:
            parts = self.save_parts(t, "str")
            d20 = self.sim.rng.randint(1, 20)
            saved = d20 + parts["bonus"] >= 15
            amount = dmg // 2 if saved else dmg
            self.sim.say("dice", "%s Strength save: d20 %d %+d = %d vs DC 15 -> %s: %d Bludgeoning (before its defenses)" % (
                self.sim.by_id(t)["name"], d20, parts["bonus"], d20 + parts["bonus"], "success (half)" if saved else "failure", amount))
            g.pcDamage(me, t, "", amount, False, "bludgeoning")
            self.sim.settle(0.2)
            if not saved and not self.sim.down(t):
                self.add(t, "Grappled", "(Whelm, escape DC 14)", by=me, dc=14, range=5, whelm=me)
                self.add(t, "Restrained", "(inside the elemental; suffocating unless it breathes water)", by=me, whelm=me)
        return True

    def pull_out(self, helper, victim):
        """A creature within 5 ft of the elemental pulls a victim out (an action): DC 14 Strength (Athletics)."""
        el = self.by(victim, "Grappled")
        if not el or self.ft_between(helper, el) > 5:
            return False
        esc = getattr(self.sim, "escape", None)
        total = esc.check(helper, "Athletics", "str")[0] if esc and esc.active else self.sim.rng.randint(1, 20)
        ok = total >= 14
        self.sim.say("dice", "%s tries to pull %s out of %s: Athletics %d vs DC 14 -> %s" % (
            self.sim.by_id(helper)["name"], self.sim.by_id(victim)["name"], self.sim.by_id(el)["name"], total,
            "pulled free" if ok else "fails"))
        if ok:
            self.remove(victim, "Grappled", "pulled free by %s" % self.sim.by_id(helper)["name"])
        return ok

    def escape_grapple(self, i):
        """Escaping a Grapple (an action): Strength (Athletics) or Dexterity (Acrobatics), the better, vs the escape DC."""
        info = self.cond.get(i, {}).get("Grappled")
        if not info:
            return False
        esc = getattr(self.sim, "escape", None)
        if esc and esc.active:
            total, d20, skill = esc.best_check(i, [("Athletics", "str"), ("Acrobatics", "dex")])
        else:
            total, skill = self.sim.rng.randint(1, 20), "a check"
        ok = total >= info.get("dc", 10)
        self.sim.say("dice", "%s tries to escape the grapple: %s %d vs DC %d -> %s" % (
            self.sim.by_id(i)["name"], skill, total, info.get("dc", 10), "free" if ok else "still held"))
        if ok:
            self.remove(i, "Grappled", "escaped")
        return ok

    def whelmed(self, i):
        return bool((self.cond.get(i, {}).get("Grappled") or {}).get("whelm")) and self.has(i, "Grappled")

    def turn_ended(self, me):
        """Effects that last until the end of a creature's next turn (Steam Breath's slow); Fire Aura."""
        self.traits_turn_ended(me)
        self.spell_turn_ended(me)                                # SIM-MECHANICS-01 (f)
        import more_spells
        more_spells.turn_ended(self.sim, me)                     # SPELL-EFFECTS-01: a zone's end-of-turn save
        self.tick(me, "end")                                     # THREAT-02 step 2: conditions that last a turn
        for t, c in list(self.cond.items()):
            info = c.get("Slowed")
            if info and info["by"] == me:
                info["ends"] -= 1
                if info["ends"] <= 0:
                    self.remove(t, "Slowed", "the end of %s's next turn" % self.sim.by_id(me)["name"])

    # ------------------------------------------------------------ a character's turn
    def pc_turn_start(self, t, live=False):
        """Speed for this turn (c["_speed_now"]): Slowed -10, Grappled 0, Frightened holds still (it will not move
        closer to the source; the scripted party does not retreat), Prone: half its Speed spent to stand.
        Returns the harpy when the character is Charmed by a song (it only walks toward it this turn).
        GM 2026-10-24 ("Check movement rules"): live = a player's character in Play live. It keeps its full Speed and
        stays Prone until the player stands (Stand up, sim/live_actions.py: half its Speed); Frightened is the player's
        to respect (no moving closer to the source), not a Speed of 0."""
        c = self.sim.by_id(t)
        self.displaced_off.discard(t)                            # PARTY-ITEMS: Cloak of Displacement works again
        self.burning_start(t)                                    # SIM-MECHANICS-01 (d)
        speed = int(str(c.get("speed", "30")).split()[0])
        if self.has(t, "Slowed"):
            speed = max(0, speed - self.cond[t]["Slowed"].get("ft", 0))
        if self.has(t, "Grappled") or any(self.cond.get(t, {}).get(n) for n in HELD):
            speed = 0
        if self.has(t, "Prone") and not live:
            if speed > 0:
                self.remove(t, "Prone", "stands up, spending half its Speed")
                speed -= speed // 2
            else:
                self.sim.say("dice", "%s cannot stand up (Speed 0)" % c["name"])
        if self.has(t, "Frightened") and not live:
            speed = 0
        esc = getattr(self.sim, "escape", None)
        carrying = 1 if esc and esc.carried_by(t) else 0         # SIM-ESC-01/05: moving a Grappled friend, +1 ft a foot
        env = getattr(self.sim, "env", None)
        if env:
            speed = env.speed(t, speed, carrying)                # SIM-ENV-01: Exhaustion, swimming
        elif carrying:
            speed //= 2
        c["_speed_now"] = speed
        return self.by(t, "Charmed") if self.has(t, "Charmed") and self.incapacitated(t) else None

    def pc_turn_end(self, t):
        self.sim.by_id(t).pop("_speed_now", None)
        for name in ("Charmed", "Frightened"):
            info = self.cond.get(t, {}).get(name) or {}
            if self.has(t, name) and not info.get("until") and not info.get("repeat"):   # THREAT-02: tick() has those
                self.repeat_save(t, name, "end of its turn")


# ---------------------------------------------------------------------- SIM-MECHANICS-01 (d), 2026-10-18: traits
# Creatures that shed light (Azer Sentinel Illumination; Magmin Ignited Illumination: the GM keeps it ablaze in a fight)
CREATURE_LIGHTS = {"Azer Sentinel": (10, 20), "Magmin": (10, 20)}


def creature_lights(sc):
    """Bright 10 ft and Dim 10 more around each lit creature, as carried lights (on maps with lighting)."""
    lit = sc.get("lighting")
    if not lit:
        return sc
    have = {str(l.get("carrier")) for l in lit.setdefault("lights", []) if l.get("carrier")}
    for c in sc.get("combatants") or []:
        kind = c.get("srd_name") or c.get("name", "").rstrip("0123456789").strip()
        if kind in CREATURE_LIGHTS and c["id"] not in have and not c.get("pc"):
            bright, dim = CREATURE_LIGHTS[kind]
            lit["lights"].append({"carrier": c["id"], "bright_ft": bright, "dim_ft": dim,
                                  "label": "%s (Illumination, SRD 5.2.1)" % c["name"]})
    return sc


def str_weapon(w):
    """A melee weapon that uses Strength (not Finesse, not a spell)."""
    return bool(w.get("str") or (w.get("reach", 5) <= 5 and not w.get("finesse")
                                 and w.get("name") not in party_mod.SPELL_DAMAGE_TYPES))


class _Traits:
    """Mixed into GmRules: stat-block traits the GM plays (FG automates Undead Fortitude itself)."""

    def _init_traits(self):
        self.turn_pos = {}          # creature -> where its current turn started (the Gore charge)
        self.displaced_off = set()  # PARTY-ITEMS: Cloak of Displacement off until the wearer's next turn

    def mark_turn_start(self, me):
        self.turn_pos[me] = self.p.pos(me)

    def traits_turn_start(self, me):
        """Regeneration (Shield Guardian): 10 HP at the start of each of its turns with at least 1 HP."""
        self.mark_turn_start(me)
        if self.kind(me) == "Shield Guardian" and not self.sim.down(me):
            g = self.sim.S
            wounds = g.getField(me, "wounds")
            if wounds > 0:
                g.heal(me, 10)
                self.sim.say("dice", "%s Regeneration: regains %d HP" % (self.sim.by_id(me)["name"], min(10, wounds)))

    def traits_turn_ended(self, me):
        """Fire Aura (Azer Sentinel): at the end of each of its turns, 1d10 Fire to the foes in its 5-ft Emanation."""
        if self.kind(me) != "Azer Sentinel" or self.sim.down(me) or self.incapacitated(me):
            return
        side = self.p.side(me)
        near = [o["id"] for o in self.sim.sc["combatants"] if self.p.side(o["id"]) != side
                and not self.sim.down(o["id"]) and self.ft_between(me, o["id"]) <= 5]
        if near:
            self.sim.say("dice", "%s's Fire Aura (end of its turn): 1d10 Fire on %s" % (
                self.sim.by_id(me)["name"], ", ".join(self.sim.by_id(t)["name"] for t in near)))
        for t in near:
            self.sim.S.pcDamage(me, t, "1d10", 0, False, "fire")
            self.sim.settle(0.2)

    def trait_mode(self, src, tgt):
        """Blurred Form (Steam Mephit) and the Doppelganger's first-round Advantage."""
        adv = dis = False
        notes = []
        if self.kind(tgt) == "Steam Mephit" and not self.incapacitated(tgt) and not self.sim.down(tgt):
            dis = True; notes.append("[Blurred Form]")
        if self.kind(src) == "Doppelganger" and self.sim.S.round() == 1:
            adv = True; notes.append("[Doppelganger: first round]")
        if self.sim.by_id(tgt).get("displacement") and tgt not in self.displaced_off and not self.incapacitated(tgt) \
                and not self.sim.down(tgt):
            dis = True; notes.append("[Cloak of Displacement]")
        return adv, dis, notes

    def react_hit(self, tid, total, ac, melee, src):
        """Parry (Knight): its Reaction when a melee attack roll hits it: +2 AC against that attack."""
        if self.kind(tid) != "Knight" or not melee or self.sim.down(tid) or self.incapacitated(tid) or total >= ac + 2:
            return 0
        self.sim.say("dice", "%s uses Parry (Reaction): +2 AC against this attack" % self.sim.by_id(tid)["name"])
        return 2

    def fortitude(self, tid, damage, radiant, crit):
        """Undead Fortitude (Zombie), as FG's 5E handleFortitudeTraitOnDamage: Con save DC 5 + the damage, unless
        Radiant or a Critical Hit; a success leaves 1 HP. True: it stays up.
        GM 2026-10-26: a raging Barbarian's Relentless Rage (sim/high_levels.py) through the same hook."""
        if self.sim.by_id(tid).get("pc"):
            import high_levels
            return high_levels.relentless(self, tid)
        if self.kind(tid) != "Zombie":
            return False
        c = self.sim.by_id(tid)
        if radiant or crit:
            self.sim.say("dice", "%s: no Undead Fortitude (%s)" % (c["name"], "Radiant damage" if radiant else "a Critical Hit"))
            return False
        dc, d20, bonus = 5 + int(damage), self.sim.rng.randint(1, 20), c.get("con_save", 0)
        ok = d20 + bonus >= dc
        self.sim.say("dice", "%s Undead Fortitude: Constitution save d20 %d %+d = %d vs DC %d -> %s" % (
            c["name"], d20, bonus, d20 + bonus, dc, "drops to 1 HP instead" if ok else "it falls"))
        return ok

    def trait_hit(self, src, tgt, action, res):
        """Gore charge, Draining Swipe, Magmin Touch (burning)."""
        kind, crit = self.kind(src), res == "crit"
        if kind == "Minotaur Skeleton" and action == "Gore":
            start = self.turn_pos.get(src)
            if not start or SIZES.index(size_of(self.sim.by_id(tgt))) > SIZES.index("large"):
                return
            now, there = self.p.pos(src), self.p.pos(tgt)
            u = self.sim.sc.get("units", 5)
            moved = (now[0] - start[0], now[1] - start[1])
            toward = (there[0] - start[0], there[1] - start[1])
            feet = max(abs(moved[0]), abs(moved[1])) * u
            norm = math.hypot(*moved) * math.hypot(*toward)
            if feet >= 20 and norm and (moved[0] * toward[0] + moved[1] * toward[1]) / norm >= 0.9:
                self.sim.say("dice", "%s's Gore charge (moved %d ft straight at %s): +2d8 Piercing and Prone" % (
                    self.sim.by_id(src)["name"], feet, self.sim.by_id(tgt)["name"]))
                self.sim.S.pcDamage(src, tgt, "2d8", 0, crit, "piercing")
                self.sim.settle(0.2)
                if not self.sim.down(tgt):
                    self.add(tgt, "Prone", "(the Gore charge)", by=src)
        elif kind == "Shadow" and action == "Draining Swipe" and self.sim.by_id(tgt).get("pc"):
            self.drain_strength(src, tgt)
        elif kind == "Magmin" and action == "Touch" and not self.sim.down(tgt):
            self.add(tgt, "Burning", "(the Magmin's Touch)", by=src)

    def drain_strength(self, src, tgt):
        c = self.sim.by_id(tgt)
        if "str_score" not in c:
            self.sim.say("dice", "%s: Draining Swipe's Strength loss not tracked (no Strength score)" % c["name"])
            return
        loss = self.sim.rng.randint(1, 4)
        old, new = c["str_score"], max(0, c["str_score"] - loss)
        delta = (new - 10) // 2 - (old - 10) // 2
        c["str_score"] = new
        if c.get("abilities"):
            c["abilities"] = dict(c["abilities"], str=new)
        c["str_save"] = c.get("str_save", 0) + delta
        for key in ("weapon", "ranged"):
            w = c.get(key)
            if w and delta and str_weapon(w):
                dice, _, bonus = str(w.get("dmg", "1d4")).partition("+")
                b = int(bonus or 0) + delta
                c[key] = dict(w, atk=w.get("atk", 0) + delta, dmg=dice + ("+%d" % b if b > 0 else ""))
        self.sim.say("dice", "%s's Draining Swipe: %s's Strength %d -> %d (1d4 = %d)%s" % (
            self.sim.by_id(src)["name"], c["name"], old, new, loss,
            "; Strength attacks and saves %+d" % delta if delta else ""))
        if new == 0:
            g = self.sim.S
            g.setField(tgt, "wounds", c["hp"]); g.setField(tgt, "sim_dying", 0)
            st = self.p.deaths.setdefault(tgt, party_mod.new_death_state())
            st["dead"] = True
            self.sim.say("turn", "%s dies: Strength 0 (Draining Swipe)" % c["name"])
            self.p.lose_concentration(tgt, "dead")             # SIM-MECHANICS-01 (e)

    def burning_start(self, t):
        """Burning (Rules Glossary): 1d4 Fire at the start of each of its turns."""
        if self.has(t, "Burning"):
            self.sim.say("dice", "%s is Burning: 1d4 Fire" % self.sim.by_id(t)["name"])
            self.sim.S.pcDamage(self.by(t, "Burning"), t, "1d4", 0, False, "fire")
            self.sim.settle(0.2)
            import traps                                         # GM 2026-10-26: oil on it (and T10: under it) catches
            traps.of(self.sim).ignite_creatures([t], self.by(t, "Burning"), "the fire on it")

    def extinguish_if_needed(self, t):
        """The scripted party's choice: a burning character at half its hit points or fewer puts the fire out (an
        action: it has the Prone condition, rolling on the ground). True: that was its action."""
        if not self.has(t, "Burning") or self.sim.down(t) or self.incapacitated(t):
            return False
        c = self.sim.by_id(t)
        if self.p.hp_left(t) > c["hp"] // 2:
            return False
        self.remove(t, "Burning", "rolls on the ground (an action)")
        self.add(t, "Prone", "(rolling out the fire)", by=t)
        return True


class GmRules(_Conditions, _Traits):
    def __init__(self, sim):
        self.sim, self.p = sim, sim.party
        self._init_conditions()
        self._init_traits()
        self.charged = {}        # creature -> breath ready (a creature starts the fight with it)
        self.burst = set()       # creatures whose Death Burst went off
        self.save_ready = {}     # THREAT-02 step 2: (creature, action) -> Recharge ready / uses left

    # ------------------------------------------------------------------ who and where
    def kind(self, i):
        return self.sim.by_id(i)["name"].rstrip("0123456789").strip()

    def effects(self, i):
        return SAVE_EFFECTS.get(self.sim.by_id(i).get("srd_name") or self.kind(i), {})

    def span(self, i):
        return max(1, int(round(float(self.sim.by_id(i).get("space") or 5) / 5)))

    def ft_between(self, a, b):
        """Feet between two creatures' spaces (FG's diagonal rule 1: every square counts 5 ft)."""
        (ax, ay), (bx, by) = self.p.pos(a), self.p.pos(b)
        gap = max(abs(ax - bx), abs(ay - by)) - (self.span(a) - 1) / 2 - (self.span(b) - 1) / 2
        return max(0, gap) * self.sim.sc.get("units", 5)

    def immune(self, i, kind):
        return kind in str(self.sim.by_id(i).get("damageimmunities") or "").split(";")[0].lower()

    def ready(self, i):
        return self.charged.get(i, True)

    # ------------------------------------------------------------------ saving throws
    def save_parts(self, t, ability):
        c, p = self.sim.by_id(t), self.p
        incapacitated = self.sim.down(t) or self.incapacitated(t)
        env = getattr(self.sim, "env", None)
        trait = self.sim.save_tweak(t, ability) if hasattr(self.sim, "save_tweak") else {}   # creature abilities
        import more_spells                                       # SPELL-EFFECTS-01: Slow -2, Haste Advantage (Dexterity)
        spell_bonus, spell_adv = more_spells.save_mod(self.sim, t, ability)
        return {"bonus": c.get(ability + "_save", 0) + (p.aura(t) if p else 0) + (env.d20_penalty(t) if env else 0) + spell_bonus,
                "dis": bool(env and env.save_dis(t)) or more_spells.save_dis(self.sim, t, ability), "spell_adv": spell_adv,
                "adv": bool(spell_adv) or (ability == "dex" and c.get("class") == "barbarian" and c.get("level", 1) >= 2 and not incapacitated)
                       or bool(trait.get("adv")),
                "adv_why": trait.get("adv") or spell_adv or "",
                "bless": bool(p and t in p.blessed and p.concentrating) or bool(trait.get("bless")),
                "evasion": ability == "dex" and self.has_evasion(t)}

    def save_result(self, t, ok, label):
        """The save's final result after the creature's own abilities (Legendary Resistance)."""
        return self.sim.save_result(t, ok, label) if hasattr(self.sim, "save_result") else ok

    def has_evasion(self, t):
        """Evasion (SRD 5.2.1 Rogue 7 and Monk 7): a Dexterity save for half damage takes none on a success and half on a
        failure; not while Incapacitated. GM 2026-10-25 (ruling S4): against spells too."""
        c = self.sim.by_id(t)
        return (c.get("class") in ("rogue", "monk") and int(c.get("level", 1) or 1) >= 7
                and not (self.sim.down(t) or self.incapacitated(t)))

    def save_and_damage(self, src, t, e, dmg):
        parts, rng = self.save_parts(t, e["save"]), self.sim.rng
        env = getattr(self.sim, "env", None)
        if env and e["save"] == "dex" and src != t:
            parts["bonus"] += env.cover(src, t)                  # SIM-ENV-03: cover adds to Dexterity saves
        __import__("martial_high").save_aid(self, src, t, e["save"], parts)   # MARTIAL-HIGH: Smite of Protection, Holy Nimbus
        d20 = rng.randint(1, 20)
        rolls = "d20 %d" % d20
        if parts["adv"] and not parts["dis"]:
            second = rng.randint(1, 20)
            rolls = "d20 %d/%d (%s: Advantage)" % (d20, second, parts["adv_why"] or "Danger Sense")
            d20 = max(d20, second)
        elif parts["dis"] and not parts["adv"]:
            second = rng.randint(1, 20)
            rolls = "d20 %d/%d (Sunlight Weakness: Disadvantage)" % (d20, second)
            d20 = min(d20, second)
        bless = rng.randint(1, 4) if parts["bless"] else 0
        total = d20 + parts["bonus"] + bless
        total += self.own_luck(t, total, e["dc"], e.get("name", "a save"))
        total = self.indomitable(t, total, e["dc"], e.get("name", "a save"), parts["bonus"] + bless)
        saved = self.save_result(t, total >= e["dc"], e.get("name", "a save"))
        amount = area_damage(dmg, saved, parts["evasion"])
        self.sim.say("dice", "%s %s save: %s %+d%s = %d vs DC %d -> %s%s: %d %s (before its defenses)" % (
            self.sim.by_id(t)["name"], ABILITY[e["save"]], rolls, parts["bonus"], " +%d Bless" % bless if bless else "",
            total, e["dc"], "success" if saved else "failure", " (Evasion)" if parts["evasion"] else "", amount,
            e["type"].capitalize()))
        if amount:
            self.sim.S.pcDamage(src, t, "", amount, False, e["type"])
            self.sim.settle(0.2)
        if e.get("slow") and not saved and not self.sim.down(t):     # Steam Breath: until the end of its next turn
            self.add(t, "Slowed", "(%s, until the end of %s's next turn)" % (e["name"], self.sim.by_id(src)["name"]),
                     by=src, ft=e["slow"], ends=2)

    # ------------------------------------------------------------------ Recharge breath at the start of the turn
    def cone_targets(self, me, e, aim=None):
        """The 15-ft Cone from the creature's square (origin: a corner or edge midpoint) catching the most characters
        and no ally the damage would harm: the creatures inside, or []. aim (REFEREE-01): gets its origin (squares)
        and direction."""
        u = self.sim.sc.get("units", 5)
        here = self.p.pos(me)
        feet = lambda q: (q[0] * u, q[1] * u)
        side = self.p.side(me)
        others = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.sim.down(o["id"])
                  and not self.p.blocked(me, o["id"])]
        pcs = [o for o in others if self.p.side(o) != side and self.ft_between(me, o) <= e["size"]]
        if not pcs:
            return []
        cx, cy = feet(here)
        best = []
        for ox, oy in [(x, y) for x in (-2.5, 0, 2.5) for y in (-2.5, 0, 2.5) if (x, y) != (0, 0)]:
            o = (cx + ox, cy + oy)
            aims = [(feet(self.p.pos(t))[0] - o[0], feet(self.p.pos(t))[1] - o[1]) for t in pcs]
            aims += [(a[0] / (math.hypot(*a) or 1) + b[0] / (math.hypot(*b) or 1),
                      a[1] / (math.hypot(*a) or 1) + b[1] / (math.hypot(*b) or 1))
                     for i, a in enumerate(aims) for b in aims[i + 1:]]
            for toward in aims:
                if toward[0] * ox + toward[1] * oy <= 0:
                    continue                                   # breathed outward, away from its own square
                inside = [t for t in others if party_mod.in_cone(o, toward, feet(self.p.pos(t)), e["size"])]
                caught = [t for t in inside if self.p.side(t) != side]
                harmed_ally = [t for t in inside if self.p.side(t) == side and not self.immune(t, e["type"])]
                if caught and not harmed_ally and len(caught) > len([t for t in best if self.p.side(t) != side]):
                    best = inside
                    if aim is not None:
                        aim.update(origin=[o[0] / u, o[1] / u], toward=list(toward))
        return best

    def refereed(self, me, action, aim=None):
        """REFEREE-01: the rules referee checks this saving-throw action against its stat block once the with-block
        has resolved it (sim/referee.py watch_action)."""
        ref = getattr(self.sim, "referee", None)
        return ref.watch_action(me, action, aim) if ref else contextlib.nullcontext({"effect": {}, "notes": []})

    def turn_start(self, me):
        """True when the GM used the creature's Recharge breath or a condition action (SIM-MECHANICS-01 c): that was
        its turn."""
        if not self.p:
            return False
        self.tick(me, "start")                                   # THREAT-02 step 2: "until the start of ... next turn"
        hz = getattr(self.sim, "hazards", None)
        if hz:
            hz.turn_start(me)                                    # HAZARDS-01: slippery ice, Cackle Fever, stress ending
            if self.sim.down(me):
                return True
        c = self.sim.by_id(me)
        if not c.get("pc"):                                      # group 1 (GM 2026-10-27): a creature burns too (1d4 at
            self.burning_start(me)                               # the start of its turn) and puts the fire out, as the
            if self.sim.down(me):                                # scripted party does, at half its Hit Points or fewer
                return True
            if self.extinguish_if_needed(me):
                self.sim.say("turn", "%s rolls on the ground to put out the fire (an action; Prone): its turn ends" % c["name"])
                return True
        self.fumes_turn(me)                                      # GM 2026-10-23: Burnt Othur Fumes
        layers = getattr(self.sim, "layers", None)               # MAP-LAYERS-01: Stinking Cloud, a zone's time
        lost = layers.turn_start(me) if layers and not self.sim.by_id(me).get("live") else ""
        if lost:
            self.sim.say("turn", "%s: %s (its turn ends)" % (self.sim.by_id(me)["name"], lost))
            return True
        import more_spells                                       # SPELL-EFFECTS-01: a zone's start-of-turn save, a
        lost = more_spells.creature_turn_start(self.sim, me)     # summoned creature's orders (sim/summons.py)
        if lost and not self.sim.by_id(me).get("pc"):
            if lost is not True:
                self.sim.say("turn", "%s: %s (its turn ends)" % (self.sim.by_id(me)["name"], lost))
            return True
        esc = getattr(self.sim, "escape", None)
        if esc and esc.dormant(me):                              # SIM-ESC-01: the guardian waits for the exposure
            self.sim.say("turn", "%s lies dormant (exposure %d/6)" % (self.sim.by_id(me)["name"], esc.exposure))
            return True
        env = getattr(self.sim, "env", None)
        if env and env.controlled_mount(me):                     # SIM-ENV-04: it moves on its rider's turn
            self.sim.say("turn", "%s is a controlled mount: it moves on %s's turn (Dash, Disengage, Dodge only)" % (
                self.sim.by_id(me)["name"], self.sim.by_id(env.rider_of(me))["name"]))
            return True
        prone = self.cond.get(me, {}).get("Prone")
        if prone and prone.get("command"):                       # SIM-MECHANICS-01 (f): Command (Grovel)
            prone.pop("command")
            self.sim.say("turn", "%s obeys the Command (Grovel): Prone, and its turn ends" % self.sim.by_id(me)["name"])
            return True
        import high_levels
        if high_levels.abjure_turn(self, me):                    # GM 2026-10-26: Abjure Foes, one thing a turn
            return True
        if high_levels.hurled_turn(self, me):                    # CASTER-HIGH: Hurl Through Hell, not here
            return True
        import martial_high                                      # MARTIAL-HIGH: Holy Nimbus's Radiant damage, Daze
        if martial_high.nimbus_turn(self, me):
            return True
        martial_high.daze_turn(self, me)
        halt = self.cond.get(me, {}).get("Commanded")
        if halt and halt.get("command") == "Halt":               # SPELL-CASTER-01: Command (Halt)
            self.remove(me, "Commanded", "it obeys")
            self.sim.say("turn", "%s obeys the Command (Halt): it doesn't move and takes no action or Bonus Action" %
                         self.sim.by_id(me)["name"])
            return True
        seared = self.cond.get(me, {}).get("Searing Smite")
        if seared and not self.sim.down(me):                     # SIM-MECHANICS-01 (f) slice 3
            self.sim.say("dice", "%s burns (Searing Smite): %s Fire" % (self.sim.by_id(me)["name"], seared["dice"]))
            self.sim.S.pcDamage(seared["by"], me, seared["dice"], 0, False, "fire")
            self.sim.settle(0.2)
            if not self.sim.down(me) and self.condition_save(me, "con", seared["dc"], "Searing Smite"):
                self.remove(me, "Searing Smite", "saved")
            if self.sim.down(me):
                return True
        if prone and not self.incapacitated(me) and not prone.get("spell") and not self.sim.by_id(me).get("live"):
            # (SPELL-EFFECTS-01: a live player's character stays Prone until its player stands it up, pc_turn_start)
            # a monster stands up at the start of its turn (half its Speed: the bridge is not told, it plans full Speed)
            self.remove(me, "Prone", "stands up")
        self.traits_turn_start(me)                               # SIM-MECHANICS-01 (d): Regeneration, the charge's start
        self.search_for_hidden(me)                               # SIM-ENV-03
        self.shadow_stealth(me)
        if self.whelm_turn(me):                                  # SIM-ESC-04: the Water Elemental's Whelm
            return True
        if self.condition_turn(me):
            return True
        e = self.effects(me).get("breath")
        if not e:
            return self.save_action_turn(me)                     # THREAT-02 step 2
        c = self.sim.by_id(me)
        if not self.ready(me):
            d6 = self.sim.rng.randint(1, 6)
            self.charged[me] = d6 >= e["recharge"]
            self.sim.say("dice", "%s %s, Recharge %d: rolls %d -> %s" % (
                c["name"], e["name"], e["recharge"], d6, "regained" if self.charged[me] else "not yet"))
            if not self.charged[me]:
                return False
        aim = {}
        targets = self.cone_targets(me, e, aim)
        if not targets:
            return False
        self.charged[me] = False
        with self.refereed(me, self.table_action(e), aim):
            dmg = party_mod.roll(self.sim.rng, e["dmg"])
            self.sim.say("dice", "%s uses %s (Recharge %d; the simulator as GM): DC %d %s save, %d-foot Cone, %s = %d %s on %s" % (
                c["name"], e["name"], e["recharge"], e["dc"], ABILITY[e["save"]], e["size"], e["dmg"], dmg,
                e["type"].capitalize(), ", ".join(self.sim.by_id(t)["name"] for t in targets)))
            for t in targets:
                self.save_and_damage(me, t, e, dmg)
        return True

    @staticmethod
    def table_action(e):
        """A SAVE_EFFECTS entry as a stat-block save action, for the referee."""
        return {"name": e["name"], "save": {"save": e["save"], "dc": e["dc"], "dmg": e["dmg"], "type": e["type"], "half": True,
                                            "area": {"shape": e["shape"], "size": e["size"]}}}

    # ------------------------------------------------------------------ Death Burst
    def on_drop(self, me):
        """A creature dropped to 0 hit points: its Death Burst goes off after the damage that dropped it."""
        self.dropped(me)
        env = getattr(self.sim, "env", None)
        if env:
            if env.rider_of(me) is not None:                     # SIM-ENV-04: a mount at 0 HP is Prone
                self.sim.later.append(lambda: env.rider_check(me, "its mount drops"))
            self.sim.later.append(lambda: env.lost_flight(me))   # SIM-ENV-02: Unconscious: a flier falls
        e = self.effects(me).get("death_burst")
        if e and me not in self.burst and not self.sim.by_id(me).get("pc"):
            self.burst.add(me)
            self.sim.later.append(lambda: self.death_burst(me, e))

    def death_burst(self, me, e):
        c = self.sim.by_id(me)
        if self.p:
            self.p.saw_burst(me, e["size"])
        targets = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me
                   and (o.get("pc") or not self.sim.down(o["id"]))
                   and not (self.p.deaths.get(o["id"], {}).get("dead"))
                   and self.ft_between(me, o["id"]) <= e["size"] and not self.p.blocked(me, o["id"])]
        with self.refereed(me, self.table_action(e), {"origin": list(self.p.pos(me))}):
            dmg = party_mod.roll(self.sim.rng, e["dmg"])
            self.sim.say("dice", "%s's Death Burst (the simulator as GM): DC %d %s save, %d-foot Emanation, %s = %d %s on %s" % (
                c["name"], e["dc"], ABILITY[e["save"]], e["size"], e["dmg"], dmg, e["type"].capitalize(),
                ", ".join(self.sim.by_id(t)["name"] for t in targets) or "no one"))
            for t in targets:
                self.save_and_damage(me, t, e, dmg)

    # ------------------------------------------------------------------ THREAT-02 step 2: the library's save actions
    # GM 2026-10-21: "Next: THREAT-02 step 2, creatures' saving-throw actions and Recharge breath weapons." Every SRD
    # creature's block (tools/srd_library.py) carries its saving-throw actions as "save": the save and DC, the area
    # (Cone, Line, Emanation, a Sphere at a point in range, or one creature), damage (half on a success when the stat
    # block says so) and conditions with how long they last; Recharge and X/Day. The simulator, as GM, uses one at the
    # start of the creature's turn in place of its turn: a Recharge or X/Day action when it catches a foe and harms no
    # ally, an at-will one when it catches two or more, lays a condition on a foe who lacks it, or the creature has no
    # attack. The hand-made tables above win.
    def save_actions(self, me):
        return [a for a in self.sim.by_id(me).get("actions") or [] if a.get("save") and not a["save"].get("rider")]

    def in_multiattack(self, me, a):
        """How the creature's Multiattack names this save action: "with" ("makes two Rotting Fist attacks and uses
        Dreadful Glare"), "replace" ("can replace one attack with a use of Sleep Breath") or None (its own action, or
        "... or uses Holy Burst twice": a whole turn instead of the attacks)."""
        multi = next((x.get("desc", "") for x in self.sim.by_id(me).get("actions") or [] if x.get("name") == "Multiattack"), "")
        base = re.sub(r"\s*\(.*?\)\s*$", "", a["name"]).strip()
        word = base.split()[-1] if base.split()[0] in ("First", "Second", "Third") else base   # the sphinx's Roars
        w = re.escape(word)
        if re.search(r"replace (?:one|any) attack with a use of (?:\(A\) )?" + w, multi):
            return "replace"
        if re.search(r"\band (?:it )?uses (?:its )?" + w, multi):
            return "with"
        return None

    def save_action_turn(self, me):
        c = self.sim.by_id(me)
        if c.get("pc") or self.sim.down(me) or self.incapacitated(me):
            return False
        best = None
        attacks = any("atk" in a for a in c.get("actions") or [])
        for a in self.save_actions(me):
            sp, key = a["save"], (me, a["name"])
            limited = "recharge" in sp or "uses" in sp
            if "recharge" in sp and not self.save_ready.get(key, True):
                d6 = self.sim.rng.randint(1, 6)
                self.save_ready[key] = d6 >= sp["recharge"]
                self.sim.say("dice", "%s %s, Recharge %d: rolls %d -> %s" % (
                    c["name"], a["name"], sp["recharge"], d6, "regained" if self.save_ready[key] else "not yet"))
            if "recharge" in sp and not self.save_ready.get(key, True):
                continue
            if "uses" in sp and self.save_ready.get(key, sp["uses"]) <= 0:
                continue
            aim = {}
            targets = self.area_targets(me, sp, aim)
            foes = [t for t in targets if self.p.side(t) != self.p.side(me)]
            # an at-will one also when it lays a condition on a foe who lacks it (the Constrictor Snake's Constrict)
            fresh = any(not self.cond.get(t, {}).get(k["name"]) for t in foes for k in sp.get("conditions") or [])
            if not foes or (not limited and attacks and len(foes) < 2 and not fresh
                            and not self.in_multiattack(me, a)):
                continue
            score = (len(foes), limited, party_mod.average_damage(sp["dmg"]) if sp.get("dmg") else 0)
            if best is None or score > best[0]:
                best = (score, a, targets, aim)
        if not best:
            return False
        _, a, targets, aim = best
        sp, key = a["save"], (me, a["name"])
        if "recharge" in sp:
            self.save_ready[key] = False
        elif "uses" in sp:
            self.save_ready[key] = self.save_ready.get(key, sp["uses"]) - 1
        part = self.in_multiattack(me, a)
        self.use_save_action(me, a, targets, part, aim)
        # part of its Multiattack: its attacks follow (the bridge plays them)
        return not part or self.sim.down(me) or self.incapacitated(me)

    def area_text(self, sp):
        ar = sp["area"]
        return {"cone": lambda: "%d-foot Cone" % ar["size"],
                "line": lambda: "%d-foot Line, %d feet wide" % (ar["length"], ar["width"]),
                "emanation": lambda: "%d-foot Emanation" % ar["size"],
                "sphere": lambda: "%d-foot-radius Sphere within %d feet" % (ar["radius"], ar["range"]),
                "one": lambda: "one creature within %d feet" % ar["range"]}[ar["shape"]]()

    def use_save_action(self, me, a, targets, part=None, aim=None):
        with self.refereed(me, a, aim):                          # REFEREE-01: checked against the stat block after
            c, sp = self.sim.by_id(me), a["save"]
            rolled = [(dice(self.sim.rng, d), t) for d, t in ((sp.get("dmg"), sp.get("type")), (sp.get("dmg2"), sp.get("type2"))) if d]
            dmg = " plus ".join("%s = %d %s" % (sp["dmg"] if i == 0 else sp["dmg2"], n, t.capitalize()) for i, (n, t) in enumerate(rolled))
            self.sim.say("dice", "%s uses %s (the simulator as GM): DC %d %s save, %s%s on %s" % (
                c["name"], a["name"], sp["dc"], ABILITY[sp["save"]], self.area_text(sp), ", " + dmg if dmg else "",
                ", ".join(self.sim.by_id(t)["name"] for t in targets)))
            if a.get("gm"):
                self.sim.say("dice", "%s's %s: %s" % (c["name"], a["name"], a["gm"]))
            if part == "with":
                self.sim.say("dice", "%s's %s is part of its Multiattack: its attacks follow" % (c["name"], a["name"]))
            elif part == "replace":
                self.sim.say("dice", "%s's %s replaces one attack of its Multiattack: GM rules this (the simulator still "
                             "makes all its attacks)" % (c["name"], a["name"]))
            for t in targets:
                if self.sim.down(t):
                    continue
                saved, evasion = self.roll_save(me, t, sp, a["name"])
                for n, dtype in rolled:
                    amount = (area_damage(n, saved, evasion) if sp.get("half") else (0 if saved else (n // 2 if evasion else n)))
                    if amount:
                        self.sim.S.pcDamage(me, t, "", amount, False, dtype)
                        self.sim.settle(0.2)
                if not saved and not self.sim.down(t):
                    self.apply_save_conditions(me, t, sp, a["name"])

    def roll_save(self, src, t, sp, label):
        """d20 + the target's save (Bless, Danger Sense, Evasion, cover, environment as save_and_damage) vs the DC;
        Paralyzed, Stunned, Unconscious, Petrified fail Strength and Dexterity saves. -> (saved, Evasion applies)."""
        ability = sp["save"]
        parts, rng = self.save_parts(t, ability), self.sim.rng
        env = getattr(self.sim, "env", None)
        if env and ability == "dex" and src != t:
            parts["bonus"] += env.cover(src, t)
        __import__("martial_high").save_aid(self, src, t, ability, parts)    # MARTIAL-HIGH: Smite of Protection, Holy Nimbus
        if self.auto_fail(t, ability):
            self.sim.say("dice", "%s %s save against %s: fails automatically (%s)" % (
                self.sim.by_id(t)["name"], ABILITY[ability], label,
                next(n for n in HELPLESS if self.cond.get(t, {}).get(n))))
            return self.save_result(t, False, label), False
        d20 = rng.randint(1, 20)
        rolls = "d20 %d" % d20
        if any(k.get("name") == "Poisoned" for k in sp.get("conditions") or []) and self.antitoxin(t, "Poisoned"):
            parts["adv"] = True                                  # GM 2026-10-23: Antitoxin (an hour)
        dis = parts["dis"] or (ability == "dex" and bool(self.cond.get(t, {}).get("Restrained")))
        if parts["adv"] and not dis:
            second = rng.randint(1, 20)
            rolls = "d20 %d/%d (%s)" % (d20, second, (parts["adv_why"] + ": Advantage") if parts["adv_why"] else "Advantage")
            d20 = max(d20, second)
        elif dis and not parts["adv"]:
            second = rng.randint(1, 20)
            rolls = "d20 %d/%d (Disadvantage)" % (d20, second); d20 = min(d20, second)
        bless = rng.randint(1, 4) if parts["bless"] else 0
        total = d20 + parts["bonus"] + bless
        total += self.own_luck(t, total, sp["dc"], label)
        total = self.indomitable(t, total, sp["dc"], label, parts["bonus"] + bless)
        saved = total >= sp["dc"]
        self.sim.say("dice", "%s %s save against %s: %s %+d%s = %d vs DC %d -> %s%s" % (
            self.sim.by_id(t)["name"], ABILITY[ability], label, rolls, parts["bonus"], " +%d Bless" % bless if bless else "",
            total, sp["dc"], "success" if saved else "failure", " (Evasion)" if parts["evasion"] and sp.get("dmg") else ""))
        return self.save_result(t, saved, label), parts["evasion"] and ability == "dex"

    def apply_save_conditions(self, me, t, sp, label):
        src = self.sim.by_id(me)
        for k in sp.get("conditions") or []:
            name = k["name"]
            if k.get("max_size") and SIZES.index(size_of(self.sim.by_id(t))) > SIZES.index(k["max_size"]):
                continue
            if self.cond_immune(t, name):
                self.sim.say("dice", "%s is immune to the %s condition" % (self.sim.by_id(t)["name"], name))
                continue
            why = "(%s's %s)" % (src["name"], label)
            if name == "Grappled":
                self.add(t, "Grappled", "(escape DC %d, %s's %s)" % (k["escape"], src["name"], label), by=me,
                         dc=k["escape"], range=max(5, sp.get("area", {}).get("range", 5)))
                continue
            info = {"by": me, "save": sp["save"], "dc": sp["dc"], "lib": True}
            if k.get("until"):
                info["until"] = dict(k["until"])
                # "until the end of the <creature>'s next turn", given on its own turn: not this turn's end
                info["skip"] = 1 if k["until"] == {"who": "self", "when": "end"} and self.sim.S.active()[0] == me else 0
                why += " until the %s of %s next turn" % (k["until"]["when"], "its" if k["until"]["who"] == "target"
                                                          else src["name"] + "'s")
            if k.get("repeat"):
                info["repeat"] = "end"
                why += ", saving again at the end of each of its turns"
            if k.get("object"):
                info["object"] = dict(k["object"])
                why += " until the web is destroyed (AC %d; HP %d)" % (k["object"]["ac"], k["object"]["hp"])
            self.add(t, name, why, **info)
            if name == "Unconscious":
                self.add(t, "Prone", "(falls %s)" % why, by=me)

    def fumes_turn(self, me):
        """Burnt Othur Fumes (SRD 5.2.1): the save again at the start of each of its turns, 1d6 Poison on a failure;
        after three successful saves the poison ends."""
        f = self.__dict__.get("fumes", {}).get(me)
        if not f or self.sim.down(me):
            return
        import party as party_mod
        ok = self.condition_save(me, "con", f["dc"], f["name"], adv=self.antitoxin(me, "Poisoned"))
        if ok:
            f["ok"] += 1
            if f["ok"] >= 3:
                self.fumes.pop(me)
                self.sim.say("dice", "%s has saved three times: %s ends" % (self.sim.by_id(me)["name"], f["name"]))
        else:
            dmg = party_mod.roll(self.sim.rng, "1d6")
            self.sim.say("dice", "%s: 1d6 = %d Poison damage" % (f["name"], dmg))
            self.sim.S.pcDamage(f["by"], me, "", dmg, False, "poison")
            self.sim.settle(0.2)

    def tick(self, me, when):
        """Start or end of me's turn: conditions given "until the start/end of its (or the creature's) next turn"
        end; at the end of a creature's own turn it repeats the save of a condition that says so."""
        for t, conds in list(self.cond.items()):
            for name, info in list(conds.items()):
                u = info.get("until") if info.get("lib") else None
                if u and u["when"] == when and (t if u["who"] == "target" else info.get("by")) == me:
                    if info.get("skip"):
                        info["skip"] -= 1
                        continue
                    self.remove(t, name, "the %s of %s's turn" % (when, self.sim.by_id(me)["name"]))
                elif when == "start" and info.get("expires") is not None and info.get("by") == me and \
                        int(self.sim.S.round() or 0) >= info["expires"]:
                    self.remove(t, name, "%s's duration ends" % info.get("spell", name))     # SPELL-CASTER-01
                elif when == "end" and t == me and info.get("lib") and info.get("repeat") and name in conds:
                    if self.condition_save(t, info["save"], info["dc"], "%s (end of its turn)" % name,
                                           adv=self.antitoxin(t, name)):
                        self.remove(t, name, "saved")

    def save_rider(self, src, tgt, action):
        """An attack's save rider (the Ghoul's Claw): the target saves or has the condition."""
        a = next((a for a in self.sim.by_id(src).get("actions") or [] if a.get("name") == action), None)
        sp = (a or {}).get("save")
        if not sp or not sp.get("rider"):
            return
        ref = getattr(self.sim, "referee", None)                  # REFEREE-02: checked against the stat block after
        with ref.watch_rider(src, tgt, a) if ref else contextlib.nullcontext():
            tc = self.sim.by_id(tgt)
            kinds = [k.lower() for k in sp.get("not") or []]
            ttype = str(tc.get("type") or "").lower()
            if any(k == ttype or (k == "elf" and (tc.get("fey_ancestry") or "elf" in str(tc.get("species", "")).lower()))
                   for k in kinds):
                return
            saved, _ = self.roll_save(src, tgt, sp, action)
            if not saved:
                self.apply_save_conditions(src, tgt, sp, action)

    def break_free(self, me):
        """A character Restrained by a web strikes it with its weapon (its action): the web's AC and HP from the stat
        block; Restrained gives Disadvantage on the attack."""
        info = self.cond.get(me, {}).get("Restrained")
        if not info or not info.get("object") or self.incapacitated(me):
            return False
        c, obj, rng = self.sim.by_id(me), info["object"], self.sim.rng
        w = c.get("weapon") or c.get("ranged") or {"atk": 0, "dmg": "1d4"}
        d20 = min(rng.randint(1, 20), rng.randint(1, 20))
        total = d20 + int(w.get("atk", 0))
        if total >= obj["ac"]:
            dmg = party_mod.roll(rng, str(w.get("dmg") or "1d4"))
            obj["hp"] -= dmg
            self.sim.say("dice", "%s strikes the web (AC %d): d20 %d (Disadvantage, Restrained) %+d = %d -> hit, %d damage (%s)" % (
                c["name"], obj["ac"], d20, int(w.get("atk", 0)), total, dmg,
                "destroyed" if obj["hp"] <= 0 else "%d HP left" % obj["hp"]))
            if obj["hp"] <= 0:
                self.remove(me, "Restrained", "the web is destroyed")
        else:
            self.sim.say("dice", "%s strikes the web (AC %d): d20 %d (Disadvantage, Restrained) %+d = %d -> miss" % (
                c["name"], obj["ac"], d20, int(w.get("atk", 0)), total))
        return True

    def area_targets(self, me, sp, aim=None):
        """The creatures a save action catches, aimed the way the GM would: the most foes, no ally the damage or the
        condition would harm; [] when nothing fits. aim (REFEREE-01): gets where it was aimed (origin in squares and
        direction; the one creature's id)."""
        aim = {} if aim is None else aim
        ar, u, side = sp["area"], self.sim.sc.get("units", 5), self.p.side(me)
        alive = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.sim.down(o["id"])
                 and not self.p.blocked(me, o["id"])]
        foes = [o for o in alive if self.p.side(o) != side]
        harms = lambda t: self.p.side(t) == side and not ar.get("enemies") and not (sp.get("type") and not sp.get("conditions")
                                                                                  and self.immune(t, sp["type"]))
        feet = lambda q: (q[0] * u, q[1] * u)
        if ar["shape"] == "cone":
            got = self.cone_targets(me, {"size": ar["size"], "type": sp.get("type") or "-"}, aim)
            if ar.get("enemies"):
                got = [t for t in got if self.p.side(t) != side]
            return got if not any(harms(t) for t in got) else []
        if ar["shape"] == "emanation":
            aim["origin"] = list(self.p.pos(me))
            got = [t for t in alive if self.ft_between(me, t) <= ar["size"]]
            got = [t for t in got if self.p.side(t) != side] if ar.get("enemies") else got
            return got if not any(harms(t) for t in got) else []
        if ar["shape"] == "one":
            pick = [t for t in foes if self.ft_between(me, t) <= ar["range"] and (not ar.get("sees") or self.sim.sees(me, t))
                    and (not ar.get("max_size") or SIZES.index(size_of(self.sim.by_id(t))) <= SIZES.index(ar["max_size"]))
                    and not any(self.cond.get(t, {}).get(k["name"]) for k in sp.get("conditions") or [] if not sp.get("dmg"))]
            pick.sort(key=lambda t: (self.ft_between(me, t), self.p.hp_left(t)))
            if pick:
                aim["target"] = pick[0]
            return pick[:1]
        here = feet(self.p.pos(me))
        best = []
        if ar["shape"] == "line":
            reach = ar["length"] + (self.span(me) - 1) / 2 * u
            for f in foes:
                toward = (feet(self.p.pos(f))[0] - here[0], feet(self.p.pos(f))[1] - here[1])
                if not any(toward):
                    continue
                got = [t for t in alive if party_mod.in_line(here, toward, feet(self.p.pos(t)), reach, ar["width"] + (self.span(t) - 1) * u)]
                n = len([t for t in got if self.p.side(t) != side])
                if got and not any(harms(t) for t in got) and n > len([t for t in best if self.p.side(t) != side]):
                    best = got
                    aim.update(origin=list(self.p.pos(me)), toward=list(toward))
            return [t for t in best if self.p.side(t) != side] if ar.get("enemies") else best
        if ar["shape"] == "sphere":
            for f in foes:
                pt = feet(self.p.pos(f))
                if max(abs(pt[0] - here[0]), abs(pt[1] - here[1])) > ar["range"]:
                    continue
                got = [t for t in alive if max(0, max(abs(feet(self.p.pos(t))[0] - pt[0]), abs(feet(self.p.pos(t))[1] - pt[1]))
                                                    - (self.span(t) - 1) / 2 * u) <= ar["radius"]]
                n = len([t for t in got if self.p.side(t) != side])
                if got and not any(harms(t) for t in got) and n > len([t for t in best if self.p.side(t) != side]):
                    best = got
                    aim["origin"] = list(self.p.pos(f))
            return [t for t in best if self.p.side(t) != side] if ar.get("enemies") else best
        return []
