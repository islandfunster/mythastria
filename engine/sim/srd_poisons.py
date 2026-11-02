"""GM 2026-10-23 (the SRD parts still to build): the SRD 5.2.1 poisons (Gameplay Toolbox: Poison; Sample Poisons), read
from the SRD text: the price of one dose, the type, and the effect. Market (sim/market.py load_catalog) sells them as SRD
items; Play live uses the injury and inhaled ones in a fight (sim/live_items.py), the rules engine applies the effect
(apply below; gm_rules.GmRules wakes a sleeper on damage and repeats Burnt Othur Fumes' save).

Types (SRD): injury: a Bonus Action applies it to a weapon or a piece of ammunition; potent until delivered through a
wound (Piercing or Slashing damage) or washed off. Inhaled: blowing the powder or releasing the gas subjects the
creatures in a 5-foot Cube. Contact and ingested poisons have no use in a fight here (the GM rules them).
"""
POISONS = {
    "assassins-blood": dict(name="Assassin's Blood", gp=150, type="ingested", dc=10, dmg="1d12", half=True, cond=["Poisoned"]),
    "burnt-othur-fumes": dict(name="Burnt Othur Fumes", gp=500, type="inhaled", dc=13, dmg="3d6", fumes=True),
    "crawler-mucus": dict(name="Crawler Mucus", gp=200, type="contact", dc=13, cond=["Poisoned", "Paralyzed"]),
    "essence-of-ether": dict(name="Essence of Ether", gp=300, type="inhaled", dc=15, cond=["Poisoned", "Unconscious"], wakes=True, shake=True),
    "malice": dict(name="Malice", gp=250, type="inhaled", dc=15, cond=["Poisoned", "Blinded"]),
    "midnight-tears": dict(name="Midnight Tears", gp=1500, type="ingested", dc=17, dmg="9d6", half=True),
    "oil-of-taggit": dict(name="Oil of Taggit", gp=400, type="contact", dc=13, cond=["Poisoned", "Unconscious"], wakes=True),
    "pale-tincture": dict(name="Pale Tincture", gp=250, type="ingested", dc=16, dmg="1d6", cond=["Poisoned"]),
    "purple-worm-poison": dict(name="Purple Worm Poison", gp=2000, type="injury", dc=21, dmg="10d6", half=True),
    "serpent-venom": dict(name="Serpent Venom", gp=200, type="injury", dc=11, dmg="3d6", half=True),
    "spiders-sting": dict(name="Spider's Sting", gp=200, type="injury", dc=13, cond=["Poisoned"], by5=["Unconscious"], wakes=True,
                          shake=True),
    "torpor": dict(name="Torpor", gp=600, type="ingested", dc=15, cond=["Poisoned"]),
    "truth-serum": dict(name="Truth Serum", gp=150, type="ingested", dc=11, cond=["Poisoned"]),
    "wyvern-poison": dict(name="Wyvern Poison", gp=1200, type="injury", dc=14, dmg="7d6", half=True),
}
FIGHT_TYPES = ("injury", "inhaled")


def catalog_items():
    """The Market's catalog lines for the poisons (sold as SRD 5.2.1 items, at the suggested price of one dose)."""
    return [{"id": pid, "name": p["name"], "kind": "poison", "cost_cp": p["gp"] * 100, "poison": p["type"],
             "source": "SRD 5.2.1, Gameplay Toolbox: Poison"} for pid, p in POISONS.items()]


def effect_text(p):
    out = []
    if p.get("dmg"):
        out.append("%s Poison%s" % (p["dmg"], ", half on a success" if p.get("half") else ""))
    if p.get("cond"):
        out.append(" and ".join(p["cond"]))
    if p.get("by5"):
        out.append("failing by 5 or more: " + " and ".join(p["by5"]))
    if p.get("fumes"):
        out.append("the save again at the start of each of its turns (1d6 on a failure) until three successes")
    return "DC %d Constitution save: %s" % (p["dc"], "; ".join(out))


def apply(sim, src, t, pid, label=None):
    """Expose creature t to poison pid (src: who used it): the save, then damage and conditions. -> saved."""
    import party as party_mod
    p, gm = POISONS[pid], sim.gm_rules
    c = sim.by_id(t)
    name = label or p["name"]
    if gm.cond_immune(t, "poisoned") and not p.get("dmg"):
        sim.say("dice", "%s is immune to the Poisoned condition: %s has no effect" % (c["name"], name))
        return True
    parts, rng = gm.save_parts(t, "con"), sim.rng
    d20 = rng.randint(1, 20)
    adv = gm.antitoxin(t, "Poisoned")
    rolls = "d20 %d" % d20
    if adv:
        second = rng.randint(1, 20)
        rolls, d20 = "d20 %d/%d (Antitoxin: Advantage)" % (d20, second), max(d20, second)
    total = d20 + parts["bonus"]
    saved = total >= p["dc"]
    sim.say("dice", "%s Constitution save against %s: %s %+d = %d vs DC %d -> %s" % (
        c["name"], name, rolls, parts["bonus"], total, p["dc"], "success" if saved else "failure"))
    if p.get("dmg") and (not saved or p.get("half")):
        dmg = party_mod.roll(rng, p["dmg"])
        dmg = dmg // 2 if saved else dmg
        sim.say("dice", "%s: %s = %d Poison damage%s" % (name, p["dmg"], dmg, " (half)" if saved else ""))
        if dmg:
            sim.S.pcDamage(src, t, "", dmg, False, "poison")
            sim.settle(0.2)
    if saved or sim.down(t):
        return saved
    conds = list(p.get("cond") or [])
    if p.get("by5") and p["dc"] - total >= 5:
        conds += p["by5"]
    if conds and gm.cond_immune(t, "poisoned"):
        sim.say("dice", "%s is immune to the Poisoned condition" % c["name"])
        return saved
    for n in conds:
        gm.add(t, n, "(%s)" % name, by=src, poison=pid, wakes=bool(p.get("wakes")) and n == "Unconscious",
               shake=bool(p.get("shake")) and n == "Unconscious")
        if n == "Unconscious":
            gm.add(t, "Prone", "(falls: %s)" % name, by=src)
    if p.get("fumes"):
        gm.__dict__.setdefault("fumes", {})[t] = {"by": src, "dc": p["dc"], "ok": 0, "name": name}
    return saved
