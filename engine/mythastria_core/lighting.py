"""v0.7.81 LIGHT-01: light, darkness and darkvision (D&D 2024, SRD 5.2.1 Rules Glossary).

  Bright Light is normal illumination. Dim Light is Lightly Obscured: Disadvantage on Wisdom (Perception) checks to
  see something there. Darkness is Heavily Obscured: you have the Blinded condition while trying to see something
  there. Darkvision: within its range, Dim Light counts as Bright Light and Darkness as Dim Light.
  Unseen attackers and targets: an attack roll against a target you can't see has Disadvantage; when a creature
  can't see you, you have Advantage on attack rolls against it.

A map's lighting: {"ambient": "bright" | "dim" | "dark", "lights": [{"pos": (x, y), "bright": r, "dim": r}]} in the
same pixel frame as the token positions and wall segments; "dim" is the outer radius (a Torch: bright 20 ft, dim
for an additional 20 ft = 40 ft). Walls and closed doors stop light (a light behind a wall does not reach the point).
No lighting data means everything is in Bright Light (the behaviour before v0.7.81). LIGHTS-01 (2026-10-26): a light
with "dir" (degrees) shines only in a Cone that way (a Bullseye Lantern). Magical Darkness,
Hide/Invisible and Truesight are not modelled.

v0.7.91 (GM's rule, 2026-10-13): FG draws light and darkvision as circles, but they apply to the creature: a creature is
in Bright/Dim Light, or within a viewer's darkvision range, when MORE THAN HALF of its space is (5 x 5 sample points
spread over its space, centred on its token). Its space comes from the 2024 size table (space_ft). The viewer's eye
stays at its token's centre, and walls still block line of sight centre to centre.

v0.7.92: Blindsight ("can see things within a specific range of it without relying on physical sight"): within its range
(more than half of the target's space, as for darkvision) the light does not matter; walls still block.
"""
import math
import re

from map_walls import blocked as wall_blocked

DARK, DIM, BRIGHT = 0, 1, 2
AMBIENT = {"bright": BRIGHT, "dim": DIM, "dark": DARK}
NAMES = {DARK: "Darkness", DIM: "Dim Light", BRIGHT: "Bright Light"}


def darkvision_ft(senses):
    """'Darkvision 60 ft.; Passive Perception 9' -> 60 (0 when absent)."""
    m = re.search(r"darkvision\s*(\d+)", str(senses or ""), re.I)
    return int(m.group(1)) if m else 0


def blindsight_ft(senses):
    """'Blindsight 60 ft.; Passive Perception 6' -> 60 (0 when absent)."""
    m = re.search(r"blindsight\s*(\d+)", str(senses or ""), re.I)
    return int(m.group(1)) if m else 0


def _within(viewer, point, side, range_px):
    """More than half of the target's space (side > 0) or its centre is within range_px of the viewer."""
    pts = footprint(point, side) if side > 0 else [point]
    return sum(math.hypot(p[0] - viewer[0], p[1] - viewer[1]) <= range_px for p in pts) * 2 > len(pts)


# SRD 5.2.1 "Creature Size and Space" (FG's "space" field, e.g. 3.75 for Small, is only the token's drawn scale)
SPACE_FT = {"tiny": 2.5, "small": 5.0, "medium": 5.0, "large": 10.0, "huge": 15.0, "gargantuan": 20.0}


def space_ft(size, space=None):
    """A creature's space in feet: the CT "size" by the 2024 table; without it FG's "space" (3.75 counts as 5)."""
    ft = SPACE_FT.get(str(size or "").strip().lower())
    if ft:
        return ft
    try:
        sp = float(str(space).strip())
    except (TypeError, ValueError):
        return 5.0
    return 2.5 if 0 < sp <= 2.5 else max(5.0, sp)


def footprint(centre, side, n=5):
    """n x n points spread evenly over a square space of `side` (same units as centre), centred on the token."""
    half = side / 2.0
    return [(centre[0] - half + (i + 0.5) * side / n, centre[1] - half + (j + 0.5) * side / n)
            for i in range(n) for j in range(n)]


def creature_level(centre, side, lighting, segs=()):
    """The creature's light: Bright when more than half of its space is in Bright Light, else Dim when more than half
    is in Dim Light or brighter, else Darkness. side 0 = the exact point (the rule before v0.7.91)."""
    if side <= 0 or not lighting:
        return level_at(centre, lighting, segs)
    levels = [level_at(p, lighting, segs) for p in footprint(centre, side)]
    if sum(l == BRIGHT for l in levels) * 2 > len(levels):
        return BRIGHT
    return DIM if sum(l >= DIM for l in levels) * 2 > len(levels) else DARK


def level_at(point, lighting, segs=()):
    """Light level at a point: the ambient level, raised by every light that reaches it (no wall in between)."""
    if not lighting:
        return BRIGHT
    level = AMBIENT.get(str(lighting.get("ambient") or "bright"), BRIGHT)
    for light in lighting.get("lights") or []:
        if level == BRIGHT:
            break
        (lx, ly), bright, dim = light["pos"], float(light.get("bright") or 0), float(light.get("dim") or 0)
        d = math.hypot(point[0] - lx, point[1] - ly)
        if d > max(bright, dim) or (segs and wall_blocked((lx, ly), point, segs)):
            continue
        if light.get("dir") is not None and d > 1e-6 and not in_cone(light["dir"], point[0] - lx, point[1] - ly):
            continue                                             # LIGHTS-01: a Bullseye Lantern's Cone
        level = max(level, BRIGHT if d <= bright else DIM)
    return level


CONE_HALF_DEG = math.degrees(math.atan(0.5))   # SRD 5.2.1 Cone: its width at a point equals the distance from its origin


def in_cone(dir_deg, dx, dy):
    """LIGHTS-01 (2026-10-26): (dx, dy) from the light lies within the Cone pointing dir_deg (0 = +x, 90 = +y)."""
    off = (math.degrees(math.atan2(dy, dx)) - float(dir_deg) + 180.0) % 360.0 - 180.0
    return abs(off) <= CONE_HALF_DEG + 1e-6


def seen_level(viewer, point, lighting, segs, darkvision_px, side=0):
    """The light level as this viewer perceives it (darkvision raises it one step within its range). side > 0: the
    target creature's space (v0.7.91): its light and the darkvision range count when more than half of it is in."""
    level = creature_level(point, side, lighting, segs)
    if darkvision_px > 0 and level < BRIGHT and _within(viewer, point, side, darkvision_px):
        level += 1
    return level


def blindsight_reaches(viewer, point, side, range_px, viewer_side=0, grid=0):
    """v0.8.4 (GM 2026-10-15): Blindsight range counts from the edge of the viewer's space to the nearest square of the
    target's, as every grid range does (5 ft = the next square). Without a grid: the v0.7.92 rule (more than half of the
    target's space within range of the viewer's centre)."""
    if not grid:
        return _within(viewer, point, side, range_px)
    vs, ts = viewer_side or grid, side or grid
    gx = max(0.0, abs(point[0] - viewer[0]) - (vs + ts) / 2)
    gy = max(0.0, abs(point[1] - viewer[1]) - (vs + ts) / 2)
    return max(gx, gy) + grid <= range_px + 1e-6


def can_see(viewer, point, lighting, segs, darkvision_px, side=0, blindsight_px=0, viewer_side=0, grid=0):
    """Line of sight (no wall or closed door between the centres) and the target not in Darkness for this viewer
    (side: the target's space, v0.7.91), or within the viewer's Blindsight (v0.7.92; v0.8.4: from the edge of the
    viewer's space when the grid is given)."""
    if segs and wall_blocked(viewer, point, segs):
        return False
    if blindsight_px > 0 and blindsight_reaches(viewer, point, side, blindsight_px, viewer_side, grid):
        return True
    return seen_level(viewer, point, lighting, segs, darkvision_px, side) > DARK


def attack_mode(attacker_sees, target_sees):
    """'adv', 'dis' or '' for an attack roll (SRD 5.2.1 "Unseen Attackers and Targets"; both cancel)."""
    adv, dis = not target_sees, not attacker_sees
    return "adv" if adv and not dis else "dis" if dis and not adv else ""
