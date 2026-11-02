"""MAP-PAINT-01 (GM 2026-10-27, Flavor: "I want the DM to be able to draw/paint on the map and erase what he did. It would
need to add an alpha channel on top of the map"; then: the GM reveals it on/off, and it is kept per map): a transparent
picture painted over each map by the GM, and whether the players see it.

Kept per map name in sim/flavor/map_paint.json (campaign data, not committed; a test port keeps its own file): the picture
(a PNG or WebP data URL with its alpha channel, the size the page chose for the map) and "shown". Each change raises the
map's revision, so a page fetches the picture only when it changed. The GM's console reads and writes it
(/api/map_paint, /api/map_paint/save); a seat at the players' door and the players' window get it only while it is shown.
Presentation only: nothing here is read by the rules.
"""
import json
import re
import threading
from pathlib import Path

MAX_PICTURE = 12 * 1024 * 1024                                   # characters of the data URL
PICTURE = re.compile(r"^data:image/(png|webp);base64,[A-Za-z0-9+/]+=*$")


class PaintError(ValueError):
    pass


class MapPaint:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.maps = None

    def _load(self):
        if self.maps is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.maps = {str(k): v for k, v in (data.get("maps") or {}).items() if isinstance(v, dict)}
            except (OSError, ValueError, TypeError, AttributeError):
                self.maps = {}
        return self.maps

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"maps": self.maps}), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _key(name):
        name = str(name or "").strip()
        if not 0 < len(name) <= 256:
            raise PaintError("Which map? Its name is missing.")
        return name

    def get(self, name, rev=None, player=False):
        """{map, rev, shown, picture?}: the picture only when it changed since `rev` (and, for a player, is shown)."""
        key = self._key(name)
        with self.lock:
            m = self._load().get(key) or {}
        out = {"map": key, "rev": int(m.get("rev") or 0), "shown": bool(m.get("shown"))}
        if player and not out["shown"]:
            out["rev"] = -1 if out["rev"] else 0                 # nothing to see: no picture, no revision to follow
            return out
        if rev is None or int(rev) != out["rev"]:
            out["picture"] = m.get("picture") or ""
        return out

    def save(self, name, picture=None, shown=None):
        """A new picture ("" erases it all) and/or the shown flag; -> get()."""
        key = self._key(name)
        if picture is not None:
            if not isinstance(picture, str) or (picture and not PICTURE.match(picture)):
                raise PaintError("The paint is a PNG or WebP picture.")
            if len(picture) > MAX_PICTURE:
                raise PaintError("The paint is too large (%d MB at most)." % (MAX_PICTURE // (1024 * 1024)))
        if shown is not None and not isinstance(shown, bool):
            raise PaintError("Shown is yes or no.")
        with self.lock:
            maps = self._load()
            m = dict(maps.get(key) or {})
            if picture is not None:
                m["picture"] = picture
            if shown is not None:
                m["shown"] = shown
            m["rev"] = int(m.get("rev") or 0) + 1
            if not m.get("picture") and not m.get("shown"):
                m = {"rev": m["rev"]}                            # empty and hidden: only the revision stays
            maps[key] = m
            self._write()
        return self.get(key)
