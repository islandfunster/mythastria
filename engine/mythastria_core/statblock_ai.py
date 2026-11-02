"""v0.7.60: the local stat-block interpreter.

When the deterministic parser (ai_turn.parse_multiattack) cannot read a creature's Multiattack text, the GM's local
Ollama model reads it ONCE and returns a structured plan: alternative patterns of steps, each step one attack from
the creature's real attack names, optionally "only if the previous attack hit, against the same target" (the 2014
Grick's beak). Ollama runs on the GM's PC, so licensed stat-block text may go to it; it never goes to OpenAI, logs or
the page (only action names and the plan). The plan is validated against the creature's actions and cached under a
hash of the text + names in mythastria_core/cache (excluded from git, snapshots and reviews); a bad or empty answer is
cached as "no plan" so the model is not asked again. The GM sees the plan on the bridge page and can forget it."""
import hashlib, json, os, threading, time
from pathlib import Path

IF_HIT = "?if_previous_hit_same_target"   # marker inside a slot (never an action name)
# v0.7.62 (review of v0.7.61): a plan with a conditional step keeps its order: every slot carries ORDERED, and the
# condition refers to the step just before it
ORDERED = "?ordered"
# v0.7.62 (review of v0.7.61): a new reading is used only after the GM approves it on the bridge page (the model's
# attack count and conditions cannot be checked independently). Only simulator scenarios turn this on.
AUTO_APPROVE = False
MAX_STEPS = 8
_lock = threading.Lock()

SYSTEM = (
    "You convert the Multiattack text of a D&D 5E creature into JSON. Use only the attack names offered. "
    "Give one pattern per alternative the text allows (\"... or it makes ...\" is a second pattern). Each step is one "
    "attack; \"attacks\" lists the attack names allowed for that step (several when the text lets it choose). "
    "only_if_previous_hit_same_target is false for almost every step: set it to true only when the text explicitly "
    "says the attack may be made if (or after) the previous attack hits, e.g. \"If that attack hits, it can make one "
    "bite attack against the same target\". A plain list such as \"one with its claws and two with its sword\" has no "
    "conditions. Leave out anything that is not an attack (a breath weapon, \"uses Constrict\", spells); "
    "describe those briefly in notes. If the text gives no clear fixed number of attacks, return no patterns.")


def cache_path():
    return Path(os.environ.get("MYTHASTRIA_PLANS_FILE") or Path(__file__).resolve().parent / "cache" / "statblock_plans.json")


def key(desc, names):
    raw = " ".join((desc or "").split()) + "|" + "|".join(sorted(n.strip() for n in names))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load():
    try:
        return json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data):
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def cached(k):
    with _lock:
        return _load().get(k)


def forget(k):
    with _lock:
        data = _load()
        found = data.pop(k, None) is not None
        if found:
            _save(data)
        return found


def schema(names):
    return {"type": "object", "properties": {
        "patterns": {"type": "array", "items": {"type": "object", "properties": {
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "attacks": {"type": "array", "items": {"type": "string", "enum": sorted(names)}},
                "only_if_previous_hit_same_target": {"type": "boolean"}},
                "required": ["attacks", "only_if_previous_hit_same_target"]}}},
            "required": ["steps"]}},
        "notes": {"type": "string"}},
        "required": ["patterns", "notes"]}


def validate(reply, names):
    """Model reply -> list of patterns [[{"attacks": [...], "if_hit": bool}, ...], ...] (only real names, 2..8 steps,
    the first step never conditional), or [] when nothing usable."""
    if not isinstance(reply, dict) or not isinstance(reply.get("patterns"), list):
        return []
    real = {n.strip(): n for n in names}
    out = []
    for pat in reply["patterns"][:4]:
        steps = pat.get("steps") if isinstance(pat, dict) else None
        if not isinstance(steps, list) or not 2 <= len(steps) <= MAX_STEPS:
            continue
        good = []
        for i, st in enumerate(steps):
            atk = st.get("attacks") if isinstance(st, dict) else None
            if not isinstance(atk, list) or not atk or any(not isinstance(a, str) or a.strip() not in real for a in atk):
                good = None; break
            if_hit = st.get("only_if_previous_hit_same_target") is True
            if if_hit and i == 0:
                good = None; break
            good.append({"attacks": sorted({real[a.strip()] for a in atk}), "if_hit": if_hit})
        if good and good not in out:
            out.append(good)
    return out


def to_slots(patterns):
    """Cached plan -> ai_turn slots: frozensets of names, plus IF_HIT in a conditional step, plus ORDERED in every slot
    of a pattern that has a conditional step."""
    out = []
    for pat in patterns:
        ordered = any(st["if_hit"] for st in pat)
        out.append([frozenset(st["attacks"] + ([IF_HIT] if st["if_hit"] else []) + ([ORDERED] if ordered else []))
                    for st in pat])
    return out or None


def usable_slots(entry):
    """Slots of an APPROVED cached reading, else None (the creature makes single attacks meanwhile)."""
    if not entry or not entry.get("approved") or not entry.get("patterns"):
        return None
    return to_slots(entry["patterns"])


def approve(k):
    with _lock:
        data = _load()
        if k not in data or not data[k].get("patterns"):
            return False
        data[k]["approved"] = True
        _save(data)
        return True


def summary(patterns):
    def step(st):
        s = " or ".join(st["attacks"])
        return s + (" (only if that hit, same target)" if st["if_hit"] else "")
    return " | or | ".join(", then ".join(step(st) for st in pat) for pat in patterns)


def interpret(desc, names, model, choose):
    """Cached plan entry for this text and these attack names, asking the local model once. choose(model, messages,
    schema) is ollama_client.choose. Returns {"key", "patterns", "summary", ...}; patterns [] means no plan."""
    k = key(desc, names)
    hit = cached(k)
    if hit is not None:
        return dict(hit, key=k)
    entry = {"patterns": [], "summary": "", "model": model, "at": time.strftime("%Y-%m-%d %H:%M"), "error": "",
             "approved": bool(AUTO_APPROVE)}
    try:
        user = "Attack names: " + json.dumps(sorted(names)) + "\nMultiattack text: " + " ".join((desc or "").split())[:1500]
        reply = choose(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], schema(names))
        entry["patterns"] = validate(reply, names)
        entry["summary"] = summary(entry["patterns"])
    except Exception as error:   # no model / Ollama down: not cached, so it is tried again next time
        return {"key": k, "patterns": [], "summary": "", "error": str(error)[:200], "transient": True, "approved": False}
    with _lock:
        data = _load(); data[k] = entry; _save(data)
    return dict(entry, key=k)
