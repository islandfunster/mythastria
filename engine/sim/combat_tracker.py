"""COMBAT-TRACKER-01 (GM 2026-10-27: "We need a combat tracker"; asked, chose: on the GM's Play live and on every
player's screen, a player seeing the party and only the creatures the party sees now; a creature's health in words for
players, exact Hit Points and AC for the GM; a click on a row highlights its token or, while an attack or a spell is
aimed, picks that creature as the target; and an action dropped on a row targets that creature, the rules engine
checking it as on the map).

The fight's combatants in turn order, sent with every live snapshot (LiveFight.snapshot) and cut per seat
(tools/table_seats.py player_view). The order is the engine's own (sim/fake_fg.lua ordered(), sim/fight_state.py
ordered()): the initiative result, then the initiative bonus, then the name, then the id. Who acts now: the character the
fight waits for, otherwise the creature whose turn the log announced last ("<name>'s turn"). The live state is published
at a character's turn and at each choice, while the log comes as it happens, so the tracker follows the creatures' turns
too. In a social or exploration scene there is no initiative and no order.

SIGHT-01 (GM 2026-10-27: "when the combat tracker is launched, the DM must select which creatures can be seen according
to each player's vision by each player. If they are blind or in the dark, they don't see the creature unless it
radiates light. This is separate from the perceptions rules."; asked, chose: the list starts from the engine's own
sight, "Let's leave the engine decide what each character sees. If a room is lit, then the room lighting also applies",
and afterwards the engine takes over): `sight` is, for each standing character, the creatures it sees now: the
engine's own answer (Sim.sees: walls, light, darkvision, Blindsight, Blinded, a creature that sheds light), changed
only where the GM picked otherwise. A pick lasts while the engine's answer for that pair is still the one the GM saw
when picking; once the engine's answer changes (the creature moved, a light went out), the engine decides again. Each
seat's screen shows its own character's sight (tools/table_seats.py). The rules (attacks, spells) keep the engine's.
"""
import re

TURN = re.compile(r"^(.+)'s turn$")
ROUND = re.compile(r"^--- round (\d+) ---$")


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def order(combatants):
    """The engine's turn order: highest initiative first, then initiative bonus, then name, then id."""
    return sorted(combatants, key=lambda c: (-num(c.get("init"), 10), -num(c.get("init_bonus")), str(c.get("name", "")),
                                             str(c.get("id", ""))))


def init_shown(v):
    n = num(v, 10)
    return int(n) if n.is_integer() else n


def view(fight, log):
    """{order: [{id, init}], acting, round, concentration: {id: spell}, scene} for the fight now (`log`: its lines)."""
    sim = fight.sim
    scenes = getattr(fight, "scenes", None)
    if scenes and scenes.in_scene():
        return {"scene": True, "order": [], "acting": None, "round": None, "concentration": {}}
    cs = list(sim.sc["combatants"])
    by_name = {c.get("name"): c["id"] for c in cs}
    acting, rnd = (None, None)
    for e in reversed(log):                                    # the newest first
        if e.get("kind") != "turn":
            continue
        text = str(e.get("text", ""))
        m = TURN.match(text)
        if acting is None and m and m.group(1) in by_name:
            acting = by_name[m.group(1)]
        m = ROUND.match(text)
        if rnd is None and m:
            rnd = int(m.group(1))
        if acting is not None and rnd is not None:
            break
    if fight.waiting is not None:
        acting = fight.waiting
    if fight.done:
        acting = None
    concentration = {}
    party = getattr(sim, "party", None)
    for c in cs:
        try:
            spell = party.concentrates(c["id"]) if party else None
        except Exception:                                      # a creature the party rules don't know
            spell = None
        if spell:
            concentration[c["id"]] = spell
    out = {"scene": False, "order": [{"id": c["id"], "init": init_shown(c.get("init"))} for c in order(cs)],
           "acting": acting, "round": rnd, "concentration": concentration}
    out.update(sight_view(fight))
    return out


def engine_sight(fight):
    """{character id: [creature ids it sees]} from the last published state (party_sight seen_by, sim/map_layers.py)."""
    seen_by = ((getattr(fight, "snap", None) or {}).get("party_sight") or {}).get("seen_by") or {}
    pcs = {c["id"] for c in fight.sim.sc["combatants"] if c.get("pc")}
    return {p: [o for o in seen if o not in pcs] for p, seen in seen_by.items()}


def sight_view(fight):
    """Each character's sight now: the engine's, with the GM's picks still standing; a pick whose engine answer changed
    since is dropped (the engine decides again)."""
    picks = fight.__dict__.setdefault("sight_picks", {})       # {character: {creature: [seen, engine's answer then]}}
    engine = engine_sight(fight)
    sight, changed = {}, []
    for p, seen in engine.items():
        mine = set(seen)
        for o, (want, then) in list((picks.get(p) or {}).items()):
            if (o in seen) != then:
                del picks[p][o]                                # the engine's answer moved on: it decides again
                continue
            (mine.add if want else mine.discard)(o)
            changed.append([p, o])
        sight[p] = [o for o in (c["id"] for c in fight.sim.sc["combatants"]) if o in mine]
    return {"sight": sight, "sight_engine": engine, "sight_picked": changed,
            "sight_confirmed": bool(fight.__dict__.get("sight_confirmed"))}


def set_sight(fight, picks):
    """The GM's picks {character id: {creature id: seen}} (at the fight's start, or later on the tracker). A pick equal
    to the engine's answer is no pick. Raises ValueError on an unknown character or creature."""
    if not isinstance(picks, dict):
        raise ValueError("picks is {character: {creature: true or false}}.")
    ids = {c["id"]: c for c in fight.sim.sc["combatants"]}
    engine = engine_sight(fight)
    store = fight.__dict__.setdefault("sight_picks", {})
    for p, row in picks.items():
        if p not in ids or not ids[p].get("pc") or not isinstance(row, dict):
            raise ValueError("%s is not a character of this fight." % p)
        for o, want in row.items():
            if o not in ids or ids[o].get("pc") or not isinstance(want, bool):
                raise ValueError("%s is not a creature of this fight (seen: true or false)." % o)
            now = o in (engine.get(p) or [])
            if want == now:
                store.get(p, {}).pop(o, None)
            else:
                store.setdefault(p, {})[o] = [want, now]
    fight.sight_confirmed = True
    return sight_view(fight)


def player_cut(tracker, kept):
    """A seat's tracker: only the creatures its map keeps (the party, and the creatures the party sees now)."""
    if not isinstance(tracker, dict):
        return tracker
    out = {k: v for k, v in tracker.items() if not k.startswith("sight")}   # the GM's sight lists stay with the GM
    return dict(out, order=[r for r in tracker.get("order") or [] if r.get("id") in kept],
                acting=tracker.get("acting") if tracker.get("acting") in kept else None,
                concentration={k: v for k, v in (tracker.get("concentration") or {}).items() if k in kept})
