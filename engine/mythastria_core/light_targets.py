"""LIGHTS-01 (GM 2026-10-26: "Simulator creatures take light into account when choosing targets they can see"): one
rule, kept apart from ai_turn.build_options (a thin hook there) so the Python creature turns can carry it over.

SRD 5.2.1 "Unseen Attackers and Targets": a creature attacking a target it can't see has Disadvantage and must guess
its location. A creature the simulator plays goes for the enemies it can see (light, Darkvision, Blindsight and walls:
the map's lighting, mythastria_core/lighting.py) when it sees any; when it sees none, every enemy it knows of stays a
choice (attacked with Disadvantage where it can't see it). Maps without lighting data: no change.
"""


def seen_first(opponents, sees, source):
    """The opponents this creature sees now, if it sees any; otherwise all of them. sees: ai_turn._sight's function or
    None (no lighting data)."""
    if not sees or not opponents:
        return opponents
    try:
        seen = [p for p in opponents if sees(source, p)]
    except Exception:                                            # positions missing: nothing to judge
        return opponents
    return seen or opponents
