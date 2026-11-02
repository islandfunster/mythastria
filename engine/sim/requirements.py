"""GM 2026-10-23 ("Check all prerequisites before allowing a tool, consumable, or process to be availed. Create in-game
links to connect prerequisites before adding to inventories, application, or determining outcomes."): the one check that
every tool, consumable and process goes through (plan: docs/development/SRD_GAPS_PLAN.md).

A need is met or not. When it is not, it says why in plain words and links to the place in Mythastria that fixes it
(the Market for an item or gold, Characters for a proficiency or a spell, Downtime for days). Nothing is spent here: the
caller spends only after every need is met, and then all at once.

  needs = [requirements.in_bag(bag, "poison-basic", "Basic Poison"), requirements.bonus_free(fight, me)]
  ready, rows = requirements.check(needs)        # rows: [{"need", "met", "why", "link"}]
"""

# Where a missing prerequisite is fixed. The page draws each one as a button (play-view.mjs needLinks).
LINKS = {
    "market": {"page": "market", "label": "Market"},           # Play live's Market: the GM's dialog, or a player's open shop
    "characters": {"page": "./characters.html", "label": "Characters"},
}


def need(what, met, why="", link=None):
    return {"need": what, "met": bool(met), "why": "" if met else why, "link": None if met else link}


def check(needs):
    """(ready, the needs): ready when every need is met."""
    rows = [n for n in needs if n]
    return all(n["met"] for n in rows), rows


def first_why(rows):
    return next((n["why"] for n in rows if not n["met"]), "")


def first_link(rows):
    return next((n["link"] for n in rows if not n["met"] and n.get("link")), None)


# ------------------------------------------------------------------ what a character carries: the Market's bag
class Bag:
    """A character's bag in the Market (sim/market.py: purses[character].bag), or a fixed list (tests, a sheet's
    equipment without a Market). Counting reads it; taking writes it back through the Market, logged there."""

    def __init__(self, character, market=None, lines=None):
        self.character, self.market, self.lines = character, market, lines

    def entries(self):
        if self.market is not None:
            return self.market.holdings(self.character)
        return list(self.lines or [])

    def count(self, item):
        return sum(int(b.get("qty", 0)) for b in self.entries() if b.get("item") == item)

    def entry(self, item):
        return next((b for b in self.entries() if b.get("item") == item and int(b.get("qty", 0)) > 0), None)

    def take(self, item, qty=1, why=""):
        if self.market is not None:
            return self.market.take(self.character, item, qty, why)
        b = self.entry(item)
        if not b or b["qty"] < qty:
            raise ValueError("%s is not in the bag." % item)
        b["qty"] -= qty
        return b["qty"]

    def use_charge(self, item, per_item, why=""):
        """One use of an item with uses (a Healer's Kit has ten): an emptied one leaves the bag."""
        if self.market is not None:
            return self.market.use_charge(self.character, item, per_item, why)
        b = self.entry(item)
        if not b:
            raise ValueError("%s is not in the bag." % item)
        left = int(b.get("uses_left", per_item)) - 1
        if left <= 0:
            b["qty"] -= 1
            left = per_item
        b["uses_left"] = left
        return left

    def uses_left(self, item, per_item):
        b = self.entry(item)
        return int(b.get("uses_left", per_item)) if b else 0


# ------------------------------------------------------------------ the needs
def in_bag(bag, item, name, qty=1):
    have = bag.count(item)
    return need("%s in %s's bag" % (name, bag.character), have >= qty,
                "%s has no %s in the bag: buy it at a Market shop the GM opens." % (bag.character, name)
                if not have else "%s needs %d %s (%d in the bag)." % (bag.character, qty, name, have), LINKS["market"])


def able(fight, me):
    import live_actions
    try:
        fight.actions.able(me)
        return need("able to act", True)
    except live_actions.ActionError as e:
        return need("able to act", False, str(e))


def action_free(fight, me, what="the Action"):
    t, c = fight.turn_state or {}, fight.sim.by_id(me)
    return need("the Action free", not t.get("action_used"), "%s's Action is used this turn (%s needs it)." % (c["name"], what))


def bonus_free(fight, me, what="it"):
    c = fight.sim.by_id(me)
    return need("the Bonus Action free", fight.sim.party.bonus_free(me),
                "%s's Bonus Action is used this turn (%s needs it)." % (c["name"], what))


def on_sheet(c, key, what):
    w = c.get(key)
    return need(what + " on the sheet", isinstance(w, dict) and w.get("name"),
                "%s has no %s on the sheet." % (c["name"], what), LINKS["characters"])


def proficient(c, name):
    """A skill or tool proficiency on the sheet (the builder's sheet: skills and tools; a class's tool: Druid, Rogue)."""
    import srd_tools
    tid = srd_tools.by_name(name)
    have = name in (c.get("skills") or []) or (tid in tool_proficiencies(c) if tid else
                                                 srd_tools.norm(name) in {srd_tools.norm(t) for t in c.get("tools") or []})
    what = srd_tools.TOOLS[tid]["name"] if tid else name
    return need("proficiency with %s" % what, have, "%s is not proficient with %s%s." % (
        c["name"], what, " (a background, a feat or a class gives it)" if tid else ""), LINKS["characters"])


# ------------------------------------------------------------------ GM 2026-10-26 (goals 10, 11, 13): tools, gold, spells
def classes_of(c):
    """The character's classes, lowercase (a saved sheet's multiclass levels: rest_classes)."""
    return {str(c.get("class") or "").lower()} | {str(k).lower() for k in (c.get("rest_classes") or {})}


def tool_proficiencies(c):
    """The SRD tools this character is proficient with (ids, sim/srd_tools.py): the sheet's tools (any spelling) and the
    ones its class gives (SRD 5.2.1: a Druid's Herbalism Kit, a Rogue's Thieves' Tools)."""
    import srd_tools
    out = []
    for n in c.get("tools") or []:
        tid = srd_tools.by_name(n) if isinstance(n, str) else None
        if tid and tid not in out:
            out.append(tid)
    for cls in sorted(classes_of(c)):
        out += [t for t in srd_tools.CLASS_TOOLS.get(cls, []) if t not in out]
    return out


def ability_mod(c, ability):
    score = (c.get("abilities") or {}).get(ability)
    if score is None:
        score = c.get(ability + "_score", 10)
    return (int(score or 10) - 10) // 2


def prof_bonus(c):
    return 2 + (int(c.get("level", 1) or 1) - 1) // 4


def tool_check(c, tid, skill=None, ability=None):
    """SRD 5.2.1 Tool Proficiency: an ability check that uses the tool adds the Proficiency Bonus when the character is
    proficient with the tool, and has Advantage when it is also proficient in the skill used with the check.
    -> {"bonus", "ability", "proficient", "advantage", "label", "text"} (text: "Intelligence (Herbalism Kit) +5")."""
    import srd_tools
    t = srd_tools.TOOLS[tid]
    ab = ability or t["ability"]
    prof = tid in tool_proficiencies(c)
    bonus = ability_mod(c, ab) + (prof_bonus(c) if prof else 0)
    adv = bool(prof and skill and skill in (c.get("skills") or []))
    label = "%s (%s)" % (srd_tools.AB[ab], t["name"])
    return {"bonus": bonus, "ability": ab, "proficient": prof, "advantage": adv, "skill": skill if adv else None, "label": label,
            "text": "%s %+d%s" % (label, bonus, ", Advantage (%s and %s)" % (t["name"], skill) if adv else "")}


def gold(have_cp, cost_cp, who, what):
    """Gold from the character's purse (the Market keeps it)."""
    import market
    return need("%s for %s" % (market.money(cost_cp), what), have_cp >= cost_cp,
                "%s needs %s for %s; %s has %s: the GM gives gold in the Market, or %s sells something there." % (
                    who, market.money(cost_cp), what, who, market.money(have_cp), who), LINKS["market"])


def sheet_spells(c):
    """The spells on the character's sheet: a saved sheet's spell list; a pregen's spells (its build's flags, named after
    the SRD spells). A spell on the sheet counts as prepared (the table keeps no separate prepared list)."""
    import re, spell_rules
    names = [sp.get("name") for sp in c.get("spell_list") or [] if isinstance(sp, dict) and sp.get("name")]
    for n in spell_rules.sheet():
        if n not in names and c.get(re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")):
            names.append(n)
    return names


def spell_prepared(c, spell):
    return need("%s prepared" % spell, spell in sheet_spells(c), "%s doesn't have %s prepared (it is not among the spells "
                "on the sheet)." % (c["name"], spell), LINKS["characters"])
