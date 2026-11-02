"""GM 2026-10-26 (goals 11 and 13: "Every tool, consumable and process is offered only when its SRD prerequisites are met";
crafting): the SRD 5.2.1 tools, read from the SRD's "Tools" section (Equipment), and what each one crafts.

- Each tool: its Ability, its Utilize uses with their DC, what it can Craft, and the Market's id (sim/srd_market.json).
- Tool Proficiency (SRD 5.2.1): "add your Proficiency Bonus to any ability check you make that uses the tool. If you have
  proficiency in a skill that's used with that check, you have Advantage on the check too." (requirements.tool_check)
- Variants (Gaming Set, Musical Instrument): "Each requires a separate proficiency."
- craft_tools(item): the tools that make a catalog item, from the Craft lines (sim/downtime.py). "The GM assigns required
  tools for items not listed there."
A tool's name on a sheet is matched loosely (curly or straight apostrophe, "Dice" for the Dice Set): names().
"""
import re

AB = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma"}

# id: (name, ability, [(Utilize, DC)], [Craft]) - the SRD 5.2.1 text, in its order
_T = [
    # Artisan's Tools
    ("alchemists-supplies", "Alchemist's Supplies", "int", [("Identify a substance", 15), ("Start a fire", 15)],
     ["Acid", "Alchemist's Fire", "Component Pouch", "Oil", "Paper", "Perfume"]),
    ("brewers-supplies", "Brewer's Supplies", "int", [("Detect poisoned drink", 15), ("Identify alcohol", 10)], ["Antitoxin"]),
    ("calligraphers-supplies", "Calligrapher's Supplies", "dex", [("Write text with impressive flourishes that guard against "
                                                                    "forgery", 15)], ["Ink", "Spell Scroll"]),
    ("carpenters-tools", "Carpenter's Tools", "str", [("Seal or pry open a door or container", 20)],
     ["Club", "Greatclub", "Quarterstaff", "Barrel", "Chest", "Ladder", "Pole", "Portable Ram", "Torch"]),
    ("cartographers-tools", "Cartographer's Tools", "wis", [("Draft a map of a small area", 15)], ["Map"]),
    ("cobblers-tools", "Cobbler's Tools", "dex", [("Modify footwear to give Advantage on the wearer's next Dexterity "
                                                   "(Acrobatics) check", 10)], ["Climber's Kit"]),
    ("cooks-utensils", "Cook's Utensils", "wis", [("Improve food's flavor", 10), ("Detect spoiled or poisoned food", 15)], ["Rations"]),
    ("glassblowers-tools", "Glassblower's Tools", "int", [("Discern what a glass object held in the past 24 hours", 15)],
     ["Glass Bottle", "Magnifying Glass", "Spyglass", "Vial"]),
    ("jewelers-tools", "Jeweler's Tools", "int", [("Discern a gem's value", 15)], ["Arcane Focus", "Holy Symbol"]),
    ("leatherworkers-tools", "Leatherworker's Tools", "dex", [("Add a design to a leather item", 10)],
     ["Sling", "Whip", "Hide Armor", "Leather Armor", "Studded Leather Armor", "Backpack", "Crossbow Bolt Case",
      "Map or Scroll Case", "Parchment", "Pouch", "Quiver", "Waterskin"]),
    ("masons-tools", "Mason's Tools", "str", [("Chisel a symbol or hole in stone", 10)], ["Block and Tackle"]),
    ("painters-supplies", "Painter's Supplies", "wis", [("Paint a recognizable image of something you've seen", 10)],
     ["Druidic Focus", "Holy Symbol"]),
    ("potters-tools", "Potter's Tools", "int", [("Discern what a ceramic object held in the past 24 hours", 15)], ["Jug", "Lamp"]),
    ("smiths-tools", "Smith's Tools", "str", [("Pry open a door or container", 20)],
     ["@melee-but:club,greatclub,quarterstaff,whip", "@armor:medium-but:hide-armor", "@armor:heavy", "Ball Bearings", "Bucket",
      "Caltrops", "Chain", "Crowbar", "Firearm Bullets", "Grappling Hook", "Iron Pot", "Iron Spikes", "Sling Bullets"]),
    ("tinkers-tools", "Tinker's Tools", "dex", [("Assemble a Tiny item composed of scrap, which falls apart in 1 minute", 20)],
     ["Musket", "Pistol", "Bell", "Bullseye Lantern", "Flask", "Hooded Lantern", "Hunting Trap", "Lock", "Manacles", "Mirror",
      "Shovel", "Signal Whistle", "Tinderbox"]),
    ("weavers-tools", "Weaver's Tools", "dex", [("Mend a tear in clothing", 10), ("Sew a Tiny design", 10)],
     ["Padded Armor", "Basket", "Bedroll", "Blanket", "Fine Clothes", "Net", "Robe", "Rope", "Sack", "String", "Tent",
      "Traveler's Clothes"]),
    ("woodcarvers-tools", "Woodcarver's Tools", "dex", [("Carve a pattern in wood", 10)],
     ["Club", "Greatclub", "Quarterstaff", "@ranged-but:pistol,musket,sling", "Arcane Focus", "Arrows", "Bolts", "Druidic Focus",
      "Ink Pen", "Needles"]),
    # Other Tools
    ("disguise-kit", "Disguise Kit", "cha", [("Apply makeup", 10)], ["Costume"]),
    ("forgery-kit", "Forgery Kit", "dex", [("Mimic 10 or fewer words of someone else's handwriting", 15),
                                           ("Duplicate a wax seal", 20)], []),
    ("herbalism-kit", "Herbalism Kit", "int", [("Identify a plant", 10)], ["Antitoxin", "Candle", "Healer's Kit", "Potion of Healing"]),
    ("navigators-tools", "Navigator's Tools", "wis", [("Plot a course", 10), ("Determine position by stargazing", 15)], []),
    ("poisoners-kit", "Poisoner's Kit", "int", [("Detect a poisoned object", 10)], ["Basic Poison"]),
    ("thieves-tools", "Thieves' Tools", "dex", [("Pick a lock", 15), ("Disarm a trap", 15)], []),
]
GAMING = [("dice-set", "Dice Set", ("Dice",)), ("dragonchess-set", "Dragonchess Set", ("Dragonchess",)),
          ("playing-cards", "Playing Cards", ()), ("three-dragon-ante-set", "Three-Dragon Ante Set", ("Three-dragon ante",))]
INSTRUMENTS = ["Bagpipes", "Drum", "Dulcimer", "Flute", "Horn", "Lute", "Lyre", "Pan Flute", "Shawm", "Viol"]

TOOLS = {}
for _id, _name, _ab, _use, _craft in _T:
    TOOLS[_id] = {"id": _id, "name": _name, "ability": _ab, "utilize": [{"what": w, "dc": dc} for w, dc in _use], "craft": _craft,
                  "kind": "artisan" if _id in ("alchemists-supplies", "brewers-supplies", "calligraphers-supplies", "carpenters-tools",
                                               "cartographers-tools", "cobblers-tools", "cooks-utensils", "glassblowers-tools",
                                               "jewelers-tools", "leatherworkers-tools", "masons-tools", "painters-supplies",
                                               "potters-tools", "smiths-tools", "tinkers-tools", "weavers-tools",
                                               "woodcarvers-tools") else "other", "aka": ()}
for _id, _name, _aka in GAMING:
    TOOLS[_id] = {"id": _id, "name": _name, "ability": "wis", "kind": "gaming", "variant_of": "Gaming Set", "craft": [], "aka": _aka,
                  "utilize": [{"what": "Discern whether someone is cheating", "dc": 10}, {"what": "Win the game", "dc": 20}]}
for _name in INSTRUMENTS:
    _id = re.sub(r"[^a-z0-9]+", "-", _name.lower())
    TOOLS[_id] = {"id": _id, "name": _name, "ability": "cha", "kind": "instrument", "variant_of": "Musical Instrument", "craft": [],
                  "aka": (), "utilize": [{"what": "Play a known tune", "dc": 10}, {"what": "Improvise a song", "dc": 15}]}

# The skill "used with that check" (Tool Proficiency's Advantage). Only where the SRD 5.2.1 text names it: a Lock (and
# Manacles) "use Thieves' Tools to pick this Lock with a successful DC 15 Dexterity (Sleight of Hand) check". Elsewhere
# the GM rules which skill applies.
SKILL = {("thieves-tools", "Pick a lock"): "Sleight of Hand", ("thieves-tools", "Disarm a trap"): "Sleight of Hand"}

# Class features that give a tool proficiency, from the SRD 5.2.1 class tables ("Tool Proficiencies"): Druid and Rogue
# name one tool; the Bard (three instruments) and the Monk (one Artisan's Tool or instrument) choose, on the sheet.
CLASS_TOOLS = {"druid": ["herbalism-kit"], "rogue": ["thieves-tools"]}

# A Craft line's name -> the Market's id, where they differ (sim/srd_market.json)
CATALOG_NAMES = {"Glass Bottle": "bottle-glass", "Iron Pot": "pot-iron", "Iron Spikes": "spikes-iron", "Portable Ram": "ram-portable",
                 "Bullseye Lantern": "lantern-bullseye", "Hooded Lantern": "lantern-hooded", "Crossbow Bolt Case": "case-crossbow-bolt",
                 "Map or Scroll Case": "case-map-or-scroll", "Fine Clothes": "clothes-fine", "Traveler's Clothes": "clothes-travelers",
                 "Basic Poison": "poison-basic", "Arrows": "arrows-20", "Bolts": "bolts-20", "Firearm Bullets": "firearm-bullets-10",
                 "Sling Bullets": "sling-bullets-20", "Needles": "blowgun-needles-50"}
GROUPS = {"Arcane Focus": "arcane-focus", "Druidic Focus": "druidic-focus", "Holy Symbol": "holy-symbol"}   # every variant


def norm(name):
    """'Thieves’ Tools' == "thieves' tools"; spaces and case don't matter."""
    return re.sub(r"\s+", " ", str(name or "").replace("’", "'").replace("‘", "'")).strip().casefold()


def names(tid):
    t = TOOLS[tid]
    out = {norm(t["name"])} | {norm(a) for a in t.get("aka", ())}
    if t.get("variant_of"):
        out.add(norm("%s (%s)" % (t["variant_of"], t["name"])))
    return out


def by_name(name):
    """A tool's id from a name on a sheet or in the Market (None when it is not an SRD 5.2.1 tool)."""
    n = norm(name)
    return next((tid for tid in TOOLS if n in names(tid)), None)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("’", "").replace("'", "")).strip("-")


def _expand(line, catalog):
    """A Craft line -> the catalog ids it names."""
    if line.startswith("@"):
        kind, _, but = line[1:].partition("-but:")
        but = set(but.split(",")) if but else set()
        if kind.startswith("armor:"):
            want = kind.split(":", 1)[1].replace("-but", "")
            return [i for i, v in catalog.items() if v.get("kind") == "armor" and v.get("armor") == want and i not in but]
        import character_rules as cr
        melee = {slug(w["name"]) for w in cr.rules()["weapons"] if w.get("kind") == "melee"}
        return [i for i, v in catalog.items() if v.get("kind") == "weapon" and ((i in melee) == (kind == "melee")) and i not in but]
    if line in GROUPS:
        return [i for i in catalog if i.endswith(GROUPS[line])]
    i = CATALOG_NAMES.get(line) or slug(line)
    return [i] if i in catalog else []


_INDEX = {}


def craft_index(catalog):
    """{catalog item id: [tool ids that craft it]} from every tool's Craft line (Potion of Healing and Spell Scroll have
    their own rules: brewing and scribing)."""
    key = id(catalog)
    if key not in _INDEX:
        out = {}
        for tid, t in TOOLS.items():
            for line in t["craft"]:
                if line in ("Potion of Healing", "Spell Scroll"):
                    continue
                for i in _expand(line, catalog):
                    out.setdefault(i, [])
                    if tid not in out[i]:
                        out[i].append(tid)
        _INDEX.clear()
        _INDEX[key] = out
    return _INDEX[key]


def craft_tools(item_id, catalog):
    return list(craft_index(catalog).get(item_id, []))
