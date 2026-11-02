"""GM 2026-10-23 ("build the shared prerequisite check with links, and Basic Poison and the Utilize action as its first
uses"): items from a character's bag in a live fight (the Market's bag: sim/market.py), each offered only when every
prerequisite is met (sim/requirements.py), with the reason and a link when one is not. SRD 5.2.1 (Equipment: Adventuring
Gear; Magic Items: Potion of Healing; Playing the Game: the Utilize action):

- Poison, Basic: a Bonus Action coats one weapon, or up to three pieces of ammunition; a creature that takes Piercing or
  Slashing damage from it takes an extra 1d4 Poison damage; it keeps for 1 minute or until its damage is dealt.
- Potion of Healing (and Greater, Superior, Supreme): a Bonus Action to drink it or give it to a creature within 5 ft:
  2d4 + 2 (4d4 + 4, 8d4 + 8, 10d4 + 20) Hit Points.
- Healer's Kit: the Utilize action spends one of its ten uses to stabilize an Unconscious creature at 0 Hit Points
  without a Wisdom (Medicine) check.
- Antitoxin: a Bonus Action to drink it: Advantage on saving throws to avoid or end the Poisoned condition for 1 hour.
- The SRD's other poisons (sim/srd_poisons.py): an injury poison is a Bonus Action on one weapon or one piece of
  ammunition, potent until it is delivered by Piercing or Slashing damage; an inhaled poison is released (the Utilize
  action) into the 5-foot Cube of a creature within 5 ft. Contact and ingested poisons are listed with why they have no
  use in a fight.
- Thrown gear (SRD 5.2.1 Adventuring Gear): Acid (2d6 Acid), Alchemist's Fire (1d4 Fire and Burning), Holy Water (2d8
  Radiant to a Fiend or Undead): one attack of the Attack action; a creature you can see within 20 ft; a Dexterity save
  (DC 8 + your Dexterity modifier + Proficiency Bonus) or the damage.
- Oil and a Net, thrown (GM 2026-10-26; SRD 5.2.1 Adventuring Gear): one attack of the Attack action and a Dexterity
  save at the same DC. Oil: a creature within 20 ft, covered for 1 minute: Fire damage before it dries adds 5 Fire
  (traps.ignite_creatures). A Net: a creature you can see within 15 ft, Restrained until it escapes (an action and DC 10
  Strength (Athletics), by it or a creature within 5 ft; Huge or larger succeed automatically).
- A Waterskin douses fire (GM 2026-10-26; SRD 5.2.1 Burning: "The fire also goes out if it is doused"): the Utilize
  action, on yourself or a burning creature within 5 ft; the skin is then empty for the rest of the fight. A burning
  character can also roll on the ground (an action and Prone: sim/live_actions.py "extinguish").
- Area gear (GM 2026-10-24, with the traps: sim/traps.py): Caltrops, Ball Bearings, Oil poured on the ground and a Hunting
  Trap, each the Utilize action on a square (x, y) within its reach; the square is checked (level ground a creature can
  enter, nothing spread there yet) before the item leaves the bag.
- Tools (GM 2026-10-26, sim/srd_tools.py): each SRD tool in the bag offers its Utilize uses (the Utilize action), an
  ability check against the use's DC with the tool's ability; proficiency with the tool adds the Proficiency Bonus, and
  the skill used with the check too gives Advantage (requirements.tool_check). The GM rules what a success tells or does.
  Thieves' Tools come with a found trap or a locked door (sim/traps.py).
The item leaves the bag (or a kit loses a use) only once every check has passed. The computer-played heroes do not use
bag items yet (their own test kits: sim/run_sim.py apply_items).
"""
import requirements as rq
import srd_poisons

AMMO_WEAPONS = {"Shortbow", "Longbow", "Light Crossbow", "Heavy Crossbow", "Hand Crossbow", "Sling", "Blowgun", "Musket",
                "Pistol"}
POTIONS = {"potion-of-healing": ("Potion of Healing", "2d4+2"), "potion-of-healing-greater": ("Potion of Healing (Greater)", "4d4+4"),
           "potion-of-healing-superior": ("Potion of Healing (Superior)", "8d4+8"),
           "potion-of-healing-supreme": ("Potion of Healing (Supreme)", "10d4+20")}
POISON, KIT, ANTITOXIN = "poison-basic", "healers-kit", "antitoxin"
KIT_USES, MINUTE, HOUR = 10, 10, 600
THROWN = {"acid": ("Acid", "2d6", "acid"), "alchemists-fire": ("Alchemist's Fire", "1d4", "fire"),
          "holy-water": ("Holy Water", "2d8", "radiant")}
TOSSED = {"oil": {"name": "Oil", "reach": 20, "sight": False}, "net": {"name": "Net", "reach": 15, "sight": True}}   # GM 2026-10-26
WATERSKIN = "waterskin"


def tossed(cmd):
    """Oil or a Net thrown at a creature (Oil poured on a square names x and y instead: sim/traps.py)."""
    return cmd.get("item") in TOSSED and cmd.get("x") is None and cmd.get("y") is None
import traps as traps_mod
import srd_tools
TOOL_USES = {tid for tid in srd_tools.TOOLS if tid != "thieves-tools"}    # Thieves' Tools: with a trap or a lock (traps.py)
FIGHT_ITEMS = ({POISON, KIT, ANTITOXIN, *POTIONS, *THROWN} | {k for k, p in srd_poisons.POISONS.items() if p["type"] in srd_poisons.FIGHT_TYPES}
               | set(traps_mod.GEAR) | TOOL_USES | set(TOSSED) | {WATERSKIN})


class ItemError(ValueError):
    pass


class LiveItems:
    def __init__(self, fight):
        self.fight = fight

    @property
    def sim(self):
        return self.fight.sim

    @property
    def party(self):
        return self.sim.party

    def bag(self, me):
        c = self.sim.by_id(me)
        return rq.Bag(c["name"], getattr(self.fight, "market", None), c.get("bag"))

    def state(self, name):
        return self.party.__dict__.setdefault(name, {})

    def coated(self, me):
        """The weapon Basic Poison coats now: {"key", "name", "until", "pieces"} or None."""
        coat = self.state("coated").get(me)
        if coat and coat["until"] is not None and int(self.party.s.round()) > coat["until"]:
            self.state("coated").pop(me, None)
            return None
        return coat

    # ------------------------------------------------------------------ the offers: every use, with its needs
    def offers(self, me):
        c, out = self.sim.by_id(me), []
        bag = self.bag(me)
        entries = [b for b in bag.entries() if int(b.get("qty", 0)) > 0]
        have = {b.get("item") for b in entries}
        if POISON in have:
            for key in __import__("character_rules").WEAPON_KEYS:
                w = c.get(key)
                if isinstance(w, dict) and w.get("name") and not w.get("cantrip") and w.get("dmgtype"):
                    out.append(self.entry(me, {"item": POISON, "weapon": key},
                                          "Basic Poison on the %s" % w["name"], "bonus", bag))
        for pid, (name, dice) in POTIONS.items():
            if pid in have:
                for tid in [me] + [a for a in self.party.allies(me) if not self.party.deaths.get(a, {}).get("dead")]:
                    if tid == me or self.party.dist(me, tid) <= 5.01:
                        who = "yourself" if tid == me else self.sim.by_id(tid)["name"]
                        out.append(self.entry(me, {"item": pid, "target": tid}, "%s: %s (%s)" % (name, who, dice), "bonus", bag))
        if KIT in have:
            fallen = [a for a in self.party.allies(me) if self.sim.down(a) and not self.party.deaths.get(a, {}).get("dead")]
            for tid in fallen or [None]:                         # none at 0 HP: the kit says so
                out.append(self.entry(me, {"item": KIT, "target": tid},
                                      "Healer's Kit: stabilize %s" % (self.sim.by_id(tid)["name"] if tid else "an ally at 0 Hit Points"),
                                      "action", bag, uses=bag.uses_left(KIT, KIT_USES)))
        if ANTITOXIN in have:
            out.append(self.entry(me, {"item": ANTITOXIN}, "Antitoxin", "bonus", bag))
        for gid, (name, dice, kind) in THROWN.items():           # thrown gear: one attack of the Attack action
            if gid in have:
                near = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.sim.down(o["id"])
                        and self.party.side(o["id"]) != self.party.side(me) and self.party.dist(me, o["id"]) <= 20.01]
                for tid in near or [None]:
                    who = self.sim.by_id(tid)["name"] if tid else "a creature within 20 ft"
                    out.append(self.entry(me, {"item": gid, "target": tid}, "Throw %s at %s" % (name, who), "attack", bag,
                                          effect="Dexterity save (DC %d) or %s %s%s" % (self.throw_dc(c), dice, kind.capitalize(),
                                                 " and Burning" if gid == "alchemists-fire" else
                                                 " (a Fiend or Undead only)" if gid == "holy-water" else "")))
        for gid, g in TOSSED.items():                             # GM 2026-10-26: Oil or a Net thrown at a creature
            if gid in have:
                near = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.sim.down(o["id"])
                        and self.party.side(o["id"]) != self.party.side(me) and self.party.dist(me, o["id"]) <= g["reach"] + 0.01]
                for tid in near or [None]:
                    who = self.sim.by_id(tid)["name"] if tid else "a creature within %d ft" % g["reach"]
                    out.append(self.entry(me, {"item": gid, "target": tid}, "Throw %s at %s" % (g["name"], who), "attack", bag,
                                          effect="Dexterity save (DC %d) or %s" % (self.throw_dc(c), "covered in oil for 1 minute: "
                                                 "Fire damage then adds 5 Fire" if gid == "oil" else "Restrained until it escapes "
                                                 "(an action, DC 10 Strength (Athletics)); Huge or larger succeed")))
        if WATERSKIN in have:                                     # GM 2026-10-26: douse a fire
            gm = self.sim.gm_rules
            burning = [i for i in [me] + [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me]
                       if gm.has(i, "Burning") and not self.sim.down(i) and (i == me or self.party.dist(me, i) <= 5.01)]
            for tid in burning:
                who = "yourself" if tid == me else self.sim.by_id(tid)["name"]
                out.append(self.entry(me, {"item": WATERSKIN, "target": tid}, "Douse the fire on %s (Waterskin)" % who, "action",
                                      bag, effect="the fire goes out (the skin is empty after)"))
        for gid, name in traps_mod.GEAR.items():                  # GM 2026-10-24: area gear, on a square the player picks
            if gid in have:
                k = traps_mod.GEAR_KINDS[gid]
                ready, rows = rq.check(traps_mod.of(self.sim).gear_needs(me, gid, None, None, bag)[:-1])
                e = {"op": "use_item", "item": gid, "square": True, "within_ft": k["within"], "size": k["size"],
                     "label": "%s on a square" % name, "time": "action", "ready": ready, "needs": rows,
                     "effect": {"caltrops": "DC 15 Dexterity save on entering: 1 Piercing and Speed 0",
                                "ball-bearings": "a 10-foot square; DC 10 Dexterity save on entering or Prone",
                                "oil": "burns once lit (a Tinderbox): 5 Fire",
                                "hunting-trap": "DC 13 Dexterity save: 1d4 Piercing and held (an Iron Spike anchors it)"}[gid]}
                if not ready:
                    e["why"], e["link"] = rq.first_why(rows), rq.first_link(rows)
                out.append(e)
        for pid, p in srd_poisons.POISONS.items():                # the SRD's other poisons
            if pid not in have:
                continue
            if p["type"] == "injury":
                for key in __import__("character_rules").WEAPON_KEYS:
                    w = c.get(key)
                    if isinstance(w, dict) and w.get("name") and not w.get("cantrip") and w.get("dmgtype"):
                        out.append(self.entry(me, {"item": pid, "weapon": key}, "%s on the %s" % (p["name"], w["name"]),
                                              "bonus", bag, effect=srd_poisons.effect_text(p)))
            elif p["type"] == "inhaled":
                near = [o["id"] for o in self.sim.sc["combatants"] if o["id"] != me and not self.sim.down(o["id"])
                        and self.party.dist(me, o["id"]) <= 5.01]
                near.sort(key=lambda o: self.party.side(o) == self.party.side(me))    # foes first, then allies
                for tid in near or [None]:
                    who = (self.sim.by_id(tid)["name"] + (" (an ally)" if self.party.side(tid) == self.party.side(me) else "")
                           if tid else "a creature within 5 ft")
                    out.append(self.entry(me, {"item": pid, "target": tid}, "%s at %s" % (p["name"], who), "action", bag,
                                          effect=srd_poisons.effect_text(p)))
            else:
                out.append(self.entry(me, {"item": pid}, p["name"], "action", bag, effect=srd_poisons.effect_text(p)))
        for tid in [b.get("item") for b in entries if b.get("item") in TOOL_USES]:   # GM 2026-10-26: Utilize a tool
            t = srd_tools.TOOLS[tid]
            for i, u in enumerate(t["utilize"]):
                chk = rq.tool_check(c, tid, srd_tools.SKILL.get((tid, u["what"])))
                out.append(self.entry(me, {"item": tid, "use": i}, "%s: %s (DC %d)" % (t["name"], u["what"], u["dc"]), "action",
                                      bag, effect="%s check%s; the GM rules what it tells or does" % (
                                          chk["text"], "" if chk["proficient"] else " (not proficient: no Proficiency Bonus)")))
        return {"uses": out, "bag": [{"name": b["name"], "qty": b["qty"], "item": b.get("item")} for b in entries][:40],
                "link": rq.LINKS["market"], "fight_items": sum(1 for b in entries if b.get("item") in FIGHT_ITEMS)}

    def entry(self, me, cmd, label, time, bag, **extra):
        ready, rows = rq.check(self.needs(me, cmd, bag))
        e = dict(cmd, op="use_item", label=label, time=time, ready=ready, needs=rows, **extra)
        if not ready:
            e["why"], e["link"] = rq.first_why(rows), rq.first_link(rows)
        return e

    def needs(self, me, cmd, bag=None):
        """Every prerequisite of one use, in the order a player meets them."""
        c, item, bag = self.sim.by_id(me), cmd.get("item"), bag or self.bag(me)
        needs = [rq.able(self.fight, me)]
        if item == POISON:
            key = cmd.get("weapon")
            needs += [rq.in_bag(bag, POISON, "Basic Poison"), rq.on_sheet(c, key if key in __import__("character_rules").WEAPON_KEYS else "", "that weapon"),
                      rq.bonus_free(self.fight, me, "Basic Poison")]
            w = c.get(key) if key in __import__("character_rules").WEAPON_KEYS else None
            if isinstance(w, dict) and w.get("name"):
                kind = str(w.get("dmgtype") or "").lower()
                needs.append(rq.need("a weapon that deals Piercing or Slashing damage", kind in ("piercing", "slashing"),
                                     "Basic Poison works through Piercing or Slashing damage; the %s deals %s." % (w["name"], kind.capitalize() or "no weapon")))
                coat = self.coated(me)
                needs.append(rq.need("no poison on it yet", not (coat and coat["key"] == key),
                                     "The %s is already coated with %s." % (w["name"], coat.get("label", "Basic Poison")) if coat else ""))
        elif item in POTIONS:
            name = POTIONS[item][0]
            tid = cmd.get("target")
            needs += [rq.in_bag(bag, item, name), rq.bonus_free(self.fight, me, name)]
            t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
            needs.append(rq.need("yourself or an ally within 5 ft", t is not None and (tid == me or (
                self.party.side(tid) == self.party.side(me) and self.party.dist(me, tid) <= 5.01)),
                "Give it to yourself or to an ally within 5 ft."))
            if t is not None:
                needs.append(rq.need("a creature that can be healed", not self.party.deaths.get(tid, {}).get("dead"),
                                     "%s is dead: a potion does not bring back the dead." % t["name"]))
        elif item == KIT:
            tid = cmd.get("target")
            t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
            needs += [rq.in_bag(bag, KIT, "a Healer's Kit"), rq.action_free(self.fight, me, "the Utilize action")]
            needs.append(rq.need("an ally at 0 Hit Points within 5 ft", t is not None and self.sim.down(tid)
                                 and self.party.side(tid) == self.party.side(me) and self.party.dist(me, tid) <= 5.01,
                                 "No ally is at 0 Hit Points now." if t is None else
                                 "The Healer's Kit stabilizes a creature at 0 Hit Points within 5 ft."))
            if t is not None:
                d = self.party.deaths.get(tid, {})
                needs.append(rq.need("not dead, not stable yet", not d.get("dead") and not d.get("stable"),
                                     "%s is %s." % (t["name"], "dead" if d.get("dead") else "already stable")))
        elif item == ANTITOXIN:
            needs += [rq.in_bag(bag, ANTITOXIN, "Antitoxin"), rq.bonus_free(self.fight, me, "Antitoxin")]
        elif item in THROWN:
            name = THROWN[item][0]
            tid = cmd.get("target")
            t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
            turn = self.fight.turn_state or {}
            needs += [rq.in_bag(bag, item, name),
                      rq.need("an attack of the Attack action", not turn.get("action_used") or turn.get("attacks_left", 0) > 0,
                              "%s's Action is used this turn (a throw replaces one attack of the Attack action)." % c["name"]),
                      rq.need("a creature you can see within 20 ft", t is not None and tid != me and not self.sim.down(tid)
                              and self.party.dist(me, tid) <= 20.01 and self.sim.sees(me, tid) and not self.party.blocked(me, tid),
                              "Throw it at a creature you can see within 20 ft." if t is None or tid == me else
                              "%s is out of reach of a throw (20 ft), out of sight or behind a wall." % t["name"])]
        elif tossed(cmd):                                         # GM 2026-10-26: Oil or a Net at a creature
            g = TOSSED[item]
            tid = cmd.get("target")
            t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
            turn = self.fight.turn_state or {}
            unseen = g["sight"] and t is not None and not self.sim.sees(me, tid)
            needs += [rq.in_bag(bag, item, g["name"]),
                      rq.need("an attack of the Attack action", not turn.get("action_used") or turn.get("attacks_left", 0) > 0,
                              "%s's Action is used this turn (a throw replaces one attack of the Attack action)." % c["name"]),
                      rq.need("a creature within %d ft" % g["reach"], t is not None and tid != me and not self.sim.down(tid)
                              and self.party.dist(me, tid) <= g["reach"] + 0.01 and not unseen and not self.party.blocked(me, tid),
                              "Throw it at a creature %swithin %d ft." % ("you can see " if g["sight"] else "", g["reach"])
                              if t is None or tid == me else "%s is out of reach of a throw (%d ft)%s or behind a wall." % (
                                  t["name"], g["reach"], ", out of sight" if g["sight"] else ""))]
        elif item == WATERSKIN:                                   # GM 2026-10-26: douse a fire
            tid = cmd.get("target")
            t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
            full = bag.count(WATERSKIN) - self.state("emptied").get(me, 0)
            burning = t is not None and self.sim.gm_rules.has(tid, "Burning")
            needs += [rq.in_bag(bag, WATERSKIN, "a Waterskin"),
                      rq.need("water in a Waterskin", full > 0, "%s's Waterskin%s empty: refill it after the fight." % (
                          c["name"], "s are" if bag.count(WATERSKIN) > 1 else " is")),
                      rq.action_free(self.fight, me, "the Utilize action"),
                      rq.need("a burning creature within 5 ft", burning and (tid == me or self.party.dist(me, tid) <= 5.01),
                              "Douse yourself or a burning creature within 5 ft." if t is None else
                              "%s is not burning." % t["name"] if not burning else "%s is not within 5 ft." % t["name"])]
        elif item in traps_mod.GEAR:                             # GM 2026-10-24: on a square (sim/traps.py)
            x, y = cmd.get("x"), cmd.get("y")
            needs = traps_mod.of(self.sim).gear_needs(me, item, None if x is None else int(x), None if y is None else int(y), bag)
        elif item in TOOL_USES:                                   # GM 2026-10-26: a tool's Utilize use
            t = srd_tools.TOOLS[item]
            use = cmd.get("use")
            needs += [rq.in_bag(bag, item, t["name"]), rq.action_free(self.fight, me, "the Utilize action"),
                      rq.need("one of the tool's uses", isinstance(use, int) and not isinstance(use, bool) and 0 <= use < len(t["utilize"]),
                              "%s's uses: %s." % (t["name"], ", ".join(u["what"] for u in t["utilize"])))]
        elif item in srd_poisons.POISONS:
            p = srd_poisons.POISONS[item]
            needs.append(rq.in_bag(bag, item, p["name"]))
            if p["type"] == "injury":
                key = cmd.get("weapon")
                needs += [rq.on_sheet(c, key if key in __import__("character_rules").WEAPON_KEYS else "", "that weapon"),
                          rq.bonus_free(self.fight, me, p["name"])]
                w = c.get(key) if key in __import__("character_rules").WEAPON_KEYS else None
                if isinstance(w, dict) and w.get("name"):
                    kind = str(w.get("dmgtype") or "").lower()
                    needs.append(rq.need("a weapon that wounds (Piercing or Slashing)", kind in ("piercing", "slashing"),
                                         "An injury poison is delivered through a wound (Piercing or Slashing damage); "
                                         "the %s deals %s." % (w["name"], kind.capitalize() or "no weapon damage")))
                    coat = self.coated(me)
                    needs.append(rq.need("no poison on it yet", not (coat and coat["key"] == key),
                                         "The %s is already coated with %s." % (w["name"], coat.get("label", "poison")) if coat else ""))
            elif p["type"] == "inhaled":
                tid = cmd.get("target")
                t = next((o for o in self.sim.sc["combatants"] if o["id"] == tid), None)
                needs += [rq.action_free(self.fight, me, "the Utilize action"),
                          rq.need("a creature within 5 ft", t is not None and tid != me and not self.sim.down(tid)
                                  and self.party.dist(me, tid) <= 5.01,
                                  "Release it into the 5-foot Cube of a creature within 5 ft." if t is None or tid == me
                                  else "%s is not within 5 ft." % t["name"])]
            else:
                needs.append(rq.need("a poison for a fight", False, "%s is %s poison: it has no use in a fight here "
                                     "(the GM rules it)." % (p["name"], "a contact" if p["type"] == "contact" else "an ingested")))
        else:
            needs.append(rq.need("an item a character can use in a fight", False, "That item has no use in a fight here yet."))
        return needs

    # ------------------------------------------------------------------ using one
    def do(self, me, cmd):
        """Checks every need again, then spends (the item, the action) and does it. -> how it was paid."""
        bag = self.bag(me)
        ready, rows = rq.check(self.needs(me, cmd, bag))
        if not ready:
            raise ItemError(rq.first_why(rows))
        c, item, party, say = self.sim.by_id(me), cmd["item"], self.party, lambda text: self.sim.say("dice", text)
        t = self.fight.turn_state
        if item == POISON:
            w = c[cmd["weapon"]]
            bag.take(POISON, 1, "on the %s in a fight" % w["name"])
            party.use_bonus(me)
            pieces = 3 if w["name"] in AMMO_WEAPONS else None
            self.state("coated")[me] = {"key": cmd["weapon"], "name": w["name"], "until": int(party.s.round()) + MINUTE - 1,
                                        "pieces": pieces, "label": "Basic Poison"}
            say("%s coats %s with Basic Poison (Bonus Action): +1d4 Poison when it deals Piercing or Slashing damage, "
                "for 1 minute or until its damage is dealt" % (c["name"], "three pieces of ammunition for the %s" % w["name"]
                                                               if pieces else "the %s" % w["name"]))
            return "bonus"
        if item in POTIONS:
            name, dice = POTIONS[item]
            tid = cmd["target"]
            bag.take(item, 1, "in a fight, for %s" % self.sim.by_id(tid)["name"])
            party.use_bonus(me)
            import party as party_mod
            heal = party_mod.roll(self.sim.rng, dice)
            who = "drinks" if tid == me else "gives %s" % self.sim.by_id(tid)["name"]
            say("%s %s a %s (Bonus Action): %s = %d Hit Points" % (c["name"], who, name, dice, heal))
            if self.sim.down(tid):
                party.revive(tid, heal)
            else:
                party.s.heal(tid, heal)
            return "bonus"
        if item == KIT:
            tid = cmd["target"]
            left = bag.use_charge(KIT, KIT_USES, "stabilize %s" % self.sim.by_id(tid)["name"])
            t["action_used"], t["attacks_left"] = True, 0
            party.deaths[tid].update(successes=0, failures=0, stable=True)
            party.s.setField(tid, "sim_dying", 0)
            say("%s uses a Healer's Kit on %s (Utilize action): stable, no Wisdom (Medicine) check (%d use%s left in the kit)" % (
                c["name"], self.sim.by_id(tid)["name"], left, "" if left == 1 else "s"))
            return "action"
        if item in THROWN:
            name, dice, kind = THROWN[item]
            tid = cmd["target"]
            target = self.sim.by_id(tid)
            bag.take(item, 1, "thrown at %s in a fight" % target["name"])
            self.one_attack(me, c, t)
            dc = self.throw_dc(c)
            say("%s throws %s at %s (one attack of the Attack action): DC %d Dexterity save" % (c["name"], name, target["name"], dc))
            saved, _ = self.sim.gm_rules.roll_save(me, tid, {"save": "dex", "dc": dc}, name)
            holy = item != "holy-water" or any(k in str(target.get("type", "")).lower() for k in ("fiend", "undead"))
            if not saved and holy:
                import party as party_mod
                dmg = party_mod.roll(self.sim.rng, dice)
                say("%s: %s = %d %s damage" % (name, dice, dmg, kind.capitalize()))
                party.s.pcDamage(me, tid, "", dmg, False, kind)
                self.sim.settle(0.2)
                if kind == "fire":                                # GM 2026-10-25 (T10): fire lights oil under it
                    import traps as oil_traps
                    oil_traps.of(self.sim).ignite_creatures([tid], me, "%s's %s" % (c["name"], name))
                if item == "alchemists-fire" and not self.sim.down(tid):
                    self.sim.gm_rules.add(tid, "Burning", "(%s's Alchemist's Fire)" % c["name"], by=me)
            elif not saved:
                say("Holy Water harms only a Fiend or an Undead: %s is neither" % target["name"])
            return "attack"
        if tossed(cmd):                                           # GM 2026-10-26: Oil or a Net
            g, tid = TOSSED[item], cmd["target"]
            target = self.sim.by_id(tid)
            bag.take(item, 1, "thrown at %s in a fight" % target["name"])
            self.one_attack(me, c, t)
            dc = self.throw_dc(c)
            say("%s throws %s at %s (one attack of the Attack action): DC %d Dexterity save" % (c["name"], g["name"], target["name"], dc))
            big = str(target.get("size") or "").lower() in ("huge", "gargantuan") or self.sim.size_sq(tid) >= 3
            if item == "net" and big:
                say("%s is Huge or larger: it shrugs off the Net (a success)" % target["name"])
                return "attack"
            saved, _ = self.sim.gm_rules.roll_save(me, tid, {"save": "dex", "dc": dc}, g["name"])
            if not saved and item == "oil":
                traps_mod.of(self.sim).oil_on(tid, me)
                say("%s is covered in oil for 1 minute: if it takes Fire damage before the oil dries, it takes 5 Fire more" % target["name"])
            elif not saved:
                traps_mod.of(self.sim).net_on(me, tid)
                say("%s is Restrained by the Net until it escapes: an action and DC 10 Strength (Athletics), by it or a "
                    "creature within 5 ft" % target["name"])
            return "attack"
        if item == WATERSKIN:
            tid = cmd["target"]
            t["action_used"], t["attacks_left"] = True, 0
            self.state("emptied")[me] = self.state("emptied").get(me, 0) + 1
            on = "the flames" if tid == me else "the flames on %s" % self.sim.by_id(tid)["name"]
            self.sim.gm_rules.remove(tid, "Burning", "doused with water from %s's Waterskin" % c["name"])
            say("%s empties a Waterskin over %s (Utilize action): the fire goes out" % (c["name"], on))
            return "action"
        if item in traps_mod.GEAR:
            t["action_used"], t["attacks_left"] = True, 0
            traps_mod.of(self.sim).put_gear(me, item, int(cmd["x"]), int(cmd["y"]), bag)
            return "action"
        if item in srd_poisons.POISONS:
            p = srd_poisons.POISONS[item]
            if p["type"] == "injury":
                w = c[cmd["weapon"]]
                bag.take(item, 1, "on the %s in a fight" % w["name"])
                party.use_bonus(me)
                pieces = 1 if w["name"] in AMMO_WEAPONS else None
                self.state("coated")[me] = {"key": cmd["weapon"], "name": w["name"], "until": None, "pieces": pieces,
                                            "poison": item, "label": p["name"]}
                say("%s coats %s with %s (Bonus Action): %s when it wounds (Piercing or Slashing damage)" % (
                    c["name"], "a piece of ammunition for the %s" % w["name"] if pieces else "the %s" % w["name"], p["name"],
                    srd_poisons.effect_text(p)))
                return "bonus"
            tid = cmd["target"]
            bag.take(item, 1, "released at %s in a fight" % self.sim.by_id(tid)["name"])
            t["action_used"], t["attacks_left"] = True, 0
            say("%s releases %s at %s (Utilize action; a 5-foot Cube)" % (c["name"], p["name"], self.sim.by_id(tid)["name"]))
            srd_poisons.apply(self.sim, me, tid, item)
            return "action"
        if item in TOOL_USES:
            tool, u = srd_tools.TOOLS[item], srd_tools.TOOLS[item]["utilize"][cmd["use"]]
            t["action_used"], t["attacks_left"] = True, 0
            chk = rq.tool_check(c, item, srd_tools.SKILL.get((item, u["what"])))
            a, b = self.sim.rng.randint(1, 20), self.sim.rng.randint(1, 20)
            d20 = max(a, b) if chk["advantage"] else a
            total = d20 + chk["bonus"]
            say("%s uses %s (Utilize action): %s. %s check: d20 %s %+d = %d vs DC %d -> %s; the GM rules what it tells or does" % (
                c["name"], tool["name"], u["what"], chk["label"],
                "%d/%d (Advantage)" % (a, b) if chk["advantage"] else str(a), chk["bonus"], total, u["dc"],
                "success" if total >= u["dc"] else "failure"))
            return "action"
        if item == ANTITOXIN:
            bag.take(ANTITOXIN, 1, "drunk in a fight")
            party.use_bonus(me)
            self.state("antitoxin")[me] = int(party.s.round()) + HOUR - 1
            say("%s drinks Antitoxin (Bonus Action): Advantage on saving throws to avoid or end the Poisoned condition for "
                "1 hour" % c["name"])
            return "bonus"
        raise ItemError("That item has no use in a fight here yet.")

    def one_attack(self, me, c, t):
        """A throw replaces one attack of the Attack action (taking the action if it is not taken yet)."""
        if not t["action_used"]:
            t["action_used"], t["attacks_left"] = True, c.get("attacks", 1)
            self.sim.say("turn", "%s takes the Attack action (%d attack%s)" % (c["name"], t["attacks_left"], "" if t["attacks_left"] == 1 else "s"))
        t["attacks_left"] -= 1
        t["attacks_made"] = t.get("attacks_made", 0) + 1

    @staticmethod
    def throw_dc(c):
        """DC 8 + the thrower's Dexterity modifier + Proficiency Bonus."""
        dex = (c.get("abilities") or {}).get("dex", c.get("dex_score", 10)) or 10
        return 8 + (int(dex) - 10) // 2 + 2 + (int(c.get("level", 1) or 1) - 1) // 4

    # ------------------------------------------------------------------ the poisoned weapon, when it attacks
    def poison_dice(self, me, key, weapon):
        """Basic Poison's 1d4 with the weapon's damage; an injury poison says it is there (its save comes after the hit).
        The party keeps the coating (Party.coat_dice), for the computer-played heroes too."""
        coat = self.coated(me)
        if not coat or coat["key"] != key:
            return ""
        return self.party.coat_dice(me, weapon)[0]

    def coated_with(self, me, key):
        coat = self.coated(me)
        return coat.get("label", "Basic Poison") if coat and coat["key"] == key else ""

    def after_attack(self, me, key, res, tid=None):
        """Ammunition: a coated piece is spent with each shot; a weapon: the poison is gone once its damage is dealt.
        An injury poison: a wound (a hit with Piercing or Slashing damage) exposes the creature to it (Party.coat_after)."""
        coat = self.coated(me)
        if not coat or coat["key"] != key:
            return
        self.party.coat_after(me, self.sim.by_id(me)[key], res, tid)


def antitoxin_on(party, t):
    """Antitoxin's hour (gm_rules reads it for saves against the Poisoned condition)."""
    until = getattr(party, "antitoxin", {}).get(t) if party is not None else None
    return until is not None and int(party.s.round()) <= until
