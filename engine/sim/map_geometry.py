"""Read-only pixel/cell conversion for isolated rehearsals, not native FG pathfinding."""
from dataclasses import dataclass
import math


def finite(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('%s is missing or not numeric' % label) from None
    if not math.isfinite(result):
        raise ValueError('%s must be finite' % label)
    return result


@dataclass(frozen=True)
class MapGeometry:
    width: float
    height: float
    offset_x: float
    offset_y: float

    def __post_init__(self):
        for field in ('width', 'height', 'offset_x', 'offset_y'):
            object.__setattr__(self, field, finite(getattr(self, field), 'Grid ' + field))
        if self.width <= 0 or self.height <= 0:
            raise ValueError('Grid width and height must be positive')

    def cells(self, x, y):
        return ((finite(x, 'Token x') - self.offset_x) / self.width,
                (finite(y, 'Token y') - self.offset_y) / self.height)

    def pixels(self, x, y):
        return (finite(x, 'Cell x') * self.width + self.offset_x,
                finite(y, 'Cell y') * self.height + self.offset_y)

    def as_dict(self):
        return {field: getattr(self, field) for field in ('width', 'height', 'offset_x', 'offset_y')}


def captured_geometry(capture):
    """Require complete, consistent spatial snapshots linked to all CT positions.

    Capture is non-atomic: map/position agreement detects common stale transfers,
    but cannot certify freshness or native getter/axis semantics.
    """
    actors = capture.get('combat', {}).get('actors', {})
    tokens = capture.get('spatial', {}).get('tokens', {})
    if not actors:
        raise ValueError('No combatants for captured grid')
    reported = finite(capture.get('spatial', {}).get('reported_count'), 'Completed spatial count')
    if reported != len(tokens):
        raise ValueError('Incomplete spatial transfer; wait for sync complete and recapture')
    geometry = None
    for path, actor in actors.items():
        token = tokens.get(path)
        if not isinstance(token, dict) or token.get('ctpath') != path:
            raise ValueError('Spatial token missing or mislinked; run /aibridge syncspatial and recapture')
        raw = actor.get('raw_fields') or {}
        if not token.get('container_node') or token.get('container_node') != raw.get('pos.map'):
            raise ValueError('Spatial/combat map mismatch; refresh both snapshots')
        if str(token.get('map_open')) != '1' or token.get('grid_type') != 'square':
            raise ValueError('Captured grid requires an open square-grid map (rectangular cells allowed)')
        current = MapGeometry(token.get('grid_width'), token.get('grid_height'),
                              token.get('grid_offset_x'), token.get('grid_offset_y'))
        if geometry and any(abs(v - geometry.as_dict()[k]) > 1e-6 for k, v in current.as_dict().items()):
            raise ValueError('Conflicting captured grid geometry; refresh spatial snapshot')
        for axis in ('x', 'y'):
            # synccombat rounds centres to whole pixels, syncspatial retains fractions.
            if abs(finite(token.get(axis), 'Spatial ' + axis) - finite(raw.get('pos.' + axis), 'Combat ' + axis)) > 0.51:
                raise ValueError('Spatial/combat position mismatch; refresh both snapshots while paused')
        geometry = current
    return geometry
