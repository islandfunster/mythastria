"""GM 2026-10-26 (goal 15, the Documents page entry "Traps"): what the creatures the simulator plays know and do about
traps (SRD 5.2.1 Gameplay Toolbox: Traps; Rules Glossary: Search, Study, Help, Climbing). sim/traps.py keeps the traps;
this module keeps the creatures' side, with thin hooks into the turn planner (re-hook notes: Minds.planner_space and
Minds.turn_start are the only two calls a turn planner makes).

- Lair knowledge. A creature that lives where the traps are knows them: the trap's "known_by" (creature ids or names, or
  "foes": every creature not on the party's side) or the creature's own "knows_traps" (true: every trap on the map; or a
  list of trap ids). The GM marks them in Play live (GM tools, Traps: Who knows it). Intruders know nothing. A creature
  also knows a trap that hurt it, an open pit (anyone sees the hole) and what its side found by searching.
  It keeps off the lids and plates it knows (the planner treats them as a space it can't enter: space["keep_off"], read
  by mythastria_core/ai_turn.py) and steps over its own trip wires (Traps.enter).
- Luring. With a hidden trap the party has not found lying between it and the nearest enemy (more than 5 ft away), a
  creature that knows it holds its ground behind it (its turn ends there) for up to LURE_TURNS turns, letting the party
  come across.
- Wary creatures search. A wary creature (the scenario's "wary", a Scout, or one a trap hurt this fight) with no enemy
  within 10 ft takes the Search or Study action on the square ahead of it toward the nearest enemy (whichever of its
  Wisdom (Perception) or Intelligence (Investigation) is better), once per square, and finds parts by the DCs the
  characters use (Traps.examine). Its side knows what it finds; the players see only that it examined the floor. The
  action ends its turn in the simulator (it doesn't move as well).
- Out of a pit. A creature at the bottom climbs out with its Speed (Traps.climb_core: a Climb Speed climbs at its own
  rate; otherwise each foot costs 1 extra foot and the smooth walls ask for a Strength (Athletics) check at the pit's
  climbing DC each turn). Climbing takes its turn in the simulator; out of the pit it stands at the edge nearest its
  nearest enemy.
"""
import re

LURE_TURNS = 2                       # turns a creature waits behind its hidden trap before it walks round
WARY_NAMES = ("scout",)              # SRD 5.2.1 Scout: a wary creature by its trade
PITS = ("hidden_pit", "spiked_pit")


def _sq(p):
    return int(round(float(p[0]))), int(round(float(p[1])))


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def creature_bonus(c, ability, skill):
    """A creature's check: the stat block's skill ("Perception +4"), else its ability modifier. A character sheet (skills
    as a list) goes through live_lore.check_bonus."""
    if isinstance(c.get("skills"), list) or c.get("abilities"):
        import live_lore
        return live_lore.check_bonus(c, ability, skill)[0]
    m = re.search(skill + r"\s*([+-]\s*\d+)", str(c.get("skills") or ""), re.I)
    if m:
        return int(m.group(1).replace(" ", ""))
    score = c.get(ability)
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        return (int(score) - 10) // 2
    return int(c.get(ability + "_mod", 0) or 0)


class Minds:
    """The creatures' side of one fight's traps (Traps.minds)."""

    def __init__(self, traps):
        self.tr = traps
        self.hurt = set()            # creatures a trap hurt this fight: wary from now on
        self.searched = set()        # (ctid, (x, y)): squares a creature examined
        self.lured = {}              # ctid -> turns spent waiting behind a hidden trap
        self.told = set()            # (ctid, trap id): the GM's line "keeps off its own trap", once

    @property
    def sim(self):
        return self.tr.sim

    # ------------------------------------------------------------------ who knows what
    def party_side(self, me):
        c = self.sim.by_id(me)
        return bool(c.get("pc")) or c.get("side") == "friend"

    def knows(self, me, t):
        """Does this creature know where the trap goes off? The party: once it found the part that says so. A creature
        the simulator plays: its lair's traps (known_by, knows_traps), a trap that hurt it, its side's finds."""
        if self.party_side(me):
            return self.tr.found_main(t)
        c = self.sim.by_id(me)
        kb = [str(k) for k in t.get("known_by") or []]
        if "foes" in kb or str(me) in kb or str(c.get("name")) in kb:
            return True
        kt = c.get("knows_traps")
        if kt is True or (isinstance(kt, (list, tuple)) and t["id"] in [str(k) for k in kt]):
            return True
        return self.tr.found_main(t, side="foe")

    def mark(self, tid, who, on=True):
        """The GM: these creatures (ids, or "foes") know this trap, or no longer do."""
        t = self.tr.by_id(tid)
        kb = [str(k) for k in t.get("known_by") or []]
        for w in who:
            w = str(w)
            if w != "foes" and not any(str(c["id"]) == w for c in self.sim.sc["combatants"]):
                raise ValueError("No creature %s in this fight." % w)
            if on and w not in kb:
                kb.append(w)
            elif not on and w in kb:
                kb.remove(w)
        t["known_by"] = kb
        return kb

    def learn(self, me, t):
        """A creature a trap hurt knows it now (and is wary for the rest of the fight)."""
        if self.party_side(me) or t.get("gear"):
            return
        self.hurt.add(me)
        kb = t.setdefault("known_by", [])
        if str(me) not in kb and "foes" not in kb:
            kb.append(str(me))

    def keep_off(self, me):
        """The squares this creature won't step on: open pits (anyone sees the hole) and the armed lids and plates it
        knows. A trip wire it knows is stepped over (Traps.enter), not walked round."""
        out = set()
        for t in self.tr.traps:
            if t.get("gone") or t.get("gear"):
                continue
            sq = {tuple(s) for s in t["squares"]}
            if t["kind"] in PITS and t["open"]:
                out |= sq
            elif t["armed"] and self.tr.place_of(t) in ("lid", "plate") and self.knows(me, t):
                out |= sq
        return out

    # ------------------------------------------------------------------ the planner's hook (no Lua: any thread)
    def planner_space(self, me, here=None):
        """Extras for the turn planner's space for one decision of creature me: "keep_off" (map pixels, the squares'
        centres). here: its square, left out."""
        if not self.tr.traps or self.party_side(me):
            return {}
        g, out = self.tr.g, {}
        keep = self.keep_off(me) - ({_sq(here)} if here else set())
        if keep:
            out["keep_off"] = [[x * g, y * g] for x, y in sorted(keep)]
        return out

    # ------------------------------------------------------------------ the start of its turn (the main thread)
    def turn_start(self, me):
        """A creature the simulator plays starts its turn free (not held by a trap): it may hold its ground behind a
        hidden trap or spend the turn searching (True: that was its turn; False: the planner plays it)."""
        if not self.tr.traps or self.party_side(me) or self.sim.down(me):
            return False
        self.tell(me)
        return self.lure(me) or self.search(me)

    def tell(self, me):
        """The GM's line (never the players'): the creature keeps off a trap it knows, said once per trap."""
        for t in self.tr.traps:
            if t.get("gone") or t.get("gear") or not t["armed"] or (me, t["id"]) in self.told or not self.knows(me, t):
                continue
            self.told.add((me, t["id"]))
            self.tr.say("%s knows the %s at %s: it %s" % (
                self.sim.by_id(me)["name"], t["name"], ", ".join("(%d, %d)" % tuple(s) for s in t["squares"]),
                "steps over its trip wire" if self.tr.place_of(t) == "wire" else "keeps off it"), "secret")

    def foes(self, me):
        side = self.party_side(me)
        return [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.sim.down(o["id"])
                and self.party_side(o["id"]) != side]

    def nearest_foe(self, me):
        here = _sq(self.tr.pos(me))
        best = None
        for f in self.foes(me):
            d = cheb(here, _sq(self.tr.pos(f)))
            if best is None or d < best[1]:
                best = (f, d)
        return best or (None, None)

    def lure(self, me):
        """Hold its ground behind a hidden trap that lies between it and its nearest enemy (on a shortest way there)."""
        if self.lured.get(me, 0) >= LURE_TURNS:
            return False
        foe, d = self.nearest_foe(me)
        if foe is None or d <= 1:
            return False
        here, there = _sq(self.tr.pos(me)), _sq(self.tr.pos(foe))
        for t in self.tr.traps:
            if (t.get("gone") or t.get("gear") or not t["armed"] or t["known"] or self.tr.found_main(t)
                    or self.tr.place_of(t) == "lock" or not self.knows(me, t)):
                continue
            between = [s for s in t["squares"] if cheb(here, s) + cheb(s, there) <= d and tuple(s) != here]
            if not between:
                continue
            self.lured[me] = self.lured.get(me, 0) + 1
            self.tr.say("%s holds its ground behind its hidden %s, letting %s come across it (its turn; %d of %d)" % (
                self.sim.by_id(me)["name"], t["name"], self.sim.by_id(foe)["name"], self.lured[me], LURE_TURNS), "secret")
            return True
        return False

    def wary(self, me):
        c = self.sim.by_id(me)
        return bool(c.get("wary")) or me in self.hurt or any(w in str(c.get("name") or "").lower() for w in WARY_NAMES)

    def search(self, me):
        """A wary creature with no enemy within 10 ft Searches or Studies the square ahead toward the nearest enemy."""
        if not self.wary(me):
            return False
        foe, d = self.nearest_foe(me)
        if foe is None or d <= 2:
            return False
        here, there = _sq(self.tr.pos(me)), _sq(self.tr.pos(foe))
        sx, sy = here[0] + (there[0] > here[0]) - (there[0] < here[0]), here[1] + (there[1] > here[1]) - (there[1] < here[1])
        if (me, (sx, sy)) in self.searched or not self.tr.enterable(sx, sy):
            return False
        if any([sx, sy] in [list(q) for q in t["squares"]] and self.knows(me, t) for t in self.tr.traps if not t.get("gone")):
            return False                                         # it knows what is there
        self.searched.add((me, (sx, sy)))
        c = self.sim.by_id(me)
        gm = getattr(self.sim, "gm_rules", None)
        look = gm.passive_perception(me) - 10 if gm else creature_bonus(c, "wis", "Perception")
        study = creature_bonus(c, "int", "Investigation")
        op = "study" if study > look else "search"
        self.tr.say("%s %s the floor at (%d, %d) (%s action; it is wary of traps)" % (
            c["name"], "studies" if op == "study" else "searches", sx, sy, "Study" if op == "study" else "Search"), "turn")
        self.tr.examine(me, op, sx, sy, bonus=study if op == "study" else look)
        return True

    def climb_turn(self, me):
        """At the bottom of a pit: climb with its Speed (Traps.climb_core). True: that was its turn."""
        h = self.tr.held.get(me) or {}
        t = next((t for t in self.tr.traps if t["id"] == h.get("trap")), None)
        c = self.sim.by_id(me)
        if t is None:
            return False
        if not self.tr.climb_means(me):
            self.tr.say("%s can't climb the pit's smooth walls: it stays at the bottom" % c["name"], "turn")
            return True
        import ai_turn
        speed = str(c.get("speed") or "30")
        m = re.search(r"Climb\s*(\d+)", speed, re.I)
        budget = int(m.group(1)) if m else ai_turn.speed_ft(speed)
        foe, _ = self.nearest_foe(me)
        want = _sq(self.tr.pos(foe)) if foe else None
        res = self.tr.climb_core(me, t, budget, toward=want, check=lambda: creature_bonus(c, "str", "Athletics"))
        if res["status"] == "no_room":
            self.tr.say("%s reaches the pit's edge but every square beside it is taken: it waits there" % c["name"], "turn")
        return True
