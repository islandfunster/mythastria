"""INITIATIVE-01 (GM 2026-10-28: "the gm will send all the players a popup for all their initiatives the same way as saving
throws and all the rolls are checked by the rules engine"). When the GM starts a fight (sim/scenes.py start_combat):
- the creatures' Initiative is rolled at once;
- every standing character of the party gets an Initiative popup on its player's screen and rolls there; the GM can roll
  for a character (one nobody plays, one the GM holds, a slow player) or for everyone left;
- the fight's first round waits until every character has rolled.
The rules engine makes every roll, here on the GM's Mythastria, never on a player's device: SRD 5.2.1 Initiative is
d20 + the Dexterity modifier (a block's own init_bonus first); a combatant surprised as the fight starts rolls with
Disadvantage; Remarkable Athlete (Champion 3) gives Advantage.
"""
import threading


class InitiativeError(ValueError):
    pass


def roll(sim, c, surprised):
    """One Initiative roll for combatant c: (total, the dice as text, no-Dexterity note)."""
    import scenes, high_levels                                   # group 3: Remarkable Athlete, Advantage
    bonus, note = scenes.init_bonus(c)
    a, b = sim.rng.randint(1, 20), sim.rng.randint(1, 20)
    athlete = high_levels.remarkable(c, initiative=True)
    if surprised and athlete:
        d20, text = a, "Surprised and Remarkable Athlete: d20 %d" % a
    elif surprised:
        d20, text = min(a, b), "Surprised: Disadvantage, d20 %d/%d" % (a, b)
    elif athlete:
        d20, text = max(a, b), "Remarkable Athlete: Advantage, d20 %d/%d" % (a, b)
    else:
        d20, text = a, "d20 %d" % a
    return d20 + bonus, "%s %+d" % (text, bonus), note


class Initiative:
    def __init__(self, fight):
        self.fight = fight
        self.lock = threading.Lock()
        self.call = None                                         # the open call: {"n", "who": [pc ids], "rolls": {}}
        self.n = 0

    @property
    def sim(self):
        return self.fight.sim

    def open_call(self, who, surprised):
        with self.lock:
            self.n += 1
            self.call = {"n": self.n, "who": list(who), "surprised": set(surprised), "rolls": {}}
        self.sim.say("note", "The GM calls for Initiative: %s roll%s on their screens." % (
            ", ".join(self.sim.by_id(w)["name"] for w in who), "s" if len(who) == 1 else ""))

    def roll_for(self, i, by):
        """The roll for character i (by "player" or "gm"): the engine rolls; the total stays for the fight."""
        sim = self.sim
        with self.lock:
            call = self.call
            if not call:
                raise InitiativeError("No Initiative is being rolled now.")
            if i not in call["who"]:
                raise InitiativeError("%s does not roll Initiative now." % sim.by_id(i)["name"])
            if i in call["rolls"]:
                raise InitiativeError("%s has rolled Initiative already." % sim.by_id(i)["name"])
            total, text, note = roll(sim, sim.by_id(i), i in call["surprised"])
            call["rolls"][i] = {"total": total, "rolls": text, "by": by, "note": note}
            self.n += 1
        sim.say("dice", "%s rolls Initiative%s: %s = %d" % (sim.by_id(i)["name"], " (the GM rolls)" if by == "gm" else "",
                                                          text, total))
        return total

    def roll_rest(self):
        """The GM rolls for every character still to roll."""
        with self.lock:
            left = [w for w in self.call["who"] if w not in self.call["rolls"]] if self.call else None
        if left is None:
            raise InitiativeError("No Initiative is being rolled now.")
        return {w: self.roll_for(w, "gm") for w in left}

    def ready(self):
        with self.lock:
            return not self.call or all(w in self.call["rolls"] for w in self.call["who"])

    def close(self):
        """The rolls, once every character has rolled; the popups close."""
        with self.lock:
            call, self.call = self.call, None
            self.n += 1
        return call["rolls"] if call else {}

    def view(self):
        """Every screen: who rolls, who has rolled (the GM's view: every total)."""
        name = lambda i: self.sim.by_id(i)["name"]
        with self.lock:
            if not self.call:
                return None
            return {"n": self.call["n"], "who": [{"id": w, "name": name(w), "surprised": w in self.call["surprised"],
                                                  **({k: r[k] for k in ("total", "rolls", "by")}
                                                     if (r := self.call["rolls"].get(w)) else {})}
                                                 for w in self.call["who"]]}


def player_cut(view, mine_id):
    """A seat's view: who has rolled (each total is on the table's log), its own roll, whether its character rolls."""
    if not isinstance(view, dict):
        return None
    return {"n": view["n"], "who": [{"id": w["id"], "name": w["name"], "rolled": "total" in w,
                                     **({"surprised": w["surprised"], **{k: w[k] for k in ("total", "rolls") if k in w}}
                                        if w["id"] == mine_id else {})} for w in view["who"]],
            "mine": any(w["id"] == mine_id for w in view["who"])}


def of(fight):
    s = getattr(fight, "init_call", None)
    if s is None:
        s = fight.init_call = Initiative(fight)
    return s
