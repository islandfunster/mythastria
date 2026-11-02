"""EPIC-BOONS-01 (GM 2026-10-28: the Epic Boons play in a fight instead of going to Ask the GM). The seven Epic
Boon feats of SRD 5.2.1 (level 19; sim/srd_character_rules.json "feats", category "epic boon"). Each one's +1 to an
ability score (to 30 at most) is the character builder's (sim/character_build.py _feat_choice). Here, the rest, for a
character played at the table (Play live) and for the computer-played party alike:

- Boon of Combat Prowess, Peerless Aim: when the character misses with an attack roll it can hit instead; then not
  again until the start of its next turn. Computer: on every miss it may. Play live: asked (not a Reaction).
- Boon of Dimensional Travel, Blink Steps: right after the Attack action or the Magic action, a teleport of up to 30 ft
  to an unoccupied space it can see (no Opportunity Attack). Play live: a sheet button once that action is taken (a
  square to click). Computer: a member that fights from range (a ranged weapon or a spellcaster) with a foe beside it
  blinks to the square within 30 ft farthest from the foes, after an attack roll or a spell slot this turn.
- Boon of Fate, Improve Fate: when it or another creature within 60 ft succeeds or fails a D20 Test, 2d4 rolled and
  added to or taken off that d20 roll; once until Initiative is rolled again (each fight) or a Short or Long Rest.
  Played on attack rolls (an ally's miss, a foe's hit on the holder or an ally) and saving throws (an ally's failure,
  a foe's success): asked live where 2d4 could change the outcome; the computer uses it when it needs 5 or less.
  Ability checks: Ask the GM.
- Boon of Irresistible Offense: its Bludgeoning, Piercing and Slashing damage ignores Resistance (Overcome Defenses);
  a 20 on the d20 of its attack roll deals extra damage equal to the score the boon raised, of the attack's type
  (Overwhelming Strike). Both always on (sim/fight_state.py reads sim_overcome and sim_overwhelm).
- Boon of Spell Recall, Free Casting: each spell cast with a level 1-4 slot rolls 1d4; on the slot's level the slot
  isn't expended (Party.spend_slot).
- Boon of the Night Spirit: Shadowy Form, in Dim Light or Darkness Resistance to all damage but Psychic and Radiant
  (sim/fight_state.py, sim_shadowy; the light where it stands: Sim.light_level). Merge with Shadows, in Dim Light or
  Darkness a Bonus Action gives it the Invisible condition, ended right after it takes an action, a Bonus Action or a
  Reaction (the attack rolls of that action keep it). Play live: a sheet button. Computer: at the end of its turn with
  the Bonus Action free (before a Rogue's Cunning Action Hide).
- Boon of Truesight: Truesight 60 ft in its senses (the builder), which the sight rules already read (sim/map_layers.py:
  Invisible creatures, magical Darkness). Seeing through illusions, true forms and into the Ethereal Plane: Ask the GM.
"""
PEERLESS, BLINK, FATE = "Boon of Combat Prowess", "Boon of Dimensional Travel", "Boon of Fate"
OFFENSE, RECALL, NIGHT, TRUESIGHT = "Boon of Irresistible Offense", "Boon of Spell Recall", "Boon of the Night Spirit", \
    "Boon of Truesight"
FLAGS = {PEERLESS: "combat_prowess", BLINK: "dimensional_travel", FATE: "boon_fate", OFFENSE: "irresistible_offense",
         RECALL: "spell_recall", NIGHT: "night_spirit", TRUESIGHT: "boon_truesight"}
PLAYED = set(FLAGS)                                              # none goes to Ask the GM as a whole
OPS = ("merge_shadows", "blink_steps")
NAMES = {"merge_shadows": "Merge with Shadows", "blink_steps": "Blink Steps"}
MERGE = "Merge with Shadows"                                     # the Invisible record's "spell" (not hiding)
FATE_FT, BLINK_FT, TRUESIGHT_FT = 60, 30, 60
WILL = 5                                                         # the computer's Improve Fate: 5 or less needed
BPS = {"bludgeoning", "piercing", "slashing"}
BRIGHT = 2                                                       # lighting.BRIGHT (Sim.light_level)
CASTERS = ("wizard", "sorcerer", "warlock", "cleric", "bard", "druid")


class BoonError(ValueError):
    pass


def _state(party, name):
    d = getattr(party, name, None)
    if d is None:
        d = {}
        setattr(party, name, d)
    return d


def _say(sim, text):
    sim.say("dice", text)


# ---------------------------------------------------------------------- the builder
def build(b, scores, boon_abilities):
    """character_build.member(): the score Overwhelming Strike deals (the one the boon raised: the sheet's
    boon_abilities, else the better of Strength and Dexterity) and Truesight in the senses."""
    if b.get("irresistible_offense"):
        a = (boon_abilities or {}).get(OFFENSE)
        b["irresistible_offense"] = int(scores.get(a) or max(scores.get("str") or 10, scores.get("dex") or 10))
    if b.get("boon_truesight") and "truesight" not in str(b.get("senses") or "").lower():
        b["senses"] = ", ".join(x for x in (b.get("senses"), "Truesight %d ft." % TRUESIGHT_FT) if x)


# ---------------------------------------------------------------------- the fight's start (Party.__init__)
def fight_start(party, c):
    """The fight state's fields for this member, and the hooks once a member has a boon that needs them."""
    s, i = party.s, c["id"]
    if c.get("irresistible_offense"):
        s.setField(i, "sim_overcome", 1)
        s.setField(i, "sim_overwhelm", int(c["irresistible_offense"]))
    if c.get("night_spirit"):
        s.setField(i, "sim_shadowy", 1)
        s.shadowResist = lambda tid: shadowy(party.sim, tid)
    if c.get("combat_prowess"):
        s.peerlessAim = lambda src, tid, total, ac: peerless(party, src, tid, total, ac)
    if c.get("boon_fate"):
        s.improveFate = lambda src, tid, total, ac, res: fate_attack(party, src, tid, total, ac, res)


def turn_start(party, me):
    """Peerless Aim comes back at the start of the character's turn."""
    _state(party, "peerless_used").pop(me, None)


# ---------------------------------------------------------------------- Boon of Combat Prowess
def peerless(party, src, tid, total, ac):
    """fight_state: src missed tid (total vs ac). True: it hits instead."""
    sim = party.sim
    c, used = sim.by_id(src), _state(party, "peerless_used")
    if not c or not c.get("combat_prowess") or src in used or party.down(src):
        return False
    asked = party.asked_live(src)
    if asked and not asked.peerless(src, tid, total, ac):
        return False
    used[src] = True
    _say(sim, "%s: Peerless Aim (Boon of Combat Prowess): the miss on %s (%d vs AC %d) is a hit instead; not again until "
              "the start of %s's next turn" % (c["name"], sim.S.name(tid), total, ac, c["name"]))
    return True


# ---------------------------------------------------------------------- Boon of Fate
def _fate_holders(party, roller):
    sim, used = party.sim, _state(party, "fate_used")
    gm = getattr(sim, "gm_rules", None)
    out = [o["id"] for o in sim.sc["combatants"] if o.get("boon_fate") and o["id"] not in used and not party.down(o["id"])
           and not (gm and gm.incapacitated(o["id"])) and (o["id"] == roller or party.dist(o["id"], roller) <= FATE_FT + 0.01)]
    return sorted(out, key=lambda h: party.dist(h, roller) if h != roller else -1)


def _fate(party, h, need, sign, trigger, what):
    """Improve Fate on one roll: asked live, or the computer's choice. -> the signed 2d4, or 0."""
    sim = party.sim
    asked = party.asked_live(h)
    if asked:
        note = "Roll 2d4 and %s %s: %d or more %s." % ("add it to" if sign > 0 else "take it off", what, need,
                                                        "turns it into a success" if sign > 0 else "turns it into a failure")
        if not asked.fate(h, trigger, note):
            return 0
    elif need > WILL:
        return 0
    _state(party, "fate_used")[h] = True
    r = sim.rng.randint(1, 4) + sim.rng.randint(1, 4)
    _say(sim, "%s: Improve Fate (Boon of Fate, once this fight): 2d4 = %d %s %s" % (
        sim.by_id(h)["name"], r, "added to" if sign > 0 else "taken off", what))
    return sign * r


def fate_attack(party, src, tid, total, ac, res):
    """fight_state: src's attack roll on tid (total vs ac, "hit" or "miss"; never a 20 or a 1). -> what it changes."""
    if res not in ("hit", "miss"):
        return 0
    for h in _fate_holders(party, src):
        mine = party.side(h)
        if res == "miss" and party.side(src) == mine:
            need, sign = ac - total, 1
        elif res == "hit" and party.side(src) not in (mine, "neutral") and party.side(tid) == mine:
            need, sign = total - ac + 1, -1
        else:
            continue
        if need > 8:
            continue
        r = _fate(party, h, need, sign, "%s's attack roll %s %s (%d vs AC %d)" % (
            party.sim.S.name(src), "misses" if res == "miss" else "hits", party.sim.S.name(tid), total, ac),
            "%s's attack roll" % party.sim.S.name(src))
        if r:
            return r
    return 0


def fate_save(gm, t, total, dc, label):
    """GmRules.indomitable (every saving throw the rules roll): an ally's failure or a foe's success. -> the total."""
    party = getattr(gm.sim, "party", None)
    if not party:
        return total
    for h in _fate_holders(party, t):
        mine = party.side(h)
        if total < dc and party.side(t) == mine:
            need, sign = dc - total, 1
        elif total >= dc and party.side(t) not in (mine, "neutral"):
            need, sign = total - dc + 1, -1
        else:
            continue
        if need > 8:
            continue
        r = _fate(party, h, need, sign, "%s %s a %s save (%d vs DC %d)" % (
            gm.sim.S.name(t), "fails" if total < dc else "succeeds on", label, total, dc), "%s's save" % gm.sim.S.name(t))
        if r:
            return total + r
    return total


# ---------------------------------------------------------------------- Boon of Spell Recall
def spell_recall(party, i, lv):
    """Party.spend_slot spent a level lv slot for a spell: 1d4, on lv the slot isn't expended."""
    sim = party.sim
    c = sim.by_id(i)
    if not c or not c.get("spell_recall") or not 1 <= lv <= 4 or getattr(party, "no_recall", None) == i:
        return False
    d4 = sim.rng.randint(1, 4)
    if d4 != lv:
        _say(sim, "%s: Free Casting (Boon of Spell Recall): d4 %d, not %d: the level %d slot is spent" % (c["name"], d4, lv, lv))
        return False
    pool = party.pools.setdefault(i, [party.slots.get(i, 0)])
    pool[lv - 1] += 1
    party.slots[i] += 1
    _say(sim, "%s: Free Casting (Boon of Spell Recall): d4 %d: the level %d slot isn't expended" % (c["name"], d4, lv))
    return True


# ---------------------------------------------------------------------- Boon of the Night Spirit
def shadowy(sim, tid):
    """Shadowy Form: in Dim Light or Darkness."""
    c = sim.by_id(tid)
    return bool(c and c.get("night_spirit")) and sim.light_level(tid) < BRIGHT


def _turn_of(sim):
    """Whose turn it is (the fight state's active combatant)."""
    return sim.S.active()[0]


def merged(sim, me):
    gm = getattr(sim, "gm_rules", None)
    info = (gm.cond.get(me) or {}).get("Invisible") if gm else None
    return info if info and info.get("spell") == MERGE else None


def merge_why(party, me):
    """None when Merge with Shadows can be used now (the Bonus Action, Dim Light or Darkness); else why not."""
    sim = party.sim
    c, gm = sim.by_id(me), getattr(sim, "gm_rules", None)
    if not c.get("night_spirit"):
        return "Merge with Shadows is the Boon of the Night Spirit's."
    if merged(sim, me):
        return "%s is already merged with the shadows." % c["name"]
    if party.down(me) or (gm and gm.incapacitated(me)):
        return "%s is down or Incapacitated." % c["name"]
    if not party.bonus_free(me):
        return "%s's Bonus Action is used this turn." % c["name"]
    if sim.light_level(me) >= BRIGHT:
        return "%s stands in Bright Light: Merge with Shadows needs Dim Light or Darkness." % c["name"]
    return None


def merge(party, me, acted):
    """The Bonus Action: Invisible until right after its next action, Bonus Action or Reaction."""
    sim, gm = party.sim, party.sim.gm_rules
    c = sim.by_id(me)
    party.use_bonus(me)
    info = {"spell": MERGE, "serial": party.s.turnSerial, "acted": bool(acted)}
    if gm.has(me, "Invisible"):                                  # hidden already: the boon's condition replaces it
        gm.cond[me]["Invisible"] = info
        _say(sim, "%s merges with the shadows (Boon of the Night Spirit, Bonus Action): Invisible now by the boon, not "
                  "hiding" % c["name"])
    else:
        sim.say("dice", "%s merges with the shadows (Boon of the Night Spirit, Bonus Action)" % c["name"])
        gm.add(me, "Invisible", "(Merge with Shadows, until right after its next action, Bonus Action or Reaction)",
               **info)


def end_merge(sim, me, why):
    if merged(sim, me):
        sim.gm_rules.remove(me, "Invisible", "Merge with Shadows ends: %s" % why)


def keeps(sim, src):
    """GmRules.attack_rolled: an attack roll on the merged character's own turn is part of its action (the condition
    ends right after the action, not on the roll); off its turn the roll is a Reaction's, and it ends."""
    return bool(merged(sim, src)) and _turn_of(sim) == src


def reacted(sim, me):
    """It took a Reaction: Merge with Shadows ends."""
    end_merge(sim, me, "it took a Reaction")


def attack_rolled(sim, src):
    """GmRules.attack_rolled: this turn it made an attack roll (Blink Steps for the computer)."""
    party = getattr(sim, "party", None)
    if party is not None and _turn_of(sim) == src:
        _state(party, "acted")[src] = party.s.turnSerial


# ---------------------------------------------------------------------- Boon of Dimensional Travel
def _far_square(party, me, squares):
    """The free square within reach farthest from the foes (Party.misty_step's search). -> (gap, (x, y)) or None."""
    foes = [f for f in party.foes(me) if not party.down(f)]
    if not foes:
        return None
    hx, hy = party.pos(me)
    taken = {party.pos(o["id"]) for o in party.sim.sc["combatants"] if o["id"] != me and not party.down(o["id"])}
    best = None
    for dx in range(-squares, squares + 1):
        for dy in range(-squares, squares + 1):
            to = (hx + dx, hy + dy)
            if (dx, dy) == (0, 0) or to in taken or party.walled((hx, hy), to):
                continue
            gap = min(max(abs(party.pos(f)[0] - to[0]), abs(party.pos(f)[1] - to[1])) for f in foes)
            if best is None or gap > best[0]:
                best = (gap, to)
    return best


def teleport(party, me, x, y):
    s = party.s                                                  # a teleport provokes no Opportunity Attack
    s.addEffect(me, "Note: Disengage", True)
    try:
        s.move(me, x, y)
    finally:
        s.removeEffect(me, "Note: Disengage")
    party.sim.settle()
    _say(party.sim, "%s: Blink Steps (Boon of Dimensional Travel): teleports to (%g, %g)" % (party.name(me), x, y))


def blink_computer(party, me, c):
    """After the class turn: a member that fights from range, a foe beside it, an attack roll or a slot this turn."""
    serial = party.s.turnSerial
    if not c.get("dimensional_travel") or party.down(me) or _state(party, "acted").get(me) != serial:
        return False
    if not (c.get("ranged") or c.get("class") in CASTERS) or not party.enemy_next_to(me):
        return False
    best = _far_square(party, me, BLINK_FT // party.sim.sc.get("units", 5))
    if not best or best[0] <= 1:
        return False
    teleport(party, me, best[1][0], best[1][1])
    return True


# ---------------------------------------------------------------------- the computer's turn (Party.turn)
def after_action(party, me, c):
    """Right after the computer-played member's class turn (its action): Merge with Shadows ends if it acted; Blink
    Steps; then Merge with Shadows again with the Bonus Action free."""
    sim = party.sim
    info = merged(sim, me)
    if info and _state(party, "acted").get(me) == party.s.turnSerial:
        end_merge(sim, me, "it took an action")
    blink_computer(party, me, c)
    if c.get("night_spirit") and party.foes(me) and not merge_why(party, me):
        merge(party, me, acted=True)


# ---------------------------------------------------------------------- Play live
def live_after(fight, me, cmd, was, out):
    """LiveFight's turn, after each choice: the Attack or Magic action just taken readies Blink Steps; Merge with Shadows
    ends right after an action, a Bonus Action (a later turn's), or the turn's end with the action taken."""
    sim, t = fight.sim, fight.turn_state
    party = sim.party
    if not party or not t or not out.get("ok"):
        return
    op, serial = cmd.get("op"), party.s.turnSerial
    if op in ("attack", "cast", "grapple", "shove") and not was.get("action_used") and t.get("action_used"):
        _state(party, "blink_ready")[me] = serial
    info = merged(sim, me)
    if not info or op == "merge_shadows":
        return
    later = info["serial"] != serial
    acted = t.get("action_used") and (later or not info["acted"])
    if acted and (t.get("attacks_left", 0) <= 0 or op == "end"):
        end_merge(sim, me, "it took an action")
    elif later and not party.bonus_free(me):
        end_merge(sim, me, "it took a Bonus Action")


def of(fight):
    b = getattr(fight, "boons", None)
    if b is None:
        b = fight.boons = LiveBoons(fight)
    return b


class LiveBoons:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    def _able(self, me):
        import live_actions
        try:
            return self.fight.actions.able(me)
        except live_actions.ActionError as e:
            raise BoonError(str(e))

    def check(self, me, op):
        t, c = self._able(me)
        party = self.party
        if op == "merge_shadows":
            why = merge_why(party, me)
            if why:
                raise BoonError(why)
            return t, c
        if not c.get("dimensional_travel"):
            raise BoonError("Blink Steps is the Boon of Dimensional Travel's.")
        if _state(party, "blink_ready").get(me) != party.s.turnSerial:
            raise BoonError("Blink Steps comes right after the Attack action or the Magic action.")
        return t, c

    def blink_square(self, me, x, y):
        import more_spells as ms
        import sim_messages
        sim, party = self.sim, self.party
        here = tuple(int(round(v)) for v in party.pos(me))
        if (x, y) == here:
            raise BoonError("Choose another square to teleport to.")
        try:
            ms.point_in_range(self.fight, me, x, y, BLINK_FT, "Blink Steps")
        except ms.EffectError as e:
            raise BoonError(str(e))
        board = sim_messages.map_part(sim.sc)
        if not (0 <= x < board["cols"] and 0 <= y < board["rows"]):
            raise BoonError("That square is off the map.")
        if (x, y) in sim.occupied_cells(me):
            raise BoonError("That square is occupied: Blink Steps takes an unoccupied space.")
        if not sim.sees_square(me, x, y):
            raise BoonError("%s can't see that square: Blink Steps goes to a space you can see." % sim.by_id(me)["name"])

    def actions(self, me):
        """The boons' buttons, with the other actions (sim/live_actions.py offers)."""
        c, out = self.sim.by_id(me), []

        def entry(e, op):
            try:
                self.check(me, op)
                e["ready"] = True
            except BoonError as err:
                e["ready"], e["why"] = False, str(err)
            out.append(e)
        if c.get("night_spirit"):
            entry({"op": "merge_shadows", "label": "Merge with Shadows (Boon of the Night Spirit)", "time": "bonus",
                   "bonus": False}, "merge_shadows")
        if c.get("dimensional_travel"):
            entry({"op": "blink_steps", "label": "Blink Steps: teleport up to 30 ft (no action)", "square": True,
                   "time": "free", "bonus": False}, "blink_steps")
        return out

    def do(self, me, cmd):
        op = cmd.get("op")
        t, c = self.check(me, op)
        party = self.party
        if op == "merge_shadows":
            merge(party, me, acted=t.get("action_used") and t.get("attacks_left", 0) <= 0)
            return "bonus"
        try:
            x, y = int(cmd["x"]), int(cmd["y"])
        except (KeyError, TypeError, ValueError):
            raise BoonError("Click the square for Blink Steps.")
        self.blink_square(me, x, y)
        _state(party, "blink_ready").pop(me, None)
        teleport(party, me, x, y)
        return "free"
