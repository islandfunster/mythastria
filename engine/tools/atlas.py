"""ATLAS-01 (GM 2026-10-22: "Don't give the places names. Number them and create a database that allows multiple maps to
be connected"; "allow the places to be named on the map manually"; then "let's make portals the allow a spot in the map
to jump to another map that's part of the database. Also, let's make a filing protocol that keeps all maps associated
with a project, and a place for spare maps"): the atlas, Mythastria's map database on the GM's PC.

Every region map (and later every indoor map and dungeon, MAPGEN-01 step 2) is kept here by id. A place can lead to
another map (place["to"] = {"map": id}, a portal also {"hex": where it comes out}) or to a tactical map (place["map"] =
a scenario name); the index records the links both ways, so a map can say what leads to it.

FILING PROTOCOL (docs/development/ATLAS_FILING.md):
 1. Every map is filed in exactly one project, or in Spare maps (project None).
 2. A new map is filed in the project that is open; a map made from a place or a portal goes into the same project as
    the map it comes from.
 3. A map moves between projects (or to Spare maps) only when the GM moves it; its links go with it.
 4. Deleting a project never deletes a map: its maps go to Spare maps.
 5. A project exports as one file with all its maps (links kept), and imports as a new project.
The maps are the GM's own: sim/atlas/ is never committed (its own .gitignore) and never shared or used for training.

  maps/<id>.json   one map (a region: format region-map/1, picture included)
  index.json       {id: {kind, name, updated, places, links: [ids], tactical: [scenario names], project}}
  projects.json    {project id: {name, created}}
"""
import datetime, json, os, re, secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATLAS = ROOT / "sim" / "atlas"
KINDS = {"region-map/1": "region"}            # MAPGEN-01 step 2 adds the indoor maps' format here
ID = re.compile(r"^m[0-9a-f]{10}$")
PID = re.compile(r"^p[0-9a-f]{8}$")
HEX = re.compile(r"^-?\d+,-?\d+$")
MAX_BYTES = 60 * 1024 * 1024
BUNDLE = "mythastria-project/1"
KEEP = object()                               # save_map: leave the map's project as it is


class AtlasError(ValueError):
    pass


def _dir(root):
    d = Path(root or ATLAS)
    (d / "maps").mkdir(parents=True, exist_ok=True)
    if not (d / ".gitignore").exists():
        (d / ".gitignore").write_text("*\n", encoding="utf-8")
    return d


def _write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)                       # never a half-written file


def _read(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def summary(m):
    """What the index keeps about a map: its kind, name, places, and where its places lead."""
    places = m.get("locations") or []
    links = sorted({p["to"]["map"] for p in places if isinstance(p.get("to"), dict) and ID.match(str(p["to"].get("map", "")))})
    tactical = sorted({p["map"] for p in places if isinstance(p.get("map"), str) and p["map"]})
    return {"kind": KINDS[m["format"]], "name": str(m.get("name") or "Map")[:80], "places": len(places), "links": links,
            "tactical": tactical, "picture": bool(m.get("picture")),
            "portals": sum(1 for p in places if p.get("kind") == "portal")}


def check(m):
    if not isinstance(m, dict) or m.get("format") not in KINDS:
        raise AtlasError("Not a Mythastria map (%s)." % ", ".join(KINDS))
    if not isinstance(m.get("locations", []), list):
        raise AtlasError("A map's places are a list.")
    for p in m.get("locations", []):
        if not isinstance(p, dict) or not isinstance(p.get("hex"), str):
            raise AtlasError("Every place has a hex.")
        to = p.get("to")
        if to is not None and not (isinstance(to, dict) and ID.match(str(to.get("map", "")))
                                   and (to.get("hex") is None or HEX.match(str(to["hex"])))):
            raise AtlasError("A place leads to a map by its id (and a portal to a hex on it).")
    return m


# ------------------------------------------------------------------ projects (the filing protocol)
def list_projects(root=None):
    """[{id, name, created, maps}] by name, then Spare maps last ({id: None})."""
    d = _dir(root)
    projects, idx = _read(d / "projects.json"), _read(d / "index.json")
    count = lambda pid: sum(1 for s in idx.values() if s.get("project") == pid)
    out = sorted(({"id": pid, "name": p["name"], "created": p.get("created"), "maps": count(pid)} for pid, p in projects.items()),
                 key=lambda p: p["name"].lower())
    return out + [{"id": None, "name": "Spare maps", "maps": count(None)}]


def _check_project(pid, root):
    if pid is not None and (not PID.match(str(pid)) or pid not in _read(_dir(root) / "projects.json")):
        raise AtlasError("No such project.")
    return pid


def _name(name):
    name = str(name or "").strip()
    if not 0 < len(name) <= 80:
        raise AtlasError("A project's name, up to 80 characters.")
    return name


def create_project(name, root=None):
    d = _dir(root)
    projects = _read(d / "projects.json")
    pid = "p" + secrets.token_hex(4)
    projects[pid] = {"name": _name(name), "created": _now()}
    _write(d / "projects.json", json.dumps(projects, indent=1))
    return pid


def rename_project(pid, name, root=None):
    d = _dir(root)
    _check_project(pid, root)
    if pid is None:
        raise AtlasError("Spare maps keeps its name.")
    projects = _read(d / "projects.json")
    projects[pid]["name"] = _name(name)
    _write(d / "projects.json", json.dumps(projects, indent=1))


def delete_project(pid, root=None):
    """Rule 4: the project goes; its maps go to Spare maps (never deleted)."""
    d = _dir(root)
    _check_project(pid, root)
    if pid is None:
        raise AtlasError("Spare maps can't be deleted.")
    idx = _read(d / "index.json")
    for s in idx.values():
        if s.get("project") == pid:
            s["project"] = None
    _write(d / "index.json", json.dumps(idx, indent=1))
    projects = _read(d / "projects.json")
    projects.pop(pid, None)
    _write(d / "projects.json", json.dumps(projects, indent=1))


def move_map(map_id, pid, root=None):
    """Rule 3: the GM moves a map to another project (or to Spare maps, pid None)."""
    d = _dir(root)
    _check_project(pid, root)
    idx = _read(d / "index.json")
    if map_id not in idx:
        raise AtlasError("No such map.")
    idx[map_id]["project"] = pid
    _write(d / "index.json", json.dumps(idx, indent=1))


# ------------------------------------------------------------------ maps
def list_maps(root=None, project=KEEP):
    """[{id, kind, name, updated, places, links, tactical, picture, portals, project, linked_from}], newest first; only
    one project's maps (None: Spare maps) when project is given."""
    idx = _read(_dir(root) / "index.json")
    back = {}
    for i, s in idx.items():
        for j in s.get("links", []):
            back.setdefault(j, []).append(i)
    out = [dict(s, id=i, project=s.get("project"), linked_from=sorted(back.get(i, []))) for i, s in idx.items()
           if project is KEEP or s.get("project") == project]
    return sorted(out, key=lambda s: s.get("updated", ""), reverse=True)


def get_map(map_id, root=None):
    if not ID.match(str(map_id)):
        raise AtlasError("No such map.")
    p = _dir(root) / "maps" / ("%s.json" % map_id)
    if not p.exists():
        raise AtlasError("No such map (it may have been deleted).")
    return json.loads(p.read_text(encoding="utf-8"))


def save_map(m, map_id=None, root=None, project=KEEP):
    """Keep a map (a new one gets an id). A new map is filed in `project` (rule 2; None: Spare maps); an existing one
    stays where it is unless `project` is given. Returns its id."""
    check(m)
    text = json.dumps(m, separators=(",", ":"))
    if len(text) > MAX_BYTES:
        raise AtlasError("That map is too large to keep (%d MB at most)." % (MAX_BYTES // 2**20))
    d = _dir(root)
    if project is not KEEP:
        _check_project(project, root)
    if map_id is None:
        map_id = "m" + secrets.token_hex(5)
    elif not ID.match(str(map_id)):
        raise AtlasError("No such map.")
    _write(d / "maps" / ("%s.json" % map_id), text)
    idx = _read(d / "index.json")
    filed = idx.get(map_id, {}).get("project") if project is KEEP else project
    idx[map_id] = dict(summary(m), updated=_now(), project=filed)
    _write(d / "index.json", json.dumps(idx, indent=1))
    return map_id


def delete_map(map_id, root=None):
    if not ID.match(str(map_id)):
        raise AtlasError("No such map.")
    d = _dir(root)
    (d / "maps" / ("%s.json" % map_id)).unlink(missing_ok=True)
    idx = _read(d / "index.json")
    idx.pop(map_id, None)
    _write(d / "index.json", json.dumps(idx, indent=1))


# ------------------------------------------------------------------ a project as one file (rule 5)
def export_project(pid, root=None):
    _check_project(pid, root)
    name = "Spare maps" if pid is None else _read(_dir(root) / "projects.json")[pid]["name"]
    return {"format": BUNDLE, "name": name, "exported": _now(),
            "maps": [{"id": s["id"], "map": get_map(s["id"], root)} for s in list_maps(root, pid)]}


def import_project(bundle, root=None):
    """A project file -> a new project with new map ids; links inside it follow the new ids (links to maps outside the
    file lead nowhere). Returns the new project's id."""
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE or not isinstance(bundle.get("maps"), list):
        raise AtlasError("Not a Mythastria project file (%s)." % BUNDLE)
    for e in bundle["maps"]:
        if not isinstance(e, dict) or not ID.match(str(e.get("id", ""))):
            raise AtlasError("A project file's maps each have an id.")
        check(e.get("map"))
    names = {p["name"] for p in list_projects(root)}
    name, n = _name(bundle.get("name") or "Imported project"), 2
    base = name
    while name in names:
        name, n = "%s (%d)" % (base, n), n + 1
    new_ids = {e["id"]: "m" + secrets.token_hex(5) for e in bundle["maps"]}
    pid = create_project(name, root)
    for e in bundle["maps"]:
        m = json.loads(json.dumps(e["map"]))
        for p in m.get("locations", []):
            if isinstance(p.get("to"), dict):
                p["to"] = dict(p["to"], map=new_ids[p["to"]["map"]]) if p["to"].get("map") in new_ids else None
        save_map(m, new_ids[e["id"]], root, project=pid)
    return pid
