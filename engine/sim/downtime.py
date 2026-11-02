"""GM 2026-10-26 (goal 13, "Crafting, brewing and scribing"; plan: docs/development/SRD_GAPS_PLAN.md group 4): downtime by
the SRD 5.2.1, between adventures, on the adventure home page beside the party's day (sim/rests.py). Every prerequisite
goes through sim/requirements.py and says why, with a link, when it is not met; gold is paid from the Market's purse and
the result goes into the Market's bag.

- Crafting Nonmagical Items (Equipment): the tool its Craft line names (sim/srd_tools.py; "The GM assigns required tools
  for items not listed there"), used and with proficiency, and anyone helping proficient with it too; raw materials worth
  half its purchase cost (round down), "the GM determines whether appropriate raw materials are available"; days = its
  cost in GP / 10, a fraction rounded up to a day; "Divide the time needed ... by the number of characters working on
  it. Normally, only one other character can assist you, but the GM might allow more assistants."
- Brewing Potions of Healing: proficiency with the Herbalism Kit, using the kit, 25 GP of raw material, 1 day.
- Scribing Spell Scrolls: proficiency in Arcana or with Calligrapher's Supplies; the spell prepared on each day; its
  Material components at hand (consumed ones only when the scroll is done); the Spell Scroll Costs table; the scroll
  uses the scribe's spell save DC and attack bonus (a cantrip works at the scribe's level).
- Crafting Magic Items (Magic Items): Arcana for the crafter and any assistants; the Magic Item Tools table's tool, used
  and with proficiency (the assistants too); the spells the item casts prepared every day (the GM confirms: the list does
  not name them); the Magic Item Crafting Time and Cost table, halved for a consumable other than a Spell Scroll; an item
  it incorporates (a weapon, a suit of armor) paid in full; raw materials: 75 percent in a city, 25 in another
  settlement, rolled for everyone to see, else at least 7 days before looking again.
Work: each day of downtime is 8 hours of work for everyone on a project ("the days needn't be consecutive"), and the
party rests: a Long Rest's benefits at the end (sim/rests.py). Kept in sim/market/downtime.json (a test port keeps its
own file).
"""
import json, math, re, secrets, threading
from pathlib import Path

import requirements as rq
import srd_tools

KINDS = {"craft": "Craft an item", "brew": "Brew a Potion of Healing", "scribe": "Scribe a Spell Scroll",
         "magic": "Craft a magic item"}
CRAFTABLE = ("gear", "tool", "weapon", "armor", "ammunition", "focus")
POTION, HERBS, CALLIGRAPHY = "potion-of-healing", "herbalism-kit", "calligraphers-supplies"
BREW_CP, BREW_DAYS = 2500, 1
SCROLL = {0: (1, 15), 1: (1, 25), 2: (3, 100), 3: (5, 150), 4: (10, 1000), 5: (25, 1500), 6: (40, 10000), 7: (50, 12500),
          8: (60, 15000), 9: (120, 50000)}                         # Spell Scroll Costs: level -> (days, GP)
MAGIC = {"Common": (5, 50), "Uncommon": (10, 200), "Rare": (50, 2000), "Very Rare": (125, 20000), "Legendary": (250, 100000)}
MAGIC_TOOLS = {"Potion": ["alchemists-supplies", HERBS], "Ring": ["jewelers-tools"], "Rod": ["woodcarvers-tools"],
               "Staff": ["woodcarvers-tools"], "Wand": ["woodcarvers-tools"], "Wondrous Item": ["tinkers-tools"]}
CHANCE = {"city": 75, "settlement": 25}                            # raw materials for a magic item
PLACES = {"city": "a city", "settlement": "another settlement"}
WAIT_DAYS, MAX_WORK_DAYS, MAX_PROJECTS = 7, 100, 200
LINKS = {"work": {"page": "#dt-work", "label": "Downtime days"}}


class DowntimeError(ValueError):
    pass


def money(cp):
    import market
    return market.money(cp)


def slug(name):
    return srd_tools.slug(name)


# ------------------------------------------------------------------ the ledger
class Ledger:
    """The projects, one list for every character (a project follows its crafter from one adventure to the next)."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.state = None

    def load(self):
        if self.state is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                assert data.get("version") == 1 and isinstance(data.get("projects"), list)
                self.state = data
            except (OSError, ValueError, AssertionError, AttributeError):
                self.state = {"version": 1, "projects": []}
        return self.state

    def save(self):
        st = self.state
        done = [p for p in st["projects"] if p["status"] in ("done", "abandoned")]
        if len(st["projects"]) > MAX_PROJECTS:                      # the oldest finished ones go first
            drop = {id(p) for p in done[:len(st["projects"]) - MAX_PROJECTS]}
            st["projects"] = [p for p in st["projects"] if id(p) not in drop]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=0), encoding="utf-8")
        tmp.replace(self.path)

    def busy(self, name, but=None):
        """The open project this character works on (as the crafter or an assistant), or None."""
        return next((p for p in self.load()["projects"] if p["status"] in ("working", "searching") and p["id"] != but
                     and (p["who"] == name or name in p["helpers"])), None)

    def by_id(self, pid):
        p = next((p for p in self.load()["projects"] if p["id"] == pid), None)
        if not p:
            raise DowntimeError("No such project (it may have been finished or abandoned on another screen).")
        return p


# ------------------------------------------------------------------ what a project is: its item, tool, cost and days
def magic_tools(item, base, catalog):
    """The tools the Magic Item Tools table names for this item (none: the GM assigns one)."""
    cat = str(item.get("category") or "").split(" (")[0]
    if cat in ("Armor", "Weapon"):                                 # "depending on the kind of armor / weapon"
        return srd_tools.craft_tools(slug(base), catalog) if base else []
    return list(MAGIC_TOOLS.get(cat, []))


def scroll_level(spell):
    import spell_rules
    s = spell_rules.sheet().get(spell)
    return int(s["level"]) if s else None


def shape(req, catalog):
    """The project the request names: {kind, item, name, base, tools, days, cost_cp, why_cost}; refused when it names
    nothing the rules know."""
    kind = req.get("kind")
    if kind not in KINDS:
        raise DowntimeError("A project is one of: %s." % ", ".join(KINDS.values()))
    if kind == "brew":
        return {"kind": kind, "item": POTION, "name": catalog[POTION]["name"], "base": None, "tools": [HERBS], "days": BREW_DAYS,
                "cost_cp": BREW_CP, "why_cost": "raw material for a Potion of Healing"}
    if kind == "scribe":
        spell = req.get("spell")
        level = scroll_level(spell) if isinstance(spell, str) else None
        sid = "spell-scroll-" + slug(spell) if level is not None else None
        if level is None or sid not in catalog:
            raise DowntimeError("Choose a spell from the scribe's sheet.")
        days, gp = SCROLL[level]
        return {"kind": kind, "item": sid, "name": catalog[sid]["name"], "base": None, "tools": [], "days": days, "cost_cp": gp * 100,
                "spell": spell, "level": level, "why_cost": "the Spell Scroll Costs table (%s)" % ("a cantrip" if not level else "level %d" % level)}
    item = catalog.get(req.get("item")) if isinstance(req.get("item"), str) else None
    if kind == "craft":
        if not item or item["kind"] not in CRAFTABLE:
            raise DowntimeError("Choose a nonmagical item from the SRD 5.2.1 list (Potions of Healing are brewed, Spell "
                                "Scrolls scribed).")
        cost = int(item["cost_cp"])
        return {"kind": kind, "item": item["id"], "name": item["name"], "base": None, "tools": srd_tools.craft_tools(item["id"], catalog),
                "days": max(1, math.ceil(cost / 1000 - 1e-9)), "cost_cp": cost // 2,
                "why_cost": "raw materials: half of %s's %s, rounded down" % (item["name"], money(cost))}
    if not item or item["kind"] not in ("magic", "potion") or item["id"] == POTION:
        raise DowntimeError("Choose a magic item from the SRD 5.2.1 list (a Potion of Healing is brewed, a Spell Scroll "
                            "scribed).")
    base = item.get("base") or req.get("base") or None
    if item.get("bases") and base not in item["bases"]:
        raise DowntimeError("Choose what %s is made from (%s)." % (item["name"], ", ".join(item["bases"][:6]) + (" ..." if len(item["bases"]) > 6 else "")))
    days, gp = MAGIC[item["rarity"]]
    cost, halved = gp * 100, bool(item.get("consumable"))
    if halved:
        days, cost = days / 2, cost // 2
    base_cp = int(catalog[slug(base)]["cost_cp"]) if base and slug(base) in catalog else 0
    name = item["name"] + (" (%s)" % base if base and item.get("bases") else "")
    return {"kind": kind, "item": item["id"], "name": name, "base": base if item.get("bases") else None, "fixed_base": item.get("base"),
            "tools": magic_tools(item, base, catalog), "days": days, "cost_cp": cost + base_cp, "rarity": item["rarity"],
            "why_cost": "a%s %s magic item%s%s" % ("n" if item["rarity"][0] in "AEIOU" else "", item["rarity"],
                                                  " (a consumable: half the time and cost)" if halved else "",
                                                  " (%s) and the %s it is made from (%s)" % (money(cost), base, money(base_cp))
                                                  if base_cp else "")}


def material(c, spell, bag):
    """A Material component with a cost at hand (an item in the bag that is that thing), as Play live casts it
    (live_general.component). -> (need or None, the bag lines that are it)."""
    import spell_rules
    m = (spell_rules.sheet().get(spell) or {}).get("components") or {}
    if not m.get("m") or not m.get("cost_gp"):
        return None, []
    noun = re.sub(r"^(a|an|some)\s+", "", m.get("material") or "").split(" worth")[0].strip().lower()
    have = [b for b in bag.entries() if int(b.get("qty", 0)) > 0 and noun and noun in str(b.get("name") or b.get("item")).lower()]
    return rq.need("%s (%d+ GP) at hand" % (m["material"], m["cost_gp"]), bool(have),
                   "%s needs %s at hand to scribe %s; %s has none in the bag." % (spell, m["material"], spell, c["name"]),
                   rq.LINKS["market"]), have


# ------------------------------------------------------------------ the checks
class Downtime:
    """One request's view of the party: chars {name: build (with "name")}, the Market, the ledger and the adventure's
    day (sim/rests.py)."""

    def __init__(self, ledger, market, chars, day, fight_running=False, roll=None):
        self.ledger, self.market, self.chars, self.day, self.fight = ledger, market, chars, day, fight_running
        self.roll = roll or (lambda sides: secrets.randbelow(sides) + 1)

    @property
    def catalog(self):
        return self.market.catalog

    def bag(self, name):
        return rq.Bag(name, self.market)

    def when(self):
        import rests
        return rests.clock_text(self.day["hour"]) if self.day else ""

    def calm(self):
        """Downtime waits for a quiet moment: no fight, no rest under way."""
        import rests
        return [rq.need("no fight running", not self.fight, "A fight is running: finish it first.", rests.LINKS["fight"]),
                rq.need("no rest under way", not (self.day or {}).get("rest"), "A rest is under way: finish or stop it first.")]

    def tool_choice(self, shp, req, c):
        """The tool this project uses: the request's, else the first the crafter both carries and is proficient with."""
        opts = shp["tools"]
        want = req.get("tool")
        if want and (want in opts or (not opts and want in srd_tools.TOOLS)):
            return want
        if not opts:
            return None
        bag, prof = self.bag(c["name"]), rq.tool_proficiencies(c)
        return next((t for t in opts if t in prof and bag.count(t)), next((t for t in opts if t in prof), opts[0]))

    def needs(self, req, shp=None):
        """Every prerequisite of the project the request names, in the order the GM meets them. -> (shape, tool, rows)"""
        who = req.get("who")
        c = self.chars.get(who) if isinstance(who, str) else None
        rows = list(self.calm())
        rows.append(rq.need("a character of the party", c is not None, "Choose who makes it: a character of tonight's party."))
        if c is None:
            return None, None, rows
        shp = shp or shape(req, self.catalog)
        busy = self.ledger.busy(who)
        rows.append(rq.need("%s free to work" % who, busy is None, "%s is working on %s: finish or abandon it first." % (
            who, (busy or {}).get("name", "another project")), LINKS["work"]))
        helpers = req.get("helpers") or []
        if not isinstance(helpers, list) or not all(isinstance(h, str) for h in helpers) or len(set(helpers)) != len(helpers):
            raise DowntimeError("Assistants are a list of characters' names.")
        kind, bag = shp["kind"], self.bag(who)
        if helpers and kind in ("brew", "scribe"):
            rows.append(rq.need("no assistants", False, "The SRD gives %s no assistants: one character does it." % (
                "brewing" if kind == "brew" else "scribing")))
        elif helpers:
            rows.append(rq.need("one assistant (the GM may allow more)", len(helpers) <= 1 or req.get("gm_more_helpers") is True,
                                "Normally only one other character can assist; the GM may allow more (tick it)."))
        for h in helpers:
            hb = self.ledger.busy(h)
            rows.append(rq.need("%s in the party" % h, h in self.chars and h != who, "%s is not another character of tonight's "
                                "party." % h))
            rows.append(rq.need("%s free to help" % h, hb is None, "%s is working on %s." % (h, (hb or {}).get("name", "another project"))))
        tool = None
        if kind in ("craft", "brew", "magic"):
            tool = self.tool_choice(shp, req, c)
            if not shp["tools"]:
                rows.append(rq.need("a tool the GM assigns", tool is not None, "The SRD names no tool for %s: the GM assigns one "
                                    "(choose it)." % shp["name"]))
            if tool:
                tname = srd_tools.TOOLS[tool]["name"]
                rows += [rq.in_bag(bag, tool, tname), rq.proficient(c, tname)]
                for h in helpers:
                    if h in self.chars:
                        rows.append(rq.proficient(self.chars[h], tname))
        if kind == "craft":
            rows.append(rq.need("raw materials available (the GM rules)", req.get("gm_materials") is True,
                                "The GM determines whether appropriate raw materials are available: tick it when they are."))
        if kind == "scribe":
            prof = "Arcana" in (c.get("skills") or []) or CALLIGRAPHY in rq.tool_proficiencies(c)
            rows.append(rq.need("proficiency in Arcana or with Calligrapher's Supplies", prof, "%s is proficient neither in "
                                "Arcana nor with Calligrapher's Supplies." % who, rq.LINKS["characters"]))
            rows.append(rq.spell_prepared(c, shp["spell"]))
            rows.append(rq.need("a spellcaster (the scroll uses the scribe's DC and attack)", bool(c.get("spell_dc")),
                                "%s has no spell save DC on the sheet." % who, rq.LINKS["characters"]))
            m, _ = material(c, shp["spell"], bag)
            if m:
                rows.append(m)
        if kind == "magic":
            rows.append(rq.proficient(c, "Arcana"))
            for h in helpers:
                if h in self.chars:
                    rows.append(rq.proficient(self.chars[h], "Arcana"))
            rows.append(rq.need("the spells it casts prepared (the GM checks)", req.get("gm_spells") is True,
                                "If the item lets its user cast spells, the crafter must have them prepared every day of the "
                                "work: the GM checks and ticks it (also when it casts none)."))
            rows.append(rq.need("a city or another settlement", req.get("place") in CHANCE, "Raw materials for a magic item "
                                "are found in a settlement: choose where the party is (a city: 75 percent, another "
                                "settlement: 25)."))
            last = self.last_look(shp["item"], req.get("place"))
            if last is not None:
                import rests
                rows.append(rq.need("%d days since the last look for these materials" % WAIT_DAYS, False,
                                    "These materials were not found here; look again from %s (at least %d days later)." % (
                                        rests.clock_text(last), WAIT_DAYS), LINKS["work"]))
        # a magic item's gold is paid once its materials are found, but it is needed in hand to buy them
        rows.append(rq.gold(self.market.gold(who), shp["cost_cp"], who, shp["why_cost"]))
        return shp, tool, rows

    def plan(self, req):
        shp, tool, rows = self.needs(req)
        ready, rows = rq.check(rows)
        out = {"ready": ready, "needs": rows, "why": rq.first_why(rows), "link": rq.first_link(rows)}
        if shp:
            workers = 1 + len(req.get("helpers") or []) if shp["kind"] in ("craft", "magic") else 1
            out.update(kind=shp["kind"], name=shp["name"], days=shp["days"], cost=money(shp["cost_cp"]), cost_cp=shp["cost_cp"],
                       why_cost=shp["why_cost"], tools=shp["tools"], tool=tool, workers=workers,
                       calendar_days=math.ceil(shp["days"] / workers - 1e-9))
            if shp["kind"] == "magic":
                out["chance"] = CHANCE.get(req.get("place"))
        return out

    # ------------------------------------------------------------------ doing
    def start(self, req):
        shp, tool, rows = self.needs(req)
        ready, rows = rq.check(rows)
        if not ready:
            raise DowntimeError(rq.first_why(rows))
        who, kind = req["who"], shp["kind"]
        helpers = list(req.get("helpers") or []) if kind in ("craft", "magic") else []
        c = self.chars[who]
        p = {"id": secrets.token_hex(5), "kind": kind, "who": who, "helpers": helpers, "item": shp["item"], "name": shp["name"],
             "base": shp.get("base"), "tool": tool, "days": shp["days"], "done": 0, "cost_cp": shp["cost_cp"], "paid": False,
             "status": "working", "started": self.when(), "log": []}
        if kind == "scribe":
            p.update(spell=shp["spell"], level=shp["level"],
                     scribe={"name": who, "dc": int(c.get("spell_dc") or 0), "atk": int(c.get("spell_atk") or 0),
                             "level": int(c.get("level") or 1)})
        lines = []
        if kind == "magic":
            p.update(place=req["place"], chance=CHANCE[req["place"]], rarity=shp["rarity"])
            found, line = self.look(p)
            lines.append(line)
            if found:
                lines.append(self.pay(p))
        else:
            lines.append(self.pay(p))
        self.ledger.load()["projects"].append(p)
        self.ledger.save()
        return p, ["%s starts: %s (%s, %s of work%s)." % (who, p["name"], money(p["cost_cp"]), days_text(p["days"]),
                                                          ", with %s" % " and ".join(helpers) if helpers else "")] + lines

    def pay(self, p):
        self.market.spend(p["who"], p["cost_cp"], "downtime: %s" % p["name"])
        p["paid"] = True
        return "%s pays %s (%s)." % (p["who"], money(p["cost_cp"]), "raw materials" if p["kind"] != "scribe" else "the Spell Scroll Costs table")

    def look(self, p):
        """A magic item's raw materials: d100 against 75 (a city) or 25 (another settlement)."""
        d = self.roll(100)
        found = d <= p["chance"]
        p["status"] = "working" if found else "searching"
        if not found and self.day:
            p["look_at"] = self.day["hour"] + WAIT_DAYS * 24
        line = "Materials for %s in %s: d100 %d against %d -> %s" % (p["name"], PLACES[p["place"]], d, p["chance"],
                                                                  "found" if found else "none now: look again in %d days" % WAIT_DAYS)
        p["log"].append({"when": self.when(), "text": line})
        return found, line

    def last_look(self, item, place):
        """When the materials for this item, not found in this kind of place, can be looked for again (None: now)."""
        if not self.day:
            return None
        times = [p["look_at"] for p in self.ledger.load()["projects"] if p["item"] == item and p.get("place") == place
                 and p.get("look_at") is not None and not p["paid"] and p["look_at"] > self.day["hour"] + 1e-9]
        return max(times) if times else None

    def look_needs(self, p):
        import rests
        rows = list(self.calm())
        rows.append(rq.need("looking for materials", p["status"] == "searching", "%s is not waiting for materials." % p["name"]))
        if self.day and p.get("look_at") is not None:
            rows.append(rq.need("%d days since the last look" % WAIT_DAYS, self.day["hour"] + 1e-9 >= p["look_at"],
                                "The materials can be looked for again from %s (at least %d days after the last look)." % (
                                    rests.clock_text(p["look_at"]), WAIT_DAYS), LINKS["work"]))
        rows.append(rq.need("%s in the party" % p["who"], p["who"] in self.chars, "%s is not in tonight's party." % p["who"]))
        rows.append(rq.gold(self.market.gold(p["who"]), p["cost_cp"], p["who"], "the raw materials for %s" % p["name"]))
        return rows

    def look_again(self, pid):
        p = self.ledger.by_id(pid)
        ready, rows = rq.check(self.look_needs(p))
        if not ready:
            raise DowntimeError(rq.first_why(rows))
        p["chance"] = CHANCE[p["place"]]
        found, line = self.look(p)
        lines = [line] + ([self.pay(p)] if found else [])
        self.ledger.save()
        return lines

    def abandon(self, pid):
        p = self.ledger.by_id(pid)
        if p["status"] not in ("working", "searching"):
            raise DowntimeError("%s is already %s." % (p["name"], p["status"]))
        p["status"] = "abandoned"
        p["log"].append({"when": self.when(), "text": "Abandoned after %s of work%s." % (
            days_text(p["done"]), "; the raw materials are spent" if p["paid"] else "")})
        self.ledger.save()
        return ["%s abandons %s (%s of %s done)%s." % (p["who"], p["name"], days_text(p["done"]), days_text(p["days"]),
                                                      "; the gold paid is spent" if p["paid"] else "")]

    def day_needs(self, p):
        """What each day of work needs again (the tool, the proficiency, the spell prepared, a component at hand)."""
        c = self.chars.get(p["who"])
        if c is None:
            return [rq.need("%s in the party" % p["who"], False, "%s is not in tonight's party." % p["who"])]
        rows = []
        if p.get("tool"):
            tname = srd_tools.TOOLS[p["tool"]]["name"]
            rows += [rq.in_bag(self.bag(p["who"]), p["tool"], tname), rq.proficient(c, tname)]
        if p["kind"] == "scribe":
            rows.append(rq.spell_prepared(c, p["spell"]))
            m, _ = material(c, p["spell"], self.bag(p["who"]))
            if m:
                rows.append(m)
        return rows

    def work_needs(self, days):
        rows = list(self.calm())
        rows.append(rq.need("1 to %d days" % MAX_WORK_DAYS, isinstance(days, int) and not isinstance(days, bool)
                            and 1 <= days <= MAX_WORK_DAYS, "Downtime passes in whole days: 1 to %d." % MAX_WORK_DAYS))
        rows.append(rq.need("the adventure's day", self.day is not None, "Start the adventure first: downtime passes on its day."))
        return rows

    def work(self, days, names):
        """days of downtime: each open project of a crafter in the party gains a day of work for every worker who can
        work (its prerequisites checked again); the clock moves on; each day ends with a Long Rest."""
        import rests
        ready, rows = rq.check(self.work_needs(days))
        if not ready:
            raise DowntimeError(rq.first_why(rows))
        lines = []
        for p in self.ledger.load()["projects"]:
            if p["status"] != "working" or p["who"] not in self.chars:
                continue
            ok, rows = rq.check(self.day_needs(p))
            if not ok:
                why = rq.first_why(rows)
                p["log"].append({"when": self.when(), "text": "No work: %s" % why})
                lines.append("%s: no work on %s (%s)" % (p["who"], p["name"], why))
                continue
            workers = 1 + sum(1 for h in p["helpers"] if h in self.chars)
            before = p["done"]
            p["done"] = min(p["days"], before + days * workers)
            used = math.ceil((p["done"] - before) / workers - 1e-9)
            p["log"].append({"when": self.when(), "text": "%s of work (%d working)." % (days_text(p["done"] - before), workers)})
            if p["done"] + 1e-9 >= p["days"]:
                lines.append(self.finish(p, used))
            else:
                lines.append("%s: %s, %s of %s done" % (p["who"], p["name"], days_text(p["done"]), days_text(p["days"])))
        self.day["hour"] += 24 * days
        rested = [rests._long_benefits(n, self.day["party"][n]) for n in names if n in self.day["party"]]
        self.day["last_long_rest_end"] = self.day["hour"]
        rests.say(self.day, "%d day%s of downtime pass (8 hours of work a day, a Long Rest each night)%s%s" % (
            days, "" if days == 1 else "s", ": " + "; ".join(lines) if lines else "", ". " + " ".join(l + "." for l in rested) if rested else "."))
        self.ledger.save()
        return lines

    def finish(self, p, used):
        who = p["who"]
        p["status"], p["finished"] = "done", self.when()
        if p["kind"] == "scribe":
            s = p["scribe"]
            _, have = material(self.chars[who], p["spell"], self.bag(who))
            import spell_rules
            m = (spell_rules.sheet().get(p["spell"]) or {}).get("components") or {}
            if m.get("consumed") and have:                       # consumed only when the scroll is complete
                self.market.take(who, have[0]["item"], 1, "consumed scribing %s" % p["name"])
            name = "%s, scribed by %s (DC %d, %+d%s)" % (p["name"], s["name"], s["dc"], s["atk"], ", level %d" % s["level"] if not p["level"] else "")
            self.market.give(who, p["item"], 1, "scribed in downtime", name=name[:60])
        else:
            self.market.give(who, p["item"], 1, "made in downtime", base=p.get("base"))
        text = "%s finishes %s (%s into these downtime days): it is in %s's bag" % (who, p["name"], days_text(max(1, used)), who)
        p["log"].append({"when": self.when(), "text": text})
        return text

    # ------------------------------------------------------------------ what the page shows
    def view(self, names):
        import rests
        projects = []
        for p in self.ledger.load()["projects"]:
            if p["who"] not in names and not any(h in names for h in p["helpers"]):
                continue
            v = {k: p.get(k) for k in ("id", "kind", "who", "helpers", "name", "status", "started", "finished", "spell", "place")}
            v.update(kind_name=KINDS[p["kind"]], days=p["days"], done=p["done"], cost=money(p["cost_cp"]), paid=p["paid"],
                     progress="%s of %s" % (days_text(p["done"]), days_text(p["days"])),
                     tool=srd_tools.TOOLS[p["tool"]]["name"] if p.get("tool") else None, log=p["log"][-6:])
            if p["status"] == "working":
                ok, rows = rq.check(self.day_needs(p))
                if not ok:
                    v["blocked"], v["link"] = rq.first_why(rows), rq.first_link(rows)
            if p["status"] == "searching":
                ok, rows = rq.check(self.look_needs(p))
                v["look"] = {"ready": ok, "why": rq.first_why(rows), "link": rq.first_link(rows),
                             "at": rests.clock_text(p["look_at"]) if p.get("look_at") is not None else ""}
            projects.append(v)
        projects.sort(key=lambda v: ({"working": 0, "searching": 1, "done": 2, "abandoned": 3}[v["status"]], v["who"]))
        ok, rows = rq.check(self.work_needs(1))                  # days may pass with no project (waiting for materials)
        return {"projects": projects[:60], "kinds": KINDS, "places": PLACES,
                "work": {"ready": ok, "why": rq.first_why(rows), "link": rq.first_link(rows), "max": MAX_WORK_DAYS},
                "chars": [{"name": n, "gold": money(self.market.gold(n)), "busy": (self.ledger.busy(n) or {}).get("name")}
                          for n in names if n in self.chars]}

    def options(self):
        """What can be made: the craftable SRD items (with their tools), the magic items, each character's spells for a
        scroll, the tools a GM may assign."""
        cat = self.catalog
        idx = srd_tools.craft_index(cat)
        craft = [{"id": i, "name": v["name"], "cost": money(v["cost_cp"]), "tools": [srd_tools.TOOLS[t]["name"] for t in idx.get(i, [])]}
                 for i, v in cat.items() if v["kind"] in CRAFTABLE]
        craft.sort(key=lambda r: (not r["tools"], r["name"]))
        magic = [{"id": i, "name": v["name"], "rarity": v["rarity"], "category": v.get("category", ""), "consumable": bool(v.get("consumable")),
                  "bases": v.get("bases") or []} for i, v in cat.items() if v["kind"] in ("magic", "potion") and i != POTION]
        order = {r: n for n, r in enumerate(MAGIC)}
        magic.sort(key=lambda r: (order.get(r["rarity"], 9), r["name"]))
        spells = {}
        for n, c in self.chars.items():
            spells[n] = sorted(({"name": s, "level": scroll_level(s)} for s in rq.sheet_spells(c) if scroll_level(s) is not None),
                               key=lambda r: (r["level"], r["name"]))
        tools = [{"id": t, "name": v["name"]} for t, v in srd_tools.TOOLS.items()]
        return {"craft": craft, "magic": magic, "spells": spells, "tools": tools,
                "scroll_costs": {str(k): {"days": d, "cost": "%s GP" % format(g, ",")} for k, (d, g) in SCROLL.items()}}


def days_text(d):
    d = round(float(d), 2)
    n = int(d) if d == int(d) else d
    return "%s day%s" % (n, "" if n == 1 else "s")
