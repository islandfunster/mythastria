"""ONE-SHOT-01 (GM 2026-11-02: "Let's build a one-shot adventure builder ... a story the GM can generate as text for locations,
and maps for those locations. Encounters can be placed, traps, puzzles, social and combat, etc."): a GM's one-shot, kept on
this PC in sim/one_shots/, and written out as an ordinary adventure pack (tools/adventure_packs.py), so it loads, plays and
remixes like any other adventure. Written with the GM's own words and SRD 5.2.1 creatures and traps. Maps are the ones the
service already has: imported, drawn by the site designer, or test maps; this file never draws one."""
import copy
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "sim" / "one_shots"
ATTITUDES = ("Hostile", "Indifferent", "Friendly")
MAX_LOCATIONS, MAX_ROWS = 30, 40
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
# generate: what the GM's local model may write, and what it is told
FIELDS = {"premise": "the adventure's premise, in two short paragraphs", "hook": "how the party gets involved, in two sentences",
          "question": "the one question this adventure asks, in one sentence", "read_aloud": "what the GM reads aloud on arrival, in three sentences",
          "gm_text": "the GM's private notes on this location: what is going on and what can happen, in a short paragraph",
          "puzzle": "a riddle or puzzle the players solve by talking and thinking, with no dice: what they see, then the solution, in a short paragraph"}
GUIDE = ("You help a GM write a one-shot tabletop adventure for a game using the System Reference Document 5.2.1. Invent your "
         "own names and places. Don't use any published setting, adventure or character. Write plain text only, with no "
         "headings and no lists. Write only the text asked for.")


def text(v, what, limit):
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > limit:
        raise ValueError("%s is text of up to %d characters." % (what, limit))
    return v.strip()


def whole(v, what, low, high):
    if not isinstance(v, int) or isinstance(v, bool) or not low <= v <= high:
        raise ValueError("%s is a whole number from %d to %d." % (what, low, high))
    return v


def rows(v, what):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > MAX_ROWS or not all(isinstance(r, dict) for r in v):
        raise ValueError("%s is a list of up to %d rows." % (what, MAX_ROWS))
    return v


def square(v, what):
    if not (isinstance(v, list) and len(v) == 2 and all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 500 for n in v)):
        raise ValueError("%s is a square [x, y]." % what)
    return v


def check_creature(r, lib, where):
    name = r.get("name")
    if name not in lib:
        raise ValueError("%s: %s isn't in the SRD 5.2.1 library." % (where, name))
    if r.get("attitude", "Hostile") not in ATTITUDES:
        raise ValueError("%s: an attitude is %s." % (where, ", ".join(ATTITUDES)))
    out = {"name": name, "count": whole(r.get("count", 1), "A count", 1, 12), "attitude": r.get("attitude", "Hostile"),
           "who": text(r.get("who"), "Who it is", 60), "wants": text(r.get("wants"), "What it wants", 300),
           "knows": text(r.get("knows"), "What it knows", 300)}
    if r.get("at") is not None:
        out["at"] = square(r["at"], "Where it starts")
    return out


def check_trap(r, traps, where):
    t = traps.get(r.get("kind"))
    if not t:
        raise ValueError("%s: pick one of the SRD traps." % where)
    if r.get("band") not in t["bands"]:
        raise ValueError("%s: %s comes as %s." % (where, t["name"], ", ".join(map(str, t["bands"]))))
    squares = [square(s, "A trap's square") for s in rows_of(r.get("squares"))]
    if not squares:
        raise ValueError("%s: click a square on the map for %s." % (where, t["name"]))
    return {"kind": r["kind"], "band": r["band"], "squares": squares}


def rows_of(v):
    return v if isinstance(v, list) and len(v) <= MAX_ROWS else []


def check_puzzle(r, where):
    """GM 2026-11-02: "puzzles are narrative": the players' words decide, so no skill, DC or roll."""
    out = {"name": text(r.get("name"), "A puzzle's name", 80), "text": text(r.get("text"), "A puzzle", 1500),
           "hint": text(r.get("hint"), "A hint", 400), "solution": text(r.get("solution"), "A solution", 800)}
    if not out["name"] or not out["text"]:
        raise ValueError("%s: a puzzle needs a name and what the players see." % where)
    return out


def check(doc, maps, lib, traps):
    """A one-shot as the GM saves it, checked -> the clean one. Refuses in the GM's words."""
    if not isinstance(doc, dict):
        raise ValueError("A one-shot is an object.")
    title = text(doc.get("title"), "The title", 80)
    if not title:
        raise ValueError("Give the one-shot a title.")
    out = {"title": title, "level": whole(doc.get("level", 3), "The level", 1, 20), "tone": text(doc.get("tone"), "The tone", 200),
           "premise": text(doc.get("premise"), "The premise", 4000), "hook": text(doc.get("hook"), "The hook", 1500),
           "question": text(doc.get("question"), "The question", 300), "locations": []}
    if isinstance(doc.get("id"), str) and ID.fullmatch(doc["id"]):
        out["id"] = doc["id"]
    places = rows(doc.get("locations"), "Locations")
    if len(places) > MAX_LOCATIONS:
        raise ValueError("A one-shot has up to %d locations." % MAX_LOCATIONS)
    for n, p in enumerate(places, 1):
        name = text(p.get("name"), "A location's name", 60)
        where = name or "Location %d" % n
        if not name:
            raise ValueError("Location %d needs a name." % n)
        if p.get("map") and p["map"] not in maps:
            raise ValueError("%s: that map isn't on this PC." % where)
        out["locations"].append({
            "name": name, "map": p.get("map") or "", "keep_creatures": p.get("keep_creatures") is True,
            "read_aloud": text(p.get("read_aloud"), "The read-aloud text", 2000), "gm_text": text(p.get("gm_text"), "The GM's notes", 4000),
            "creatures": [check_creature(r, lib, where) for r in rows(p.get("creatures"), "Creatures")],
            "traps": [check_trap(r, traps, where) for r in rows(p.get("traps"), "Traps")],
            "puzzles": [check_puzzle(r, where) for r in rows(p.get("puzzles"), "Puzzles")]})
    return out


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:32] or "one_shot"


def store_path(sid, store=STORE):
    if not isinstance(sid, str) or not ID.fullmatch(sid):
        raise ValueError("That isn't a one-shot on this PC.")
    return store / (sid + ".json")


def save(doc, store=STORE):
    doc = copy.deepcopy(doc)
    if not doc.get("id"):
        base, n = slug(doc["title"]), 1
        doc["id"] = base
        while store_path(doc["id"], store).exists():
            n += 1
            doc["id"] = "%s_%d" % (base, n)
    doc["saved"] = time.strftime("%Y-%m-%d %H:%M")
    store.mkdir(parents=True, exist_ok=True)
    store_path(doc["id"], store).write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return doc


def load(sid, store=STORE):
    p = store_path(sid, store)
    if not p.is_file():
        raise ValueError("That one-shot isn't on this PC.")
    return json.loads(p.read_text(encoding="utf-8"))


def listing(store=STORE):
    out = []
    for f in sorted(store.glob("*.json")) if store.is_dir() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": d["id"], "title": d["title"], "level": d.get("level"), "places": len(d.get("locations") or []), "saved": d.get("saved")})
        except (OSError, ValueError, KeyError):
            continue
    return out


def delete(sid, store=STORE):
    store_path(sid, store).unlink(missing_ok=True)


def scenario_for(doc, place, raw, lib):
    """A location's map with its creatures and traps. The map's own file never changes; its party marks stay."""
    import remix
    sc = copy.deepcopy(raw)
    if not place["keep_creatures"]:
        sc["combatants"] = [c for c in sc["combatants"] if c.get("pc")]
        if sc.get("aware") is not None:
            sc["aware"] = []
    party = next(([int(round(c["x"])), int(round(c["y"]))] for c in sc["combatants"] if c.get("pc")), None)   # play-test 2026-11-02: people to
    add = [dict({"name": r["name"], "count": r["count"]},                  # talk to start by the party, in sight; foes at the foes' start
                **({"at": r["at"]} if r.get("at") else {"at": party} if party and r["attitude"] != "Hostile" and r["count"] <= 2 else {})) for r in place["creatures"]]
    if add:
        known = {c["id"] for c in sc["combatants"]}
        sc = remix.apply(sc, {"seed": 1, "changes": [], "add": add}, lib)
        sc.pop("remix", None)
        fresh = iter(c for c in sc["combatants"] if c["id"] not in known)
        for r in place["creatures"]:
            for n in range(r["count"]):
                c = next(fresh)
                c["attitude"] = r["attitude"]
                if r["who"]:
                    c["name"] = r["who"] if r["count"] == 1 else "%s %d" % (r["who"], n + 1)
    if place["traps"]:
        sc["traps"] = list(sc.get("traps") or []) + copy.deepcopy(place["traps"])
    sc["name"] = "%s - %s" % (doc["title"], place["name"])
    sc["map_name"] = sc["name"]
    return sc


def people(place):
    return [{"name": r["who"] or r["name"], "attitude": r["attitude"], "wants": r["wants"], "knows": r["knows"]}
            for r in place["creatures"] if r["attitude"] != "Hostile" or r["who"] or r["wants"] or r["knows"]]


def pack(doc, raw_map, lib):
    """(manifest, lore, {key: scenario}): the pack's files. Every location needs a map."""
    pid = "oneshot_" + doc["id"]
    encounters, maps = {}, {}
    if not doc["locations"]:
        raise ValueError("Add a location first.")
    for n, p in enumerate(doc["locations"], 1):
        if not p["map"]:
            raise ValueError("%s needs a map." % p["name"])
        key = "p%d_%s" % (n, slug(p["name"])[:24])
        maps[key] = scenario_for(doc, p, raw_map(p["map"]), lib)
        encounters[key] = {"scenario": "scenarios/%s.json" % key,
                           "notes": {"read_aloud": p["read_aloud"], "gm_text": p["gm_text"], "puzzles": p["puzzles"], "people": people(p)}}
    manifest = {"format": "mythastria-adventure/1", "id": pid, "name": "%s (One-shot)" % doc["title"], "version": time.strftime("%Y-%m-%d"),
                "one_shot": True, "lore": "lore.json", "encounters": encounters}
    lore = {"format": "mythastria-lore/1", "title": doc["title"], "levels": "One-shot for level %d" % doc["level"], "question": doc["question"],
            "premise": [x for x in (doc["premise"], doc["hook"]) if x], "tone": doc["tone"], "cast": [], "secrets": [],
            "chapters": [{"chapter": "One-shot", "level": doc["level"], "places": list(encounters)}]}
    return manifest, lore, maps


def publish(doc, library, raw_map, lib):
    """Write the pack into the adventure library -> its id. Replaces only a pack this builder wrote."""
    if library is None:
        raise ValueError("Start Mythastria with an adventures folder first.")
    manifest, lore, maps = pack(doc, raw_map, lib)
    folder = Path(library) / manifest["id"]
    old = folder / "adventure.json"
    if old.is_file() and json.loads(old.read_text(encoding="utf-8")).get("one_shot") is not True:
        raise ValueError("An adventure that isn't a one-shot already has that name.")
    if folder.is_dir():
        shutil.rmtree(folder)
    (folder / "scenarios").mkdir(parents=True)
    old.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (folder / "lore.json").write_text(json.dumps(lore, indent=1, ensure_ascii=False), encoding="utf-8")
    for key, sc in maps.items():
        (folder / "scenarios" / (key + ".json")).write_text(json.dumps(sc, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest["id"]


def prompt(field, doc, place=None, idea=""):
    """The messages that ask the GM's local model for one field."""
    if field not in FIELDS:
        raise ValueError("That field can't be generated.")
    about = ["One-shot: %s (level %s)." % (doc.get("title") or "untitled", doc.get("level", "?"))]
    if doc.get("tone"):
        about.append("Tone: %s." % doc["tone"])
    if doc.get("premise") and field != "premise":
        about.append("Premise: %s" % doc["premise"])
    if place:
        about.append("Location: %s." % place.get("name", ""))
        if place.get("creatures"):
            about.append("Who is here: %s." % ", ".join(r.get("who") or r.get("name", "") for r in place["creatures"]))
    if idea:
        about.append("The GM's idea: %s" % text(idea, "Your idea", 500))
    return [{"role": "system", "content": GUIDE}, {"role": "user", "content": "%s\nWrite %s." % ("\n".join(about), FIELDS[field])}]


def map_view(raw):
    """A map for the builder's small picture: its size, walls and who starts where."""
    import remix
    cols, n_rows = remix._extent(raw)
    return {"cols": cols, "rows": n_rows, "wall_cells": raw.get("wall_cells") or [], "name": raw.get("map_name") or raw.get("name"),
            "walls": [w.get("points") for w in raw.get("walls") or []],
            "marks": [{"x": c.get("x"), "y": c.get("y"), "name": c.get("name"), "pc": bool(c.get("pc"))} for c in raw.get("combatants") or []]}
