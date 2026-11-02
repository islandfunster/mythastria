"""GM 2026-10-23 ("I do believe meta magic is part of the SRD therefore, sorcerers should have those necessary tools";
then "Let's do the sorcerer slice here"): the Sorcerer's own tools in a live fight, checked against SRD 5.2.1 (Sorcerer:
Innate Sorcery, Font of Magic, Metamagic, Sorcery Incarnate). The state lives on the party, shared with the simulator's
own turns (sim/party.py: sorcery, innate_left, innate_until, extended, quickened_turn).

- Innate Sorcery (level 1): a Bonus Action, two uses per Long Rest, for 1 minute (10 rounds): the Sorcerer's spell save
  DC +1, and Advantage on the attack rolls of its spells (Party.spell_dc and Party.attack read Party.innate_on).
- Sorcery Incarnate (level 7): with no use of Innate Sorcery left, 2 Sorcery Points start it; while it is active, up to
  two Metamagic options on each spell.
- Font of Magic (level 2): Sorcery Points equal to the Sorcerer level, never more. A spell slot becomes points equal to
  its level (no action); points become one slot of level 1-5 as a Bonus Action (level 1: 2 points, 2: 3, 3: 5, 4: 6,
  5: 7; the level needs Sorcerer level 2, 3, 5, 7, 9).
- Metamagic (level 2): one option per spell (Empowered and Seeking can join another), paid in points when the spell is
  cast. Played here, on the spells and attack cantrips of the sheet:
  Careful (1: up to the Charisma modifier of creatures in an area succeed on the save and take no damage; the allies
  in the area unless the player names others), Distant (1: double range; Touch becomes 30 ft), Empowered (1: up to the
  Charisma modifier of damage dice rolled again, the lowest ones), Extended (1: a Concentration spell; Advantage on the
  saves to keep it; its doubled duration outlasts any fight), Heightened (2: one creature has Disadvantage on its saves
  against the spell; the target, or the foe with the most Hit Points left in an area unless the player names one),
  Quickened (2: an Action spell as a Bonus Action; not after a level 1+ spell this turn, and no level 1+ spell after
  it), Seeking (1: a missed spell attack roll is rolled again; paid only when it misses), Subtle (1: no Verbal, Somatic
  or Material components; nothing at this table counters a spell yet, so it shows in the log), Transmuted (1: acid,
  cold, fire, lightning, poison or thunder instead), Twinned (1: one more creature for a spell whose higher slot adds
  one: Hold Person here).
  Not played (the GM rules it, docs/development/CLASS_FEATURES_AUDIT.md): Empowered Spell on an attack cantrip (the
  table rolls a cantrip's damage dice itself).

GM 2026-10-28 ("heroes 20", the Sorcerer to level 20):
- Dragon Wings (Draconic Sorcery 14): a Bonus Action, once per Long Rest (3 Sorcery Points restore the use, no action):
  a Fly Speed of 60 ft for 1 hour (it outlasts any fight), dismissed at will (no action). The wings are the Fly
  spell's "Flying" record (sim/battle_spells.py: the turn's movement, falling when they go while aloft), marked
  wings=True and held by no spell, so no Concentration ends them. Play live; the computer-played Sorcerer keeps its
  Bonus Action for Innate Sorcery.
- Arcane Apotheosis (Sorcerer 20): while Innate Sorcery is active, one Metamagic option on each of the Sorcerer's own
  turns costs no Sorcery Points (the costliest one chosen; Seeking Spell when it misses). Play live and the
  computer-played Sorcerer (charge).
- Dragon Companion (Draconic Sorcery 18) stays Ask the GM: Summon Dragon is a summoned creature, still the GM's
  (sim/live_general.py GM_WHY).
"""
import party as party_mod

OPS = ("innate_sorcery", "font_convert", "font_create", "dragon_wings", "fold_wings")
INNATE_USES, INNATE_ROUNDS = 2, 10
CREATE_COST = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7}
CREATE_LEVEL = {1: 2, 2: 3, 3: 5, 4: 7, 5: 9}
COST = {"Careful Spell": 1, "Distant Spell": 1, "Empowered Spell": 1, "Extended Spell": 1, "Heightened Spell": 2,
        "Quickened Spell": 2, "Seeking Spell": 1, "Subtle Spell": 1, "Transmuted Spell": 1, "Twinned Spell": 1}
ON_TOP = ("Empowered Spell", "Seeking Spell")      # usable with another option on the same spell
TRANSMUTE = ("acid", "cold", "fire", "lightning", "poison", "thunder")
DAMAGE = {"Burning Hands": "fire", "Fireball": "fire", "Cone of Cold": "cold"}   # the live damage spells (sim/live_spells.py)
SAVES = {"Burning Hands", "Fireball", "Sleep", "Hold Person", "Cone of Cold", "Hold Monster"}   # they force a saving throw
TWIN = {"Hold Person", "Hold Monster"}                           # one more creature per slot level above its own
DETAIL = {"Quickened Spell": "cast as a Bonus Action", "Subtle Spell": "no Verbal, Somatic or Material components",
          "Extended Spell": "Advantage on the saves to keep its Concentration", "Twinned Spell": "one more creature",
          "Distant Spell": "range doubled (Touch: 30 ft)"}
WINGS_COST, WINGS_FT = 3, 60                                     # Dragon Wings: the points that restore it, its Fly Speed
FLYING = "Flying"                                                # sim/battle_spells.py FLYING: the Fly Speed's record


class SorceryError(ValueError):
    pass


def of(fight):
    """The fight's Sorcery (one per LiveFight)."""
    s = getattr(fight, "sorcery", None)
    if s is None:
        s = fight.sorcery = Sorcery(fight)
    return s


def is_sorcerer(c):
    return c.get("class") == "sorcerer" or bool(c.get("innate_sorcery")) or bool(c.get("sorcery_points"))


def sorcerer_level(c):
    return int(c.get("sorcerer_level") or c.get("level", 1) or 1)


def cha_mod(c):
    return max(1, int(c.get("cha_mod", c.get("spell_mod", 1)) or 1))


def _state(party, name):
    d = getattr(party, name, None)
    if d is None:
        d = {}
        setattr(party, name, d)
    return d


def points(party, me):
    """Sorcery Points left in this fight (Party.__init__ starts them at the sheet's number)."""
    pool = _state(party, "sorcery")
    if me not in pool:
        pool[me] = int(party.sim.by_id(me).get("sorcery_points", 0) or 0)
    return pool[me]


def set_points(party, me, n):
    points(party, me)
    party.sorcery[me] = n


def innate_left(party, me):
    left = _state(party, "innate_left")
    if me not in left:
        left[me] = int(party.sim.by_id(me).get("innate_sorcery", 0) or 0)
    return left[me]


def rounds_left(party, me):
    until = _state(party, "innate_until").get(me)
    return max(0, until - int(party.s.round()) + 1) if until is not None else 0


def slot_pool(party, me):
    return party.pools.setdefault(me, [party.slots.get(me, 0)])


# ---------------------------------------------------------------------- levels 14 and 20 (GM 2026-10-28)
def wings_left(party, me):
    """Dragon Wings' use (one per Long Rest; sim/rests.py carries it from fight to fight)."""
    left = _state(party, "wings_left")
    if me not in left:
        left[me] = 1 if party.sim.by_id(me).get("dragon_wings") else 0
    return left[me]


def wings_on(party, me):
    gm = getattr(party.sim, "gm_rules", None)
    return bool(gm and ((gm.cond.get(me) or {}).get(FLYING) or {}).get("wings"))


def spread_wings(party, me, c):
    """Dragon Wings' Bonus Action (checked by the caller): its use, or 3 Sorcery Points restore it first."""
    if wings_left(party, me) <= 0:
        set_points(party, me, points(party, me) - WINGS_COST)
        party.sim.say("dice", "%s spends %d Sorcery Points to restore Dragon Wings (no action): %d left" % (
            c["name"], WINGS_COST, points(party, me)))
    else:
        party.wings_left[me] -= 1
    party.use_bonus(me)
    party.sim.say("dice", "%s calls up draconic wings (Dragon Wings, Bonus Action): Fly Speed %d ft for 1 hour" % (
        c["name"], WINGS_FT))
    party.sim.gm_rules.add(me, FLYING, "(Dragon Wings: Fly Speed %d ft, 1 hour or until dismissed)" % WINGS_FT,
                           by=me, wings=True)


def fold_wings(party, me, c):
    party.sim.gm_rules.remove(me, FLYING, "%s dismisses Dragon Wings (no action)" % c["name"])


def apotheosis_free(party, me):
    """Arcane Apotheosis (Sorcerer 20): True while Innate Sorcery is active, on the Sorcerer's own turn, and this turn's
    free Metamagic option is not used yet."""
    c = party.sim.by_id(me)
    return bool(c.get("arcane_apotheosis")) and bool(party.innate_on(me)) and party.s.active()[0] == me \
        and _state(party, "apotheosis").get(me) != party.s.turnSerial


def charge(party, me, cost):
    """The computer-played Sorcerer's Metamagic option: its points, or none (Arcane Apotheosis). Returns how it was
    paid, for the log."""
    if apotheosis_free(party, me):
        _state(party, "apotheosis")[me] = party.s.turnSerial
        return "no Sorcery Points: Arcane Apotheosis"
    set_points(party, me, points(party, me) - cost)
    return "%d Sorcery Point%s, %d left" % (cost, "" if cost == 1 else "s", points(party, me))


def unleash(party, me, c):
    """Innate Sorcery's Bonus Action (checked by the caller): a use, or 2 Sorcery Points (Sorcery Incarnate). Shared by
    Play live and the computer-played Sorcerer (Party.turn_sorcerer)."""
    party.use_bonus(me)
    if innate_left(party, me) > 0:
        party.innate_left[me] -= 1
        how = "%d use%s left" % (party.innate_left[me], "" if party.innate_left[me] == 1 else "s")
    else:
        set_points(party, me, points(party, me) - 2)
        how = "Sorcery Incarnate: 2 Sorcery Points, %d left" % points(party, me)
    _state(party, "innate_until")[me] = int(party.s.round()) + INNATE_ROUNDS - 1
    party.sim.say("dice", "%s unleashes Innate Sorcery (Bonus Action, 1 minute): spell save DC +1, Advantage on spell "
                  "attack rolls%s (%s)" % (c["name"], ", up to two Metamagic options per spell (Sorcery Incarnate)"
                                           if sorcerer_level(c) >= 7 else "", how))


def create_slot(party, me, c, lv):
    """Font of Magic: Sorcery Points into one slot of level lv (checked by the caller; the Bonus Action is the caller's)."""
    set_points(party, me, points(party, me) - CREATE_COST[lv])
    pool = slot_pool(party, me)
    while len(pool) < lv:
        pool.append(0)
    pool[lv - 1] += 1
    party.slots[me] = sum(pool)
    party.sim.say("dice", "%s turns %d Sorcery Points into a level %d spell slot (Font of Magic, Bonus Action): %d points "
                  "left" % (c["name"], CREATE_COST[lv], lv, points(party, me)))


class Sorcery:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    def say(self, text):
        self.sim.say("dice", text)

    def _able(self, me):
        import live_actions
        actions = getattr(self.fight, "actions", None)
        if actions is None:
            return
        try:
            actions.able(me)
        except live_actions.ActionError as e:
            raise SorceryError(str(e))

    def summary(self, me):
        """For the sheet: points, Innate Sorcery, the Metamagic known and how many options a spell may take now."""
        c, party = self.sim.by_id(me), self.party
        if not is_sorcerer(c):
            return None
        return {"points": points(party, me), "max": int(c.get("sorcery_points", 0) or 0),
                "innate_left": innate_left(party, me), "innate_rounds": rounds_left(party, me),
                "metamagic": [{"name": m, "cost": COST.get(m, 1)} for m in c.get("metamagic") or []],
                "per_spell": self.per_spell(me),
                # GM 2026-10-28: Arcane Apotheosis ("free": this turn's option costs nothing), Dragon Wings
                "apotheosis": None if not c.get("arcane_apotheosis") else "free" if apotheosis_free(party, me)
                else "used" if party.innate_on(me) and _state(party, "apotheosis").get(me) == party.s.turnSerial else "off",
                "wings": None if not c.get("dragon_wings") else {"on": wings_on(party, me), "left": wings_left(party, me)}}

    def per_spell(self, me):
        return 2 if sorcerer_level(self.sim.by_id(me)) >= 7 and self.party.innate_on(me) else 1

    # ------------------------------------------------------------------ Innate Sorcery, Font of Magic
    def actions(self, me):
        """The Sorcerer's buttons, with the other actions (sim/live_actions.py offers)."""
        c, party, out = self.sim.by_id(me), self.party, []
        if not is_sorcerer(c):
            return out

        def entry(e, check):
            try:
                check()
                e["ready"] = True
            except SorceryError as err:
                e["ready"], e["why"] = False, str(err)
            out.append(e)
        entry({"op": "innate_sorcery", "label": "Innate Sorcery", "time": "bonus", "bonus": False,
               "uses": innate_left(party, me), "rounds": rounds_left(party, me)}, lambda: self.check_innate(me))
        if int(c.get("sorcery_points", 0) or 0):
            pool, sp = slot_pool(party, me), points(party, me)
            for lv in range(1, len(pool) + 1):
                if pool[lv - 1] > 0:
                    entry({"op": "font_convert", "level": lv, "time": "free", "bonus": False, "points": sp,
                           "label": "Font of Magic: a level %d slot into %d Sorcery Point%s" % (lv, lv, "" if lv == 1 else "s")},
                          lambda lv=lv: self.check_convert(me, lv))
            for lv, cost in CREATE_COST.items():
                if sorcerer_level(c) >= CREATE_LEVEL[lv]:
                    entry({"op": "font_create", "level": lv, "time": "bonus", "bonus": False, "points": sp, "cost": cost,
                           "label": "Font of Magic: %d Sorcery Points into a level %d slot" % (cost, lv)},
                          lambda lv=lv: self.check_create(me, lv))
        if c.get("dragon_wings"):                                # GM 2026-10-28: Draconic Sorcery 14
            if wings_on(party, me):
                entry({"op": "fold_wings", "label": "Dragon Wings: dismiss them", "time": "free", "bonus": False},
                      lambda: self._able(me))
            else:
                entry({"op": "dragon_wings", "label": "Dragon Wings: Fly Speed %d ft%s" % (
                    WINGS_FT, "" if wings_left(party, me) else " (%d Sorcery Points restore it)" % WINGS_COST),
                    "time": "bonus", "bonus": False, "uses": wings_left(party, me)}, lambda: self.check_wings(me))
        return out

    def check_wings(self, me):
        party, c = self.party, self.sim.by_id(me)
        self._able(me)
        if not c.get("dragon_wings"):
            raise SorceryError("Dragon Wings is Draconic Sorcery's (Sorcerer level 14).")
        if wings_on(party, me):
            raise SorceryError("%s's wings are out already." % c["name"])
        gm = self.sim.gm_rules
        if gm and gm.has(me, FLYING):
            raise SorceryError("%s already has a Fly Speed (the Fly spell)." % c["name"])
        if wings_left(party, me) <= 0 and points(party, me) < WINGS_COST:
            raise SorceryError("Dragon Wings is used (once per Long Rest); %d Sorcery Points restore it (%d left)." % (
                WINGS_COST, points(party, me)))
        if not party.bonus_free(me):
            raise SorceryError("%s's Bonus Action is used this turn." % c["name"])

    def check_innate(self, me):
        party, c = self.party, self.sim.by_id(me)
        self._able(me)
        if party.innate_on(me):
            n = rounds_left(party, me)
            raise SorceryError("Innate Sorcery is active (%d round%s left)." % (n, "" if n == 1 else "s"))
        if innate_left(party, me) <= 0:
            if sorcerer_level(c) < 7:
                raise SorceryError("No use of Innate Sorcery left (two per Long Rest).")
            if points(party, me) < 2:
                raise SorceryError("No use of Innate Sorcery left; Sorcery Incarnate needs 2 Sorcery Points (%d left)."
                                   % points(party, me))
        if not party.bonus_free(me):
            raise SorceryError("%s's Bonus Action is used this turn." % c["name"])

    def check_convert(self, me, lv):
        party, c = self.party, self.sim.by_id(me)
        self._able(me)
        most = int(c.get("sorcery_points", 0) or 0)
        if not most:
            raise SorceryError("Font of Magic comes at Sorcerer level 2.")
        pool = slot_pool(party, me)
        if not 1 <= lv <= len(pool) or pool[lv - 1] <= 0:
            raise SorceryError("No level %d spell slot left." % lv)
        if points(party, me) + lv > most:
            raise SorceryError("That would make %d Sorcery Points: the most is %d at this level." % (points(party, me) + lv, most))

    def check_create(self, me, lv):
        party, c = self.party, self.sim.by_id(me)
        self._able(me)
        if not int(c.get("sorcery_points", 0) or 0):
            raise SorceryError("Font of Magic comes at Sorcerer level 2.")
        if lv not in CREATE_COST:
            raise SorceryError("Font of Magic creates a slot of level 1 to 5.")
        if sorcerer_level(c) < CREATE_LEVEL[lv]:
            raise SorceryError("A level %d slot needs Sorcerer level %d." % (lv, CREATE_LEVEL[lv]))
        if points(party, me) < CREATE_COST[lv]:
            raise SorceryError("A level %d slot costs %d Sorcery Points (%d left)." % (lv, CREATE_COST[lv], points(party, me)))
        if not party.bonus_free(me):
            raise SorceryError("%s's Bonus Action is used this turn." % c["name"])

    def do(self, me, cmd):
        """innate_sorcery / font_convert / font_create. Returns how it was paid: "bonus" or "free"."""
        op, party, c = cmd.get("op"), self.party, self.sim.by_id(me)
        if not is_sorcerer(c):
            raise SorceryError("%s is not a Sorcerer." % c["name"])
        if op == "innate_sorcery":
            self.check_innate(me)
            unleash(party, me, c)
            return "bonus"
        if op == "dragon_wings":
            self.check_wings(me)
            spread_wings(party, me, c)
            return "bonus"
        if op == "fold_wings":
            self._able(me)
            if not wings_on(party, me):
                raise SorceryError("%s has no draconic wings out." % c["name"])
            fold_wings(party, me, c)
            return "free"
        try:
            lv = int(cmd.get("level"))
        except (TypeError, ValueError):
            raise SorceryError("Choose a slot level.")
        pool = slot_pool(party, me)
        if op == "font_convert":
            self.check_convert(me, lv)
            pool[lv - 1] -= 1
            party.slots[me] = sum(pool)
            set_points(party, me, points(party, me) + lv)
            self.say("%s turns a level %d spell slot into %d Sorcery Point%s (Font of Magic, no action): %d now" % (
                c["name"], lv, lv, "" if lv == 1 else "s", points(party, me)))
            return "free"
        if op == "font_create":
            self.check_create(me, lv)
            party.use_bonus(me)
            create_slot(party, me, c, lv)
            return "bonus"
        raise SorceryError("Not a Sorcerer action.")

    # ------------------------------------------------------------------ Metamagic
    @staticmethod
    def chosen(cmd):
        m = (cmd or {}).get("metamagic")
        if not m:
            return []
        return [m] if isinstance(m, str) else list(m)

    def plan(self, me, name, s, cmd, attack=False, check_only=False):
        """The Metamagic options chosen for this spell (cmd["metamagic"]), checked; returns (its casting entry as they
        change it, the plan). Nothing is spent. attack: an attack cantrip of the sheet (s: time, range_ft, kind)."""
        c, party = self.sim.by_id(me), self.party
        metas = self.chosen(cmd)
        if not metas:
            return s, None
        known = list(c.get("metamagic") or [])
        if not known:
            raise SorceryError("%s has no Metamagic (Sorcerer level 2)." % c["name"])
        for m in metas:
            if m not in COST:
                raise SorceryError("%s is not a Metamagic option." % m)
            if m not in known:
                raise SorceryError("%s does not know %s." % (c["name"], m))
        if len(set(metas)) != len(metas):
            raise SorceryError("Each Metamagic option once on a spell.")
        if len([m for m in metas if m not in ON_TOP]) > self.per_spell(me):
            raise SorceryError("One Metamagic option per spell%s (Empowered and Seeking can join another)." % (
                "; two while Innate Sorcery is active (Sorcery Incarnate)" if sorcerer_level(c) >= 7 else ""))
        need = sum(COST[m] for m in metas)
        free = None                                              # GM 2026-10-28: Arcane Apotheosis, the costliest option
        if apotheosis_free(party, me):
            paid = [m for m in metas if m != "Seeking Spell"]
            free = max(paid, key=lambda m: COST[m]) if paid else None
            need -= COST[free] if free else COST["Seeking Spell"]   # Seeking alone: free when it misses
        if points(party, me) < need:
            raise SorceryError("%s cost%s %d Sorcery Point%s (%d left)." % (
                " and ".join(metas), "s" if len(metas) == 1 else "", need, "" if need == 1 else "s", points(party, me)))
        s, plan = dict(s), {"metas": metas, "cost": sum(COST[m] for m in metas if m not in ("Seeking Spell", free)),
                            "free": free}
        for m in metas:
            if m == "Quickened Spell":
                if s.get("time") != "action":
                    raise SorceryError("Quickened Spell changes a spell cast with an Action.")
                if party.slot_turn.get(me) == party.s.turnSerial:
                    raise SorceryError("Quickened Spell: not after a level 1+ spell this turn.")
                s["time"], plan["quick"] = "bonus", True
            elif m == "Distant Spell":
                if not s.get("range_ft"):
                    raise SorceryError("Distant Spell needs a spell with a range (%s starts from the caster)." % name)
                s["range_ft"] = 30 if s["range_ft"] <= 5 else s["range_ft"] * 2
            elif m == "Careful Spell":                         # SPELL-EFFECTS-01: and the area spells of sim/more_spells.py
                if attack or not (name in DAMAGE or s.get("area_damage")):
                    raise SorceryError("Careful Spell protects creatures caught in an area spell (Burning Hands, Fireball, Cone of Cold).")
                plan["careful"] = True
            elif m == "Transmuted Spell":
                kind = s.get("kind") if attack else DAMAGE.get(name) or s.get("kind")
                if kind not in TRANSMUTE:
                    raise SorceryError("Transmuted Spell changes acid, cold, fire, lightning, poison or thunder damage.")
                new = (cmd or {}).get("transmute")
                if not check_only and (new not in TRANSMUTE or new == kind):
                    raise SorceryError("Transmuted Spell: choose the new damage type (%s)." % ", ".join(
                        k for k in TRANSMUTE if k != kind))
                plan["kind"], plan["was"] = new, kind
            elif m == "Extended Spell":                        # SPELL-EFFECTS-01: or one lasting 1 minute or longer
                if attack or not (s.get("concentration") or (s.get("rounds") or 0) >= 10):
                    raise SorceryError("Extended Spell needs a spell lasting 1 minute or longer (a Concentration spell, "
                                       "or Charm Person and the like).")
            elif m == "Empowered Spell":
                if attack:
                    raise SorceryError("Empowered Spell on an attack cantrip: the table rolls its damage dice itself; the GM rules it.")
                if not (name in DAMAGE or s.get("kind") and s.get("area_damage")):
                    raise SorceryError("Empowered Spell rerolls a spell's damage dice.")
                plan["empower"] = cha_mod(c)
            elif m == "Heightened Spell":
                if attack or not (name in SAVES or s.get("save") is True):
                    raise SorceryError("Heightened Spell needs a spell that forces a saving throw.")
                plan["heighten"] = True
            elif m == "Seeking Spell":
                if not attack:
                    raise SorceryError("Seeking Spell rerolls a spell attack roll: use it on an attack cantrip.")
                plan["seeking"] = True
            elif m == "Twinned Spell":
                if attack or not (name in TWIN or s.get("twin")):
                    raise SorceryError("Twinned Spell needs a spell whose higher slot adds a creature (Hold Person, Charm Person, Animal Friendship here); "
                                       "not a cantrip.")
                s["shape"], s["max_targets"], plan["twin"] = "creatures", 2, True
        return s, plan

    def options(self, me, name, s, attack=False):
        """[{name, cost, ready, why}] for one spell or attack cantrip card."""
        c, out = self.sim.by_id(me), []
        for m in c.get("metamagic") or []:
            e = {"name": m, "cost": COST.get(m, 1)}
            try:
                changed, plan = self.plan(me, name, s, {"metamagic": [m]}, attack=attack, check_only=True)
                e["ready"] = True
                if m == "Transmuted Spell":
                    e["types"] = [k for k in TRANSMUTE if k != plan["was"]]
                if m == "Distant Spell":
                    e["range_ft"] = changed["range_ft"]
                if m == "Twinned Spell":
                    e["max_targets"] = 2
            except SorceryError as err:
                e["ready"], e["why"] = False, str(err)
            out.append(e)
        return out

    def attack_plan(self, me, w, cmd):
        """Metamagic on an attack cantrip: returns (the plan, the weapon as changed: range, damage type)."""
        if not party_mod.spell_attack(w):
            raise SorceryError("Metamagic changes a spell; %s is not one." % w.get("name", "that attack"))
        s = {"time": "action", "range_ft": w.get("reach", 5), "kind": party_mod.damage_type(w)}
        s, plan = self.plan(me, w["name"], s, cmd, attack=True)
        w = dict(w, reach=s["range_ft"])
        if plan.get("kind"):
            w["dmgtype"] = plan["kind"]
        return plan, w

    def attack_options(self, me, w):
        if not party_mod.spell_attack(w) or not self.sim.by_id(me).get("metamagic"):
            return None
        return self.options(me, w["name"], {"time": "action", "range_ft": w.get("reach", 5),
                                            "kind": party_mod.damage_type(w)}, attack=True)

    def careful(self, me, caught, cmd):
        """The creatures Careful Spell protects: the ones the player names (in the area), else the caster's allies in
        it; at most the Charisma modifier."""
        c, party = self.sim.by_id(me), self.party
        want = (cmd or {}).get("careful")
        pick = [t for t in want if t in caught] if isinstance(want, list) and want else \
            [t for t in caught if t == me or t in party.allies(me)]
        return pick[:cha_mod(c)]

    def heightened(self, me, caught, cmd):
        """The creature with Disadvantage (Heightened Spell): the one the player names, else the foe with the most Hit
        Points left (the only target of a one-creature spell)."""
        party, want = self.party, (cmd or {}).get("heightened")
        if want in caught:
            return [want]
        foes = [t for t in caught if t in party.foes(me)] or list(caught)
        return [max(foes, key=lambda t: party.hp_left(t))] if foes else []

    def pay(self, me, name, plan, careful=(), heightened=()):
        """Spend the points (Seeking waits for a miss) and say what each option does."""
        party, c = self.party, self.sim.by_id(me)
        set_points(party, me, points(party, me) - plan["cost"])
        if plan.get("free"):
            _state(party, "apotheosis")[me] = party.s.turnSerial
        for m in plan["metas"]:
            if m == "Seeking Spell":
                continue
            detail = DETAIL.get(m, "")
            if m == "Careful Spell":
                one = len(careful) == 1
                detail = ("%s succeed%s on the save and take%s no damage" % (
                    " and ".join(party.name(t) for t in careful), "s" if one else "", "s" if one else "")
                          if careful else "no creature in the area to protect")
            elif m == "Transmuted Spell":
                detail = "%s damage instead of %s" % (plan["kind"].capitalize(), plan["was"].capitalize())
            elif m == "Empowered Spell":
                detail = "up to %d damage dice rolled again" % plan["empower"]
            elif m == "Heightened Spell":
                detail = ("%s has Disadvantage on its saves against it" % party.name(heightened[0])) if heightened \
                    else "no creature to affect"
            paid = "no Sorcery Points: Arcane Apotheosis" if m == plan.get("free") else \
                "%d Sorcery Point%s" % (COST[m], "" if COST[m] == 1 else "s")
            self.say("%s uses %s on %s (%s): %s" % (c["name"], m, name, paid, detail))
        if plan["cost"]:
            self.say("%s has %d Sorcery Point%s left" % (c["name"], points(party, me), "" if points(party, me) == 1 else "s"))
        if plan.get("quick"):
            _state(party, "quickened_turn")[me] = party.s.turnSerial

    def pay_seeking(self, me, name):
        party, c = self.party, self.sim.by_id(me)
        if apotheosis_free(party, me):                           # GM 2026-10-28: Arcane Apotheosis
            _state(party, "apotheosis")[me] = party.s.turnSerial
            self.say("%s uses Seeking Spell on %s (no Sorcery Points: Arcane Apotheosis): the missed attack roll is rolled "
                     "again" % (c["name"], name))
            return
        set_points(party, me, points(party, me) - COST["Seeking Spell"])
        self.say("%s uses Seeking Spell on %s (1 Sorcery Point): the missed attack roll is rolled again (%d left)" % (
            c["name"], name, points(party, me)))
