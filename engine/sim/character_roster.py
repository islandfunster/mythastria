"""The Characters roster check (RUST-DEPRECATE-01 parity item 2; GM 2026-10-20: "Deprecate the old Rust rules engine and
keep Python as the sole rules authority ... Archive Rust only after checking feature parity").

The same rules and messages as the deprecated Rust check (isles-table engine/src/characters.rs), so the Characters tool
can move to the simulator service (POST /api/characters) without anything changing for the player. The shared cases in
sim/character_cases.json prove the two agree (test_character_roster.py here; the browser runs them against the Rust
engine). Plain JSON in and out; no I/O apart from load_catalog().

A saved sheet ("isles-character/1"): identity (id, name, kind pc|npc), a small combat profile, artwork from the creature
manifest whose footprint matches the sheet's space, and any other sheet fields (kept as they are).
"""
import json
from pathlib import Path

FORMAT = "isles-character/1"
CATALOG_FORMAT = "mythastria-creature-catalog/1"
MAX_CHARACTERS, MAX_BYTES = 100, 180_000

IDENTITY = "Invalid character identity"
BOUNDS = "Combat values are outside this prototype's supported bounds"
ART = "Choose registered artwork with the correct grid footprint"
TOO_LARGE = "Character record is too large"
BAD_SHEET = "Invalid character sheet"
BAD_COLLECTION = "Invalid character collection"
FULL = "Maximum 100 characters per browser"
DUPLICATE = "Duplicate character ID"
UNSUPPORTED = "Unsupported command"

# (field, smallest, largest) for 32-bit integers in the Rust struct; damage_count is unsigned and defaults to 1
COMBAT_INTS = ("hp_max", "ac", "speed", "attack_bonus", "damage_bonus", "reach")
COMBAT_UINTS = ("damage_die", "damage_count")


def load_catalog(table_dir):
    """The approved creatures of the table's manifest (table_dir/creatures.json), or None when there is none."""
    if not table_dir:
        return None
    try:
        doc = json.loads((Path(table_dir) / "creatures.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("format") != CATALOG_FORMAT or not isinstance(doc.get("creatures"), list):
        return None
    return [t for t in doc["creatures"] if isinstance(t, dict) and isinstance(t.get("id"), str)]


def _int(v, unsigned=False):
    """A JSON integer as Rust's serde reads it into i32/u32 (no booleans, no fractions)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 53:
        v = int(v)
    if not isinstance(v, int):
        return False
    return 0 <= v < 2 ** 32 if unsigned else -2 ** 31 <= v < 2 ** 31


def parse(sheet):
    """The sheet as the Rust struct reads it, or None (BAD_SHEET). Extra fields are kept; damage_count defaults to 1."""
    if not isinstance(sheet, dict):
        return None
    for k in ("format", "id", "name", "kind", "token_id"):
        if not isinstance(sheet.get(k), str):
            return None
    space = sheet.get("space_ft")
    if isinstance(space, bool) or not isinstance(space, (int, float)):
        return None
    combat = sheet.get("combat")
    if not isinstance(combat, dict):
        return None
    combat = dict(combat)
    combat.setdefault("damage_count", 1)
    if not all(_int(combat.get(k)) for k in COMBAT_INTS) or not all(_int(combat.get(k), True) for k in COMBAT_UINTS):
        return None
    out = dict(sheet)
    out["combat"] = {k: int(v) if k in COMBAT_INTS + COMBAT_UINTS else v for k, v in combat.items()}
    return out


def validate(c, catalog):
    """The first problem with a parsed sheet, or None."""
    if c["format"] != FORMAT or not 0 < len(c["id"]) <= 100 or not c["name"].strip() or len(c["name"]) > 160 \
            or c["kind"] not in ("pc", "npc"):
        return IDENTITY
    k = c["combat"]
    if not (1 <= k["hp_max"] <= 1000 and 1 <= k["ac"] <= 40 and 5 <= k["speed"] <= 60 and k["speed"] % 5 == 0
            and abs(k["attack_bonus"]) <= 30 and 1 <= k["damage_die"] <= 100 and 1 <= k["damage_count"] <= 10
            and abs(k["damage_bonus"]) <= 100 and 5 <= k["reach"] <= 15 and k["reach"] % 5 == 0):
        return BOUNDS
    if not any(t.get("id") == c["token_id"] and t.get("approved") is True
               and isinstance(t.get("squares"), (int, float)) and abs(t["squares"] * 5 - c["space_ft"]) < 0.01
               for t in catalog or []):
        return ART
    if len(json.dumps(c, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        return TOO_LARGE
    return None


class Roster:
    """One browser's saved characters, as the Rust roster kept them: a failed command changes nothing."""

    def __init__(self, catalog):
        self.catalog, self.characters = catalog or [], []

    def apply(self, req):
        op = req.get("op") if isinstance(req, dict) else None
        err = None
        if op == "character_list":
            pass
        elif op == "character_roster_load":
            err = self._load(req.get("characters"))
        elif op == "character_save":
            err = self._save(req.get("character"))
        elif op == "character_delete":
            cid = req.get("character_id") if isinstance(req.get("character_id"), str) else ""
            self.characters = [c for c in self.characters if c["id"] != cid]
        else:
            err = UNSUPPORTED
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "characters": json.loads(json.dumps(self.characters))}

    def _load(self, sheets):
        if not isinstance(sheets, list):
            return BAD_COLLECTION
        parsed = [parse(s) for s in sheets]
        if any(p is None for p in parsed):
            return BAD_COLLECTION
        if len(parsed) > MAX_CHARACTERS:
            return FULL
        ids = set()
        for c in parsed:
            err = validate(c, self.catalog)
            if err:
                return err
            if c["id"] in ids:
                return DUPLICATE
            ids.add(c["id"])
        self.characters = parsed
        return None

    def _save(self, sheet):
        c = parse(sheet)
        if c is None:
            return BAD_SHEET
        err = validate(c, self.catalog)
        if err:
            return err
        for i, old in enumerate(self.characters):
            if old["id"] == c["id"]:
                self.characters[i] = c
                return None
        if len(self.characters) >= MAX_CHARACTERS:
            return FULL
        self.characters.append(c)
        return None
