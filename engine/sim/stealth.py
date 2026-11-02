"""STEALTH-01 (GM 2026-10-28: "movement needs a stealth option. The individual can declare stealth and has a button. The
DM rolls perception. If the group calls for a group stealth check, everyone gets a popup from the DM for a group stealth
roll and each rolls stealth for their character on the popup itself"). He chose:
- Declared stealth is the Hide action in a fight (the Action, or a Bonus Action with Cunning Action; its cover and sight
  needs are unchanged, sim/live_actions.py) and free outside one (a scene's choices are all free, sim/scenes.py). The
  player rolls Dexterity (Stealth) once, from a popup on their own screen; the total stays while the character moves.
  Then the GM rolls Wisdom (Perception) for each creature that might notice (every standing foe; Dim Light gives
  Disadvantage and Darkness hides the character from that creature, as sim/light_sources.py): one whose roll reaches
  the total spots the character (as a Search does, sim/live_actions.py); otherwise the character is hidden: Invisible
  with that total as the DC to find it (as GmRules.hide). No movement cost (SRD 5.2.1).
- A group stealth check, called by the GM: a popup on each named character's player screen, each rolls their own
  character's Stealth there (the GM rolls for a character nobody plays, or answers for a slow player). Then the GM rolls
  Perception: the best roll among the creatures that might notice. SRD 5.2.1 group check: the group succeeds when at
  least half the rolls beat it; then every member is hidden (Invisible, the DC to find them at least one more than the
  GM's roll); otherwise nobody is.
Every roll is made here, on the GM's Mythastria, never on a player's device. The GM's Perception rolls are the GM's log
only ("secret"); the players see the outcome.
"""
import threading


class StealthError(ValueError):
    pass


def stealth_bonus(c):
    """Dexterity (Stealth): a sheet's own Stealth bonus, else as the sheet's Checks & saves tab works it out (sim/live_lore.py:
    the Dexterity modifier, + PB when proficient, + PB again with Expertise)."""
    s = c.get("stealth")
    if s is not None:
        return int(s)
    import live_lore
    return live_lore.check_bonus(c, "dex", "Stealth")[0]


class Stealth:
    def __init__(self, fight):
        self.fight = fight
        self.lock = threading.Lock()
        self.sneaks = {}                                         # pc id -> {"total", "rolls"}: waiting for the GM's Perception
        self.call = None                                         # the GM's group stealth check, while open
        self.last = None                                         # the latest outcome, for the screens
        self.n = 0

    @property
    def sim(self):
        return self.fight.sim

    @property
    def gm(self):
        return getattr(self.sim, "gm_rules", None)

    # ------------------------------------------------------------------ dice
    def roll(self, i):
        """Dexterity (Stealth) for character i: (total, the dice as text). Boots of Stealth: Advantage; armor with the SRD's
        Stealth Disadvantage; the two cancel; Reliable Talent."""
        c, rng = self.sim.by_id(i), self.sim.rng
        bonus = stealth_bonus(c)
        d20 = rng.randint(1, 20)
        rolls = "d20 %d" % d20
        boots, armor = bool(c.get("stealth_boots")), bool(c.get("stealth_disadvantage"))
        if boots != armor:
            second = rng.randint(1, 20)
            rolls, d20 = ("d20 %d/%d (Advantage)" % (d20, second), max(d20, second)) if boots else (
                "d20 %d/%d (armor: Disadvantage)" % (d20, second), min(d20, second))
        if c.get("reliable_talent") and d20 < 10:
            rolls, d20 = rolls + " (Reliable Talent: 10)", 10
        return d20 + bonus, "%s %+d" % (rolls, bonus)

    def watchers(self, i):
        """The creatures that might notice character i: every standing foe that can see where it is (not in Darkness)."""
        import light_sources
        out = []
        for f in self.sim.party.foes(i) if self.sim.party else []:
            look = light_sources.perception(self.sim, f, i)
            if look != "blind":
                out.append((f, look == "dis"))
        return out

    def perceive(self, f, dis):
        """One Wisdom (Perception) roll for creature f: (total, text)."""
        rng = self.sim.rng
        bonus = self.gm.passive_perception(f) - 10 if self.gm else 0
        d20 = rng.randint(1, 20)
        text = "d20 %d" % d20
        if dis:
            second = rng.randint(1, 20)
            text, d20 = "d20 %d/%d (Dim Light: Disadvantage)" % (d20, second), min(d20, second)
        return d20 + bonus, "%s %+d" % (text, bonus)

    def hidden(self, i, total, why):
        """Hidden: Invisible, `total` the DC to find it (as GmRules.hide); an older hiding gives way to the new total."""
        if self.gm.has(i, "Invisible") and not self.gm.cond[i]["Invisible"].get("spell"):
            self.gm.remove(i, "Invisible", "hides again")
        self.gm.add(i, "Invisible", "(%s, Stealth %d)" % (why, total), by=i, total=total)

    # ------------------------------------------------------------------ one character: the Hide action, declared
    def declare(self, i, how=""):
        """The player's Roll in the Stealth popup (the Hide action, already paid): the total waits for the GM."""
        c = self.sim.by_id(i)
        total, rolls = self.roll(i)
        if getattr(self.fight, "by_srd", False):                 # BY-THE-SRD-01: the Hide action as written
            return self.hide_by_srd(i, c, how, total, rolls)
        with self.lock:
            self.sneaks[i] = {"total": total, "rolls": rolls}
            self.n += 1
        self.sim.say("dice", "%s tries to hide%s, moving stealthily: Dexterity (Stealth) %s = %d. The GM rolls Perception." % (
            c["name"], how, rolls, total))
        return total

    def hide_by_srd(self, i, c, how, total, rolls):
        """SRD 5.2.1 Hide: a DC 15 Dexterity (Stealth) check. On a success the character is Invisible while hidden, and the total
        is the DC to find it with Wisdom (Perception): no creature rolls until one looks."""
        ok = total >= 15
        self.sim.say("dice", "%s tries to hide%s: Dexterity (Stealth) %s = %d vs DC 15 -> %s" % (
            c["name"], how, rolls, total, "hidden" if ok else "not hidden"))
        if ok:
            self.hidden(i, total, "Hide")
        self.last = {"id": i, "name": c["name"], "hidden": ok, "n": self.bump()}
        return total

    def check(self, i):
        """The GM's Perception against one declared stealth: hidden, or spotted by the first creature whose roll reaches it."""
        with self.lock:
            s = self.sneaks.pop(i, None)
        if not s:
            raise StealthError("%s is not waiting for a Perception roll." % self.sim.by_id(i)["name"])
        name, best = self.sim.by_id(i)["name"], None
        for f, dis in self.watchers(i):
            total, text = self.perceive(f, dis)
            self.sim.say("secret", "%s looks for %s: Wisdom (Perception) %s = %d vs Stealth %d" % (
                self.sim.by_id(f)["name"], name, text, total, s["total"]))
            if total >= s["total"] and (best is None or total > best[1]):
                best = (f, total)
        if best:                                                 # the players' log never names a creature they don't see
            self.sim.say("secret", "%s spots %s (Perception %d)" % (self.sim.by_id(best[0])["name"], name, best[1]))
            self.sim.say("turn", "%s is noticed: not hidden" % name)
            out = {"id": i, "name": name, "hidden": False, "by": self.sim.by_id(best[0])["name"]}
        else:
            self.hidden(i, s["total"], "sneaking")
            self.sim.say("turn", "%s is hidden (Stealth %d): no creature notices" % (name, s["total"]))
            out = {"id": i, "name": name, "hidden": True}
        self.last = dict({k: v for k, v in out.items() if k != "by"}, n=self.bump())   # every screen sees it: no creature name
        return out

    # ------------------------------------------------------------------ the GM's group stealth check
    def open_call(self, who):
        pcs = [c["id"] for c in self.sim.sc["combatants"] if c.get("pc") and not self.sim.down(c["id"])]
        who = pcs if who in (None, "all") else who
        if not isinstance(who, list) or not who or any(w not in pcs for w in who):
            raise StealthError("A group stealth check names standing characters of the party.")
        with self.lock:
            if self.call:
                raise StealthError("A group stealth check is already open: finish or cancel it first.")
            self.call = {"n": self.bump(), "who": list(dict.fromkeys(who)), "rolls": {}}
        self.sim.say("note", "The GM calls for a group Dexterity (Stealth) check: %s." % ", ".join(
            self.sim.by_id(w)["name"] for w in who))
        return self.call

    def call_roll(self, i, by):
        with self.lock:
            if not self.call:
                raise StealthError("No group stealth check is open.")
            if i not in self.call["who"]:
                raise StealthError("%s is not in this group stealth check." % self.sim.by_id(i)["name"])
            if i in self.call["rolls"]:
                raise StealthError("%s has rolled already." % self.sim.by_id(i)["name"])
        total, rolls = self.roll(i)
        with self.lock:
            if not self.call or i in self.call["rolls"]:
                raise StealthError("That group stealth check has moved on.")
            self.call["rolls"][i] = {"total": total, "rolls": rolls, "by": by}
            self.n += 1
        self.sim.say("dice", "%s rolls for the group stealth check%s: Dexterity (Stealth) %s = %d" % (
            self.sim.by_id(i)["name"], " (the GM rolls)" if by == "gm" else "", rolls, total))
        return total

    def resolve(self, dc=None):
        """The GM's Perception: the best roll among the creatures that might notice any member; SRD 5.2.1 group check."""
        with self.lock:
            call = self.call
            if not call:
                raise StealthError("No group stealth check is open.")
            missing = [w for w in call["who"] if w not in call["rolls"]]
            if missing:
                raise StealthError("Waiting for %s to roll (Roll for them, or wait)." % ", ".join(
                    self.sim.by_id(w)["name"] for w in missing))
            self.call = None
        watchers = {}
        for w in call["who"]:
            for f, dis in self.watchers(w):
                watchers[f] = watchers.get(f, True) and dis       # Disadvantage only if it is dim toward everyone
        best, by = None, None
        for f, dis in watchers.items():
            total, text = self.perceive(f, dis)
            self.sim.say("secret", "%s looks for the party: Wisdom (Perception) %s = %d" % (self.sim.by_id(f)["name"], text, total))
            if best is None or total > best:
                best, by = total, f
        rolls = call["rolls"]
        beat = [w for w in call["who"] if best is None or rolls[w]["total"] > best]
        if dc is not None:                                       # play-test 2026-11-02: the adventure's written DC decides
            best, by = dc - 1, None
            beat = [w for w in call["who"] if rolls[w]["total"] >= dc]
        ok = len(beat) * 2 >= len(call["who"])
        names = ", ".join(self.sim.by_id(w)["name"] for w in call["who"])
        if ok:
            for w in call["who"]:
                self.hidden(w, max(rolls[w]["total"], (best or 0) + 1), "group stealth")
            self.sim.say("turn", "Group stealth: %d of %d %s: the group is hidden (%s)" % (
                len(beat), len(call["who"]), "beat the watchers' Perception" if dc is None else "met DC %d" % dc, names))
        else:
            if dc is None:
                self.sim.say("secret", "%s's Perception %d is the one to beat" % (self.sim.by_id(by)["name"], best) if by else
                             "No creature can see the party")
            self.sim.say("turn", "Group stealth: only %d of %d %s: the group is noticed" % (
                len(beat), len(call["who"]), "beat the watchers' Perception" if dc is None else "met DC %d" % dc))
        self.last = {"n": self.bump(), "group": True, "hidden": ok, "beat": len(beat), "of": len(call["who"])}
        return self.last

    def cancel(self):
        with self.lock:
            call, self.call = self.call, None
            if call:
                self.n += 1
        if call:
            self.sim.say("note", "The GM cancels the group stealth check.")
        return bool(call)

    def bump(self):
        self.n += 1
        return self.n

    # ------------------------------------------------------------------ the screens
    def view(self):
        """The GM's: every waiting declared stealth with its total, the open group check with every roll, the outcome."""
        name = lambda i: self.sim.by_id(i)["name"]
        with self.lock:
            call = self.call and {"n": self.call["n"], "who": [{"id": w, "name": name(w), **({"total": r["total"], "rolls": r["rolls"],
                                                                                          "by": r["by"]} if (r := self.call["rolls"].get(w)) else {})}
                                                              for w in self.call["who"]]}
            return {"sneaks": [{"id": i, "name": name(i), **s} for i, s in self.sneaks.items()], "call": call,
                    "last": self.last}


def player_cut(view, mine_id):
    """A seat's view: its own waiting stealth; the open group check (who has rolled, its own total only); the outcome."""
    if not isinstance(view, dict):
        return None
    call = view.get("call")
    if call:
        call = {"n": call["n"], "who": [{"id": w["id"], "name": w["name"], "rolled": "total" in w,
                                         **({"total": w["total"], "rolls": w["rolls"]} if w["id"] == mine_id and "total" in w else {})}
                                        for w in call["who"]],
                "mine": any(w["id"] == mine_id for w in call["who"])}
    return {"sneaks": [s for s in view.get("sneaks") or [] if s["id"] == mine_id], "call": call, "last": view.get("last")}


def of(fight):
    s = getattr(fight, "stealth", None)
    if s is None:
        s = fight.stealth = Stealth(fight)
    return s
