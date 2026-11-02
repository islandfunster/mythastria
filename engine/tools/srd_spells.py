"""REFEREE-01 (GM 2026-10-22: "is there an agent that is expert on spell rules and double checks all aspects of the rules
are followed? It would need to be something built into the game itself." ... "for instance sleep spell can choose to not
affect a creature in its AoE. So yes build it"). Step 1: the spell rule sheet. Every SRD 5.2.1 spell (CC-BY-4.0), read
from the SRD's own words (the header fields and the description text; not any program's encoding of them) into one data
file the referee and the engine share: sim/spells/srd_spells.json.

Per spell: level, school, classes, casting time (action / bonus / reaction / longer), ritual, range (feet, Self, Touch),
components (V, S, M with a cost and whether it is consumed), duration and Concentration; how it picks its targets (one or
several creatures, "of your choice", an area: Cone, Cube, Cylinder, Emanation, Line, Sphere and its size); a spell attack
(melee or ranged) or a saving throw (ability; half on a success only when the text says so); damage (dice and type);
healing; the conditions it gives; how it grows (a higher-level slot, a cantrip's character level). What the reader cannot
pin down stays in "unread" so the coverage list says so instead of guessing. Parser only (GM: "No, parser only").

GM 2026-11-01 ("Yes, rebuild it"): the words come from the official SRD 5.2.1 PDF, which decides what is SRD, and from nothing
else. The PDF is not in this repository: MYTHASTRIA_SRD_PDF names it, and building needs pypdf. The game reads only the file
this writes.

  py tools/srd_spells.py            writes sim/spells/srd_spells.json and prints the counts
"""
import os
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = Path(os.environ.get("MYTHASTRIA_SRD_PDF") or "SRD_CC_v5.2.1.pdf")
PAGES = (106, 176)                                               # the pages of Spell Descriptions (printed 107 to 176)
MIDDLE, FOOT = 300, 40                                           # points: the gap between the two columns; the page footer lies below
OUT = ROOT / "sim" / "spells" / "srd_spells.json"
FORMAT = "srd-spells/1"
SRD = ("This work includes material from the System Reference Document 5.2.1 (\"SRD 5.2.1\") by Wizards of the Coast LLC, "
       "available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 "
       "International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.")
ABILITIES = ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma")
CONDITIONS = ("Blinded", "Charmed", "Deafened", "Exhaustion", "Frightened", "Grappled", "Incapacitated", "Invisible",
              "Paralyzed", "Petrified", "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious")
DAMAGE = ("Acid", "Bludgeoning", "Cold", "Fire", "Force", "Lightning", "Necrotic", "Piercing", "Poison", "Psychic",
          "Radiant", "Slashing", "Thunder")
SHAPES = ("Cone", "Cube", "Cylinder", "Emanation", "Line", "Sphere")


HEADER = re.compile(r"(?:Level (\d) (\w+)|(\w+) Cantrip) \((.*)$")
FIELDS = (("castingtime", "Casting Time:"), ("range", "Range:"), ("components", "Component"), ("duration", "Duration:"))   # 12 spells say "Component:"
LOWER = {"a", "an", "and", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "via", "with", "without"}
SHORT, WIDE, INDENT = 34, 48, 8                                  # a wrapped line is longer than SHORT; a paragraph's indent in points
END = (".", ":", "!", "?", ")", '"')
STAT = re.compile(r"(MOD SAVE|Str |Int |AC |HP |Speed |Skills |Senses |Languages |CR |Immunities |Resistances |Traits|Actions|Bonus Actions|Reactions)")


def page_lines(page):
    """A page's lines, left column then right, each top to bottom. The PDF stores some pages' columns the other way round and
    floats stat blocks among them, so the order comes from where each line sits on the page."""
    rows = []

    def visit(text, cm, tm, font, size):
        x, y = tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        if text.strip() and y > FOOT:
            name = str((font or {}).get("/BaseFont", ""))
            text = text.rstrip("\n")
            rows.append((x, y, name, text.title() if "-SC" in name else text))   # small capitals: "WiS" is Wis

    page.extract_text(visitor_text=visit)
    lines = []
    for x, y, font, text in rows:
        right = x >= MIDDLE
        if lines and lines[-1]["right"] == right and abs(lines[-1]["y"] - y) < 2:
            left = lines[-1]["text"][-1:]                        # a gap can be kept by position alone
            lines[-1]["text"] += (" " if (left.isalnum() or left in (".", ":", ";", ",")) and text[:1].isalnum() else "") + text
        else:
            lines.append({"right": right, "x": x, "y": y, "font": font, "first": text, "text": text})
    out = []
    for l in sorted(lines, key=lambda l: (l["right"], -l["y"])):
        if out and out[-1]["right"] == l["right"] and abs(out[-1]["y"] - l["y"]) < 2:        # tables side by side
            a, b = sorted((out[-1], l), key=lambda q: q["x"])
            out[-1] = dict(a, text=a["text"].rstrip() + " " + b["text"].lstrip())
        else:
            out.append(l)
    return out


def chapter(path=PDF):
    """The lines of Spell Descriptions in reading order: {"text", "body" (the spells' own words, not a table or a stat block),
    "lead" (a bold lead-in opens the line), "space" (a leading space), "off" (points in from the column's edge)}."""
    import pypdf
    lines = []
    for page in pypdf.PdfReader(str(path)).pages[PAGES[0]:PAGES[1]]:
        lines += page_lines(page)
    out = []
    for l in lines:
        text = l["text"].replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
        out.append({"text": text, "body": "Cambria" in l["font"], "space": text.startswith(" "),
                    "lead": "Cambria-Bold" in l["font"] and l["first"].rstrip().endswith((".", ":")),   # not a bold name in a sentence
                    "off": l["x"] - (313.5 if l["right"] else 63)})
    names = [l["text"].strip() for l in out]
    return out[names.index("Spell Descriptions") + 1:names.index("Rules Glossary")]


def spell_name(line):
    """A heading set in small capitals comes out as "Acid SplASh"."""
    words = line.strip().lower().split()
    return " ".join(w if i and w in LOWER else "/".join(p[:1].upper() + p[1:] for p in w.split("/")) for i, w in enumerate(words))


def whole_words(lines):
    """Every word the chapter prints unbroken: the two halves of a word split at a line's end don't count."""
    seen, split = set(), False
    for l in lines:
        words, broken = re.findall(r"[A-Za-z]+", l["text"]), l["text"].rstrip().endswith("-")
        seen.update(w.lower() for w in words[1 if split else 0:len(words) - broken])
        split = broken
    return seen


def joined(a, b, seen):
    """Two wrapped lines of one paragraph. "dam -" + "age" and "Ra-" + "diant" are one word. A hyphen stays when both halves
    are words and together they aren't ("long-" + "dead"), and after a number ("10-" + "foot")."""
    if a.endswith(" -"):
        return a[:-2] + b
    if a.endswith("-"):
        left, right = re.search(r"([A-Za-z]*)-$", a).group(1).lower(), re.match(r"[A-Za-z]*", b).group(0).lower()
        return a + b if not left or (left in seen and right in seen and left + right not in seen) else a[:-1] + b
    return a + b if a.endswith("\u2014") else a + " " + b


def tidy(s):
    return re.sub(r" {2,}", " ", s.strip()).replace("\u2013", "-").replace("\u2212", "-")


def table_rows(rows, seen):
    """A table's or a stat block's lines, one row to a line. A row opens with a number or a stat block's label; its wrapped
    lines stand further in than its first, or follow a long line that stops mid-sentence."""
    out, base, wide = [], 0, False
    for r in rows:
        line = tidy(r["text"])
        opens = (re.match(r"\d+(-\d+)? ", line) and not wide) or STAT.match(line)
        if out and (out[-1].endswith("-") or line[0].islower() or (not opens and (r["off"] > base + 5 or wide))):
            out[-1] = joined(out[-1], line, seen)
        else:
            out.append(line)
            base = r["off"]
        wide = len(line) >= WIDE and not line.endswith(END)
    return out


def paragraphs(rows, seen):
    """A spell's lines -> its text, one paragraph to a line. A paragraph starts with a leading space, an indent past the line
    before, a bold lead-in, a bullet, after a line that ends in a colon, or after a short line. A bullet or a lead-in opens a
    list item, whose wrapped lines can stand further in. A table or a stat block keeps its own rows, and one that splits a
    paragraph of the spell's words waits until that paragraph ends."""
    out, held, last, off, fresh, item, hang = [], [], "", 0, False, False, None
    for r in rows:
        line = tidy(r["text"])
        if not line:
            continue
        if not r["body"]:
            held.append(r)
            continue
        closed = not out or out[-1].endswith(END)
        if held and closed:
            out += table_rows(held, seen)
            held, fresh = [], True
        bullet, lead = line[0] == "\u2022", r["lead"] and closed
        back = hang is not None and r["off"] < hang - 2          # out of a hanging item, or a paragraph's own indent after one
        shift = (closed and (back or (r["off"] > off + 5 and abs(r["off"] - INDENT) < 1.5))) if item else r["off"] > off + 5
        if (fresh or not out or r["space"] or lead or bullet or out[-1].endswith(":") or (shift and not line[0].islower())
                or (len(last) < SHORT and not line[0].islower())):
            out.append(line)
            item, hang = bullet or lead, None
        else:
            out[-1] = joined(out[-1], line, seen)
            hang = r["off"] if hang is None else hang
        last, off, fresh = line, r["off"], False
    return "\n".join(out + table_rows(held, seen))


def records(path=PDF):
    lines = chapter(path)
    seen = whole_words(lines)
    starts = [i - 1 for i, l in enumerate(lines) if HEADER.match(l["text"].strip())]
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        block = lines[a:b]
        rows = [l["text"].strip() for l in block]
        head = HEADER.match(rows[1])
        f = {"name": spell_name(rows[0]), "level": head.group(1) or "0", "school": head.group(2) or head.group(3)}
        i, source = 2, head.group(4)
        while not rows[i].startswith(FIELDS[0][1]):              # the class list can wrap
            source, i = joined(source.strip(), rows[i], seen), i + 1
        f["source"] = source.strip().rstrip(")")
        for (key, label), (_, after) in zip(FIELDS, FIELDS[1:] + (("", None),)):
            value = rows[i].split(":", 1)[1].strip()
            i += 1
            while after and not rows[i].startswith(after):
                value, i = joined(value, rows[i], seen), i + 1
            f[key] = tidy(value)
        f["ritual"] = "1" if "ritual" in f["castingtime"].lower() else "0"
        f["text"] = paragraphs(block[i:], seen)
        yield f


def _feet(s):
    m = re.search(r"(\d+)[- ](?:foot|feet)", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+) mile", s)
    return int(m.group(1)) * 5280 if m else None


def casting_time(s):
    s = s.lower()
    for k in ("bonus action", "reaction", "action"):
        if s.startswith(k):
            return k.replace(" ", "_")
    return "long"            # 1 minute, 10 minutes, 1 hour ...


def range_of(s):
    s = s.strip()
    if s.lower().startswith("self"):
        return {"kind": "self", "ft": 0}
    if s.lower() == "touch":
        return {"kind": "touch", "ft": 5}
    ft = _feet(s)
    return {"kind": "ranged", "ft": ft} if ft else {"kind": "special", "ft": None, "text": s}


def components(s):
    out = {"v": bool(re.search(r"\bV\b", s)), "s": bool(re.search(r"\bS\b", s)), "m": bool(re.search(r"\bM\b", s))}
    m = re.search(r"M \((.*)\)", s)
    if m:
        out["material"] = m.group(1)
        cost = re.search(r"([\d,]+)\+? ?GP", m.group(1))
        out["cost_gp"] = int(cost.group(1).replace(",", "")) if cost else 0
        out["consumed"] = "consume" in m.group(1).lower()
    return out


def duration(s):
    conc = s.lower().startswith("concentration")
    return {"text": s, "concentration": conc, "instant": s.lower() == "instantaneous"}


def first_paragraph(text):
    """The spell's own effect, before "Using a Higher-Level Spell Slot" / "Cantrip Upgrade"."""
    return re.split(r"\n\s*(Using a Higher-Level Spell Slot|Cantrip Upgrade)\b", text)[0]


def area_of(text):
    """The first area the text names: "a 20-foot-radius Sphere", "a 15-foot Cone", "a 60-foot-long, 5-foot-wide Line"."""
    for m in re.finditer(r"(\d+)-foot(?:-(?:radius|long|wide|high|tall))?,?(?: \d+-foot-(?:wide|high|tall))?[ -]([A-Z][a-z]+)", text):
        shape = m.group(2)
        if shape not in SHAPES:
            continue
        out = {"shape": shape.lower(), "size_ft": int(m.group(1))}
        if shape == "Line":
            w = re.search(r"(\d+)[- ](?:foot|feet)[- ]wide", text)
            out["width_ft"] = int(w.group(1)) if w else 5
        if shape == "Cylinder":
            h = re.search(r"(\d+)[- ](?:foot|feet)[- ](?:high|tall)", text)
            if h:
                out["height_ft"] = int(h.group(1))
        out["origin"] = "self" if shape in ("Cone", "Line", "Emanation") else "point"
        return out
    return None


def objects_of(name):
    """SPELL-OBJECTS-01: whether the spell targets objects too (sim/spell_objects.py, read by hand from each text)."""
    sys.path.insert(0, str(ROOT / "sim"))
    import spell_objects
    return spell_objects.objects(name)


def targets_of(text, area):
    t = {"choice": bool(re.search(r"(creatures?|targets?) of your choice", text)), "max": None, "kind": None}
    m = re.search(r"\b(up to (\w+)|one|two|three|a|an) (?:willing |other )?(?:\w+ )?(creatures?|targets?|Humanoids?|Beasts?"
                  r"|Undead|Constructs?|Plants?|corpses?)\b", text, re.I)
    words = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10, "twelve": 12}
    if area:
        t["kind"] = "area"
    elif m:
        n = words.get((m.group(2) or m.group(1)).lower())
        t.update(kind="creatures" if (n or 1) > 1 else "creature", max=n or 1)
    elif re.search(r"\byou\b.*\b(gain|have|are)\b", text[:200]):
        t["kind"] = "self"
    return t


def save_of(text):
    m = re.search(r"(" + "|".join(ABILITIES) + r") saving throw", text)
    if not m:
        return None
    half = bool(re.search(r"half as much damage|half (?:the|that) damage|Half damage", text))
    return {"ability": m.group(1)[:3].lower(), "half": half}


def attack_of(text):
    m = re.search(r"(melee|ranged) spell attack", text, re.I)
    return m.group(1).lower() if m else None


def damage_of(text):
    """Damage dice and type, read three ways: "3d6 Fire damage"; "Force damage equal to 4d12 plus your spellcasting
    ability modifier" (Arcane Sword, Conjure Fey); "3d8 damage of the chosen type" with "Choose Acid, Cold ... or
    Thunder" (Chromatic Orb: one entry per type it may be, the same dice)."""
    found = []
    for m in re.finditer(r"(\d+d\d+(?: ?\+ ?\d+)?)(?: (?:\+|plus) your spellcasting ability modifier)? (" + "|".join(DAMAGE)
                         + r") damage", text):
        found.append((m.start(), m.group(1), m.group(2), "spellcasting ability modifier" in m.group(0)))
    for m in re.finditer(r"(" + "|".join(DAMAGE) + r") damage equal to (\d+d\d+(?: ?\+ ?\d+)?)( (?:\+|plus) your spellcasting "
                         r"ability modifier)?", text):
        found.append((m.start(), m.group(2), m.group(1), bool(m.group(3))))
    chosen = re.search(r"Choose ((?:\w+, )+(?:or )?\w+) for the type", text)
    for m in re.finditer(r"(\d+d\d+(?: ?\+ ?\d+)?) damage of the chosen type", text) if chosen else ():
        for kind in re.findall(r"\w+", chosen.group(1)):
            if kind in DAMAGE:
                found.append((m.start(), m.group(1), kind, False))
    out = []
    for _, dice, kind, plus in sorted(found, key=lambda f: f[0]):
        if (dice, kind.lower()) not in [(d["dice"], d["type"]) for d in out]:
            out.append({"dice": dice, "type": kind.lower(), "plus_mod": plus})
    return out


WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10}


def count_of(text):
    """How many times the spell strikes when its darts, rays or beams grow in number ("You create three glowing darts"
    ... "one more dart for each spell slot level above 1"; "You hurl a beam" ... "two beams at level 5, three beams at
    level 11, and four beams at level 17"): {"n", "word", "per_level", "above"} or {"n", "word", "levels"}; None for a
    spell that strikes once. All of them may strike the same creature."""
    up = re.search(r"(?:Using a Higher-Level Spell Slot|Cantrip Upgrade)\.?(.*)", text, re.S)
    if not up:
        return None
    m = re.search(r"\b(?:one|an) (?:more|additional) (\w+?) (?:\w+ )*?for each (?:spell )?slot level above (\d)", up.group(1))
    c = re.search(r"creates (\w+) (\w+?)s at level 5, (\w+) \w+ at level 11, and (\w+) \w+ at level 17", up.group(1))
    noun = m.group(1) if m else c.group(2) if c else None
    if noun and (noun[0].isupper() or noun in ("creature", "target", "object")):
        return None                                              # more targets ("one additional creature"): scaling_of
    base = noun and re.search(r"\b(a|an|one|two|three|four|five|six|seven|eight|nine|ten) (?:[\w-]+ ){0,2}?%ss?\b" % noun,
                              first_paragraph(text))
    if not base:
        return None
    out = {"n": WORDS[base.group(1).lower()], "word": noun}
    if m:
        out.update(per_level=1, above=int(m.group(2)))
    else:
        out["levels"] = [WORDS.get(c.group(i), 1) for i in (1, 3, 4)]
    return out


def extra_of(text):
    """Damage the text adds in a case it names ("The damage increases by 1d8 if the target is a Fiend or an Undead")."""
    return [{"dice": m.group(1), "if": m.group(2)} for m in re.finditer(r"damage increases by (\d+d\d+) if ([^.]+)\.", text)]


def near_of(text):
    """Creatures around the target the spell also reaches ("The target and each creature within 5 feet of it")."""
    m = re.search(r"(?:each|every) creature within (\d+) feet of (?:it|the target)\b", text)
    return {"ft": int(m.group(1))} if m else None


def healing_of(text):
    m = re.search(r"regains? (?:a number of )?Hit Points equal to (\d+d\d+)?( (?:\+|plus) your spellcasting ability modifier)?", text)
    if m:
        return {"dice": m.group(1), "plus_mod": bool(m.group(2))}
    # Regenerate "regains 4d8 + 15 Hit Points"; Heal "restoring 70 Hit Points"; Mass Heal "restore up to 700 Hit Points"
    m = re.search(r"(?:regains?|restor(?:es|ing|e)(?: up to)?) (\d+d\d+(?: ?\+ ?\d+)?|\d+) Hit Points", text)
    if m:
        return {"dice": m.group(1), "plus_mod": False}
    return {"dice": "all", "plus_mod": False} if re.search(r"regains? all (?:its|of its|their) Hit Points", text) else None


_ONE = r"(?:%s)" % "|".join(CONDITIONS)
_LIST = re.compile(r"\b(%s(?:(?:,? (?:or|and) |, )%s)*) conditions?\b" % (_ONE, _ONE))


# Words before a list of conditions, in its own clause, that mean the spell does not give them: it ends or removes them
# (Heal, Protection from Poison, Greater Restoration), keeps them away (Freedom of Movement, Magic Circle, Protection
# from Evil and Good, Hallow, "can't benefit from the Invisible condition"), gives Immunity to them (Calm Emotions,
# Heroes' Feast, Mind Blank), or names a creature that already has one (Power Word Heal, Dispel Evil and Good).
_NOT_GIVEN = re.compile(r"\bend (?:the|one|it)\b|\bends the\b|\bremove\b|\bcan't\b|\bcannot\b|\bneither\b|\bImmunity\b|"
                        r"\bimmune\b|\bsuppress|\bpossessed by\b|\b[Ii]f (?:it|the creature|the target) has the\b|\bto avoid\b|"
                        r"\bescape\b")


def conditions_of(text):
    """The conditions a spell gives, also named in a list ("has the Blinded or Deafened condition (your choice)"). Each
    list is judged by its own clause (the words before it, after the last ", and" or ";": _NOT_GIVEN) and the words right
    after it ("... conditions removed from them", "the condition ends"); the items under "remove one of the following
    effects:" are what the spell takes away."""
    given, taking_away = set(), False
    for line in (l.strip() for l in text.split("\n")):
        if taking_away and line.endswith("."):
            taking_away = False                                  # the list of effects it removes is over
        for sentence in ([] if taking_away else re.split(r"(?<=[.!?])\s+", line)):
            for m in _LIST.finditer(sentence):
                clause = re.split(r", and |; ", sentence[:m.start()])[-1]
                if _NOT_GIVEN.search(clause) or re.match(r"\s*(?:removed|ends?)\b", sentence[m.end():]):
                    continue
                given.update(re.findall(_ONE, m.group(1)))
        if line.endswith(":") and _NOT_GIVEN.search(line):
            taking_away = True
    return [c for c in CONDITIONS if c in given]


TIME_UNITS = {"round": 1, "minute": 10, "hour": 600}


def lasting(sentence):
    """How long the sentence says a condition lasts, or None."""
    m = re.search(r"until the (start|end) of (your|its|their|the target's|the creature's) next turn", sentence, re.I)
    if m:
        return {"until": {"who": "caster" if m.group(2).lower() == "your" else "target", "when": m.group(1).lower()}}
    if re.search(r"until the end of the current turn", sentence, re.I):
        return {"until": {"who": "current", "when": "end"}}
    if re.search(r"for the duration|until the spell ends", sentence, re.I):
        return {"spell": True}
    m = re.search(r"for (\d+|one|ten) (round|minute|hour)s?\b", sentence)
    if m:
        return {"rounds": (int(m.group(1)) if m.group(1).isdigit() else WORDS[m.group(1)]) * TIME_UNITS[m.group(2)]}
    return None


def lasts_of(text, conditions):
    """How long each condition the spell gives lasts, read from the sentence that gives it: {"spell": True} (for the
    duration, until the spell ends), {"until": {"who": "caster" / "target" / "current", "when": "start" / "end"}} (until
    the start or end of your / its next turn, until the end of the current turn), {"rounds": n} (for 1 minute = 10).
    A condition given without a time (Command's Grovel: Prone, until it stands up) is left out."""
    out = {}
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        when = lasting(sentence)
        for c in conditions:
            if when and re.search(r"\b%s\b" % c, sentence):
                out.setdefault(c, when)
    return out


def scaling_of(text, level):
    up = re.search(r"Using a Higher-Level Spell Slot\.?(.*)", text, re.S)
    if level == 0:
        cu = re.search(r"Cantrip Upgrade\.?(.*)", text, re.S)
        if cu:
            m = re.search(r"increases by (\d+d\d+) when you reach levels? 5 \((\d+d\d+)\), 11 \((\d+d\d+)\), and 17 \((\d+d\d+)\)", cu.group(1))
            return {"kind": "cantrip", "text": cu.group(1).strip()[:300], "levels": [m.group(2), m.group(3), m.group(4)] if m else None}
        return None
    if not up:
        return None
    t = up.group(1).strip()
    m = re.search(r"(?:damage|healing|Hit Points)[^.]*increases? by (\d+d\d+) for each (?:spell )?slot level above (\d)", t)
    n = re.search(r"(?:one|an) additional (creature|target)[^.]*for each (?:spell )?slot level above (\d)", t)
    out = {"kind": "slot", "text": t[:400]}
    if m:
        out.update(dice_per_level=m.group(1), above=int(m.group(2)))
    if n:
        out.update(extra_targets_per_level=1, above=int(n.group(2)))
    return out


def sheet(f):
    level = int(f.get("level") or 0)
    text = f["text"]
    effect = first_paragraph(text)
    area = area_of(effect)
    if area and range_of(f.get("range", ""))["kind"] == "self":
        area["origin"] = "self"                                  # Thunderwave's "Cube originating from you"
    s = {"name": f["name"], "level": level, "school": f.get("school", ""),
         "classes": [c.strip() for c in f.get("source", "").split(",") if c.strip()],
         "casting_time": casting_time(f.get("castingtime", "")), "casting_time_text": f.get("castingtime", ""),
         "ritual": f.get("ritual") == "1" or "ritual" in f.get("castingtime", "").lower(),
         "range": range_of(f.get("range", "")), "components": components(f.get("components", "")),
         "duration": duration(f.get("duration", "")), "area": area,
         "targets": dict(targets_of(effect, area), objects=objects_of(f["name"])),   # SPELL-OBJECTS-01 (sim/spell_objects.py)
         "attack": attack_of(effect), "save": save_of(effect), "damage": damage_of(effect), "healing": healing_of(effect),
         "conditions": conditions_of(effect), "scaling": scaling_of(text, level), "text": text}
    for key, value in (("count", count_of(text)), ("extra", extra_of(effect)), ("near", near_of(effect)),
                       ("lasts", lasts_of(effect, s["conditions"]))):
        if value:                                                # REFEREE-01 step 2: only where the text says so
            s[key] = value
    unread = []
    if s["range"]["kind"] == "special":
        unread.append("range")
    if not s["targets"]["kind"]:
        unread.append("targets")
    if not (s["attack"] or s["save"] or s["damage"] or s["healing"] or s["conditions"]):
        unread.append("effect (no attack, save, damage, healing or condition in the text: a utility spell)")
    s["unread"] = unread
    return s


def build(path=PDF):
    spells = sorted((sheet(f) for f in records(path)), key=lambda s: (s["level"], s["name"]))
    return {"format": FORMAT, "source": SRD, "count": len(spells), "spells": spells}


def load(path=OUT):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {s["name"]: s for s in data["spells"]}


def main(argv=None):
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    sp = data["spells"]
    print("wrote %s: %d spells; areas %d (choice %d), saves %d, attacks %d, damage %d, healing %d, conditions %d, unread %d" % (
        OUT.relative_to(ROOT), len(sp), sum(1 for s in sp if s["area"]), sum(1 for s in sp if s["targets"]["choice"]),
        sum(1 for s in sp if s["save"]), sum(1 for s in sp if s["attack"]), sum(1 for s in sp if s["damage"]),
        sum(1 for s in sp if s["healing"]), sum(1 for s in sp if s["conditions"]), sum(1 for s in sp if s["unread"])))


if __name__ == "__main__":
    main()
