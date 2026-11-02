"""DICE-TOOL-01 (GM 2026-10-19: "The UI needs a dice tool for when dice rolls need to be made outside the mechanics"):
free rolls the GM or a player asks for (an improvised check, a random table, a wandering-monster die). The reference
for the ports, like sim/stage.py: no I/O, no clock, and the dice come from `rng(sides) -> 1..sides` given by the caller
(the service uses the system's secure random; the shared cases in sim/dice_cases.json use scripted dice).

Notation: terms joined by + or -: NdS (N 1-100; S one of the standard dice 4, 6, 8, 10, 12, 20, 100; "d20" = "1d20"),
NdSkhK / NdSklK (keep the K highest / lowest: 2d20kh1 is advantage, 2d20kl1 disadvantage, 4d6kh3 an ability score), and
whole numbers (the bonus or penalty: each 0-100, and -100 to +100 in all). Dice of different sizes mix in one roll
(DICE-POOL-01, GM 2026-10-21: "mix dice and add fixed bonuses": 2d6 + 1d8 + 3). At most 100 dice and 10 terms; spaces
are ignored; case does not matter. The text shows each die with its faces: "2d6 [3, 5] + 1d8 [7] + 3 = 18". The result
never touches the game: nothing here is applied to a character, a creature or the fight.
"""
import re

CASES_FORMAT = "dice-cases/1"
MAX_DICE, MAX_TERMS, MAX_TEXT, MAX_LABEL = 100, 10, 60, 60
SIDES, MAX_BONUS = (4, 6, 8, 10, 12, 20, 100), 100
TERM = re.compile(r"([+-]?)(?:(\d*)d(\d+)(?:(kh|kl)(\d+))?|(\d+))")


class DiceError(ValueError):
    pass


def parse(expr):
    """'2d20kh1 + 5' -> [{'sign': 1, 'n': 2, 'sides': 20, 'keep': ('kh', 1)}, {'sign': 1, 'const': 5}]."""
    if not isinstance(expr, str):
        raise DiceError("Dice: write the roll as text, e.g. 1d20+3.")
    text = re.sub(r"\s*([+-])\s*", r"\1", expr.strip()).lower()      # spaces only around + and - ("2d6 3" is not 2d63)
    if not text:
        raise DiceError("Dice: what should be rolled? e.g. 1d20+3")
    if re.search(r"\s", text):
        raise DiceError("Dice: cannot read %r. Use terms like 2d6, d20, 4d6kh3, +3 or -1." % expr.strip())
    if len(text) > MAX_TEXT:
        raise DiceError("Dice: that roll is too long (%d characters at most)." % MAX_TEXT)
    terms, pos, dice = [], 0, 0
    while pos < len(text):
        m = TERM.match(text, pos)
        if not m or m.end() == pos or (pos > 0 and not m.group(1)):
            raise DiceError("Dice: cannot read %r. Use terms like 2d6, d20, 4d6kh3, +3 or -1." % expr.strip())
        sign = -1 if m.group(1) == "-" else 1
        if m.group(6) is not None:
            if int(m.group(6)) > MAX_BONUS:
                raise DiceError("Dice: a bonus or penalty of %d at most." % MAX_BONUS)
            terms.append({"sign": sign, "const": int(m.group(6))})
        else:
            n, sides = int(m.group(2) or 1), int(m.group(3))
            if sides not in SIDES:
                raise DiceError("Dice: only d4, d6, d8, d10, d12, d20 and d100.")
            if not 1 <= n <= MAX_DICE:
                raise DiceError("Dice: 1 to %d dice in one roll." % MAX_DICE)
            t = {"sign": sign, "n": n, "sides": sides}
            if m.group(4):
                k = int(m.group(5))
                if not 1 <= k <= n:
                    raise DiceError("Dice: keep between 1 and %d of %dd%d." % (n, n, sides))
                t["keep"] = (m.group(4), k)
            dice += n
            terms.append(t)
        pos = m.end()
    if dice > MAX_DICE or len(terms) > MAX_TERMS:
        raise DiceError("Dice: at most %d dice and %d terms in one roll." % (MAX_DICE, MAX_TERMS))
    if not dice:
        raise DiceError("Dice: roll at least one die.")
    if abs(sum(t["sign"] * t["const"] for t in terms if "const" in t)) > MAX_BONUS:
        raise DiceError("Dice: the bonus or penalty is -%d to +%d in all." % (MAX_BONUS, MAX_BONUS))
    return terms


def canonical(terms):
    out = ""
    for i, t in enumerate(terms):
        sign = "-" if t["sign"] < 0 else ("+" if i else "")
        if "const" in t:
            out += sign + str(t["const"])
        else:
            out += "%s%dd%d" % (sign, t["n"], t["sides"]) + ("%s%d" % t["keep"] if "keep" in t else "")
    return out


def roll(expr, rng, who="", label=""):
    """Roll it. Returns {'expr', 'total', 'terms', 'natural', 'text'}; raises DiceError for a bad expression.
    'natural' is 20 or 1 when exactly one added term keeps a single d20 (a d20 test: 1d20, 2d20kh1), else None."""
    terms = parse(expr)
    label = (label or "").strip()[:MAX_LABEL]
    total, parts, shown = 0, [], []
    for t in terms:
        if "const" in t:
            total += t["sign"] * t["const"]
            parts.append(dict(t))
            shown.append(("- " if t["sign"] < 0 else "+ ") + str(t["const"]))
            continue
        rolls = [int(rng(t["sides"])) for _ in range(t["n"])]
        if any(not 1 <= r <= t["sides"] for r in rolls):
            raise DiceError("Dice: the dice gave an impossible number.")
        kept = list(range(len(rolls)))
        if "keep" in t:
            how, k = t["keep"]
            order = sorted(kept, key=lambda i: (-rolls[i], i) if how == "kh" else (rolls[i], i))
            kept = sorted(order[:k])
        sub = sum(rolls[i] for i in kept)
        total += t["sign"] * sub
        parts.append({"sign": t["sign"], "dice": "%dd%d" % (t["n"], t["sides"]) + ("%s%d" % t["keep"] if "keep" in t else ""),
                      "rolls": rolls, "kept": kept, "subtotal": sub})
        face = "[" + ", ".join(str(r) if i in kept else "(%d)" % r for i, r in enumerate(rolls)) + "]"
        shown.append(("- " if t["sign"] < 0 else ("+ " if shown else "")) + parts[-1]["dice"] + " " + face)
    d20s = [p for p in parts if "dice" in p and p["sign"] > 0 and re.fullmatch(r"\d+d20(k[hl]1)?", p["dice"])
            and len(p["kept"]) == 1]
    natural = None
    if len(d20s) == 1:                                         # one d20 decides (Bless's d4 may ride along)
        face = d20s[0]["rolls"][d20s[0]["kept"][0]]
        natural = face if face in (1, 20) else None
    expr_c = canonical(terms)
    text = "%s rolls %s%s: %s = %d" % (who or "Someone", expr_c, " (%s)" % label if label else "", " ".join(shown), total)
    if natural:
        text += " · natural %d" % natural
    return {"expr": expr_c, "label": label, "total": total, "terms": parts, "natural": natural, "text": text}


def run_case(case):
    """Play one case from dice_cases.json with its scripted dice; returns a list of mismatches."""
    faces = list(case.get("dice", []))

    def rng(sides):
        if not faces:
            raise AssertionError("the case ran out of scripted dice")
        return faces.pop(0)

    try:
        got = roll(case["expr"], rng, case.get("who", ""), case.get("label", ""))
    except DiceError as e:
        got = {"error": str(e)}
    problems = []
    for k, want in case["expect"].items():
        if got.get(k) != want:
            problems.append("%s %s: want %r, got %r" % (case["name"], k, want, got.get(k)))
    return problems
