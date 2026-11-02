"""ON-THE-FLY-01 (GM 2026-11-02: "Those tools should be able to handle on-the-fly- adventuring and available through remix"):
the GM's changes to the running fight, without starting it again. Creatures join as a summons does (sim/summons.py), each
with its own Initiative roll and attitude. The service calls join under the fight's lock and writes the log line after it,
because the log takes that lock itself. Undo step replays both in order (tools/sim_service.py live_fly)."""
import attitude
import summons


def number(sim, name):
    """The next free number for this kind of creature."""
    taken = [c["name"] for c in sim.sc["combatants"]]
    n = 1
    while "%s %d" % (name, n) in taken:
        n += 1
    return "%s %d" % (name, n)


def join(fight, block, name, spots, mood=None):
    """Creatures of one kind into the running fight at `spots` -> their names. A mood is an attitude (Hostile by default)."""
    sim, st = fight.sim, summons.of(fight.sim)
    made = []
    for x, y in spots:
        c = summons._clean(block)
        init, bonus = st.initiative(block=block)
        c.update(id=st.new_id(), name=number(sim, name), side="foe", x=x, y=y, init=init, init_bonus=bonus)
        if mood:
            c["attitude"] = mood
        attitude.apply({"combatants": [c], "optional_rules": sim.sc.get("optional_rules")})
        st._join(c)
        fight.attitudes.add(c)
        made.append(c["name"])
    return made


def joined(made):
    return "%s join%s the scene." % (", ".join(made), "" if len(made) > 1 else "s")
