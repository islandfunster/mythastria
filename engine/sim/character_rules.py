"""CHARACTERS-01 (GM 2026-10-21: "I would like it able to import formats like forge, dnd beyond, fantasy grounds, etc. as
well as a having a first rate character builder that can quickly be tested in live"): the SRD 5.2.1 character rules of
the simulator service, the rules authority for characters (POST /api/characters, ops character_check, ...).

Data: sim/srd_character_rules.json (tools/build_srd_character_rules.py, from the SRD 5.2.1 PDF). Content policy (GM
2026-10-21): only own MIT and SRD 5.2.1 content ships. Anything else on an imported sheet (third-party or 2014-rules
species, classes, feats, spells, features) is the user's own homebrew: it stays on their sheet, is flagged "homebrew, GM
rules it", and is never added to the shipped data nor used to train or prepare anything. Plain JSON in and out.
"""
import json, re
from functools import lru_cache
from pathlib import Path

# NOTES 7.8: a sheet's attacks beyond `weapon` and `ranged`, each with its own card; the simulator's tactics pick from
# the two, and Party.unwasted_attack turns to the rest
MORE_ATTACKS = tuple("more%d" % n for n in range(1, 19))
WEAPON_KEYS = ("weapon", "ranged") + MORE_ATTACKS

RULES_FILE = Path(__file__).resolve().parent / "srd_character_rules.json"
HOMEBREW = "homebrew, GM rules it"
ABILITIES = ("str", "dex", "con", "int", "wis", "cha")


@lru_cache(maxsize=1)
def rules():
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def norm(s):
    """'Hunter\u2019s Mark ' -> "hunter's mark": names compared without case, curly quotes or extra spaces."""
    return re.sub(r"\s+", " ", str(s or "").replace("\u2019", "'").replace("\u2018", "'")).strip().lower()


def bare(s):
    """A feature name without its counts and notes: 'Rage (2/day)' / 'Rage: 2 uses' / 'Rage - x' -> 'rage'."""
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", norm(s))
    return re.split(r"\s+[-\u2013\u2014:]\s+|:\s*", s)[0].strip(" .")


@lru_cache(maxsize=1)
def known():
    """Every SRD 5.2.1 character name the checks know, by kind."""
    r = rules()
    spells = {norm(s["name"]) for s in r["spells"]}
    classes = {norm(c) for c in r["classes"]}
    subclasses = {norm(c["subclass"]["name"]) for c in r["classes"].values()}
    species = {norm(s) for s in r["species"]}
    feats = {norm(f) for f in r["feats"]}
    features = set(feats)
    for c in r["classes"].values():
        features |= {bare(f) for _, f in c["features"] + c["subclass"]["features"]}
    for s in r["species"].values():
        features |= {bare(t) for t in s["traits"]}
    # words an import uses for sheet sections or counters rather than rules features
    features |= subclasses | {norm(x) for x in r.get("invocations", {})} | {norm(x) for x in r.get("metamagic", [])}
    features |= {"divine order", "primal order", "lineage", "ancestry", "blessed warrior", "druidic warrior"}
    features |= {"hit points", "proficiencies", "languages", "senses", "armor class", "speed", "initiative",
                 "spellcasting ability", "unarmed strike", "subclass feature", "epic boon", "metamagic",
                 "eldritch invocation", "eldritch invocations", "fighting style", "spell slots", "pact slots",
                 "sorcery points", "focus points", "ki", "bardic inspiration", "channel divinity", "wild shape",
                 "lay on hands", "sneak attack", "rage", "second wind", "action surge", "extra attack", "core traits",
                 "magic initiate", "darkvision", "background feat", "origin feat"} | spells
    backgrounds = {norm(b) for b in r["backgrounds"]}
    return dict(spells=spells, classes=classes, subclasses=subclasses, species=species, feats=feats,
                features=features, backgrounds=backgrounds)


def species_is_srd(name):
    """'Elf', 'Wood Elf', 'Elf (High Elf)', 'Gold Dragonborn', 'Infernal Tiefling', 'Goliath (Stone)' are SRD;
    'Half-Elf' or 'Hill Dwarf' are not (2014 or third-party)."""
    s = norm(name)
    if not s:
        return True
    words = re.sub(r"[()\-\u2013\u2014,/]", " ", s).split()
    for species, data in rules()["species"].items():
        sp = norm(species)
        if sp not in words:
            continue
        rest = " ".join(w for w in words if w not in (sp, "lineage", "ancestry", "legacy"))
        lineages = {norm(x) for x in data.get("lineages", {})}
        if not rest or rest in lineages or rest + " " + sp in lineages:
            return True
    return any(s in {norm(x) for x in data.get("lineages", {})} for data in rules()["species"].values() if " " in s or s == "drow")


def feat_is_srd(name):
    s = bare(name)
    s = re.sub(r"^feat\s+", "", s)
    return s in known()["feats"] or s.startswith("magic initiate") or s.startswith("ability score improvement")


def _names(values):
    for v in values or []:
        n = v.get("name") if isinstance(v, dict) else v
        if isinstance(n, str) and n.strip():
            yield n.strip()


def flags(sheet):
    """What on an isles-character/1 sheet is not SRD 5.2.1: [{kind, name, note}] (empty when it is all SRD). Never refuses
    the character: the GM rules each flagged thing."""
    k, out = known(), []
    def flag(kind, name, note=HOMEBREW):
        if not any(f["kind"] == kind and f["name"] == name for f in out):
            out.append({"kind": kind, "name": name, "note": note})
    if not isinstance(sheet, dict):
        return out
    ruleset = norm(sheet.get("ruleset"))
    if re.search(r"2014|legacy|5e \(old\)|\bphb 14\b", ruleset):
        flag("rules", sheet.get("ruleset"), "2014 rules: " + HOMEBREW)
    if not species_is_srd(sheet.get("species")):
        flag("species", sheet["species"])
    bg = norm(sheet.get("background"))
    if bg and bg not in k["backgrounds"]:
        flag("background", sheet["background"])
    for c in sheet.get("classes") or []:
        if not isinstance(c, dict):
            continue
        if norm(c.get("name")) not in k["classes"]:
            flag("class", c.get("name") or "?")
        sub = norm(c.get("subclass"))
        if sub and sub not in k["subclasses"]:
            flag("subclass", c["subclass"])
    for f in _names(sheet.get("feats")):
        if not feat_is_srd(f):
            flag("feat", f)
    for s in _names(sheet.get("spells")):
        if norm(s) not in k["spells"]:
            flag("spell", s)
    for f in _names(sheet.get("features")):
        b = bare(f)
        if b and b not in k["features"] and not b.startswith("species") and not feat_is_srd(f):
            flag("feature", f)
    return out


def check(sheet):
    """The op character_check: the sheet's homebrew flags (nothing is changed or refused)."""
    return {"ok": True, "flags": flags(sheet), "rules": rules()["version"]}
