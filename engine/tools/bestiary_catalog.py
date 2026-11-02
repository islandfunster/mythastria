"""CATALOG-01 (2026-10-14): a bestiary catalogue for choosing creatures by theme, setting, tone, tactics and level.

  py tools/bestiary_catalog.py build                    # the SRD 5.2.1 bestiary
  py tools/bestiary_catalog.py query --theme aquatic --habitat Coastal --level 1 --tone family [--role skirmisher]
                                     [--type undead] [--behaviour tactician] [--cr 0-2] [--limit 40]
  py tools/bestiary_catalog.py html                     # a local page with filters (opens in a browser)
  py tools/bestiary_catalog.py export-srd FILE          # the SRD-only part (shareable, with the SRD attribution)

Source: the FG module DNDSRD521BESTIARY (SRD 5.2.1, CC-BY-4.0) only. The paid bestiary is not used (GM decision
2026-10-14, DECISIONS.md SRD-ONLY-MONSTERS). The catalogue is written to mythastria_core/cache/catalog/ (never
committed); export-srd writes it with the SRD attribution.

Each creature gets, besides its stat line (CR, XP, type, size, speeds, senses, Intelligence, Wisdom):
  habitat    the stat block's own habitat list (2024 books), e.g. Coastal, Underdark, Planar (...)
  treasure   its treasure tags (Arcana, Armaments, Implements, Individual, Relics, Any)
  themes     what it is about: its type, plus aquatic, flying, fire, poison, spellcaster, ambusher, pack, ... (THEMES)
  roles      how it fights: brute, soldier, artillery, skirmisher, controller, lurker, leader, solo (role_tags)
  tone       family < spooky < dark < mature, with the words that raised it (tone); a GM override file wins
  behaviour  the GM's Intelligence/Wisdom quadrant (2026-10-14 discussion): relentless, instinct-wary, clever-rash,
             tactician, with the Int and Wis bands
  levels     with a party of 4 (2024 XP budget): the lowest level at which one of it is a Moderate encounter, the level
             at which four of them are, and whether its CR is above the party level (SRD 5.2.1 "Powerful Creatures")
Heuristics are listed with their reasons so the GM can see why a tag was given.
"""
import os
import argparse, html, json, re, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FG = Path(os.environ.get("MYTHASTRIA_FG_DIR") or Path(os.environ.get("APPDATA", "")) / "SmiteWorks" / "Fantasy Grounds")   # FG's own data (the SRD modules)
SRD_MODULE = FG / "modules" / "DNDSRD521BESTIARY.mod"
SRD_RECORDS = ROOT / "sim" / "creatures" / "srd_records.json"   # RELEASE-01: what play needs, shipped: nothing is read from outside
OUT = ROOT / "mythastria_core" / "cache" / "catalog"
OVERRIDES = OUT / "tone_overrides.json"          # {"Creature name": "family" | "spooky" | "dark" | "mature"}
SRD_ATTRIBUTION = ('This work includes material from the System Reference Document 5.2.1 ("SRD 5.2.1") by Wizards of '
                   'the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the '
                   'Creative Commons Attribution 4.0 International License, available at '
                   'https://creativecommons.org/licenses/by/4.0/legalcode.')

# 2024 encounter building: XP budget per character (Low, Moderate, High) by party level; the SRD 5.2.1 examples agree
XP_BUDGET = {1: (50, 75, 100), 2: (100, 150, 200), 3: (150, 225, 400), 4: (250, 375, 500), 5: (500, 750, 1100),
             6: (600, 1000, 1400), 7: (750, 1300, 1700), 8: (1000, 1700, 2100), 9: (1300, 2000, 2600),
             10: (1600, 2300, 3100), 11: (1900, 2900, 4100), 12: (2200, 3700, 4700), 13: (2600, 4200, 5400),
             14: (2900, 4900, 6200), 15: (3300, 5400, 7800), 16: (3800, 6100, 9800), 17: (4500, 7200, 11700),
             18: (5000, 8700, 14200), 19: (5500, 10700, 17200), 20: (6400, 13200, 22000)}
# CR -> XP (the stat-block XP for each Challenge Rating); used when a record carries no XP (the 2024 animals)
CR_XP = {0: 10, 0.125: 25, 0.25: 50, 0.5: 100, 1: 200, 2: 450, 3: 700, 4: 1100, 5: 1800, 6: 2300, 7: 2900, 8: 3900,
         9: 5000, 10: 5900, 11: 7200, 12: 8400, 13: 10000, 14: 11500, 15: 13000, 16: 15000, 17: 18000, 18: 20000,
         19: 22000, 20: 25000, 21: 33000, 22: 41000, 23: 50000, 24: 62000, 25: 75000, 26: 90000, 27: 105000,
         28: 120000, 29: 135000, 30: 155000}
TONES = ["family", "spooky", "dark", "mature"]
CONDITIONS = ("blinded", "charmed", "deafened", "frightened", "grappled", "incapacitated", "paralyzed", "petrified",
              "poisoned", "prone", "restrained", "stunned", "unconscious")


# ------------------------------------------------------------------ reading the sources
def _xml_value(el):
    kids = list(el)
    if not kids:
        return (el.text or "").strip()
    return {k.tag: _xml_value(k) for k in kids}


def srd_records(path=SRD_RECORDS):
    """The SRD 5.2.1 numbers play needs (XP, CR, hit dice, saves, damage defenses), as load_srd's records, from the file
    that ships with Mythastria. Play reads this, so every PC gets the same rules."""
    return json.loads(Path(path).read_text(encoding="utf-8"))["records"]


def write_srd_records(path=SRD_RECORDS):
    """sim/creatures/srd_records.json, rebuilt from the module: numbers and defenses only, no stat-block text."""
    keep = ("cr", "xp", "hd", "damageimmunities", "damageresistances", "damagevulnerabilities")
    records = []
    for r in sorted(load_srd(), key=lambda r: r["name"]):
        f = r["fields"]
        fields = {k: f[k] for k in keep if f.get(k)}
        fields["abilities"] = {ab: {k: v[k] for k in ("bonus", "savemodifier") if k in v}
                               for ab, v in (f.get("abilities") or {}).items() if isinstance(v, dict)}
        records.append({"name": r["name"], "source": "srd", "fields": fields})
    if len(records) < 300:
        raise SystemExit("The SRD module wasn't read: %d records." % len(records))
    Path(path).write_text(json.dumps({"attribution": SRD_ATTRIBUTION, "records": records}, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(records)


def load_srd(path=SRD_MODULE):
    """SRD 5.2.1 bestiary records from the FG module: [{"name", "source": "srd", "fields": {...}}]. Only the tools that
    rebuild the shipped files read it; play reads srd_records()."""
    if not Path(path).exists():
        return []
    z = zipfile.ZipFile(path)
    out = []
    for n in z.namelist():
        if not n.endswith(".xml") or n == "definition.xml":
            continue
        root = ET.fromstring(z.read(n))
        for npc in root.iter("npc"):
            for rec in npc.iter():
                if rec.tag.startswith("id-") and rec.find("abilities") is not None and rec.find("name") is not None:
                    out.append({"name": rec.findtext("name", "").strip(), "source": "srd", "fields": _xml_value(rec),
                                "id": rec.tag})   # 2026-10-18: the FG record id (npc.<id>@DNDSRD521BESTIARY)
    seen, uniq = set(), []
    for r in out:
        if r["name"] not in seen:
            seen.add(r["name"]); uniq.append(r)
    return uniq


def cr_value(cr):
    s = str(cr or "").strip()
    if "/" in s:
        a, b = s.split("/", 1)
        return int(a) / int(b) if a.isdigit() and b.isdigit() else None
    try:
        return float(s)
    except ValueError:
        return None


def speeds(text):
    """'30 ft., fly 60 ft. (hover), swim 40 ft.' -> {"walk": 30, "fly": 60, "swim": 40, "hover": True}."""
    s = str(text or "").lower()
    out = {}
    m = re.match(r"\s*(\d+)\s*ft", s)
    if m:
        out["walk"] = int(m.group(1))
    for kind in ("fly", "swim", "climb", "burrow"):
        m = re.search(kind + r"\s+(\d+)\s*ft", s)
        if m:
            out[kind] = int(m.group(1))
    if "hover" in s:
        out["hover"] = True
    return out


def senses(text):
    s = str(text or "").lower()
    return {k: int(m.group(1)) for k in ("darkvision", "blindsight", "tremorsense", "truesight")
            for m in [re.search(k + r"\s+(\d+)", s)] if m}


def split_list(text):
    """'Mountain, Planar (Elemental Plane of Air, Plane of Water)' -> top-level comma split, parentheses kept."""
    out, depth, cur = [], 0, ""
    for ch in str(text or ""):
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return [x for x in out if x]


def score(fields, ability):
    a = (fields.get("abilities") or {}).get(ability) or {}
    try:
        return int(a.get("score")) if isinstance(a, dict) else None
    except (TypeError, ValueError):
        return None


def blocks(fields):
    """All trait/action texts: [(section, name, desc)]."""
    out = []
    for sec in ("traits", "actions", "bonusactions", "reactions", "legendaryactions", "lairactions"):
        for v in (fields.get(sec) or {}).values() if isinstance(fields.get(sec), dict) else []:
            if isinstance(v, dict):
                out.append((sec, str(v.get("name") or ""), str(v.get("desc") or "")))
    return out


def normalise(rec):
    f = rec["fields"]
    typ = str(f.get("type") or "")
    base = re.split(r"[\s(,]", typ.strip().lower())[0] if typ.strip() else ""
    crv = cr_value(f.get("cr"))
    xp = int(f.get("xp") or 0) if str(f.get("xp") or "0").isdigit() else 0
    habitat = split_list(f.get("habitat"))
    sp = speeds(f.get("speed"))
    if not habitat and sp.get("swim"):
        habitat = ["Coastal (inferred: swims; no habitat listed)"]   # the 2024 animals list no habitat
    return {"name": rec["name"], "source": rec["source"], "cr": str(f.get("cr") or ""), "cr_value": crv,
            "xp": xp or CR_XP.get(crv, 0), "xp_from_cr": not xp and crv in CR_XP,
            "type": typ, "type_base": base, "size": str(f.get("size") or ""), "alignment": str(f.get("alignment") or ""),
            "ac": str(f.get("ac") or ""), "hp": int(f.get("hp") or 0) if str(f.get("hp") or "0").isdigit() else 0,
            "speed": sp, "senses": senses(f.get("senses")),
            "int": score(f, "intelligence"), "wis": score(f, "wisdom"),
            "habitat": habitat, "treasure": split_list(f.get("treasure")),
            "languages": str(f.get("languages") or ""), "skills": str(f.get("skills") or ""),
            "immunities": str(f.get("damageimmunities") or "").lower(),
            "legendary": bool(f.get("legendaryactions")), "lair": bool(f.get("lairactions")),
            "_blocks": blocks(f)}


# ------------------------------------------------------------------ the tags
def _text(c):
    return " ".join((n + " " + d) for _, n, d in c["_blocks"]).lower()


THEMES = [   # (theme, test) — test(c, text) -> reason or None
    ("aquatic", lambda c, t: "swim speed" if c["speed"].get("swim") else
                             ("habitat " + h for h in c["habitat"] if h.split(" (")[0] in ("Underwater", "Coastal")).__next__()
                             if any(h.split(" (")[0] in ("Underwater", "Coastal") for h in c["habitat"]) else
                             ("amphibious" if "amphibious" in t else None)),
    ("flying", lambda c, t: "fly speed" if c["speed"].get("fly") else None),
    ("burrower", lambda c, t: "burrow speed" if c["speed"].get("burrow") else None),
    ("underground", lambda c, t: "Underdark" if any(h.startswith("Underdark") for h in c["habitat"]) else
                                 ("tremorsense" if c["senses"].get("tremorsense") else None)),
    ("fire", lambda c, t: "fire damage" if "fire damage" in t or "fire" in c["immunities"] else None),
    ("cold", lambda c, t: "cold damage" if "cold damage" in t or "cold" in c["immunities"] else None),
    ("storm", lambda c, t: "lightning/thunder" if "lightning damage" in t or "thunder damage" in t else None),
    ("poison", lambda c, t: "poison" if "poison damage" in t or "poisoned condition" in t else None),
    ("necrotic", lambda c, t: "necrotic damage" if "necrotic damage" in t else None),
    ("psychic", lambda c, t: "psychic damage" if "psychic damage" in t else None),
    ("radiant", lambda c, t: "radiant damage" if "radiant damage" in t else None),
    ("acid", lambda c, t: "acid damage" if "acid damage" in t else None),
    ("spellcaster", lambda c, t: "Spellcasting" if "spellcasting" in t or "casts one of the following spells" in t else None),
    ("shapechanger", lambda c, t: "shape-shifts" if "shape-shift" in t or "shapechanger" in c["type"].lower() else None),
    ("pack", lambda c, t: "Pack Tactics" if "pack tactics" in t else None),
    ("ambusher", lambda c, t: "stealthy" if re.search(r"stealth \+([5-9]|\d\d)", c["skills"].lower()) or
                              "false appearance" in t or "invisib" in t else None),
    ("grappler", lambda c, t: "grapples" if "grappled condition" in t or "grapple" in t else None),
    ("swallower", lambda c, t: "swallows" if "swallow" in t else None),
    ("charmer", lambda c, t: "charms" if "charmed condition" in t else None),
    ("fearsome", lambda c, t: "frightens" if "frightened condition" in t else None),
    ("paralyzing", lambda c, t: "paralyzes" if "paralyzed condition" in t or "petrified condition" in t else None),
    ("regenerating", lambda c, t: "regenerates" if "regenerat" in t else None),
    ("swarm", lambda c, t: "swarm" if c["name"].lower().startswith("swarm") or "swarm of" in c["type"].lower() else None),
    ("legendary", lambda c, t: "legendary actions" if c["legendary"] else None),
    ("lair", lambda c, t: "lair actions" if c["lair"] else None),
]


def themes(c, t=None):
    t = _text(c) if t is None else t
    out = {}
    if c["type_base"]:
        out[c["type_base"]] = "creature type"
    for name, test in THEMES:
        try:
            why = test(c, t)
        except StopIteration:
            why = None
        if why:
            out[name] = why
    return out


def role_tags(c, t=None):
    """How it fights (first = main role). Heuristics with their reasons."""
    t = _text(c) if t is None else t
    melee, ranged = "melee attack roll" in t, "ranged attack roll" in t or bool(re.search(r"range \d+ ft", t))
    try:
        ac = int(re.match(r"\d+", c["ac"]).group(0))
    except (AttributeError, ValueError):
        ac = 10
    cr = c["cr_value"] or 0.0
    roles = {}
    if c["legendary"]:
        roles["solo"] = "legendary actions"
    conds = [x for x in CONDITIONS if x + " condition" in t]
    if len(conds) >= 2 or (conds and "saving throw" in t and not melee):
        roles["controller"] = "imposes " + ", ".join(conds)
    if ranged and (not melee or t.count("ranged attack roll") > t.count("melee attack roll")):
        roles["artillery"] = "fights at range"
    fast = max([v for k, v in c["speed"].items() if k != "hover"] or [0])
    if fast >= 40 or "disengage" in t or "nimble escape" in t or "flyby" in t:
        roles["skirmisher"] = "mobile (%d ft%s)" % (fast, ", disengages" if "disengage" in t else "")
    if "ambusher" in themes(c, t):
        roles["lurker"] = "stealth or invisibility"
    lead = t.replace("pack tactics", "")          # Pack Tactics helps itself, not its allies
    if "leadership" in lead or re.search(r"(command|rally|inspir|bolster)\w*[^.]{0,80}\ball(y|ies)\b", lead) or \
            re.search(r"\ball(y|ies)\b[^.]{0,60}(gains?|adds?) (a |an )?(bonus|advantage|temporary hit points)", lead):
        roles["leader"] = "helps its allies"
    if melee and ac >= 16:
        roles["soldier"] = "melee, AC %d" % ac
    if melee and c["hp"] >= 15 + 15 * cr and ac <= 14:
        roles["brute"] = "melee, %d HP for CR %s" % (c["hp"], c["cr"])
    if not roles and melee:
        roles["melee"] = "plain melee (no stronger role)"
    return roles


TONE_WORDS = {   # (tone, words): the highest matching tone wins; the reasons are kept
    "spooky": ["ghost", "haunt", "skeleton", "zombie", "web", "spider", "frightened condition", "shadow", "wail"],
    "dark": ["corpse", "flesh", "blood", "devour", "torment", "brain", "disease", "rot", "curse", "drain", "possess",
             "soul", "fiend"],
    "mature": ["implant", "larva", "flay", "torture", "sacrifice", "extract", "eggs in"],
}
TYPE_TONE = {"undead": "spooky", "fiend": "dark", "aberration": "dark"}


def tone(c, t=None, overrides=None):
    t = _text(c) if t is None else t
    level, why = "family", []
    def raise_to(lv, reason):
        nonlocal level
        if TONES.index(lv) > TONES.index(level):
            level = lv
        why.append(reason)
    if c["type_base"] in TYPE_TONE:
        raise_to(TYPE_TONE[c["type_base"]], "type " + c["type_base"])
    blob = (c["name"] + " " + t).lower()
    for lv in ("spooky", "dark", "mature"):
        for w in TONE_WORDS[lv]:
            if w in blob:
                raise_to(lv, '"%s"' % w)
    if overrides and c["name"] in overrides:
        level, why = overrides[c["name"]], ["GM override"]
    return level, why


def band(score, cuts=(5, 10, 14)):
    if score is None:
        return None
    return sum(score >= x for x in cuts)   # 0: 1-4, 1: 5-9, 2: 10-13, 3: 14+


def behaviour(c):
    """The GM's quadrants (Intelligence decides which options it sees, Wisdom how well it chooses)."""
    if c["int"] is None or c["wis"] is None:
        return None
    clever, wise = c["int"] >= 10, c["wis"] >= 10
    return {(False, False): "relentless", (False, True): "instinct-wary", (True, False): "clever-rash",
            (True, True): "tactician"}[(clever, wise)]


def levels(c, party=4):
    xp = c["xp"]
    if not xp:
        return {}
    alone = next((L for L in range(1, 21) if xp <= party * XP_BUDGET[L][1]), None)
    four = next((L for L in range(1, 21) if 4 * xp <= party * XP_BUDGET[L][1]), None)
    out = {"alone_moderate_from": alone, "four_moderate_from": four}
    if c["cr_value"] is not None and alone and c["cr_value"] > alone:
        out["note"] = "CR above party level %d: one action may drop a character" % alone
    return out


def classify(c, overrides=None):
    t = _text(c)
    th = themes(c, t)
    tn, why = tone(c, t, overrides)
    out = {k: v for k, v in c.items() if not k.startswith("_")}
    out.update(themes=sorted(th), theme_reasons=th, roles=list(role_tags(c, t)), role_reasons=role_tags(c, t),
               tone=tn, tone_reasons=why, behaviour=behaviour(c),
               int_band=band(c["int"]), wis_band=band(c["wis"]), levels=levels(c))
    return out


# ------------------------------------------------------------------ build, query, page
def build(srd=SRD_MODULE, out=OUT):
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    cat = [classify(normalise(r), overrides) for r in load_srd(srd)]
    out.mkdir(parents=True, exist_ok=True)
    (out / "bestiary.json").write_text(json.dumps(cat, indent=1, ensure_ascii=False), encoding="utf-8")
    return cat


def load(out=OUT):
    return json.loads((out / "bestiary.json").read_text(encoding="utf-8"))


def _cr_range(text):
    a, _, b = text.partition("-")
    return cr_value(a), cr_value(b or a)


def query(cat, theme=None, habitat=None, tone_max=None, role=None, type_=None, behaviour_=None, cr=None, level=None):
    out = []
    for c in cat:
        if theme and theme not in c["themes"]: continue
        if habitat and not any(h.lower().startswith(habitat.lower()) for h in c["habitat"]): continue
        if tone_max and TONES.index(c["tone"]) > TONES.index(tone_max): continue
        if role and role not in c["roles"]: continue
        if type_ and c["type_base"] != type_.lower(): continue
        if behaviour_ and c["behaviour"] != behaviour_: continue
        if c.get("source", "srd") != "srd": continue   # SRD only (an older catalogue file may still list paid bestiary records)
        if cr:
            lo, hi = _cr_range(cr)
            if c["cr_value"] is None or not (lo <= c["cr_value"] <= hi): continue
        if level:
            lv = c["levels"].get("alone_moderate_from")
            four = c["levels"].get("four_moderate_from")
            if not ((lv and lv <= level) and (four is None or four >= level - 4)): continue
        out.append(c)
    return sorted(out, key=lambda c: (c["cr_value"] or 0, c["name"]))


def page(cat):
    data = json.dumps([{k: c[k] for k in ("name", "cr", "cr_value", "xp", "type", "size", "habitat",
                                          "treasure", "themes", "roles", "tone", "tone_reasons", "behaviour", "levels")}
                       for c in cat if c.get("source", "srd") == "srd"], ensure_ascii=False)
    return """<!doctype html><html><head><meta charset="utf-8"><title>Bestiary catalogue</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a66;--line:#e2dfd8;--acc:#2f5d8a}
@media (prefers-color-scheme:dark){:root{--bg:#1b1c1e;--fg:#e9e7e2;--mut:#a3a19b;--line:#33343a;--acc:#8fb4e0}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 4px}.note{color:var(--mut);font-size:12px;margin:0 0 12px}
.f{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}.f input,.f select{font:inherit;padding:4px 6px;
background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:4px}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);
vertical-align:top}th{position:sticky;top:0;background:var(--bg);font-size:12px;color:var(--mut)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 6px;margin:1px;font-size:12px}
.wrap{overflow-x:auto}</style></head><body>
<h1>Bestiary catalogue</h1><p class="note">SRD 5.2.1 bestiary (CC-BY-4.0). Tags are heuristics; hover a
tone for its reasons. Levels: party of 4, 2024 XP budget (Moderate).</p>
<div class="f"><input id="q" placeholder="name"><select id="theme"><option value="">any theme</option></select>
<select id="hab"><option value="">any habitat</option></select><select id="role"><option value="">any role</option>
</select><select id="tone"><option value="">any tone</option><option>family</option><option>spooky</option>
<option>dark</option><option>mature</option></select><select id="beh"><option value="">any behaviour</option>
<option>relentless</option><option>instinct-wary</option><option>clever-rash</option><option>tactician</option></select>
<input id="lv" type="number" min="1" max="20" placeholder="party level"><span id="n" class="note"></span></div>
<div class="wrap"><table><thead><tr><th>Name</th><th>CR</th><th>Type</th><th>Habitat</th><th>Themes</th><th>Roles</th>
<th>Tone</th><th>Behaviour</th><th>Alone from</th></tr></thead><tbody id="b"></tbody></table></div>
<script>const D=""" + data + """;const T=["family","spooky","dark","mature"];const $=i=>document.getElementById(i);
const uniq=k=>[...new Set(D.flatMap(c=>c[k].map(x=>x.split(" (")[0])))].sort();
for(const[id,k]of[["theme","themes"],["hab","habitat"],["role","roles"]])for(const v of uniq(k)){const o=document.createElement("option");o.textContent=v;$(id).appendChild(o)}
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function draw(){const q=$("q").value.toLowerCase(),th=$("theme").value,h=$("hab").value,r=$("role").value,
t=$("tone").value,b=$("beh").value,lv=+$("lv").value;
const rows=D.filter(c=>(!q||c.name.toLowerCase().includes(q))&&(!th||c.themes.includes(th))&&
(!h||c.habitat.some(x=>x.startsWith(h)))&&(!r||c.roles.includes(r))&&(!t||T.indexOf(c.tone)<=T.indexOf(t))&&
(!b||c.behaviour===b)&&(!lv||(c.levels.alone_moderate_from&&c.levels.alone_moderate_from<=lv&&
(c.levels.four_moderate_from==null||c.levels.four_moderate_from>=lv-4))));
$("n").textContent=rows.length+" creatures";$("b").innerHTML=rows.slice(0,600).map(c=>"<tr><td>"+esc(c.name)+
"</td><td>"+esc(c.cr)+"</td><td>"+esc(c.type)+"</td><td>"+c.habitat.map(x=>"<span class=tag>"+esc(x)+"</span>").join("")+
"</td><td>"+c.themes.map(x=>"<span class=tag>"+esc(x)+"</span>").join("")+"</td><td>"+esc(c.roles.join(", "))+
"</td><td title=\\""+esc(c.tone_reasons.join(", "))+"\\">"+esc(c.tone)+"</td><td>"+esc(c.behaviour||"")+"</td><td>"+
esc(c.levels.alone_moderate_from||"")+"</td></tr>").join("")}
document.querySelectorAll("input,select").forEach(e=>e.addEventListener("input",draw));draw();</script></body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("records")
    q = sub.add_parser("query")
    for a in ("--theme", "--habitat", "--tone", "--role", "--type", "--behaviour", "--cr"):
        q.add_argument(a)
    q.add_argument("--level", type=int); q.add_argument("--limit", type=int, default=40)
    sub.add_parser("html")
    e = sub.add_parser("export-srd"); e.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        cat = build()
        print("catalogue: %d SRD creatures -> %s" % (len(cat), OUT / "bestiary.json"))
    elif a.cmd == "records":
        print("%d SRD creatures -> %s" % (write_srd_records(), SRD_RECORDS))
    elif a.cmd == "query":
        rows = query(load(), a.theme, a.habitat, a.tone, a.role, a.type, a.behaviour, a.cr, a.level)
        for c in rows[:a.limit]:
            print("%-28s CR %-4s %-22s %-6s %-14s %s | %s" % (c["name"][:28], c["cr"], c["type"][:22], c["tone"],
                  c["behaviour"] or "", ", ".join(c["roles"]), ", ".join(h.split(" (")[0] for h in c["habitat"])))
        print("%d match%s" % (len(rows), "" if len(rows) == 1 else "es"))
    elif a.cmd == "html":
        p = OUT / "bestiary.html"
        p.write_text(page(load()), encoding="utf-8")
        print(p)
    elif a.cmd == "export-srd":
        cat = [c for c in load() if c["source"] == "srd"]
        Path(a.file).write_text(json.dumps({"attribution": SRD_ATTRIBUTION, "creatures": cat}, indent=1,
                                           ensure_ascii=False), encoding="utf-8")
        print("%d SRD creatures -> %s" % (len(cat), a.file))


if __name__ == "__main__":
    sys.exit(main())
