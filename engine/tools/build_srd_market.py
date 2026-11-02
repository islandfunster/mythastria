"""MARKET-01 (GM 2026-10-21: "a marketspace activated only by the DM ... equipment, potions, scrolls, magic items"): build
sim/srd_market.json, the SRD 5.2.1 price list the market sells from (sim/market.py).

  py tools/build_srd_market.py SRD_CC_v5.2.1-flow.txt

The input is `pdftotext -enc UTF-8 SRD_CC_v5.2.1.pdf flow.txt` of the official SRD 5.2.1 PDF (CC-BY-4.0), as for
tools/build_srd_character_rules.py. Every price comes from that text:
- adventuring gear and tools: their "Name (cost)" headings in "Equipment"; variants (instruments, gaming sets, foci,
  holy symbols, ammunition) from their tables, each name and cost checked against the text;
- weapons, armor and the Shield: sim/srd_character_rules.json (built from the same PDF);
- magic items: "Magic Items A-Z" (name, category, rarity, attunement) priced by the Magic Item Rarities and Values table:
  Common 100 GP, Uncommon 400, Rare 4,000, Very Rare 40,000, Legendary 200,000; Artifacts are priceless and never sold;
  halved for a consumable other than a Spell Scroll; the cost of the armor or weapon it is made from is added;
- spell scrolls: double the Spell Scroll Costs table (Cantrip 30 GP ... Level 9 100,000 GP), rarity by the Spell Scroll
  table, one scroll for each of the 339 SRD spells.
Nothing else ships (content policy): the GM's own items are added in the market as homebrew.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sim" / "srd_market.json"
RULES = ROOT / "sim" / "srd_character_rules.json"
RARITIES = ["Common", "Uncommon", "Rare", "Very Rare", "Legendary", "Artifact"]
VALUE_GP = {"Common": 100, "Uncommon": 400, "Rare": 4000, "Very Rare": 40000, "Legendary": 200000}
SCRIBE_GP = [15, 25, 100, 150, 1000, 1500, 10000, 12500, 15000, 50000]          # Spell Scroll Costs, cantrip..9
SCROLL_RARITY = ["Common", "Common", "Uncommon", "Uncommon", "Rare", "Rare", "Very Rare", "Very Rare", "Very Rare", "Legendary"]
COIN = {"CP": 1, "SP": 10, "EP": 50, "GP": 100, "PP": 1000}
CATEGORIES = ("Armor", "Weapon", "Wondrous Item", "Potion", "Ring", "Rod", "Scroll", "Staff", "Wand")
# Tools are their own kind; the rest of the "Name (cost)" headings between Tools and Mounts are adventuring gear.
TOOL_WORDS = ("Supplies", "Tools", "Utensils", "Kit")
# Variants priced in tables (name, cost text): each pair is checked against the PDF text before it is written.
VARIANTS = {
    "tool": [("Dice Set", "1 SP", "Dice (1 SP)"), ("Dragonchess Set", "1 GP", "dragonchess (1 GP)"),
             ("Playing Cards", "5 SP", "playing cards||(5 SP)"), ("Three-Dragon Ante Set", "1 GP", "three-dragon ante (1 GP)"),
             ("Bagpipes", "30 GP", "Bagpipes (30 GP"), ("Drum", "6 GP", "drum (6 GP"), ("Dulcimer", "25 GP", "cimer (25 GP"),
             ("Flute", "2 GP", "flute (2 GP"), ("Horn", "3 GP", "horn (3 GP"), ("Lute", "35 GP", "lute (35 GP"),
             ("Lyre", "30 GP", "lyre (30 GP"), ("Pan Flute", "12 GP", "pan flute (12 GP"), ("Shawm", "2 GP", "shawm (2 GP"),
             ("Viol", "30 GP", "viol (30 GP")],
    "ammunition": [("Arrows (20)", "1 GP", None), ("Bolts (20)", "1 GP", None), ("Firearm Bullets (10)", "3 GP", None),
                   ("Sling Bullets (20)", "4 CP", None), ("Blowgun Needles (50)", "1 GP", None)],
    "focus": [("Crystal (Arcane Focus)", "10 GP", None), ("Orb (Arcane Focus)", "20 GP", None), ("Rod (Arcane Focus)", "10 GP", None),
              ("Staff (Arcane Focus)", "5 GP", None), ("Wand (Arcane Focus)", "10 GP", None),
              ("Sprig of Mistletoe (Druidic Focus)", "1 GP", None), ("Wooden Staff (Druidic Focus)", "5 GP", None),
              ("Yew Wand (Druidic Focus)", "10 GP", None), ("Amulet (Holy Symbol)", "5 GP", None),
              ("Emblem (Holy Symbol)", "5 GP", None), ("Reliquary (Holy Symbol)", "5 GP", None)],
}
# The tables those come from, as pdftotext lays them out (the builder fails if the SRD text differs)
TABLE_CHECKS = ["Type Arrows Bolts Bullets, Firearm Bullets, Sling Needles", "Amount 20 20 10 20 50", "Cost 1 GP 1 GP 3 GP 4 CP 1 GP",
                "Focus Crystal Orb Rod Staff (also a Quarterstaff) Wand", "Cost 10 GP 20 GP 10 GP 5 GP 10 GP",
                "Focus Sprig of mistletoe Wooden staff (also a Quarterstaff) Yew wand", "Cost 1 GP 5 GP 10 GP",
                "Symbol Amulet (worn or held) Emblem (borne on fabric or a Shield) Reliquary (held)", "Cost 5 GP 5 GP 5 GP",
                "Spell Scroll (Cantrip, 30 GP; Level 1, 50 GP)", "Cost 15 GP 25 GP 100 GP 150 GP 1,000 GP 1,500 GP 10,000 GP 12,500 GP 15,000 GP 50,000 GP",
                "Rarity Common Common Uncommon Uncommon", "Rarity Rare Rare Very Rare Very Rare Very Rare Legendary",
                "Common||100 GP Very Rare||Uncommon||400 GP Legendary||Rare||4,000 GP Artifact||Value* 40,000 GP 200,000 GP",
                "Halve the value for a consumable item other than a Spell Scroll",
                "add that item’s cost to the magic item’s value"]
# Items whose rarity "varies": their kinds and rarities, read from each item's own table in the text
VARIES = {
    "Belt of Giant Strength": [("hill", "Rare"), ("frost", "Very Rare"), ("stone", "Very Rare"), ("fire", "Very Rare"),
                               ("cloud", "Legendary"), ("storm", "Legendary")],
    "Potion of Giant Strength": [("hill", "Uncommon"), ("frost", "Rare"), ("stone", "Rare"), ("fire", "Rare"),
                                 ("cloud", "Very Rare"), ("storm", "Legendary")],
    "Potions of Healing": [(None, "Common"), ("greater", "Uncommon"), ("superior", "Rare"), ("supreme", "Very Rare")],
}
VARIES_CHECKS = ["Belt of Giant Strength (hill) Belt of Giant Strength (frost or stone) Belt of Giant Strength (fire) Belt of Giant "
                 "Strength (cloud) Belt of Giant Strength (storm)||Str. Rarity 21 Rare 23 Very Rare|25 Very Rare 27 Legendary 29 Legendary",
                 "Potion of Giant Strength (hill)||21 Uncommon||Potion of Giant Strength (frost or stone)||23 Rare||Potion of Giant "
                 "Strength (fire)||25 Rare||Potion of Giant Strength (cloud)||27 Very Rare||Potion of Giant Strength (storm)||29 Legendary",
                 "Potion of Healing||2d4 + 2||Common||Potion of Healing (greater)||4d4 + 4||Uncommon||Potion of Healing (superior)||8d4 + 8"]
SUB_ENTRIES = ("Feather Token", "Figurine of Wondrous Power", "Ioun Stone")   # "Kind (Rarity)." paragraphs in the item


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("’", "")).strip("-")


def cp(text):
    m = re.fullmatch(r"([\d,]+) (CP|SP|EP|GP|PP)", text.strip())
    if not m:
        raise ValueError("Not a cost: %r" % text)
    return int(m.group(1).replace(",", "")) * COIN[m.group(2)]


def flat(text):
    return "|".join(text.splitlines())


def gear(lines, text):
    """Adventuring gear and tools: every "Name (cost)" heading from Artisan's Tools to Mounts and Vehicles."""
    start = next(i for i, l in enumerate(lines) if l.startswith("Alchemist’s Supplies (50 GP)"))
    end = next(i for i, l in enumerate(lines) if i > start and l.strip() == "Mounts and Vehicles")
    out, head = [], re.compile(r"^([A-Z][A-Za-z’', -]+?) \(([\d,]+ (?:CP|SP|EP|GP|PP))\)$")
    for l in lines[start:end]:
        m = head.match(l.strip())
        if not m:
            continue
        name = m.group(1)
        if name.startswith(("Potion of Healing", "Spell Scroll")):     # priced as magic items below
            continue
        kind = "tool" if name.endswith(TOOL_WORDS) and name not in ("Climber’s Kit", "Healer’s Kit") else "gear"
        out.append({"name": name, "kind": kind, "cost_cp": cp(m.group(2))})
    for kind, rows in VARIANTS.items():
        for name, cost, where in rows:
            if where and where not in flat(text):
                raise SystemExit("SRD text check failed for %s: %r not found" % (name, where))
            out.append({"name": name, "kind": kind, "cost_cp": cp(cost)})
    return out


def arms(rules):
    out = [{"name": w["name"], "kind": "weapon", "cost_cp": round(w["cost"] * 100), "weapon": w["category"]} for w in rules["weapons"]]
    out += [{"name": a["name"], "kind": "armor", "cost_cp": round(a["cost"] * 100), "armor": a["category"]} for a in rules["armor"]]
    out.append({"name": "Shield", "kind": "armor", "cost_cp": round(rules["shield"]["cost"] * 100), "armor": "shield"})
    return out


def bases(category, rules):
    """The equipment a magic weapon or armor is made from: (names it may be, the one named if only one)."""
    m = re.match(r"(Armor|Weapon) \((.*)\)$", category)
    if not m:
        return []
    kind, inner = m.groups()
    weapons, armor = rules["weapons"], rules["armor"]
    if inner == "Any Ammunition":
        return []                                                  # a single arrow or bolt: no cost to add
    if inner == "Any Simple or Martial":
        return [w["name"] for w in weapons]
    if inner == "Any Melee Weapon":
        return [w["name"] for w in weapons if w["kind"] == "melee"]
    if inner == "Any Light, Medium, or Heavy":
        return [a["name"] for a in armor]
    if inner == "Any Medium or Heavy, Except Hide Armor":
        return [a["name"] for a in armor if a["category"] in ("medium", "heavy") and a["name"] != "Hide Armor"]
    if inner == "Shield":
        return ["Shield"]
    names = [n.strip() for n in re.split(r",\s*(?:or\s+)?|\s+or\s+", inner) if n.strip()]
    known = {w["name"] for w in weapons} | {a["name"] for a in armor}
    names = [{"Chain Mail": "Chain Mail"}.get(n, n) for n in names]
    missing = [n for n in names if n not in known]
    if missing:
        raise SystemExit("Unknown base %s in %r" % (missing, category))
    return names


def magic(lines, text, rules):
    start = next(i for i, l in enumerate(lines) if l.strip() == "Magic Items A–Z")
    cat = re.compile(r"^(%s)( \([^)]*\))?, (.*)$" % "|".join(CATEGORIES))
    rar = re.compile(r"^(Common|Uncommon|Rare|Very Rare|Legendary|Artifact|Rarity Varies)\b")
    found, n = [], 0
    for i in range(start, len(lines)):
        m = cat.match(lines[i].strip())
        if not m or not rar.match(m.group(3)):
            continue
        name = lines[i - 1].strip()
        if not name:
            raise SystemExit("No name above %r (line %d)" % (lines[i], i + 1))
        category = (m.group(1) + (m.group(2) or "")).strip()
        rest = m.group(3)
        att = re.search(r"\(Requires Attunement(?: by an? ([^)]*))?\)", rest)
        who = [w.strip() for w in re.split(r",\s*(?:or\s+)?|\s+or\s+", att.group(1) or "") if w.strip()] if att else []
        who = [w[2:] if w.startswith("a ") else w for w in who]
        body = "\n".join(lines[i + 1:i + 60])
        found.append({"name": name, "category": category, "rarity_text": re.sub(r"\s*\(Requires Attunement[^)]*\)", "", rest).strip(),
                      "attunement": bool(att), "attune_by": who, "body": body})
        n += 1
    out = []
    for f in found:
        variants = []
        r = f["rarity_text"]
        if f["name"] == "Spell Scroll":
            continue                                                # one scroll per spell, below
        plus = re.findall(r"(Uncommon|Rare|Very Rare|Legendary) \(\+(\d)\)", r)
        horn = re.findall(r"(Rare|Very Rare|Legendary) \(([A-Za-z ]+)\)", r) if not plus else []
        if plus:
            base = re.sub(r",? \+1, \+2, or \+3$", "", f["name"])
            variants = [("%s, +%s" % (base, k), v) for v, k in plus]
        elif horn:
            for v, kinds in horn:
                variants += [("%s (%s)" % (f["name"], k.strip().lower()), v) for k in kinds.split(" or ")]
        elif r.startswith("Rarity Varies"):
            if f["name"] in VARIES:
                single = "Potion of Healing" if f["name"] == "Potions of Healing" else f["name"]
                variants = [(single if k is None else "%s (%s)" % (single, k), v) for k, v in VARIES[f["name"]]]
            elif f["name"] in SUB_ENTRIES:
                subs = re.findall(r"^([A-Z][A-Za-z ]+) \((Uncommon|Rare|Very Rare|Legendary)\)\.", f["body"], re.M)
                variants = [("%s (%s)" % (f["name"], k.lower()), v) for k, v in subs]
            if not variants:
                raise SystemExit("No rarity table read for %s" % f["name"])
        else:
            variants = [(f["name"], r.split(" (")[0].strip())]
        for name, rarity in variants:
            if rarity not in RARITIES:
                raise SystemExit("Unknown rarity %r for %s" % (rarity, name))
            if rarity == "Artifact":
                continue                                            # priceless: never in a shop
            consumable = f["category"] == "Potion" or "Ammunition" in f["category"]
            value = VALUE_GP[rarity] * 100 // (2 if consumable else 1)
            choices = bases(f["category"], rules)
            item = {"name": name, "kind": "potion" if f["category"] == "Potion" else "magic", "category": f["category"],
                    "rarity": rarity, "cost_cp": value, "attunement": f["attunement"]}
            if f["attune_by"]:
                item["attune_by"] = f["attune_by"]
            if consumable:
                item["consumable"] = True
            if len(choices) == 1:                                   # made from one named armor or weapon: its cost is added
                item["base"] = choices[0]
            elif choices:
                item["bases"] = choices                             # the GM picks which when stocking it
            out.append(item)
    return out, n


def scrolls(rules):
    out = []
    for s in rules["spells"]:
        lv = s["level"]
        out.append({"name": "Spell Scroll (%s)" % s["name"], "kind": "scroll", "spell": s["name"], "level": lv,
                    "classes": s["classes"], "rarity": SCROLL_RARITY[lv], "cost_cp": SCRIBE_GP[lv] * 2 * 100,
                    "consumable": True})
    return out


# SPELL-OBJECTS-01 (GM 2026-10-27, "Gold dust in the Market"): a Material component priced in an SRD spell's own text,
# sold like gear (the SRD's equipment tables don't list it): Arcane Lock's "gold dust worth 25+ GP, which the spell
# consumes".
COMPONENTS = [{"name": "Gold Dust", "kind": "gear", "cost_cp": 2500,
               "note": "Arcane Lock's Material component (SRD 5.2.1: gold dust worth 25+ GP, which the spell consumes)"},
              # group 2 (GM 2026-10-27): the other costly components of spells the engine plays
              {"name": "Diamond", "kind": "gear", "cost_cp": 5000,
               "note": "Chromatic Orb's Material component (SRD 5.2.1: a diamond worth 50+ GP; not consumed)"},
              {"name": "Black Pearl", "kind": "gear", "cost_cp": 50000,
               "note": "Circle of Death's Material component (SRD 5.2.1: the powder of a crushed black pearl worth 500+ GP; not consumed)"},
              {"name": "Ruby Dust", "kind": "gear", "cost_cp": 5000,
               "note": "Continual Flame's Material component (SRD 5.2.1: ruby dust worth 50+ GP, which the spell consumes)"},
              # SPELL-BATCH-01 (GM 2026-10-28): Revivify's diamond
              {"name": "Diamond (300 GP)", "kind": "gear", "cost_cp": 30000,
               "note": "Revivify's Material component (SRD 5.2.1: a diamond worth 300+ GP, which the spell consumes)"}]


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        raise SystemExit(__doc__)
    text = Path(argv[0]).read_text(encoding="utf-8")
    lines = text.splitlines()
    for check in TABLE_CHECKS + VARIES_CHECKS:
        if check not in flat(text):
            raise SystemExit("SRD text check failed: %r not found" % check)
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    eq = gear(lines, text) + arms(rules)
    cost = {e["name"]: e["cost_cp"] for e in eq}
    mi, read = magic(lines, text, rules)
    for item in mi:
        if item.get("base"):
            item["cost_cp"] += cost[item["base"]]
    items = eq + COMPONENTS + mi + scrolls(rules)
    seen = set()
    for item in items:
        item["id"] = slug(item["name"])
        if item["id"] in seen:
            raise SystemExit("Two items named %s" % item["name"])
        seen.add(item["id"])
    out = {"format": "mythastria-market-srd/1", "version": "SRD 5.2.1",
           "about": "SRD 5.2.1 equipment, magic items and spell scrolls with their prices, for the Mythastria market "
                    "(sim/market.py). Built by tools/build_srd_market.py from the official SRD 5.2.1 PDF; CC-BY-4.0, see the "
                    "SRD's attribution. Only SRD 5.2.1 content: anything else is the GM's homebrew.",
           "rules": {"rarity_value_gp": VALUE_GP, "artifact": "priceless (never sold)",
                     "consumable": "half the rarity value, except a Spell Scroll",
                     "spell_scroll": "double the scribing cost: " + ", ".join("%s %s GP" % ("Cantrip" if i == 0 else "Level %d" % i, 2 * c)
                                                                                for i, c in enumerate(SCRIBE_GP)),
                     "made_from_equipment": "the armor's or weapon's own cost is added",
                     "selling": "Equipment fetches half its cost when sold (SRD 5.2.1, Selling Equipment)"},
           "items": [{k: item[k] for k in ["id"] + [k for k in item if k != "id"]} for item in items]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    kinds = {}
    for item in items:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    print("%s: %d items %s; %d magic item entries read" % (OUT, len(items), kinds, read))


if __name__ == "__main__":
    main()
