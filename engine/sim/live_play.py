"""LIVE-PLAY-01 (GM 2026-10-19: "make sure attacks and effects can be dragged from a player character sheet onto
another token and checking the action passes the SRD"; then "Use the simulator: let players choose actions in a live
fight, starting with weapon attacks dragged from the sheet, then spells").

A simulator fight in which people play the characters marked live: the fight runs in its own thread, and on a live
character's turn it waits for that player's choices. Each choice is checked here against SRD 5.2.1 before anything is
rolled, and then resolved by the simulator's own code (Party.attack: sight, Advantage/Disadvantage, Bless, Vex, Sneak
Attack, the fake FG's attack and damage rolls) exactly as for a scripted character. The creatures play as usual.

Slice 1: weapon attacks (the sheet's weapon and ranged weapon; attack cantrips the builds carry as their weapon), the
Attack action with Extra Attack, movement within Speed, ending the turn. Slice 2: spells (sim/live_spells.py).
Slice 3 (2026-10-20): Dash, Disengage, Dodge, Cunning Action, doors (sim/live_actions.py). Reactions chosen by a
person: Shield and Counterspell, asked live (SPELL-BATCH-02, sim/live_reactions.py); not yet the others. GM 2026-10-23: the Sorcerer's Innate Sorcery, Font of Magic and
Metamagic, on spells and on attack cantrips (sim/live_sorcery.py).

SRD 5.2.1 checks before an attack (Playing the Game, "Actions" / "Attack", "Making an Attack"; Rules Glossary):
- it is this character's turn, the character is not down and not Incapacitated (no actions);
- the Attack action: taking it uses the action; it allows `attacks` attacks (Extra Attack), made during that action;
- the target is another creature that is still in the fight (attacks on creatures at 0 HP are not simulated);
- melee: within the weapon's reach; ranged: within its range (the builds keep the longest range as `reach`);
- no wall between attacker and target (the simulator has no partial cover for walls: a wall blocks).
"""
import copy, queue, threading, time, uuid

EXTRA = ("ranged", "offhand", "torch", "unarmed") + __import__("character_rules").MORE_ATTACKS                    # torch: LIGHTS-01, a lit Torch in hand (sim/light_sources.py); unarmed: MONK-01, a Monk's Unarmed Strike                            # weapons a sheet carries besides `weapon` (offhand: the Light
                                                          # property's extra attack, GM 2026-10-25)
# LIVE-UNDO-01 (GM 2026-10-21: "All the combat tools need an undo if they don't trigger any other event and their turn
# accidently hits the wrong button. Like taking a disengage action when they can't move where they would be aggressed."):
# the choices a player may take back, on the same turn, while they changed nothing but the character's own turn.
UNDOABLE = ("move", "dash", "disengage", "dodge", "ready", "stand", "drop_prone")
NO_UNDO = {"attack": "an attack rolls dice.", "cast": "a spell can't be taken back (slots, dice, effects).",
           "door": "a door changes the map for everyone.", "help": "Help marks another creature.",
           "stabilize": "Stabilizing rolls Medicine.",
           "hide": "Hide rolls Stealth.", "search": "Search rolls Perception.", "second_wind": "Second Wind rolls and heals.",
           "action_surge": "Action Surge gives one more action.",
           "rage": "Rage spends a use.", "lay_on_hands": "Lay On Hands spends the pool and heals.",
           "grapple": "a Grapple rolls a saving throw.", "shove": "a Shove rolls a saving throw.",
           "innate_sorcery": "Innate Sorcery spends a use.", "font_convert": "Font of Magic changed a slot into points.",
           "font_create": "Font of Magic changed points into a slot.",
           "martial_arts": "an Unarmed Strike rolls dice.", "flurry": "Flurry of Blows spends a Focus Point and rolls dice.",
           "patient_defense": "Patient Defense is a Bonus Action (it may spend a Focus Point).",
           "step_of_the_wind": "Step of the Wind is a Bonus Action (it may spend a Focus Point).",
           "superior_defense": "Superior Defense spends 3 Focus Points.", "use_item": "an item was used from the bag (or a tool's check rolled).",
           "study": "Study rolls a check.", "influence": "the GM was asked to rule it.",
           "ask_gm": "the GM was asked to rule it.", "trap": "a trap or a lock changed.",
           "light": "a light changes what everyone sees."}                    # LIGHTS-01
UNDO_LABEL = {"move": "move", "dash": "Dash", "disengage": "Disengage", "dodge": "Dodge", "ready": "Ready",
              "attack": "attack", "cast": "spell", "door": "door", "stand": "Stand up", "drop_prone": "Drop prone"}


class Quit(Exception):
    pass


class LiveError(ValueError):
    pass


def monk_summary(fight, me):
    import monk
    return monk.of(fight).summary(me)


def nick(c):
    """Nick (SRD 5.2.1 Weapon Mastery): the Light property's extra attack is part of the Attack action, not a Bonus
    Action (once per turn)."""
    return bool((c.get("offhand") or {}).get("nick") or (c.get("weapon") or {}).get("nick"))


def sheet_attacks(c):
    """The attacks on a character sheet the table can drag: [{'key', 'name', 'reach', 'atk', 'dmg', 'spell'}]."""
    out = []
    for key in ("weapon",) + EXTRA:
        w = c.get(key)
        if isinstance(w, dict) and w.get("name"):
            out.append({"key": key, "name": w["name"], "reach": w.get("reach", 5), "atk": w.get("atk", 0),
                        "dmg": w.get("dmg", ""), "type": w.get("dmgtype", ""), "ranged": w.get("reach", 5) > 10,
                        "cantrip": (not w.get("dmgtype") and w.get("reach", 5) > 10) or bool(w.get("cantrip")),
                        **({"choices": w["dmg_choices"]} if w.get("dmg_choices") else {}),
                        **({"light_extra": "attack" if nick(c) else "bonus"} if key == "offhand" else {})})
    return out


EFFECT_SECONDS = 8      # a cast's effect stays in the live state this long (screens poll every second)


class LiveFight:
    """One live fight. The simulator thread calls turn(); the service calls act() and snapshot() from its threads."""

    def __init__(self, sim, rounds=20, live_ids=None, on_done=None, ask_reactions=False):
        self.sim, self.rounds = sim, rounds
        self.live_ids = set(live_ids if live_ids is not None else [c["id"] for c in sim.sc["combatants"] if c.get("pc")])
        for c in sim.sc["combatants"]:
            if c["id"] in self.live_ids:
                c["live"] = True
                c.pop("script", None)
        sim.live = self
        import live_spells
        self.spells = live_spells.LiveSpells(self)                   # slice 2: spells (sim/live_spells.py)
        import referee
        self.referee = getattr(sim, "referee", None) or referee.Referee(self)   # REFEREE-01: the rules referee
        self.referee.fight = self                                    # (sim/referee.py), the simulator's own
        import live_actions
        self.actions = live_actions.LiveActions(self)   # slice 3
        import live_sorcery
        self.sorcery = live_sorcery.Sorcery(self)       # GM 2026-10-23: the Sorcerer
        import live_items
        self.items = live_items.LiveItems(self)         # GM 2026-10-23: items from the bag (prerequisites checked)
        self.market = None                              # the service's Market (the bags); None: each sheet's own "bag"
        import live_asks
        self.asks = live_asks.Asks(self)                # GM 2026-10-24: everything else on the sheet, ruled by the GM
        self.asks_open, self.ask_n = [], 0
        import map_layers
        self.layers = map_layers.Layers(self)           # MAP-LAYERS-01: spell zones, who sees whom, mounts
        import invisibility
        self.invisibility = invisibility.LiveInvisibility(self)   # INVISIBILITY-01: the Invisibility spell
        import attitude
        self.attitudes = attitude.Attitudes(self)       # GM 2026-10-24: attitudes and morale (sim/attitude.py)
        self.scenes = None                              # GM 2026-10-26: a social or exploration scene (sim/scenes.py)
        import light_sources
        self.lights = light_sources.LiveLights(self)    # LIGHTS-01: torches, lanterns and the light spells
        import live_reactions
        self.reactions = live_reactions.Reactions(self)  # SPELL-BATCH-02: Shield and Counterspell, asked live
        self.reactions.asking = ask_reactions           # only where a screen can answer (the service), never a test fight
        self.monitor = None                             # RULES-MONITOR-01: the service's Rules monitor (sim/rules_monitor.py)
        self.lock = threading.RLock()                            # play-test 2026-11-02: re-entrant, because building a player's offers
                                                                 # under this lock can end a timed condition, and its log line takes it too
        self.changed = threading.Condition(self.lock)
        self.inbox = queue.Queue()
        self.fight_id, self.turn_serial = uuid.uuid4().hex, 0
        self.revision, self.waiting, self.turn_state, self.done, self.error = 0, None, None, False, None
        self.log, self.log_n = [], 0
        self.effects, self.effect_n = [], 0                      # cast effects every screen draws (EFFECT_SECONDS)
        self.snap = None
        self.undo = []                                           # LIVE-UNDO-01: this turn's choices, newest last
        self.undo_asked = None                                   # a player's undo waiting for the GM's approval
        self.on_done = on_done
        real_say = sim.say

        def say(kind, text):
            real_say(kind, text)
            with self.lock:
                self.log_n += 1
                self.log = (self.log + [{"n": self.log_n, "kind": kind, "text": str(text)}])[-400:]

        sim.say = say
        sim.S.say = say
        # 2026-10-20 (GM: "The simulator stopped: URLError ... [WinError 10060]"): a quit must stop the fight even while its
        # creatures act. The creatures pass a checkpoint at every decision, so the fight stops at the next one.
        self.stopping = False
        self.frozen = False                                      # GM 2026-10-24: the GM froze the fight (End the adventure)
        self.gm_control = {}                                     # GM 2026-10-24: character id -> "gm" (taken) or "player" (handed)
        self.thawed = threading.Event(); self.thawed.set()
        # GM-UNDO-01 (tools/sim_service.py): a rebuilt fight replays its steps, one creature's turn at a time
        self.on_step, self.creature_turns, self.released = None, 0, 0
        self.held, self.replaying, self.rewinds, self.inflight = False, False, 0, None
        # GM 2026-11-01: the tracker's turn timer; a frozen fight's clock waits
        self.timer_on, self.turn_began, self.turn_paused, self.pause_began = True, None, 0.0, None
        self.by_srd = False                                      # BY-THE-SRD-01: the GM's By the SRD switch

        def checkpoint():
            while not self.thawed.wait(0.5):                     # frozen: the creatures wait at their next step
                if self.stopping:
                    raise Quit()
            if self.stopping:
                raise Quit()

        sim.checkpoint = checkpoint
        self.thread = threading.Thread(target=self._run, daemon=True)

    # ------------------------------------------------------------------ the simulator thread
    def start(self):
        cr = getattr(self.sim, "creatures", None)      # RULES-MONITOR-01: a creature's whole turn is one action watched
        if cr is not None and not getattr(cr, "watched", False):
            take = cr.take_turn

            def take_turn(cid):
                self.creature_turn(cid)
                start = self.log_n
                try:
                    return take(cid)
                finally:
                    self.watched(cid, "its turn (creature)", start)
            cr.take_turn, cr.watched = take_turn, True
        self.thread.start()
        return self

    def creature_turn(self, cid):
        """GM-UNDO-01: each creature's turn is a step of the fight."""
        self.creature_turns += 1
        if self.on_step:
            self.on_step(cid)

    def hold_turn(self, cid):
        """GM-UNDO-01, on the fight's own loop with a creature's turn next (Sim.combat). A replay stands here until that turn's
        place on the timeline comes, and a fight taken back stands here, frozen, until the GM goes on. The GM's choices still
        land; True makes the loop look again, since they may have changed who acts."""
        if not self.replaying or self.released > self.creature_turns:
            return False
        with self.lock:
            self.held = True
            self.revision += 1
            self._publish_locked()
        hz = getattr(self.sim, "hazards", None)
        while self.held and not self.stopping:
            if (hz.drain() if hz else False) | self.attitudes.drain():
                with self.lock:
                    self.revision += 1
                    self._publish_locked()
                if self.attitudes.over():
                    self.held = False
            time.sleep(0.002)
        self.sim.checkpoint()
        return True

    def release(self, timeout=60):
        """A replay: the creature's turn it stands before. False when the fight isn't standing there."""
        turns = self.creature_turns
        self.settle(timeout)
        if not self.held:
            return False
        self.released, self.held = turns + 1, False
        end = time.monotonic() + timeout
        while self.creature_turns == turns and not self.done and time.monotonic() < end:
            time.sleep(0.002)
        return self.creature_turns > turns

    def turn_clock(self):
        """How long this turn has run, in whole seconds, not counting a freeze; None between turns."""
        if self.turn_began is None:
            return None
        now = self.pause_began if self.pause_began is not None else time.monotonic()
        return max(0, int(now - self.turn_began - self.turn_paused))

    def set_by_srd(self, on):
        with self.lock:
            self.by_srd = bool(on)
            self.revision += 1
            self._publish_locked()
        self.sim.say("note", "By the SRD: Hide and Spirit Guardians play as the SRD writes them." if self.by_srd else
                     "By the SRD is off: this table's rulings for Hide and Spirit Guardians apply.")

    def set_timer(self, on):
        with self.lock:
            self.timer_on = bool(on)
            self.revision += 1
            self._publish_locked()

    def watched(self, actor, action, start, cmd=None):
        """RULES-MONITOR-01: hand an action to the Rules monitor when the GM has it on (queued, never waited on)."""
        m = self.monitor
        if m is None or not m.on:
            return
        import rules_monitor
        rec = rules_monitor.record(self, actor, action, start, cmd)
        if rec:
            m.submit(rec)

    def _run(self):
        try:
            self.sim.run(self.rounds, 20)
            if self.attitudes.over():                            # GM 2026-10-24: how the fight ended (a winner or not)
                self.attitudes.finish()
        except Quit:
            pass
        except Exception as e:                                   # shown to the table, never hidden
            if not self.stopping:                                # a quit can surface through Lua as another error
                self.error = "%s: %s" % (type(e).__name__, e)
        finally:
            with self.lock:
                self.done, self.waiting = True, None
                self._publish_locked()
            self.attitudes.refuse_waiting()
            if self.scenes:
                self.scenes.refuse_waiting()
            if getattr(self.sim, "hazards", None):
                self.sim.hazards.refuse_waiting()
            # A quit/error must answer commands left in the queue, not leave callers waiting 120 s.
            while True:
                try:
                    _, reply = self.inbox.get_nowait()
                except queue.Empty:
                    break
                reply.put({"ok": False, "status": 409, "refused": "The fight is over."})
            try:
                self.sim.close()
            except Exception:
                pass
            if self.on_done:
                self.on_done(self)

    def turn(self, ctid):
        """Called by Sim.run on a live character's turn: wait for the player's choices until the turn ends."""
        sim, c = self.sim, self.sim.by_id(ctid)
        if sim.party:
            sim.party.turn_start(ctid)
            sim.party.actor = ctid
        gm = getattr(sim, "gm_rules", None)
        self.reactions.turn_start(ctid)                          # SPELL-BATCH-02: Shield's +5 AC ends
        if gm:                                                   # GM 2026-10-24 ("Check movement rules"): the turn-start
            gm.pc_turn_start(ctid, live=True)                    # conditions (Slowed, Grappled, Exhaustion, swimming, burning)
        speed = c["_speed_now"] if "_speed_now" in c else int(str(c.get("speed", "30")).split()[0])
        self.turn_state = {"id": ctid, "movement": speed, "speed": speed, "action_used": False, "attacks_left": 0,
                           "sneak_used": False, "attacks_made": 0}
        c.pop("dodging", None)                                  # slice 3: Dodge lasts until the start of its next turn
        self.actions.turn_start(ctid)                          # slice 4: its readied attack and its Help lapse
        self.layers.live_turn_start(ctid)                      # MAP-LAYERS-01: riding, Stinking Cloud, a zone's time
        self.spells.turn_start(ctid)                           # Hex: a later turn after its creature dropped moves it
        self.invisibility.turn_start(ctid)                     # INVISIBILITY-01: its hour
        self.lights.turn_start(ctid)                           # LIGHTS-01: burned out, dispelled, dropped
        import more_spells
        more_spells.live_turn_start(self, ctid)                # SPELL-EFFECTS-01: Haste, Slow, zones, summons
        self.undo, self.undo_asked = [], None
        with self.lock:
            self.turn_serial += 1
            self.waiting = ctid
            self.turn_began, self.turn_paused = time.monotonic(), 0.0
            self.pause_began = self.turn_began if self.frozen else None
            self._publish_locked()
        try:
            while True:
                if self.stopping:
                    raise Quit()
                try:
                    cmd, reply = self.inbox.get(timeout=0.2)
                except queue.Empty:                              # GM 2026-10-24: the GM's scene choices meanwhile
                    hz = getattr(sim, "hazards", None)           # HAZARDS-01: and the GM's hazards
                    if (hz.drain() if hz else False) | self.attitudes.drain():
                        with self.lock:
                            self.revision += 1
                            self._publish_locked()
                        if self.attitudes.over():                # a truce, a retreat, the last foe surrendered
                            break
                    continue
                if cmd.get("op") == "quit":
                    reply.put({"ok": True}); raise Quit()
                try:
                    # The single simulation worker owns application. An admission-time check is not
                    # enough: another admitted request may already have committed or ended the turn.
                    with self.lock:
                        stale = (self.stopping or cmd.get("revision") != self.revision
                                 or cmd.get("_turn") != self.turn_serial or cmd.get("_actor") != ctid)
                    was = dict(self.turn_state or {})
                    began = self.log_n
                    out = ({"ok": False, "status": 409, "refused": "Stale: the fight has moved on."}
                           if stale else self._choose(ctid, cmd))
                    if out.get("ok") and cmd.get("op") not in ("end", "undo", "undo_approve", "undo_refuse"):
                        self.watched(ctid, str(cmd.get("op")) + (" " + cmd["spell"] if cmd.get("spell") else ""), began, cmd)
                    __import__("epic_boons").live_after(self, ctid, cmd, was, out)   # EPIC-BOONS-01
                except LiveError as e:
                    out = {"ok": False, "refused": str(e)}
                self.layers.sweep()                              # MAP-LAYERS-01: a zone whose Concentration ended
                self.lights.sweep()                              # LIGHTS-01: a light dispelled or dropped meanwhile
                with self.lock:
                    if out.get("ok"):
                        self.revision += 1
                    if cmd.get("op") == "end" and out.get("ok"):
                        self.waiting = None
                    self._publish_locked()
                    out["snapshot"] = self.snap
                reply.put(out)
                if cmd.get("op") == "end" and out.get("ok"):
                    break
                if self.attitudes.over():                        # the last foe surrendered or stood down
                    break
        finally:
            self.layers.live_turn_end(ctid)
            if self.turn_state and self.turn_state.get("disengaged"):
                sim.S.removeEffect(ctid, "Note: Disengage")   # slice 3: Disengage ends with the turn
            if sim.party:
                sim.party.end_turn(ctid)
            gm = getattr(sim, "gm_rules", None)
            if gm:
                gm.pc_turn_end(ctid)                             # GM 2026-10-24: end-of-turn saves (Charmed, Frightened)
            self.turn_state, self.undo, self.undo_asked = None, [], None
            # The playtester's finding 1 (GM 2026-10-27: "let's fix finding 1"): a turn the fight ended (the last foe
            # down, surrendered or fled, a truce) is no longer shown, nor its buttons, while the others' turns run on.
            with self.lock:
                self.turn_began = None
                if self.waiting == ctid:
                    self.waiting = None
                    self._publish_locked()

    # ------------------------------------------------------------------ LIVE-UNDO-01: taking a choice back
    def _choose(self, me, cmd):
        """A choice, remembered so the player can take it back this turn (undo) when it touched nothing else.
        GM 2026-10-21 ("or rather approve an undo button"): a player's undo is a request; the GM approves or refuses it.
        Any other choice before that, or the turn's end, lets the request lapse."""
        op = cmd.get("op")
        if op == "undo":
            return self._ask_undo(me)
        if op in ("undo_approve", "undo_refuse"):
            return self._answer_undo(me, op == "undo_approve")
        keep = self._undo_point(me) if op in UNDOABLE and not cmd.get("spell") else None   # a readied spell spent a slot
        start = self.log_n
        try:
            import more_spells                                   # SPELL-EFFECTS-01: Haste's extra action, Slow's limits
            out = more_spells.choose(self, me, cmd, self._do)
        except LiveError:
            if self.log_n != start:                              # something happened: an open request lapses
                self.undo_asked = None
            if keep is None and op != "end" and self.log_n != start:      # refused after it began: nothing to take back
                self.undo.append({"op": op, "why": NO_UNDO.get(op, "it can't be taken back.")})
            raise
        if out.get("ok"):
            self.undo_asked = None                               # something new happens: an open request lapses
            self.attitudes.after_choice(me, cmd)                 # GM 2026-10-24: attacks provoke, help befriends
        if out.get("ok") and op != "end":
            why = self._undo_blocker(me, keep, out) if keep else NO_UNDO.get(op, "it can't be taken back.")
            self.undo.append({"op": op, "keep": keep, "why": why})
        return out

    def _undo_point(self, me):
        """The acting character's own turn, before a choice: what an undo puts back."""
        c, party = self.sim.by_id(me), self.sim.party
        with self.lock:
            log_n = self.log_n
        return {"turn": copy.deepcopy(self.turn_state), "pos": tuple(party.pos(me)), "dodging": c.get("dodging"),
                "bonus": party.bonus_turn.get(me), "has_bonus": me in party.bonus_turn,
                "readied": self.actions.readied.get(me), "log_n": log_n, "world": self._world(me)}

    def _world(self, me):
        """Everything a choice may change besides the character's own turn: dice, every creature (HP, conditions,
        effects, Reactions, place), who noticed whom, what the party sees, doors, anything still queued."""
        import sim_messages
        sim = self.sim
        s = sim.S
        rows = {}
        for e in sim_messages.state(sim, 0, None)["combatants"]:
            i = e["id"]
            e = dict(e, reaction=int(s.getField(i, "reaction")),
                     effects=sorted(str(v) for v in s.effectLabels(i).values() if not (i == me and str(v) == "Note: Disengage")))
            if i == me:                                          # its place is the choice itself
                for k in ("x", "y", "underwater", "aloft", "flying", "fly_ft"):
                    e.pop(k, None)
            rows[i] = e
        aware, queued = sim.awareness(), sim.queued()
        pcs =[c["id"] for c in sim.sc["combatants"] if c.get("pc") and not sim.down(c["id"])]
        seen = [c["id"] for c in sim.sc["combatants"] if not c.get("pc") and any(sim.sees(i, c["id"]) for i in pcs)]
        return {"rng": sim.rng.getstate(), "rows": rows, "aware": aware, "queued": queued + len(sim.later),
                "seen": seen, "doors": sorted(str(d) for d in (sim.walls or {}).get("open_doors", [])),
                "helped": dict(getattr(sim.gm_rules, "helped", None) or {}), "problems": len(sim.problems),
                "readied": {k: v for k, v in self.actions.readied.items() if k != me}}

    def _undo_blocker(self, me, keep, out):
        """Why this choice can't be taken back (it set something else going), or None."""
        if out.get("stopped"):
            return "the move was stopped: %s" % out["stopped"]
        sim, was, now = self.sim, keep["world"], self._world(me)
        if was["rng"] != now["rng"]:
            return "dice were rolled."
        for i, row in now["rows"].items():
            old = was["rows"].get(i)
            if row != old:
                if old and row.get("reaction") != old.get("reaction"):
                    return "%s used a Reaction." % row["name"]
                return "%s was affected." % row["name"]
        if was["aware"] != now["aware"]:
            return "a creature noticed the party."
        new = [sim.by_id(i)["name"] for i in now["seen"] if i not in was["seen"]]
        if new:
            return "the party now sees %s." % ", ".join(new)
        if was["doors"] != now["doors"]:
            return "a door opened or closed."
        if (was["queued"], was["helped"], was["readied"], was["problems"]) != (now["queued"], now["helped"], now["readied"], now["problems"]):
            return "something else in the fight changed."
        name = sim.by_id(me)["name"]
        import run_sim
        with self.lock:
            lines = [(e["kind"], e["text"]) for e in self.log if e["n"] > keep["log_n"]]
        for kind, text in lines:                                  # only the choice's own lines ("Hero 4 moves to ...")
            if not ((kind == "turn" and text.startswith(name + " ")) or run_sim.Sim._sync_noise(text)):
                return "something happened: %s" % text
        return None

    def undo_offer(self):
        """For the sheet: can the last choice be taken back, and why not."""
        if not self.undo:
            return {"ready": False, "why": "Nothing to undo this turn."}
        top = self.undo[-1]
        import live_actions
        label = UNDO_LABEL.get(top["op"]) or live_actions.NAMES.get(top["op"], top["op"])
        if top["why"]:
            return {"ready": False, "op": top["op"], "label": label, "why": "Can't undo the %s: %s" % (label, top["why"])}
        if self.undo_asked:
            return {"ready": False, "asked": True, "op": top["op"], "label": label,
                    "why": "Undo of the %s asked: waiting for the GM." % label}
        return {"ready": True, "op": top["op"], "label": label}

    def _ask_undo(self, me):
        offer = self.undo_offer()
        if not offer["ready"]:
            raise LiveError(offer["why"])
        name = self.sim.by_id(me)["name"]
        self.undo_asked = {"pc": me, "name": name, "op": offer["op"], "label": offer["label"]}
        self.sim.say("turn", "%s asks to take back the %s (waiting for the GM)" % (name, offer["label"]))
        return {"ok": True, "result": "undo_asked", "label": offer["label"]}

    def _answer_undo(self, me, approve):
        ask = self.undo_asked
        if not ask:
            raise LiveError("No undo is waiting for the GM (another choice or the turn's end cancels a request).")
        self.undo_asked = None
        if approve:
            return self._undo(me, gm=True)
        self.sim.say("turn", "The GM refuses %s's undo of the %s" % (ask["name"], ask["label"]))
        return {"ok": True, "result": "undo_refused", "label": ask["label"]}

    def _undo(self, me, gm=False):
        """Put the character's own turn back as it was before its last choice (approved by the GM)."""
        offer = self.undo_offer()
        if not offer["ready"]:
            raise LiveError(offer["why"])
        keep, sim, party = self.undo[-1]["keep"], self.sim, self.sim.party
        c, t, s = sim.by_id(me), self.turn_state, sim.S
        if t.get("disengaged") and not keep["turn"].get("disengaged"):
            s.removeEffect(me, "Note: Disengage")
        if tuple(party.pos(me)) != keep["pos"]:
            self._put_back(me, *keep["pos"])
        t.clear()
        t.update(copy.deepcopy(keep["turn"]))
        if keep["dodging"] is None:
            c.pop("dodging", None)
        else:
            c["dodging"] = keep["dodging"]
        if keep["has_bonus"]:
            party.bonus_turn[me] = keep["bonus"]
        else:
            party.bonus_turn.pop(me, None)
        if keep["readied"] is None:
            self.actions.readied.pop(me, None)
        else:
            self.actions.readied[me] = keep["readied"]
        self.undo.pop()
        sim.settle()
        sim.say("turn", "%s takes back the %s (%s)" % (c["name"], offer["label"], "approved by the GM" if gm else "undo"))
        return {"ok": True, "result": "undo", "undone": offer["op"], "label": offer["label"]}

    def _put_back(self, me, x, y):
        """Return the token to where the move began without a step: no Opportunity Attack, readied attack or wall audit
        (it never left the turn's own path). The bridge's onMove still learns the place (a Disengage note while it does)."""
        s = self.sim.S
        hook = s.tokenMoved
        s.tokenMoved = None
        s.addEffect(me, "Note: Disengage", True)
        try:
            self.sim.place(me, x, y)
        finally:
            s.removeEffect(me, "Note: Disengage")
            s.tokenMoved = hook

    def _do(self, me, cmd):
        op = cmd.get("op")
        if op == "end":
            return {"ok": True}
        if op == "move":
            return self._move(me, cmd)
        if op == "attack":
            return self._attack(me, cmd)
        if op == "cast":
            return self._cast(me, cmd)
        if op == "use_item":                                     # GM 2026-10-23: from the bag (sim/live_items.py)
            return self._use_item(me, cmd)
        if op == "light":                                        # LIGHTS-01: torches, lanterns, the light spells
            return self._light(me, cmd)
        if op in ("mount", "dismount", "mount_action", "mount_consent"):   # mount_consent: GM 2026-10-25 (M2)          # MAP-LAYERS-01: Mounted Combat (sim/map_layers.py)
            return self._layer(me, cmd)
        import more_spells
        if op in more_spells.ops():                              # SPELL-EFFECTS-01: a zone moved, a web broken, a summons
            start = self.log_n
            try:
                out = more_spells.act(self, me, cmd)
            except more_spells.EffectError as e:
                raise LiveError(str(e))
            self.sim.settle()
            with self.lock:
                out["lines"] = [e["text"] for e in self.log if e["n"] > start]
            return out
        if op == "ask_gm":                                       # GM 2026-10-24: Ask the GM (sim/live_asks.py)
            import live_asks
            start = self.log_n
            try:
                out = self.asks.do(me, cmd)
            except live_asks.AskError as e:
                raise LiveError(str(e))
            with self.lock:
                lines = [e["text"] for e in self.log if e["n"] > start]
            return dict(out, ok=True, result="ask_gm", lines=lines)
        if op in ("dash", "disengage", "dodge", "door", "help", "hide", "search", "ready", "second_wind", "action_surge", "rage", "stand", "drop_prone",
                  "shake", "stabilize", "spirit_strike",         # GM 2026-10-25 (ruling L4; Spiritual Weapon)
                  "extinguish",                                  # GM 2026-10-26: SRD 5.2.1 Burning
                  "lay_on_hands", "grapple", "shove",                  # slices 3 and 4 (sim/live_actions.py)
                  "innate_sorcery", "font_convert", "font_create",     # GM 2026-10-23: the Sorcerer
                  "dragon_wings", "fold_wings",                        # SORCERER-20: Dragon Wings (sim/live_sorcery.py)
                  "study", "influence",                                # GM 2026-10-23: sim/live_lore.py
                  "trap",                                              # GM 2026-10-24: sim/traps.py
                  "abjure_foes",                                       # GM 2026-10-26: sim/high_levels.py
                  "intimidating_presence", "holy_nimbus",              # MARTIAL-HIGH: sim/martial_high.py
                  "martial_arts", "flurry", "patient_defense", "step_of_the_wind",    # MONK-01: sim/monk.py
                  "superior_defense",                                  # GM 2026-10-28: Monk 18
                  "merge_shadows", "blink_steps"):                     # EPIC-BOONS-01: sim/epic_boons.py
            return self._action(me, cmd)
        raise LiveError("Not something a character can do yet (attack, cast, move, dash, disengage, dodge, help, hide, search, ready, a door, class Bonus Actions, grapple, shove, Innate Sorcery, Font of Magic, end the turn).")

    def _action(self, me, cmd):
        """Slice 3: Dash, Disengage, Dodge, a door (sim/live_actions.py)."""
        import live_actions
        start = self.log_n
        try:
            out = self.actions.do(me, cmd)
        except live_actions.ActionError as e:
            raise LiveError(str(e))
        self.sim.settle()
        with self.lock:
            out["lines"] = [e["text"] for e in self.log if e["n"] > start]
        return out

    def _layer(self, me, cmd):
        import map_layers
        start = self.log_n
        try:
            out = getattr(self.layers, cmd["op"])(me, cmd)
        except map_layers.LayerError as e:
            raise LiveError(str(e))
        self.sim.settle()
        with self.lock:
            out["lines"] = [e["text"] for e in self.log if e["n"] > start]
        return out

    def _light(self, me, cmd):
        import light_sources
        start = self.log_n
        try:
            out = self.lights.do(me, cmd)
        except (light_sources.LightError, ValueError) as e:
            raise LiveError(str(e))
        if out.get("do") == "cast":                              # INVISIBILITY-01: a spell cast ends the caster's
            import invisibility
            invisibility.cast_spell(self.sim, me, cmd.get("spell"))
        self.sim.settle()
        with self.lock:
            out["lines"] = [e["text"] for e in self.log if e["n"] > start]
        return out

    def _use_item(self, me, cmd):
        import live_items
        start = self.log_n
        try:
            paid = self.items.do(me, cmd)
        except (live_items.ItemError, ValueError) as e:
            raise LiveError(str(e))
        self.sim.settle()
        with self.lock:
            lines = [e["text"] for e in self.log if e["n"] > start]
        return {"ok": True, "result": "use_item", "item": cmd.get("item"), "paid": paid, "lines": lines}

    # ------------------------------------------------------------------ GM 2026-10-24: Ask the GM
    def add_ask(self, pc, name, kind, what, targets, note):
        with self.lock:
            self.ask_n += 1
            self.asks_open.append({"n": self.ask_n, "pc": pc, "name": name, "kind": kind, "what": what,
                                   "targets": list(targets), "note": note})
            return self.ask_n

    def rule_ask(self, n, text, allow=False):
        """The GM's ruling on a request (from the GM's screen, any time in the fight): logged for everyone. allow: the GM
        lets a character climb out of a pit (sim/traps.py), with its own movement on its turn."""
        with self.lock:
            a = next((a for a in self.asks_open if a["n"] == n), None)
            if not a:
                raise LiveError("No open request %s." % n)
            self.asks_open.remove(a)
            self.log_n += 1
            text = str(text or "").strip()[:300] or ("may climb out" if allow else "done as asked")
            if allow and getattr(self.sim, "traps", None):
                self.sim.traps.allowed.add(a["pc"])
            self.log = (self.log + [{"n": self.log_n, "kind": "gm", "text": "The GM rules %s's %s (request %d): %s" % (
                a["name"], a["what"], n, text)}])[-400:]
            self.revision += 1
            self._publish_locked()
            return {"ok": True, "ruled": n}

    def _cast(self, me, cmd):
        """Slice 2: a spell from the sheet, checked against SRD 5.2.1 and resolved by the simulator's spell code
        (sim/live_spells.py); the reply carries its real area for the table's effect graphics."""
        import live_spells, map_layers, invisibility, more_spells
        start = self.log_n
        try:                                                     # SPELL-EFFECTS-01: Silence (no Verbal component), Slow
            failed = more_spells.before_cast(self, me, cmd)     # (a Somatic spell fails 25 percent of the time)
        except more_spells.EffectError as e:
            raise LiveError(str(e))
        if failed:
            self.sim.settle()
            with self.lock:
                failed["lines"] = [e["text"] for e in self.log if e["n"] > start]
            return failed
        if cmd.get("spell") in map_layers.ZONE_SPELLS:           # MAP-LAYERS-01: Fog Cloud, Darkness, Stinking Cloud
            with self.referee.watch(me, cmd.get("spell"), cmd) as w:   # REFEREE-02: checked too; its later saves after
                try:
                    effect = self.layers.cast(me, cmd)
                except map_layers.LayerError as e:
                    raise LiveError(str(e))
                invisibility.cast_spell(self.sim, me, cmd.get("spell"))   # INVISIBILITY-01: a spell cast ends it
                self.sim.settle()
                w["effect"].update(effect or {})
            with self.lock:
                lines = [e["text"] for e in self.log if e["n"] > start]
            return {"ok": True, "result": "cast", "lines": lines, "effect": effect, "referee": w["notes"],
                    "effect_n": self._show(me, cmd.get("spell"), effect)}
        import high_levels                                       # CASTER-HIGH: no slot (Spell Mastery, Signature Spells,
        try:                                                     # Divine Intervention), Overchannel
            how = high_levels.arm(self.sim.party, me, cmd.get("spell"), cmd)
        except high_levels.HighError as e:
            raise LiveError(str(e))
        with self.referee.watch(me, cmd.get("spell"), cmd) as w:  # REFEREE-01: what the cast changes is checked after
            try:
                effect = self.spells.cast(me, cmd)
            except live_spells.SpellError as e:
                raise LiveError(str(e))
            finally:
                high_levels.disarm(self.sim.party, me)
            self.sim.settle()
            if how:
                w["cmd"]["free"] = how
            w["cmd"].update((effect or {}).pop("_cmd", None) or {})   # SPELL-CASTER-01: the creatures it really took
            w["effect"].update(effect or {})
            invisibility.cast_spell(self.sim, me, cmd.get("spell"))   # INVISIBILITY-01: a spell cast ends it
        with self.lock:
            lines = [e["text"] for e in self.log if e["n"] > start]     # the referee's notes too
        return {"ok": True, "result": "cast", "lines": lines, "effect": effect, "referee": w["notes"],
                "effect_n": self._show(me, cmd.get("spell"), effect)}

    def _show(self, me, spell, effect):
        """GM 2026-10-22: "the phone display doesn't shows effects". A cast's effect goes into the live state for
        EFFECT_SECONDS, so every screen draws it once (by its number), not only the screen that cast it."""
        if not effect:
            return None
        with self.lock:
            self.effect_n += 1
            self.effects = (self.effects + [{"n": self.effect_n, "caster": me, "spell": spell, "effect": effect,
                                             "at": time.monotonic()}])[-12:]
            return self.effect_n

    def _move(self, me, cmd):
        try:
            x, y = int(cmd["x"]), int(cmd["y"])
        except (KeyError, TypeError, ValueError):
            raise LiveError("Move where? Give a square (x, y).")
        t = self.turn_state
        reason = self.movement_blocked(me) or self.layers.ride_blocked(me)   # MAP-LAYERS-01: an independent mount
        if reason:
            raise LiveError(reason)
        if t["movement"] <= 0:
            raise LiveError("No movement left this turn.")
        before = self.sim.party.pos(me) if self.sim.party else None
        crawl = 2 if self.prone(me) else 1                       # SRD 5.2.1 Crawling: 1 extra foot for every foot while Prone
        route = self.route(me, x, y, t["movement"] // crawl)
        dashed = None
        if isinstance(route, str) and cmd.get("dash"):           # GM 2026-10-24: Dash to reach a square past the movement left
            dashed = self.dash_by(me)
            if not dashed:
                raise LiveError("%s cannot Dash now: %s" % (self.sim.by_id(me)["name"], route))
            if isinstance(self.route(me, x, y, (t["movement"] + t["speed"]) // crawl), str):
                raise LiveError("Too far even with a Dash.")
            self._action(me, {"op": "dash", "bonus": dashed == "bonus"})
            route = self.route(me, x, y, t["movement"] // crawl)
        if isinstance(route, str):
            raise LiveError(route)
        path, _ = route
        import martial_high                                      # MARTIAL-HIGH: Tactical Shift, no Opportunity Attacks
        shift = martial_high.shift_left(t)
        shift = shift and not dashed and not t.get("disengaged") and \
            not isinstance(self.route(me, x, y, min(shift, t["movement"]) // crawl), str)
        if shift:
            self.sim.S.addEffect(me, "Note: Disengage", True)
        try:
            cost, stopped = self._walk(me, path, crawl)
        finally:
            if shift:
                self.sim.S.removeEffect(me, "Note: Disengage")
        if not cost:
            raise LiveError(stopped or "That route is no longer available.")
        if shift:
            t["shift_ft"] = max(0, t["shift_ft"] - cost)
            self.sim.say("turn", "%s moves %d ft with %s: no Opportunity Attacks (%d ft of it left)" % (
                self.sim.by_id(me)["name"], cost, t.get("shift_name", "Tactical Shift"), t["shift_ft"]))
        t["movement"] -= cost
        out = {"ok": True, "moved_ft": cost, "from": before}
        if dashed:
            out["dashed"] = dashed
        if crawl > 1:
            out["crawled"] = True
        if stopped:
            out["stopped"] = stopped
        return out

    def prone(self, me):
        gm = getattr(self.sim, "gm_rules", None)
        return bool(gm and gm.cond.get(me, {}).get("Prone"))

    def dash_by(self, me):
        """How this character could Dash now: 'bonus' (Cunning Action, keeping the Action), 'action', or None."""
        import live_actions
        c = self.sim.by_id(me)
        if live_actions.cunning(c):
            try:
                self.actions.check(me, "dash", bonus=True)
                return "bonus"
            except live_actions.ActionError:
                pass
        try:
            self.actions.check(me, "dash")
            return "action"
        except live_actions.ActionError:
            return None

    def movement_blocked(self, me):
        """Current eligibility, separate from unspent movement. A reaction can change it mid-turn.

        Incapacitated alone is not a general movement prohibition; check the actual condition.
        """
        if self.sim.down(me) or self.sim.party.deaths.get(me, {}).get("dead"):
            return "%s is down: movement stops." % self.sim.by_id(me)["name"]
        held = getattr(getattr(self.sim, "traps", None), "held", {}).get(me)     # GM 2026-10-24: sim/traps.py
        if held:
            return "%s is %s: no moving from there%s." % (self.sim.by_id(me)["name"], held["why"],
                                                       " (climb out: Other actions)" if held["until"] == "climb" else "")
        gm = getattr(self.sim, "gm_rules", None)
        if gm:
            for condition in ("Grappled", "Restrained", "Paralyzed", "Petrified", "Unconscious"):
                info = gm.cond.get(me, {}).get(condition)
                # Offers are built under the publication lock. Do not call gm.has here:
                # expiring a grapple logs/removes an effect and would re-enter that lock.
                if info and condition == "Grappled" and info.get("by"):
                    by = info["by"]
                    if self.sim.down(by) or gm.incapacitated(by) or gm.ft_between(by, me) > info.get("range", 5):
                        continue
                if info:
                    return "%s is %s: cannot move (Speed 0)." % (self.sim.by_id(me)["name"], condition)
        return None

    def route(self, me, x, y, budget):
        """The cheapest route to exactly square (x, y) within `budget` feet by SRD 5.2.1 movement (Sim.exact_route,
        shared with the scripted party since 2026-10-19). Returns (path in squares, feet) or the reason it cannot be
        done. Medium and smaller characters (one square)."""
        start = tuple(int(round(v)) for v in self.sim.party.pos(me))
        if (x, y) == start:
            return "%s is already there." % self.sim.by_id(me)["name"]
        return self.sim.exact_route(me, x, y, budget)

    def _walk(self, me, path, crawl=1):
        import ai_turn
        s = self.sim.S
        walked, extra, cost = [path[0]], 0, 0
        g, units, diag = self.sim.sc.get("grid", 50), self.sim.sc.get("units", 5), self.sim.sc.get("diag", 1)
        party = self.sim.party                                   # REFEREE-02: Spirit Guardians reaches a foe as she walks
        reach = party.guardian_foes(me) if me in getattr(party, "guardians", {}) else None
        hz = getattr(self.sim, "hazards", None)                  # HAZARDS-01: ice and frigid water cost 1 extra foot
        rough = (hz.difficult_cells(me) if hz else set()) | \
            (self.sim.traps.route_cells(me)[1] if getattr(self.sim, "traps", None) else set())
        import more_spells                                       # SPELL-EFFECTS-01: Web, Spike Growth, Grease, sleet
        rough |= more_spells.difficult_cells(self.sim, me)
        for px, py in path[1:]:
            reason = self.movement_blocked(me)
            if reason:
                return cost, reason
            # Revalidate this adjacent step after reactions, including corner/occupancy changes.
            # _route_search allows passing an ally; exact_route would forbid that intermediate step.
            best, kinds, _ = self.sim._route_search(me, (self.turn_state["movement"] - cost) // crawl, (px, py))
            step = best.get((px, py))
            if not step or len(step[1]) != 2 or ((px, py) == path[-1] and (px, py) in kinds):
                return cost, "The next square is no longer reachable."
            ex = extra + int(kinds.get((px, py)) == ai_turn.PASS_DIFFICULT or (px, py) in rough)
            next_cost = crawl * ai_turn.route_cost([(x * g, y * g) for x, y in walked + [(px, py)]], g, units, diag, ex)
            if next_cost > self.turn_state["movement"]:
                return cost, "Not enough movement for the next step."
            s.move(me, px, py)
            walked.append((px, py))
            extra, cost = ex, next_cost
            for f in self.sim.followers(me):
                s.move(f, *self.layers.follow_at(me, f, px, py))  # MAP-LAYERS-01: a Large mount keeps its offset
            self.sim.settle()
            if reach is not None:
                reach = party.guardians_reach(me, reach)
            if tuple(self.sim.party.pos(me)) != (px, py):
                return cost, "An effect moved the character off the planned route."
        return cost, None

    def attack_check(self, me, key, tid, weapon=None, quick=False):
        """SRD 5.2.1 checks for one attack (see the module notes). Returns the weapon, or raises LiveError with why.
        GM 2026-10-23 (Metamagic on an attack cantrip): weapon = the sheet's attack as changed (Distant Spell's range,
        Transmuted Spell's damage type); quick = cast as a Bonus Action (Quickened Spell), not with the Action."""
        sim, t = self.sim, self.turn_state
        if not t or t["id"] != me:
            raise LiveError("It is not this character's turn.")
        c, party = sim.by_id(me), sim.party
        gm = getattr(sim, "gm_rules", None)
        if sim.down(me):
            raise LiveError("%s is down." % c["name"])
        if gm and gm.incapacitated(me):
            raise LiveError("%s is Incapacitated: no actions (SRD 5.2.1 Incapacitated)." % c["name"])
        w = c.get(key) if key in ("weapon",) + EXTRA else None
        if not isinstance(w, dict) or not w.get("name"):
            raise LiveError("That attack is not on %s's sheet." % c["name"])
        w = weapon or w
        import party as party_mod
        magic = party_mod.spell_attack(w)                        # a cantrip takes the Magic action, not the Attack action
        if key == "offhand":                                     # GM 2026-10-25: SRD 5.2.1 Light property
            if not t.get("light_attacked"):
                raise LiveError("The extra attack with %s comes after an Attack action attack with a Light weapon (%s)." % (
                    w["name"], c["weapon"]["name"]))
            if t.get("offhand_used"):
                raise LiveError("%s has made the Light weapon's extra attack this turn." % c["name"])
            if not nick(c) and not party.bonus_free(me):
                raise LiveError("%s's Bonus Action is used this turn." % c["name"])
        elif quick:
            if not party.bonus_free(me):
                raise LiveError("%s's Bonus Action is used this turn." % c["name"])
        elif magic and t["action_used"] and t.get("magic_attack") != w["name"]:
            raise LiveError("%s takes the Magic action: %s's action is used this turn." % (w["name"], c["name"]))
        elif not magic and t.get("magic_attack"):
            raise LiveError("%s's action went on %s: no Attack action this turn." % (c["name"], t["magic_attack"]))
        elif t["action_used"] and t["attacks_left"] <= 0:
            n = c.get("attacks", 1)
            raise LiveError("%s's action is used: the Attack action allows %d attack%s." % (c["name"], n, "" if n == 1 else "s"))
        target = next((o for o in sim.sc["combatants"] if o["id"] == tid), None)
        if not target or tid == me:
            raise LiveError("Choose another creature as the target.")
        if sim.down(tid):
            raise LiveError("%s is down: attacks on a creature at 0 HP are not simulated yet." % target["name"])
        import high_levels                                       # CASTER-HIGH: Hurl Through Hell
        if high_levels.gone(party, tid):
            raise LiveError(high_levels.gone_why(party, tid))
        dist = party.dist(me, tid)
        reach = w.get("reach", 5)
        if dist > reach + 0.01:
            what = "range" if reach > 10 else "reach"
            raise LiveError("%s is %d ft away: out of %s's %s (%d ft)." % (target["name"], round(dist), w["name"], what, reach))
        if party.blocked(me, tid):
            raise LiveError("A wall blocks the line from %s to %s." % (c["name"], target["name"]))
        pit = getattr(sim, "traps", None) and sim.traps.pit_gap(me, tid)   # GM 2026-10-24: a creature down a pit
        if pit and reach <= 10 and reach < pit:
            raise LiveError("%s is %d ft down in a pit: out of %s's reach (%d ft)." % (
                (target if tid in sim.traps.in_pit else c)["name"], pit, w["name"], reach))
        return w

    def _attack(self, me, cmd):
        key, tid = cmd.get("weapon"), cmd.get("target")
        t, c, sim = self.turn_state, self.sim.by_id(me), self.sim
        plan, changed = None, None
        if cmd.get("metamagic"):                                 # GM 2026-10-23: Metamagic on an attack cantrip
            import live_sorcery
            base = c.get(key) if key in ("weapon",) + EXTRA else None
            if not isinstance(base, dict) or not base.get("name"):
                raise LiveError("That attack is not on %s's sheet." % c["name"])
            try:
                plan, changed = self.sorcery.attack_plan(me, base, cmd)
            except live_sorcery.SorceryError as e:
                raise LiveError(str(e))
        chosen = cmd.get("dmgtype")                              # GM 2026-11-01: Sorcerous Burst's type, this cast
        if chosen:
            base = changed or c.get(key)
            if not isinstance(base, dict) or chosen not in (base.get("dmg_choices") or []):
                raise LiveError("That attack has no choice of %s damage." % chosen)
            changed = dict(base, dmgtype=chosen)
        quick = bool(plan and plan.get("quick"))
        w = self.attack_check(me, key, tid, weapon=changed, quick=quick)
        import high_levels                                       # GM 2026-10-26: Tactical Master, Supreme Sneak
        mastery, stealth = cmd.get("mastery"), cmd.get("cunning") == "stealth_attack"
        if mastery and mastery not in high_levels.tactical_options(c, w):
            raise LiveError("Tactical Master (Fighter 9) swaps the mastery of a weapon %s uses: not this attack." % c["name"])
        if stealth and (high_levels.stealth_ok(sim.party, me, c) or t["sneak_used"]):
            raise LiveError(high_levels.stealth_ok(sim.party, me, c) or "Sneak Attack is used this turn.")
        import martial_high                                      # MARTIAL-HIGH: Devious Strikes (Rogue 14)
        devious = cmd.get("devious") or None
        if devious:
            offer = martial_high.devious_offer(sim.party, me, c, w, t["sneak_used"])
            pick = next((o for o in (offer or {}).get("options", []) if o["key"] == devious), None)
            if not pick or not pick["ready"]:
                raise LiveError(pick["why"] if pick else "Devious Strikes (Rogue 14) needs a Sneak Attack weapon: not this attack.")
            if stealth and not offer["two"]:
                raise LiveError("One Cunning Strike option per Sneak Attack: two need Improved Cunning Strike (Rogue 11).")
        strikes = list(cmd.get("strike") or [])                  # Cunning Strike (Rogue 5): Trip, Poison, Withdraw
        if strikes:
            why = martial_high.cunning_why(sim.party, me, tid, c, w, strikes, stealth, devious, t["sneak_used"])
            if why:
                raise LiveError(why)
        import monk                                              # MONK-01: Stunning Strike, paid only on a hit
        stun = bool(cmd.get("stun"))
        if stun and monk.stun_why(sim.party, me, w):
            raise LiveError(monk.stun_why(sim.party, me, w))
        hurl = bool(cmd.get("hurl"))                             # CASTER-HIGH: Hurl Through Hell, on a hit
        if hurl and high_levels.hurl_why(sim.party, me):
            raise LiveError(high_levels.hurl_why(sim.party, me))
        start = self.log_n
        import party as party_mod
        magic = party_mod.spell_attack(w)
        light = key == "offhand"
        if light:                                                # GM 2026-10-25: SRD 5.2.1 Light property (Nick)
            t["offhand_used"] = True
            if nick(c):
                sim.say("turn", "%s attacks with %s too (Light; Nick: part of the Attack action)" % (c["name"], w["name"]))
            else:
                sim.party.use_bonus(me)
                sim.say("turn", "%s attacks with %s as a Bonus Action (Light)" % (c["name"], w["name"]))
        elif quick:
            sim.party.use_bonus(me)
            sim.say("turn", "%s casts %s as a Bonus Action (Quickened Spell)" % (c["name"], w["name"]))
        elif not t["action_used"] and magic:                     # Eldritch Blast: an attack roll for each beam, at any target
            beams = c.get("beams", 1) if w["name"] == "Eldritch Blast" else 1
            t["action_used"], t["attacks_left"], t["magic_attack"] = True, beams, w["name"]
            sim.say("turn", "%s casts %s (Magic action%s)" % (c["name"], w["name"], ", %d beams" % beams if beams > 1 else ""))
        elif not t["action_used"]:
            t["action_used"], t["attacks_left"] = True, c.get("attacks", 1)
            sim.say("turn", "%s takes the Attack action (%d attack%s)" % (c["name"], t["attacks_left"], "" if t["attacks_left"] == 1 else "s"))
        if plan:
            self.sorcery.pay(me, w["name"], plan)
        if chosen:
            sim.say("dice", "%s's %s: %s damage" % (c["name"], w["name"], chosen.capitalize()))
        sneak = bool(c.get("sneak")) and not t["sneak_used"] and not magic   # SRD 5.2.1: with a weapon
        hexed = sim.party.hex.get(me) == tid                         # slice 2: Hex adds 1d6 Necrotic on each hit
        import live_general
        marked = live_general.of(self).marked(me) == tid             # SPELL-CASTER-01: Hunter's Mark, 1d6 Force
        poison = self.items.poison_dice(me, key, w)                 # GM 2026-10-23: Basic Poison on the weapon
        coated = self.items.coated_with(me, key)                      # Basic Poison or an injury poison
        extra = ";".join(x for x in ("1d6:necrotic" if hexed else "", "1d6:force" if marked else "", poison) if x)
        notes = ", ".join(x for x in ("Hex" if hexed else "", "Hunter's Mark" if marked else "", coated) if x)
        res = sim.party.attack(me, tid, w, sneak=sneak, bonus_dice=extra, note=notes, retarget_grapple=False,
                               mastery=mastery, stealth=stealth, devious=devious, strikes=strikes)
        sim.settle()
        if res == "miss" and plan and plan.get("seeking") and not sim.down(tid):   # Seeking Spell: the d20 again
            self.sorcery.pay_seeking(me, w["name"])
            res = sim.party.attack(me, tid, w, sneak=sneak, bonus_dice=extra, note=notes, retarget_grapple=False)
            sim.settle()
        if res is None:                                          # Party.attack refused (it re-checks reach and walls)
            raise LiveError("The simulator refused that attack (out of reach or blocked).")
        if magic and res in ("hit", "crit") and not sim.down(tid):
            live_general.of(self).card_hit(me, c, w["name"], tid)
            sim.settle()
        if stun and monk.stunning_strike(sim.party, me, tid, w, res):
            sim.settle()
        if hurl and res in ("hit", "crit") and high_levels.hurl(sim.party, me, tid):
            sim.settle()
        if coated:
            self.items.after_attack(me, key, res, tid)
        if res in ("hit", "crit") and str(w.get("dmgtype") or "").lower() == "fire":   # GM 2026-10-26: Fire Bolt on oil
            import traps
            traps.of(sim).ignite_creatures([tid], me, "%s's %s" % (c["name"], w["name"]))
            sim.settle()
        with self.lock:
            lines = [e["text"] for e in self.log if e["n"] > start]
        if sneak and res in ("hit", "crit") and any("Sneak Attack" in x for x in lines):
            t["sneak_used"] = True                               # once per turn, on a hit (SRD 5.2.1 Sneak Attack)
            if "withdraw" in strikes:
                martial_high.withdraw(self, me, c, t)
        if not quick and not light:
            t["attacks_left"] -= 1
            if w.get("light") and key == "weapon":
                t["light_attacked"] = True                       # GM 2026-10-25: the Light extra attack may follow
        t["attacks_made"] += 1
        return {"ok": True, "result": res, "lines": lines}

    # ------------------------------------------------------------------ what the table sees
    def offers(self):
        """For the waiting character: its sheet attacks with the targets that pass the checks now (and why the others
        do not), the movement left. The checks are the same ones act() makes."""
        me, t = self.waiting, self.turn_state
        if not me or not t:
            return None
        c = self.sim.by_id(me)
        attacks = []
        for a in sheet_attacks(c):
            ok, no = [], {}
            for o in self.sim.sc["combatants"]:
                if o["id"] == me:
                    continue
                try:
                    self.attack_check(me, a["key"], o["id"])
                    ok.append(o["id"])
                except LiveError as e:
                    no[o["id"]] = str(e)
            meta = self.sorcery.attack_options(me, c[a["key"]])    # GM 2026-10-23: Metamagic on an attack cantrip
            import high_levels                                   # GM 2026-10-26: Tactical Master, Supreme Sneak
            more = {}
            tm = high_levels.tactical_options(c, c[a["key"]])
            if tm:
                more["masteries"], more["own_mastery"] = tm, high_levels.own_mastery(c[a["key"]])
            if c.get("supreme_sneak") and c.get("sneak") and (c[a["key"]].get("finesse") or c[a["key"]].get("reach", 5) > 10):   # ranged (party.ranged)
                why = high_levels.stealth_ok(self.sim.party, me, c)
                more["stealth_attack"] = {"ready": not why and not t["sneak_used"],
                                          "why": why or ("Sneak Attack is used this turn." if t["sneak_used"] else "")}
            import monk                                          # MONK-01: Stunning Strike beside a Monk weapon
            stun = monk.of(self).attack_offer(me, c[a["key"]])
            if stun:
                more["stunning_strike"] = stun
            hurl = high_levels.hurl_offer(self.sim.party, me, c)   # CASTER-HIGH: Hurl Through Hell (Fiend 14)
            if hurl:
                more["hurl_through_hell"] = hurl
            import martial_high                                  # MARTIAL-HIGH: Devious Strikes (Rogue 14)
            devious = martial_high.devious_offer(self.sim.party, me, c, c[a["key"]], t["sneak_used"])
            if devious:
                more["devious"] = devious
            strike = martial_high.cunning_offer(self.sim.party, me, c, c[a["key"]], t["sneak_used"])
            if strike:
                more["cunning_strike"] = strike
            attacks.append(dict(a, targets=ok, refused=no, **({"metamagic": meta} if meta else {}), **more))
        movement = 0 if self.movement_blocked(me) else t["movement"]
        crawl = 2 if self.prone(me) else 1                       # GM 2026-10-24: crawling costs double
        reach = self.sim.reach(me, movement // crawl, as_seen=True) if movement > 0 else []   # INVISIBILITY-01
        for r in reach:
            r[2] *= crawl
        # GM 2026-10-24 ("characters should have Dash as an action"): the squares a Dash would add, and how it is paid
        dash = self.dash_by(me) if not self.movement_blocked(me) and t.get("speed", 0) > 0 else None
        dash_reach = []
        if dash:
            near = {(r[0], r[1]) for r in reach}
            dash_reach = [r for r in self.sim.reach(me, (t["movement"] + t["speed"]) // crawl, as_seen=True) if (r[0], r[1]) not in near]
            for r in dash_reach:
                r[2] *= crawl
        import live_spells
        full = self.sim.by_id(me).get("slots")                      # GM 2026-10-28: the slot pips (spent ones hollow)
        spells = {"spells": self.spells.offers(me) + self.layers.spell_offers(me), "slots": live_spells.slots_of(self.sim.party, me),
                  "slots_max": list(full) if isinstance(full, list) else [int(full or 0)],
                  "concentrating": self.spells.concentrating(me), "bonus_used": not self.sim.party.bonus_free(me),
                  "sorcery": self.sorcery.summary(me),                 # GM 2026-10-23: Sorcery Points, Innate Sorcery
                  "focus": monk_summary(self, me),                     # MONK-01: Focus Points, the Martial Arts die
                  "items": self.items.offers(me),                      # GM 2026-10-23: the bag's items, prerequisites checked
                  "lights": self.lights.offers(me),                    # LIGHTS-01: torches, lanterns, light spells
                  "coated": self.items.coated(me),
                  "asks": self.asks.offers(me),                        # GM 2026-10-24: Ask the GM
                  "checks": self.checks(me),                           # GM 2026-10-24: the sheet's Checks & saves tab
                  "reaction_used": bool(int(self.sim.S.getField(me, "reaction") or 0))}
        acts = {"actions": self.actions.offers(me), "doors": self.actions.door_offers(me),
                "interaction_used": bool(t.get("interaction_used")), "dodging": bool(c.get("dodging")),
                "undo": self.undo_offer(),                          # LIVE-UNDO-01
                "mount": self.layers.mount_offers(me)}              # MAP-LAYERS-01: Mount, Dismount, the mount's action
        out = {**spells, **acts, "actor": me, "name": c["name"], "side": c.get("side"), "movement": movement, "reach": reach,
               "dash_reach": dash_reach, "dash_by": dash, "prone": self.prone(me), "action_used": t["action_used"],
               "attacks_left": t["attacks_left"], "attacks_per_action": c.get("attacks", 1), "attacks": attacks}
        import more_spells                                       # SPELL-EFFECTS-01: Haste's action, Slow, the zones' and
        more_spells.adjust_offers(self, me, out)                 # summons' own actions
        import live_hints
        out["hints"] = live_hints.reminders(self, out)          # HINTS-01: reminders, cut per seat (table_seats.player_view)
        return out

    def checks(self, me):
        """GM 2026-10-24: the character's ability checks, saving throws and skills (the sheet's Checks & saves tab: each a
        d20 roll with this bonus, rolled in the table's dice tower)."""
        import character_rules as cr, live_lore
        c = self.sim.by_id(me)
        scores = c.get("abilities") or {}
        mods = {a: (int(scores[a]) - 10) // 2 for a in ("str", "dex", "con", "int", "wis", "cha") if a in scores}
        saves = {a: int(c.get(a + "_save", mods.get(a, 0)) or 0) for a in ("str", "dex", "con", "int", "wis", "cha")}
        skills = {}
        for skill, ability in cr.rules()["skills"].items():
            skills[skill] = live_lore.check_bonus(c, ability, skill)[0]
        # GM 2026-10-26: the tools it is proficient with or carries (SRD 5.2.1 Tool Proficiency: + PB when proficient)
        import requirements as rq, srd_tools
        held = [b.get("item") for b in self.items.bag(me).entries() if b.get("item") in srd_tools.TOOLS and int(b.get("qty", 0)) > 0]
        tools = [{"name": srd_tools.TOOLS[t]["name"], "ability": srd_tools.TOOLS[t]["ability"], "bonus": rq.tool_check(c, t)["bonus"],
                  "proficient": t in rq.tool_proficiencies(c), "carried": t in held}
                 for t in dict.fromkeys(rq.tool_proficiencies(c) + held)]
        return {"abilities": mods, "saves": saves, "skills": skills, "proficient": list(c.get("skills") or []), "tools": tools}

    def _publish_locked(self):
        import sim_messages
        g = self.sim.S
        try:
            rnd = int(g.round())
            active = self.waiting
            state = sim_messages.state(self.sim, rnd, active)
            offers = self.offers() if self.waiting else None
        except Exception as e:                                   # the simulator closed under us
            state, offers, rnd = (self.snap or {}).get("state"), None, (self.snap or {}).get("round")
            self.error = self.error or "%s: %s" % (type(e).__name__, e)
        try:                                                     # slice 2: lasting areas the table keeps drawn
            party = self.sim.party
            auras = [{"caster": cid, "radius_ft": 15, "appearance": "radiant", "spell": "Spirit Guardians"}
                     for cid in (getattr(party, "guardians", {}) or {}) if not self.sim.down(cid)] if party else []
        except Exception:
            auras = (self.snap or {}).get("auras", [])
        try:                                                     # VIEW-01: the party's sight (fog) and the doors now
            sight, doors = self.party_sight(), [str(d) for d in (self.sim.walls or {}).get("open_doors", [])]
        except Exception:
            sight, doors = (self.snap or {}).get("party_sight"), (self.snap or {}).get("open_doors", [])
        try:                                                     # GM 2026-10-24: traps and gear (sim/traps.py; GM view)
            traps = self.sim.traps.view(gm=True) if getattr(self.sim, "traps", None) else []
        except Exception:
            traps = (self.snap or {}).get("traps", [])
        try:                                                     # MAP-LAYERS-01: lasting spell zones and riders
            layers = self.layers.publish()
        except Exception:
            layers = (self.snap or {}).get("layers")
        try:                                                     # LIGHTS-01: each light where it is now
            lights = self.lights.publish()
        except Exception:
            lights = (self.snap or {}).get("lights")
        try:                                                     # HAZARDS-01: ice, water, weather (the GM's view)
            hz = self.sim.hazards.view(gm=True) if getattr(self.sim, "hazards", None) else None
        except Exception:
            hz = (self.snap or {}).get("hazards")
        self.snap = {"fight_id": self.fight_id, "revision": self.revision, "round": rnd, "waiting": self.waiting, "done": self.done,
                     "error": self.error, "state": state, "offers": offers, "log_n": self.log_n, "auras": auras,
                     "party_sight": sight, "open_doors": doors, "traps": traps, "layers": layers, "frozen": self.frozen,
                     "hazards": hz, "lights": lights,
                     "gm_control": dict(self.gm_control),
                     "locked_doors": [str(d) for d in (self.sim.walls or {}).get("locked_doors", [])],
                     "door_states": self._door_states("doors"),  # SPELL-OBJECTS-01: AC, Hit Points, burning, broken
                     "prop_states": self._door_states("props")}
        self.changed.notify_all()

    def _door_states(self, which):
        try:
            import spell_doors
            return spell_doors.of(self.sim).view(which)
        except Exception:
            return (self.snap or {}).get("door_states" if which == "doors" else "prop_states") or {}

    def party_sight(self, reach=24):
        """VIEW-01 (GM 2026-10-20: \"we already have fog of war mostly with sight, hearing, and perception\"): the squares
        any standing player character sees now (Sim.sees_square, within `reach` squares) and the creatures they see
        (Sim.sees: hidden ones stay unseen). The table draws the fog from this; it decides nothing itself."""
        import sim_messages
        sim = self.sim
        board = sim_messages.map_part(sim.sc)
        pcs = [c["id"] for c in sim.sc["combatants"] if c.get("pc") and not sim.down(c["id"])]
        seen = set()
        for i in pcs:
            px, py = sim.party.pos(i)
            for x in range(max(0, int(px) - reach), min(board["cols"], int(px) + reach + 1)):
                for y in range(max(0, int(py) - reach), min(board["rows"], int(py) + reach + 1)):
                    if (x, y) not in seen and sim.sees_square(i, x, y):
                        seen.add((x, y))
        others = [c["id"] for c in sim.sc["combatants"] if not c.get("pc")]
        creatures = [o for o in others if any(sim.sees(i, o) for i in pcs)]
        out = {"squares": sorted([x, y] for x, y in seen), "creatures": creatures}
        out.update(self.layers.sight_parts(pcs))                 # MAP-LAYERS-01: each character's own sight, the Invisible
        return out

    def _publish_now(self):
        with self.lock:
            self._publish_locked()

    def snapshot(self, since=0):
        with self.lock:
            out = dict(self.snap or {"fight_id": self.fight_id, "revision": 0, "waiting": None, "done": self.done, "state": None, "offers": None})
            out["log"] = [e for e in self.log if e["n"] > since]
            out["asks_open"] = [dict(a) for a in self.asks_open]     # GM 2026-10-24: requests waiting for the GM
            out["reaction"] = self.reactions.view()                  # SPELL-BATCH-02: a Reaction asked now (Shield ...)
            out["reaction_auto"] = self.reactions.auto               # OA-AUTO-01: the GM's Auto mode
            out["social_off"] = self.actions.lore.off                # GM 2026-11-01: the Influence buttons
            out["turn_timer"], out["turn_seconds"] = self.timer_on, self.turn_clock()   # GM 2026-11-01: the tracker's timer
            out["rewinds"] = self.rewinds                            # GM-UNDO-01: a screen starts its log again
            out["by_srd"] = self.by_srd                              # BY-THE-SRD-01
            import stealth                                           # STEALTH-01: declared stealth, the group check
            out["stealth"] = stealth.of(self).view()
            import initiative                                        # INITIATIVE-01: the players' Initiative popups
            out["initiative"] = initiative.of(self).view()
            out["scene"] = self.attitudes.view(gm=True)              # GM 2026-10-24: attitudes, morale (players: cut)
            if self.scenes:                                          # GM 2026-10-26: the scene (players: no GM cards)
                out["pillar"] = self.scenes.view(gm=True)
            now = time.monotonic()
            out["effects"] = [{k: v for k, v in e.items() if k != "at"} for e in self.effects if now - e["at"] < EFFECT_SECONDS]
            import combat_tracker                                    # COMBAT-TRACKER-01: turn order, who acts now
            out["tracker"] = combat_tracker.view(self, self.log)
            return out

    def wait_ready(self, timeout=120):
        """Until the fight waits for a player or ends (the service's first answer); INITIATIVE-01: or for the players'
        Initiative rolls (a fight that starts at once)."""
        rolling = lambda: getattr(getattr(self, "init_call", None), "call", None) is not None or self.held
        with self.lock:
            self.changed.wait_for(lambda: self.waiting is not None or self.done or rolling(), timeout)
            return self.waiting is not None or self.done or rolling()

    def settle(self, timeout=60):
        """GM-UNDO-01: until the fight stands still for the next step of a replay: a Reaction asked or, its last choice done, a
        character's turn, the end, the players' Initiative, or a creature's turn next."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.reactions.view() is not None:
                return True
            if (self.inflight is None or not self.inflight.empty()) and (self.waiting is not None or self.done or self.held
                    or getattr(getattr(self, "init_call", None), "call", None) is not None):
                return True
            time.sleep(0.002)
        return False

    def answer(self, reply, timeout):
        """The fight's answer to a choice. GM-UNDO-01: no choice outlives its fight (a rewind ends one in the middle of a
        Reaction), and a replay goes on when a choice stops for a Reaction: the answer is the timeline's next step."""
        end = time.monotonic() + timeout
        while True:
            try:
                return reply.get(timeout=0.01 if self.replaying else 0.25)
            except queue.Empty:
                if self.replaying and self.reactions.view() is not None:
                    return {"ok": True, "waits": "a Reaction"}
                if self.done and reply.empty():
                    return {"ok": False, "status": 409, "refused": "The fight is over."}
                if time.monotonic() > end:
                    raise

    # ------------------------------------------------------------------ from the service
    def act(self, cmd, timeout=120):
        with self.lock:
            if self.done or self.stopping:
                return {"ok": False, "status": 409, "refused": "The fight is over."}
            if self.frozen:
                return {"ok": False, "status": 409, "refused": "The GM has frozen the fight; it goes on when the GM unfreezes it."}
            # GM 2026-10-26 (sim/scenes.py): in a social or exploration scene any character of the party may act
            scene = bool(self.scenes and self.scenes.in_scene() and self.waiting is not None)
            if self.waiting is None and getattr(getattr(self, "init_call", None), "call", None) is not None:
                return {"ok": False, "status": 409, "refused": "Initiative is being rolled: roll yours in the popup first."}
            if self.waiting is None:
                return {"ok": False, "status": 409, "refused": "The creatures are acting; wait for a character's turn."}
            if cmd.get("revision") != self.revision:
                return {"ok": False, "status": 409, "refused": "Stale: the fight has moved on.", "revision": self.revision}
            if (not scene and cmd.get("actor", self.waiting) != self.waiting) or cmd.get("fight_id", self.fight_id) != self.fight_id:
                return {"ok": False, "status": 409, "refused": "Stale: a different fight or character is active."}
            cmd = dict(cmd, _turn=self.turn_serial, _actor=cmd.get("actor", self.waiting) if scene else self.waiting)
            reply = queue.Queue()
            self.inbox.put((cmd, reply))
            self.inflight = reply
        try:
            out = self.answer(reply, timeout)
        except queue.Empty:
            return {"ok": False, "status": 504, "refused": "The simulator did not answer."}
        if "waits" not in out:
            self.inflight = None
        if cmd.get("op") == "end" and out.get("ok") and not self.replaying:
            self.wait_ready(timeout)
        out["snapshot"] = self.snapshot(cmd.get("since", 0))      # with the log lines the choice produced
        return out

    def control(self, cid, by):
        """GM 2026-10-24: who plays a character: by "gm" (the GM took it; no permission needed), "player" (its player
        handed it to the GM) or None (back to its player). Its player's door refuses its choices while the GM holds it."""
        c = next((x for x in self.sim.sc["combatants"] if x.get("id") == cid and x.get("pc")), None)
        if not c:
            raise LiveError("Choose a player character.")
        with self.lock:
            if by:
                self.gm_control[cid] = by
            else:
                self.gm_control.pop(cid, None)
            self.revision += 1
            self._publish_locked()
        self.sim.say("note", "The GM takes over %s." % c["name"] if by == "gm" else
                     "%s's player hands the character to the GM." % c["name"] if by == "player" else
                     "%s is back with its player." % c["name"])

    def freeze(self, frozen):
        """GM 2026-10-24: freeze the fight (nothing moves: the creatures wait at their next step and every character's
        button is refused) or let it go on."""
        with self.lock:
            if self.done or self.stopping:
                raise LiveError("The fight is over.")
            self.frozen = bool(frozen)
            self.held = self.held and self.frozen                # GM-UNDO-01: going on plays the creature's turn it stands before
            now = time.monotonic()
            if self.frozen and self.pause_began is None:
                self.pause_began = now
            elif not self.frozen and self.pause_began is not None:
                self.turn_paused, self.pause_began = self.turn_paused + now - self.pause_began, None
            (self.thawed.clear if self.frozen else self.thawed.set)()
            self.revision += 1
            self._publish_locked()
        self.sim.say("note", "The GM froze the fight." if self.frozen else "The GM unfroze the fight: it goes on.")

    def quit(self):
        self.stopping = True                                     # creatures acting: stops at the next bridge call
        self.thawed.set()
        if self.waiting is not None and not self.done:
            reply = queue.Queue()
            self.inbox.put(({"op": "quit"}, reply))
            try:
                reply.get(timeout=10)
            except queue.Empty:
                pass
