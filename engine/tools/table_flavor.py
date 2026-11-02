"""FLAVOR-01 (GM 2026-10-21): the table's Flavor kept by the service, so players on their own devices see it too.

Flavor is presentation only (isles-table FLAVOR.md, dist/flavor.mjs): a creature's shown name, role, footnote, catalog
picture and paint; an attack's or spell's name, description and visuals. It never changes a rule, and nothing here is
read by the simulator. The GM's console reads and writes the whole collection (POST /api/flavor, /api/flavor/save);
a seat at the players' door gets only what it may see (player_view). The same allowlist as flavor.mjs is checked again
here: a page cannot store anything else. Kept in sim/flavor/flavor.json (campaign data, not committed).

PLAYER-FLAVOR-01 (the Player Client Plan, item 7: "Each flavor change needs DM approval"): a player asks for a look for a
creature they control (FlavorStore.ask); it waits in `asks`, one to a creature, seen only by that player and the GM. The
GM approves it (it joins the collection on every map, for all to see) or refuses it (it is gone, with no note).
"""
import json
import re
import threading
from pathlib import Path

EVERY_MAP = "*"
MAX_ENTRIES, MAX_PAINT = 2000, 400000
ROLES = ("pet", "familiar", "mount", "companion")
PALETTES = ("fire", "frost", "lightning", "poison", "smoke", "arcane", "physical", "radiant", "acid", "thunder",
            "healing", "shadow", "transport")                    # dist/effects.mjs palettes
# GM 2026-10-23 ("Keep the flat standees. Include them to be edited in flavor"): base (a round base under the standee)
# and true_height (as tall as its picture, not 40% taller) are yes/no settings of the 3D view's standee, like share;
# rider (a catalog picture shown on a Large or bigger creature's back; a look only: DECISIONS, MOUNTS ARE DOMESTIC
# ANIMALS).
FIELDS = {"actor": ("name", "description", "token_id", "role", "share", "base", "true_height", "rider", "mask", "paint",
                    "paint_on", "paint_until"),
          "attack": ("name", "description"),
          "spell": ("name", "description", "appearance")}
YES_NO = ("share", "base", "true_height")
TEXT = {"description": 1000, "token_id": 160, "rider": 160}                    # other text fields: 80
PICTURE = re.compile(r"^data:image/(png|webp);base64,[A-Za-z0-9+/]+=*$")
# what a seat may see of an actor's Flavor (the strokes alone, the "mask", stay with the GM); the standee's look is on
# the map, so the players see it too
PLAYER_ACTOR = ("name", "token_id", "base", "true_height", "rider", "paint", "paint_on", "paint_until")
# what a player may ask for: a creature's looks. share and paint_until are the GM's and the service's to set.
ASKABLE = ("name", "description", "token_id", "role", "base", "true_height", "rider", "mask", "paint", "paint_on")


def actor_key(scope, actor):
    """A creature's own entry (flavor.mjs flavorKey)."""
    return json.dumps([scope, actor, "actor", ""], ensure_ascii=False, separators=(",", ":"))


def key_parts(entry_id):
    """[scope, actor, kind, key] of an entry id (flavor.mjs flavorKey), or None."""
    try:
        parts = json.loads(entry_id)
    except (TypeError, ValueError):
        return None
    if not (isinstance(parts, list) and len(parts) == 4 and all(isinstance(p, str) for p in parts)):
        return None
    scope, actor, kind, key = parts
    if not (0 < len(scope) <= 256 and 0 < len(actor) <= 256 and kind in FIELDS and len(key) <= 256):
        return None
    if json.dumps(parts, ensure_ascii=False, separators=(",", ":")) != entry_id:
        return None
    return parts


def clean(kind, value):
    """One entry cut to its allowlisted fields (ValueError for anything else, as flavor.mjs does on an edit)."""
    if not isinstance(value, dict):
        raise ValueError("Invalid Flavor.")
    extra = [k for k in value if k not in FIELDS[kind]]
    if extra:
        raise ValueError("Flavor can change presentation only (not %s)." % ", ".join(sorted(extra)[:3]))
    out = {}
    for f in FIELDS[kind]:
        v = value.get(f)
        if f in YES_NO:
            if v is True:
                out[f] = True
            continue
        if v in (None, ""):
            continue
        if not isinstance(v, str):
            raise ValueError("Flavor %s must be text." % f)
        if f in ("mask", "paint"):
            if len(v) > MAX_PAINT or not PICTURE.match(v):
                raise ValueError("The paint is not a picture this table can keep (PNG or WebP, under 400 KB).")
            out[f] = v
            continue
        v = v.strip()[:TEXT.get(f, 80)]
        if not v:
            continue
        if f == "appearance" and v not in PALETTES:
            raise ValueError("Choose an existing visual effect.")
        if f == "role" and v not in ROLES:
            raise ValueError("Choose a listed role.")
        out[f] = v
    if "paint" not in out:
        for f in ("mask", "paint_on", "paint_until"):
            out.pop(f, None)
    if list(out) == ["share"]:
        return {}
    return out


def clean_state(state):
    """The whole collection, checked: {"version": 1, "entries": {id: entry}}."""
    if not (isinstance(state, dict) and state.get("version") == 1 and isinstance(state.get("entries"), dict)):
        raise ValueError("Flavor is {version: 1, entries: {...}}.")
    if len(state["entries"]) > MAX_ENTRIES:
        raise ValueError("At most %d Flavor entries." % MAX_ENTRIES)
    entries = {}
    for entry_id, value in state["entries"].items():
        parts = key_parts(entry_id)
        if not parts:
            raise ValueError("A Flavor entry has a bad name.")
        record = clean(parts[2], value)
        if record:
            entries[entry_id] = record
    return {"version": 1, "entries": entries}


def end_adventure(state, pack):
    """An adventure ended or started again: its paint comes off (the rest of each creature's Flavor stays)."""
    entries = {}
    for entry_id, r in state["entries"].items():
        if r.get("paint_until") != "adventure:%s" % pack:
            entries[entry_id] = r
            continue
        rest = {k: v for k, v in r.items() if k not in ("mask", "paint", "paint_on", "paint_until")}
        if rest and list(rest) != ["share"]:
            entries[entry_id] = rest
    return {"version": 1, "entries": entries}


def player_view(state, map_name, names):
    """What a seat may see: Flavor for this map (or every map) of the creatures it sees now (`names`, rules names), and
    attacks' and spells' looks. A footnote and role only when the GM let the players read it; never the paint strokes."""
    names = set(names)
    entries = {}
    for entry_id, r in state["entries"].items():
        scope, actor, kind, key = key_parts(entry_id)
        if scope not in (map_name, EVERY_MAP) or actor not in names:
            continue
        if kind == "actor":
            out = {k: r[k] for k in PLAYER_ACTOR if k in r}
            if r.get("share"):
                out.update({k: r[k] for k in ("description", "role") if k in r}, share=True)
        else:
            out = dict(r)
        if out:
            entries[entry_id] = out
    return {"version": 1, "entries": entries}


def asked(value):
    """A player's request cut to looks; what they write is shared with the table, as the plan has it."""
    if not isinstance(value, dict):
        raise ValueError("Invalid Flavor.")
    extra = [k for k in value if k not in ASKABLE]
    if extra:
        raise ValueError("Flavor can change looks only (not %s)." % ", ".join(sorted(extra)[:3]))
    record = clean("actor", value)
    if "description" in record or "role" in record:
        record["share"] = True
    return record


def clean_asks(asks):
    """The requests kept on disk; anything that no longer reads as one is dropped."""
    out = {}
    for actor, a in (asks or {}).items() if isinstance(asks, dict) else ():
        try:
            record = clean("actor", a["flavor"])
            out[actor] = {"actor": actor, "seat": str(a["seat"]), "character": str(a["character"]), "scope": str(a["scope"]), "flavor": record}
        except (KeyError, TypeError, ValueError):
            continue
    return out


class FlavorStore:
    """The collection on disk with a revision number: a page saves on the revision it read, so two consoles (the GM and
    a stand-in) never overwrite each other unseen. Players' requests beside it, with a revision of their own."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.state, self.rev = None, 0
        self.asks, self.asks_rev = {}, 0

    def _load(self):
        if self.state is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.state, self.rev = clean_state(data.get("flavor")), int(data.get("rev", 1))
                self.asks, self.asks_rev = clean_asks(data.get("asks")), int(data.get("asks_rev", 0))
            except (OSError, ValueError, TypeError, AttributeError):
                self.state, self.rev = {"version": 1, "entries": {}}, 0
                self.asks, self.asks_rev = {}, 0
        return self.state

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"rev": self.rev, "flavor": self.state, "asks_rev": self.asks_rev, "asks": self.asks}), encoding="utf-8")
        tmp.replace(self.path)

    def get(self):
        with self.lock:
            return self._load(), self.rev

    def save(self, state, base_rev):
        """Replace the collection; refused (Conflict) when it changed since the page read revision `base_rev`."""
        state = clean_state(state)
        with self.lock:
            self._load()
            if base_rev != self.rev:
                raise Conflict("Flavor was changed on another screen. Close Flavor and open it again, then make the change.")
            self.state, self.rev = state, self.rev + 1
            self._write()
            return self.state, self.rev

    def end_adventure(self, pack):
        with self.lock:
            state = self._load()
            nxt = end_adventure(state, pack)
            if nxt != state:
                self.state, self.rev = nxt, self.rev + 1
                self._write()

    # ------------------------------------------------------------------ PLAYER-FLAVOR-01: a player's request
    def ask(self, seat, character, actor, scope, value):
        """A player's look for a creature they control: it waits for the GM, in place of any request before it."""
        record = asked(value)
        with self.lock:
            self._load()
            self.asks[actor] = {"actor": actor, "seat": seat, "character": character, "scope": scope, "flavor": record}
            self.asks_rev += 1
            self._write()
        return record

    def waiting(self, character=None):
        """(requests, their revision): all for the GM, one player's own with `character`."""
        with self.lock:
            self._load()
            asks = [a for a in self.asks.values() if character is None or a["character"].casefold() == character.casefold()]
            return asks, self.asks_rev

    def rule(self, actor, approve):
        """The GM's answer. Approved, the look joins the collection on every map and replaces this map's copy, keeping what
        the GM wrote and never shared when the player asked for no footnote of their own. Refused, it is simply gone."""
        with self.lock:
            state = self._load()
            a = self.asks.get(actor)
            if not a:
                raise ValueError("That request is no longer waiting.")
            if approve:
                every, here = actor_key(EVERY_MAP, actor), actor_key(a["scope"], actor)
                entries, old, record = dict(state["entries"]), state["entries"].get(here) or state["entries"].get(every) or {}, dict(a["flavor"])
                if every not in entries and len(entries) >= MAX_ENTRIES:
                    raise ValueError("At most %d Flavor entries." % MAX_ENTRIES)
                if not old.get("share") and not ("description" in record or "role" in record):
                    record.update({k: old[k] for k in ("description", "role") if k in old})
                entries.pop(here, None)
                if record:
                    entries[every] = record
                else:
                    entries.pop(every, None)
                self.state, self.rev = {"version": 1, "entries": entries}, self.rev + 1
            del self.asks[actor]
            self.asks_rev += 1
            self._write()
            return self.state, self.rev


class Conflict(Exception):
    pass
