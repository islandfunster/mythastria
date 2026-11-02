"""GM 2026-10-26 (goal 14; docs/development/ADVENTURE_PILLARS_PLAN.md step 4): an encounter is a scene of the three
pillars. The GM starts it as a social scene (on The Stage), an exploration scene (on the map) or a fight, and it changes
as the table plays: talk breaks down into a fight, a fight de-escalates (a surrender, a truce, the party's retreat) into
talk, exploration finds the fight.

- No turns and no initiative in a social or exploration scene (SRD 5.2.1 Playing the Game: combat is the part of the
  game in rounds and turns). Each character acts when its player chooses: the scene's focus moves to the character
  that acts, every choice is checked by the same rules as in a fight (sim/live_play.py: Search, Study, Influence,
  doors, traps, items, helpful spells, Ask the GM), and its Action, Bonus Action and movement are fresh again after
  each choice (moving freely, up to its Speed each time). Fog of war, light, hazards and traps keep working.
- Social: Influence (Deception, Intimidation, Performance, Persuasion; Animal Handling) reads the creature's attitude
  (sim/attitude.py) and the GM rules Influence (Ask the GM, GM 2026-11-01); any other
  ability check is rolled with the character's own bonus and ruled by the GM (the SRD leaves the DC to the GM). Every
  attitude change is logged with its reason.
- What starts a fight: the GM, always. The engine suggests it when a Hostile creature that is still in it sees the
  party or is seen by it (exploration), or is present at all (social: talk broke down), and when a player tries an
  attack or a spell that is not purely helpful (which would start a fight by itself). Initiative is rolled then
  (SRD 5.2.1 Initiative: d20 + Dexterity modifier), and a combatant surprised by combat starting has Disadvantage on
  it (SRD 5.2.1 Surprise). The engine suggests who is surprised (those who see nobody on the other side; a creature
  that was not Hostile when the party struck); the GM ticks or unticks each.
- The fight ends by the tools already built (sim/attitude.py: Call a truce, The party retreats, End the scene, a
  surrender, a flight, the party's win), and the scene goes on: a truce or creatures left standing out of the fight ->
  social; a retreat or the party's win -> exploration. End the scene ends it all.

Every GM choice is checked first (sim/requirements.py), with the reason when it can't be taken.
"""
import queue

import attitude
import requirements as rq

MODES = ("social", "exploration", "fight")
LABEL = {"social": "Social scene (on The Stage)", "exploration": "Exploration (on the map)", "fight": "Fight (Initiative)"}
# choices that are a fight's own: refused in a scene, with the reason
FIGHT_ONLY = {"dash": "no turns in a scene: move freely (as far as your Speed, as often as you like).",
              "disengage": "no turns in a scene: nobody is making Opportunity Attacks.",
              "dodge": "Dodge is for a fight.", "ready": "Ready is for a fight's turn.",
              "end": "no turns in a scene: every character acts when its player chooses.",
              "undo": "Undo is for a fight's turn.", "undo_approve": "Undo is for a fight's turn.",
              "undo_refuse": "Undo is for a fight's turn.", "rage": "Rage is for a fight.",
              "help": "in a scene the GM grants Advantage on a check that is helped (Ability check, with Advantage).",
              "spirit_strike": "Spiritual Weapon's attack is for a fight.", "mount_action": "the mount's action is for a fight."}
STARTS_A_FIGHT = {"attack": "an attack", "grapple": "a Grapple", "shove": "a Shove"}
# spells that change nobody's attitude and harm no one: cast freely in a scene (with the helpful ones, attitude.HELPFUL)
UTILITY = {"Alarm", "Augury", "Comprehend Languages", "Dancing Lights", "Darkvision", "Detect Evil and Good",
           "Detect Magic", "Detect Poison and Disease", "Druidcraft", "Feather Fall", "Find Familiar", "Gentle Repose",
           "Identify", "Invisibility", "Jump", "Knock", "Light", "Locate Object", "Mage Hand", "Mending", "Message",
           "Minor Illusion", "Pass without Trace", "Prestidigitation", "See Invisibility", "Speak with Animals",
           "Thaumaturgy", "Tongues", "Water Breathing", "Water Walk"}
ABILITIES = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom",
             "cha": "Charisma"}
GM_OPS = ("talk", "explore", "fight", "not_yet")


class SceneError(ValueError):
    pass


def init_bonus(c):
    """(bonus, how): the creature's Initiative bonus, SRD 5.2.1 its Dexterity modifier (a block's own init_bonus
    first)."""
    if isinstance(c.get("init_bonus"), int):
        return c["init_bonus"], ""
    dex = (c.get("abilities") or {}).get("dex", c.get("dex"))
    if isinstance(dex, (int, float)):
        return (int(dex) - 10) // 2, ""
    return 0, "no Dexterity"


def roll_check(fight, me, cmd):
    """Any ability check: (the check's name, the total, the d20, what it is about, the line for the log). The dice are
    rolled here, for a scene's control and for the GM's Call a check in a fight."""
    import character_rules as cr
    c, sim = fight.sim.by_id(me), fight.sim
    sheet = fight.checks(me)
    skill, ability = cmd.get("skill"), cmd.get("ability")
    if skill:
        usual = cr.rules()["skills"].get(skill)
        if not usual:
            raise SceneError("Choose a skill from the sheet.")
        ability = ability if ability in ABILITIES else usual     # play-test 2026-11-02: the GM's Wisdom (Religion)
        bonus = sheet["skills"][skill] + sheet["abilities"].get(ability, 0) - sheet["abilities"].get(usual, 0)
        name = "%s (%s)" % (ABILITIES.get(ability, ability), skill)
    elif ability in ABILITIES:
        bonus = sheet["abilities"].get(ability, 0)
        name = ABILITIES[ability]
    else:
        raise SceneError("Choose an ability or a skill.")
    how = cmd.get("roll")
    import high_levels                                           # group 3: Remarkable Athlete, Indomitable Might
    if high_levels.remarkable(c, skill=skill):
        how = None if how == "disadvantage" else "advantage"
    a, b = sim.rng.randint(1, 20), sim.rng.randint(1, 20)
    d20 = max(a, b) if how == "advantage" else min(a, b) if how == "disadvantage" else a
    dice = "d20 %d/%d (%s)" % (a, b, how.capitalize()) if how in ("advantage", "disadvantage") else "d20 %d" % a
    about = str(cmd.get("about") or "").strip()[:120]
    total = high_levels.indomitable_might(sim, c, ability, d20 + bonus, "%s check" % name)
    line = "%s makes %s %s check%s: %s %+d = %d" % (c["name"], "an" if name[0] in "AEIOU" else "a", name,
                                                     ' ("%s")' % about if about else "", dice, bonus, total)
    return name, total, d20, about, line


class Scenes:
    """The scene of one live encounter. Runs on the simulator's thread (hold, start_combat, after_fight); the service
    hands the GM's choices over with submit()."""

    def __init__(self, fight, mode="fight"):
        if mode not in MODES:
            raise SceneError("A scene starts as social, exploration or a fight.")
        self.fight, self.mode, self.started = fight, mode, mode
        self.history = [{"n": 1, "mode": mode, "why": "the GM started the encounter as %s" % LABEL[mode].lower()}]
        self.cards, self.card_n, self.not_yet = [], 0, set()
        self.checks, self.check_n = [], 0
        self.surprised = []                                  # the GM's choice for the fight about to start
        self.fights = 0
        self.gmq = queue.Queue()
        fight.scenes = self

    @property
    def sim(self):
        return self.fight.sim

    @property
    def att(self):
        return self.fight.attitudes

    def in_scene(self):
        return self.mode != "fight"

    # ------------------------------------------------------------------ who is there
    def pcs(self):
        f = self.fight
        return [c["id"] for c in self.sim.sc["combatants"] if c.get("pc") and c["id"] in f.live_ids and not self.sim.down(c["id"])]

    def standing(self, cid):
        r = self.att.rows.get(cid)
        return bool(r) and not self.sim.down(cid) and not r.get("gone")

    def hostile(self):
        """The creatures that would fight now: Hostile, not surrendered, fled or bargaining, not down or gone."""
        return [i for i, r in self.att.rows.items() if self.standing(i) and r["attitude"] == "Hostile" and not r["status"]
                and not r["joined"]]

    def _switch(self, to, why):
        self.mode = to
        self.history.append({"n": len(self.history) + 1, "mode": to, "why": why})
        self.sim.say("scene", "Scene: %s (%s)" % (LABEL[to], why))

    # ------------------------------------------------------------------ the engine's suggestions
    def suggest_surprise(self, by=None, target=None):
        """Who the engine suggests is surprised as the fight starts (the GM decides): a creature that sees nobody on the
        other side; when a character strikes first, the creatures that were not Hostile."""
        sim, pcs, foes = self.sim, self.pcs(), self.hostile()
        out = []
        if by:
            group = self.att.group_of(target) if target in self.att.rows else []
            out += [i for i in group if self.standing(i) and self.att.rows[i]["attitude"] != "Hostile"]
        for p in pcs:
            if foes and not any(sim.sees(p, o) for o in foes) and not by:
                out.append(p)
        for o in foes:
            if pcs and not any(sim.sees(o, p) for p in pcs):
                out.append(o)
        return sorted(set(out))

    def refresh_cards(self):
        """The GM's cards in a scene: Hostile creatures the party meets (start the fight?), and choices a player tried
        that would start one."""
        if not self.in_scene():
            self.cards = []
            return
        sim, pcs = self.sim, self.pcs()
        met = [o for o in self.hostile() if o not in self.not_yet and (self.mode == "social" or any(
            sim.sees(p, o) or sim.sees(o, p) for p in pcs))]
        self.cards = [c for c in self.cards if c["kind"] == "strike" and self.standing(c["target"])]
        if met:
            names = [sim.by_id(o)["name"] for o in met]
            text = ("%s %s Hostile: the talk has broken down. Start the fight?" if self.mode == "social" else
                    "%s (Hostile) %s the party: start the fight?") % (
                ", ".join(names), ("is" if len(met) == 1 else "are") if self.mode == "social" else
                ("meets" if len(met) == 1 else "meet"))
            old = next((c for c in getattr(self, "_met", []) if c["who"] == met), None)
            if old is None:
                self.card_n += 1
                old = {"n": self.card_n, "kind": "met", "who": met}
            old.update(text=text, surprised=self.suggest_surprise(), names=names)
            self._met = [old]
            self.cards.insert(0, old)
        else:
            self._met = []

    def strike_card(self, me, tid, what):
        c, t = self.sim.by_id(me), self.sim.by_id(tid) if tid else None
        if any(k["kind"] == "strike" and k["by"] == me and k["target"] == tid for k in self.cards):
            return
        self.card_n += 1
        self.cards.append({"n": self.card_n, "kind": "strike", "by": me, "target": tid, "what": what,
                           "text": "%s wants to use %s%s: that starts a fight. Start it?" % (
                               c["name"], what, " on %s" % t["name"] if t else ""),
                           "surprised": self.suggest_surprise(me, tid)})

    # ------------------------------------------------------------------ the GM's choices
    def needs(self, cmd):
        op = cmd.get("op")
        needs = [rq.need("the encounter still on", not self.fight.done and self.att.ended != "end",
                         "The encounter is over."),
                 rq.need("a scene, not a fight", self.in_scene(),
                         "A fight is on: call a truce, have the party retreat, or end the scene (the Attitudes panel).")]
        if op in ("talk", "explore"):
            to = "social" if op == "talk" else "exploration"
            needs.append(rq.need("another scene", self.mode != to, "This is already %s." % LABEL[to].lower()))
        if op == "fight":
            card = self.card(cmd.get("n"))
            ids = {c["id"] for c in self.sim.sc["combatants"]}
            sur = cmd.get("surprised") or []
            needs.append(rq.need("combatants", isinstance(sur, list) and all(s in ids for s in sur),
                                 "The surprised are combatants in this encounter."))
            needs.append(rq.need("someone to fight", bool(self.hostile()) or bool(card and card["kind"] == "strike"),
                                 "Nobody is Hostile: set a creature Hostile first (the Attitudes panel), or a character "
                                 "strikes."))
            if cmd.get("n") is not None:
                needs.append(rq.need("an open card", card is not None, "That suggestion is no longer open."))
        if op == "not_yet":
            needs.append(rq.need("an open card", self.card(cmd.get("n")) is not None, "That suggestion is no longer open."))
        if op not in GM_OPS:
            needs.append(rq.need("a scene choice", False, "The GM moves the scene to talk, to exploration, or starts "
                                                          "the fight (or waits: not yet)."))
        return needs

    def card(self, n):
        return next((c for c in self.cards if c["n"] == n), None) if n is not None else None

    def do(self, cmd):
        ready, rows = rq.check(self.needs(cmd))
        if not ready:
            raise SceneError(rq.first_why(rows))
        op, why = cmd["op"], str(cmd.get("why") or "").strip()[:120]
        if op == "talk":
            self._switch("social", why or "the GM: the party talks")
        elif op == "explore":
            self._switch("exploration", why or "the GM: the party explores")
        elif op == "not_yet":
            card = self.card(cmd["n"])
            self.cards.remove(card)
            if card["kind"] == "met":
                self.not_yet |= set(card["who"])
            self.sim.say("scene", "The GM: not yet (%s)" % card["text"].split(":")[0])
        elif op == "fight":
            card = self.card(cmd.get("n"))
            if card and card["kind"] == "strike" and card["target"]:   # the strike makes its target Hostile
                self.att.provoke(card["by"], card["target"], {"an attack": "attacked", "a Grapple": "grappled",
                                                              "a Shove": "shoved"}.get(card["what"],
                                                                                       "targeted with " + card["what"]))
            self.surprised = list(cmd.get("surprised") or [])
            self.not_yet.clear()
            self._switch("fight", why or (card["text"].split(":")[0] if card else "the GM starts the fight"))
        self.refresh_cards()
        return {"ok": True}

    def submit(self, cmd, timeout=30):
        """From the service's thread: hand a GM choice to the scene and wait for its answer."""
        ready, rows = rq.check(self.needs(cmd))
        if not ready:
            return {"ok": False, "refused": rq.first_why(rows)}
        reply = queue.Queue()
        self.gmq.put((cmd, reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "refused": "The scene did not answer: try again."}

    def drain(self):
        did = False
        while True:
            try:
                cmd, reply = self.gmq.get_nowait()
            except queue.Empty:
                return did
            try:
                out = self.do(cmd)
                did = True
            except SceneError as e:
                out = {"ok": False, "refused": str(e)}
            except Exception as e:                              # shown to the GM, never hidden
                out = {"ok": False, "refused": "%s: %s" % (type(e).__name__, e)}
            reply.put(out)

    def refuse_waiting(self):
        while True:
            try:
                _, reply = self.gmq.get_nowait()
            except queue.Empty:
                return
            reply.put({"ok": False, "refused": "The encounter is over."})

    # ------------------------------------------------------------------ the simulator's thread
    def _focus(self, me):
        """The scene's focus moves to the character that acts: a fresh Action, Bonus Action and movement."""
        f, sim = self.fight, self.sim
        c = sim.by_id(me)
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        f.turn_state = {"id": me, "movement": speed, "speed": speed, "action_used": False, "attacks_left": 0,
                        "sneak_used": False, "attacks_made": 0, "scene": True}
        f.undo, f.undo_asked = [], None
        g = sim.S
        g.turnSerial = int(g.turnSerial or 0) + 1                # a Bonus Action is free again (Party.bonus_free)
        if sim.party:
            sim.party.actor = me
        if f.waiting != me:
            f.turn_serial += 1
        f.waiting = me

    def _publish(self, changed=True):
        f = self.fight
        with f.lock:
            if changed:
                f.revision += 1
            f._publish_locked()

    def hold(self):
        """Before a fight (and between fights): the scene, until the GM starts the fight (True) or ends the scene
        (False). Players' choices arrive on the fight's inbox (LiveFight.act), the GM's on the queues."""
        import live_play
        if self.mode == "fight":
            return True
        f, sim, att = self.fight, self.sim, self.att
        pcs = self.pcs()
        if not pcs:
            return False
        self._focus(f.waiting if f.waiting in pcs else pcs[0])
        self.refresh_cards()
        self._publish()
        while True:
            if f.stopping:
                raise live_play.Quit()
            hz = getattr(sim, "hazards", None)
            did = att.drain() | self.drain() | (hz.drain() if hz else False)
            if att.ended == "end":
                return False
            if self.mode == "fight":
                f.waiting = None
                return True
            if did:
                self.refresh_cards()
                self._publish()
            try:
                cmd, reply = f.inbox.get(timeout=0.2)
            except queue.Empty:
                continue
            if cmd.get("op") == "quit":
                reply.put({"ok": True})
                raise live_play.Quit()
            try:
                out = self.choose(cmd)
            except (live_play.LiveError, SceneError) as e:
                out = {"ok": False, "refused": str(e)}
            f.layers.sweep()
            self.refresh_cards()
            with f.lock:
                if out.get("ok"):
                    f.revision += 1
                f._publish_locked()
                out["snapshot"] = f.snap
            reply.put(out)

    def choose(self, cmd):
        """A player's choice in a scene, for the character it names."""
        f, sim = self.fight, self.sim
        me, op = cmd.get("_actor"), cmd.get("op")
        with f.lock:
            stale = f.stopping or cmd.get("revision") != f.revision
        if stale:
            return {"ok": False, "status": 409, "refused": "Stale: the scene has moved on."}
        if me not in self.pcs():
            raise SceneError("Choose a standing character of the party.")
        if op in FIGHT_ONLY:
            raise SceneError("Not in a scene: %s" % FIGHT_ONLY[op])
        tid = cmd.get("target") or next(iter(cmd.get("targets") or []), None)
        if op in STARTS_A_FIGHT or (op == "cast" and self.harmful(me, cmd)):
            what = STARTS_A_FIGHT.get(op) or cmd.get("spell")
            target = tid if tid in self.att.rows else None
            self.strike_card(me, target, what)
            raise SceneError("No initiative yet: %s starts a fight. The GM is asked to start it (Initiative is rolled "
                             "then, with Surprise)." % (what if op != "cast" else "casting " + what))
        self._focus(me)
        if op == "focus":
            sim.say("scene", "%s steps forward" % sim.by_id(me)["name"])
            return {"ok": True}
        if op == "check":
            return self.check(me, cmd)
        out = f._choose(me, cmd)
        if out.get("ok"):
            self._focus(me)                                      # free again for the next choice (no turns)
        return out

    def harmful(self, me, cmd):
        """A spell that would start a fight: not purely helpful or a utility, aimed at a creature that is not with the
        party, or at a point."""
        spell = cmd.get("spell")
        if spell in attitude.HELPFUL or spell in UTILITY:
            return False
        ts = [t for t in [cmd.get("target")] + list(cmd.get("targets") or []) if t]
        if cmd.get("x") is not None:
            return True
        return any(t in self.att.rows and not self.att.rows[t]["joined"] for t in ts)

    def check(self, me, cmd):
        """Any other ability check (SRD 5.2.1 Ability Checks): d20 + the character's bonus for the ability or skill;
        the GM sets the DC and rules the result. Advantage or Disadvantage when the GM grants it (help, the attitude)."""
        name, total, d20, about, line = roll_check(self.fight, me, cmd)
        self.sim.say("dice", line + ". The GM sets the DC and rules it.")
        self.check_n += 1
        self.checks = (self.checks + [{"n": self.check_n, "who": self.sim.by_id(me)["name"], "check": name, "total": total,
                                       "d20": d20, "about": about}])[-20:]
        return {"ok": True, "total": total}

    def start_combat(self):
        """The fight starts: Initiative rolled for everyone (SRD 5.2.1: d20 + Dexterity modifier; Disadvantage when
        surprised), then round 1. INITIATIVE-01 (GM 2026-10-28, sim/initiative.py): the creatures' rolls at once; each
        played character's from its player's popup (or the GM's Roll for them), the first round waiting for them all."""
        import initiative
        sim = self.sim
        s = sim.S
        self.fights += 1
        sur, rolls = set(self.surprised), {}
        here = [c for c in sim.sc["combatants"]
                if not sim.down(c["id"]) and not (self.att.rows.get(c["id"]) or {}).get("gone")]
        played = set(self.pcs())
        for c in here:
            if c["id"] not in played:
                total, text, note = initiative.roll(sim, c, c["id"] in sur)
                rolls[c["id"]] = {"total": total, "rolls": text, "note": note}
        who = [c["id"] for c in here if c["id"] in played]
        if who:
            rolls.update(self.wait_for_initiative(initiative.of(self.fight), who, sur))
        parts, plain = [], []
        for c in here:
            r = rolls[c["id"]]
            c["init"] = r["total"]
            s.setValue(c["id"], "initresult", r["total"])
            if r["note"]:
                plain.append(c["name"])
            parts.append("%s %d (%s)" % (c["name"], r["total"], r["rolls"]))
        sim.say("dice", "Initiative (the fight starts): " + "; ".join(parts) + (
            ". No Dexterity on the blocks of %s here: +0" % ", ".join(plain) if plain else ""))
        self.surprised = []
        self.fight.waiting = None
        s.startCombat()

    def wait_for_initiative(self, call, who, sur):
        """INITIATIVE-01: the popups are up; the GM's queues are answered and a player's other choice is refused until
        every character has rolled (the rolls arrive through the service: POST /api/live/initiative)."""
        import live_play
        f = self.fight
        call.open_call(who, sur)
        self._publish()
        hz = getattr(self.sim, "hazards", None)
        while not call.ready():
            if f.stopping:
                raise live_play.Quit()
            if self.att.drain() | self.drain() | (hz.drain() if hz else False):
                self._publish()
            try:
                cmd, reply = f.inbox.get(timeout=0.2)
            except queue.Empty:
                continue
            if cmd.get("op") == "quit":
                reply.put({"ok": True})
                raise live_play.Quit()
            with f.lock:
                f._publish_locked()
                reply.put({"ok": False, "refused": "Initiative is being rolled: roll yours in the popup first.",
                           "snapshot": f.snap})
        rolls = call.close()
        self._publish()
        return rolls

    def after_fight(self):
        """The fight is over: where the scene goes on (True), or the encounter ends (False)."""
        f, att, sim = self.fight, self.att, self.sim
        if f.stopping or att.ended == "end":
            return False
        sim.calm()                                               # nothing queued for the fight runs in the scene
        if att.over():
            outcome = att.finish()
        else:
            outcome = "The fight stops after its rounds (the table's limit)."
            sim.say("scene", outcome)
        self.history[-1]["outcome"] = outcome
        if not self.pcs():
            return False
        ended = att.ended
        calm = [i for i, r in att.rows.items() if self.standing(i) and not r["joined"] and
                (r["status"] or r["attitude"] != "Hostile")]
        to = "social" if ended == "truce" or (ended != "retreat" and calm) else "exploration"
        att.ended = att.outcome = None                           # a new fight may start later in the scene
        att.cards = [c for c in att.cards if c.get("kind") == "urge"]
        att.answered = {}
        for r in att.rows.values():
            r["hostile_once"] = r["attitude"] == "Hostile" and not r["status"]
        self._switch(to, {"truce": "a truce", "retreat": "the party retreats"}.get(ended) or outcome.split(":")[0].rstrip("."))
        return True

    # ------------------------------------------------------------------ what the table sees
    def view(self, gm=True):
        v = {"mode": self.mode, "label": LABEL[self.mode], "started": self.started, "history": list(self.history[-12:]),
             "checks": list(self.checks[-8:]), "fights": self.fights}
        if gm:
            v["cards"] = [dict(c) for c in self.cards]
        return v


def player_view(snap):
    """A seat's cut: the scene, its history and checks, never the GM's cards."""
    if not isinstance(snap, dict) or not isinstance(snap.get("pillar"), dict):
        return snap
    out = dict(snap)
    out["pillar"] = {k: v for k, v in snap["pillar"].items() if k != "cards"}
    return out
