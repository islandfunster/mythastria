"""MARKET-01 (GM 2026-10-21: "I want to add a marketspace activated only by the DM"; asked, chose: players add to a
shopping cart and the GM approves or rejects line items, with select all or none; shops belong to adventure places; each
character's gold is kept by Mythastria): the market's rules. The service (tools/sim_service.py, POST /api/market) is the
only way in; it hands this module the places of the loaded adventures, the party and which seat plays which character.

- Shops: each belongs to a place of an adventure (its plan's place, or a place the GM names), has a kind (general store,
  smith, alchemist, temple, scribe, rare goods broker) and its own stock. Off by default; the GM opens one shop at a time
  and closes it again. Players see the open shop only.
- Prices: SRD 5.2.1 only (sim/srd_market.json, built by tools/build_srd_market.py from the SRD PDF). The GM may set a
  line's price (haggling: a Persuasion check, then the agreed price) and add homebrew lines, which are marked homebrew.
- Gold: one purse per character, in copper pieces, kept here. Selling back: the shop's buy-back share of the item's value
  (SRD 5.2.1: equipment fetches half its cost).
- Carts: a seat fills its own character's cart and sends it; the GM approves chosen lines and the rest are refused. On
  approval the gold is checked and taken, the items go into the character's bag and the market log. Attunement (three
  at most), class fit and spell lists are warnings for the GM, never blocks.
Kept in sim/market/market.json (campaign data on this PC, not committed; a test port keeps its own file).
"""
import json, random, re, secrets, threading, time
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "srd_market.json"
KINDS = {"general": "General store", "smith": "Smith", "alchemist": "Alchemist", "temple": "Temple", "scribe": "Scribe",
         "broker": "Rare goods broker"}
NAME = re.compile(r"^[^\x00-\x1f<>]{1,60}$")
MAX_SHOPS, MAX_STOCK, MAX_CART, MAX_BAG, MAX_LOG, MAX_QTY = 80, 250, 40, 300, 300, 999
MAX_CP = 10 ** 11                                                  # a billion gold: more than any purse needs
ATTUNE_MAX = 3
CASTERS = {"Bard", "Cleric", "Druid", "Paladin", "Ranger", "Sorcerer", "Warlock", "Wizard"}
FULL_CASTERS = {"Bard", "Cleric", "Druid", "Sorcerer", "Warlock", "Wizard"}
RARITY_ORDER = ["Common", "Uncommon", "Rare", "Very Rare", "Legendary"]
# Magic items per tier over a campaign (the 2024 guideline the magic-item-placement skill budgets with), used only as
# numbers: which rarities a shop at the party's level offers.
TIERS = {(1, 4): (6, 4, 1, 0, 0), (5, 10): (10, 17, 6, 1, 0), (11, 16): (3, 7, 11, 7, 2), (17, 20): (0, 0, 5, 11, 9)}
# A shop kind's everyday stock (SRD 5.2.1 item ids); the magic part is picked for the party (template()).
EVERYDAY = {
    "general": ["backpack", "bedroll", "blanket", "candle", "chain", "chest", "climbers-kit", "clothes-travelers", "crowbar",
                "dungeoneers-pack", "explorers-pack", "flask", "grappling-hook", "healers-kit", "hunting-trap", "ink", "ink-pen",
                "lamp", "lantern-hooded", "lantern-bullseye", "lock", "manacles", "mirror", "oil", "paper", "pouch", "quiver",
                "rations", "rope", "sack", "shovel", "spikes-iron", "tent", "tinderbox", "torch", "waterskin", "ball-bearings",
                "caltrops", "arrows-20", "bolts-20", "sling-bullets-20"],
    "smith": None,                                                 # every weapon (no firearms), armor and the Shield
    "alchemist": ["acid", "alchemists-fire", "antitoxin", "oil", "vial", "bottle-glass", "herbalism-kit", "alchemists-supplies",
                  "potion-of-healing"],
    "temple": ["holy-water", "healers-kit", "amulet-holy-symbol", "emblem-holy-symbol", "reliquary-holy-symbol", "candle", "robe",
               "potion-of-healing", "diamond-300-gp"],             # SPELL-BATCH-01: Revivify's diamond
    "scribe": ["book", "ink", "ink-pen", "paper", "parchment", "case-map-or-scroll", "calligraphers-supplies", "component-pouch",
               "crystal-arcane-focus", "orb-arcane-focus", "wand-arcane-focus", "map",
               "gold-dust",                                        # SPELL-OBJECTS-01: Arcane Lock's component
               "diamond", "black-pearl", "ruby-dust",              # group 2: Chromatic Orb, Circle of Death, Continual Flame
               "diamond-300-gp"],                                  # SPELL-BATCH-01: Revivify
    "broker": [],
}
LIMITED = {"potion-of-healing": 5, "holy-water": 4, "alchemists-fire": 4, "acid": 4, "antitoxin": 4}
SCROLL_CLASSES = {"temple": ("Cleric",), "scribe": ("Wizard", "Sorcerer", "Bard", "Warlock")}


class Conflict(Exception):
    """The market changed on another screen since the page read it."""


def money(cp):
    """1234 -> '12 GP 3 SP 4 CP' (0 -> '0 GP')."""
    cp = int(cp)
    gp, rest = divmod(abs(cp), 100)
    sp, c = divmod(rest, 10)
    parts = (["%s GP" % format(gp, ",")] if gp else []) + (["%d SP" % sp] if sp else []) + (["%d CP" % c] if c else [])
    return ("-" if cp < 0 else "") + (" ".join(parts) or "0 GP")


def to_cp(gp):
    """A GP amount (a number; 0.01 GP is one copper) as copper pieces."""
    if isinstance(gp, bool) or not isinstance(gp, (int, float)) or gp != gp:
        raise ValueError("An amount of gold is a number of GP (0.1 GP is 1 SP, 0.01 GP is 1 CP).")
    cp = round(gp * 100)
    if abs(cp) > MAX_CP:
        raise ValueError("That is more gold than the market keeps.")
    return cp


# LOOT-01 (GM 2026-10-29: "a loot calculator ... that calculates and divides all the coins per person from a party loot
# list"; then "a special loot inventory": its own Market tab, the GM edits it, the players see it and their share, the
# shares go into the purses). SRD 5.2.1 Coin Values, in copper pieces.
COINS = {"pp": 1000, "gp": 100, "ep": 50, "sp": 10, "cp": 1}
COIN_WORDS = {"platinum": "pp", "gold": "gp", "electrum": "ep", "silver": "sp", "copper": "cp"}
_COIN = re.compile(r"(\d[\d,]*)\s*(?:(pp|gp|ep|sp|cp)\b|(platinum|gold|electrum|silver|copper)\s+(?:pieces?|coins?)\b)", re.I)
_FILLER = re.compile(r"\b(?:and|plus|in|of|loose|coins?|pieces?)\b|[&+.()\-]", re.I)
MAX_LOOT_TEXT, MAX_FINDS, MAX_SHARERS = 4000, 200, 12


def loot_finds(text):
    """What the GM typed -> the finds: one per line or between semicolons. A comma parts coins from the rest ("120 gp,
    35 sp, a ruby"), but an item keeps its own commas ("Rope, hempen (50 feet)"); "1,200 gp" stays one number."""
    if not isinstance(text, str) or len(text) > MAX_LOOT_TEXT:
        raise ValueError("The loot is text, up to %d characters." % MAX_LOOT_TEXT)
    finds = []
    for line in re.split(r"[;\n]", text):
        item = []
        for part in re.split(r",(?!\d{3}\b)", line):
            part = re.sub(r"\s+", " ", part.strip(" \t\r-*•"))
            if part and find_coins(part) is not None:
                finds += [", ".join(item)] if item else []
                finds.append(part)
                item = []
            elif part:
                item.append(part)
        finds += [", ".join(item)] if item else []
    return [f[:120] for f in finds]


def find_coins(find):
    """One find's coins {coin: count}, or None when it is not only coins: "30 gp and 12 sp", "40 silver pieces" are
    coins; "a ruby worth 50 gp" or "3 gold rings" is an item, never split."""
    found = list(_COIN.finditer(find))
    rest = _FILLER.sub(" ", _COIN.sub(" ", find))
    if not found or re.search(r"[^\W\d_]|\d", rest):
        return None
    coins = {}
    for m in found:
        coin = (m.group(2) or COIN_WORDS[m.group(3).lower()]).lower()
        coins[coin] = coins.get(coin, 0) + int(m.group(1).replace(",", ""))
    return coins


def key(name):
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def clean_name(name, what="A name"):
    name = re.sub(r"\s+", " ", name.strip()) if isinstance(name, str) else ""
    if not NAME.match(name):
        raise ValueError("%s is 1 to 60 characters." % what)
    return name


def load_catalog(path=CATALOG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {i["id"]: i for i in data["items"]}
    import srd_poisons                                          # GM 2026-10-23: the SRD's poisons (Gameplay Toolbox)
    for i in srd_poisons.catalog_items():
        out.setdefault(i["id"], i)
    return out


def shares(level):
    """Magic items of each rarity the guideline hands a whole party per level, at this level."""
    level = max(1, min(20, int(level or 1)))
    (a, b), counts = next(((a, b), c) for (a, b), c in TIERS.items() if a <= level <= b)
    return {r: n / (b - a + 1) for r, n in zip(RARITY_ORDER, counts)}


def rarities_for(level):
    """The rarities a shop offers to a party of this level (at least 0.3 items a level, as the skill's budget)."""
    return [r for r, n in shares(level).items() if n >= 0.3] or ["Common"]


def max_scroll_level(level):
    """The highest spell a scroll in a shop carries: what a full caster of the party's level can cast (up to 9)."""
    return max(1, min(9, (max(1, int(level or 1)) + 1) // 2))


def score(item, member):
    """How well one magic item suits one character (the magic-item-placement skill's ranking), with the reasons and the
    armor or weapon it should be made from."""
    s, why, base = 0, [], None
    cls = member.get("class") or ""
    who = item.get("attune_by") or []
    if who:
        if cls in who or ("Spellcaster" in who and cls in CASTERS):
            s += 3; why.append("attunes to a %s" % cls)
        else:
            return 0, [], None
    for w in member.get("weapons") or []:
        if w in (item.get("bases") or []) or item.get("base") == w or re.search(r"\b%s\b" % re.escape(w.lower()), item["name"].lower()):
            s += 4; why.append("a better %s" % w); base = w if item.get("bases") else None
            break
    armor = member.get("armor")
    if armor and (armor in (item.get("bases") or []) or item.get("base") == armor):
        s += 3; why.append("better %s" % armor); base = armor if item.get("bases") else None
    if member.get("shield") and (item.get("base") == "Shield"):
        s += 3; why.append("a better Shield")
    if cls in FULL_CASTERS and item.get("category") in ("Wand", "Rod", "Staff") and "weapon" not in item["name"].lower():
        s += 2; why.append("a caster's %s" % item["category"].lower())
    if re.search(r", \+\d$", item["name"]) and why:
        s += 2; why.append("a straight bonus")
    if item.get("bases") and not base:
        return 0, [], None                                         # a magic weapon or armor nobody here uses
    return s, why, base


def party_picks(catalog, party, level, count, seed):
    """One to three magic items for this party at this level: each character's best item in turn (ties shuffled by
    `seed`, so "suggest again" gives others)."""
    rng = random.Random(seed)
    allowed, share = rarities_for(level), shares(level)
    pool = [i for i in catalog.values() if i["kind"] == "magic" and i.get("rarity") in allowed and not i.get("consumable")]
    rng.shuffle(pool)
    # a rarity the level barely hands out goes down the list (the skill's budget rule)
    scarce = lambda i: 4 if share[i["rarity"]] < 0.75 else 1 if share[i["rarity"]] < 1.5 else 0
    ranked = []
    for m in party:
        scored = []
        for i in pool:
            s, why, base = score(i, m)
            if s > 0 and s - scarce(i) > 0:
                scored.append((s - scarce(i), why, base, i))
        scored.sort(key=lambda x: -(x[0] + rng.random() * 3))     # close scores in another order each time
        ranked.append([(i, why, base, m["name"]) for s, why, base, i in scored][:6])
    picks, seen = [], set()
    for _ in range(6):                                             # each character's best item not picked yet, in turn
        for row in ranked:
            if len(picks) >= count:
                return picks
            pick = next((x for x in row if (x[0]["id"], x[2]) not in seen), None)
            if pick:
                seen.add((pick[0]["id"], pick[2])); picks.append(pick)
    if len(picks) < count:                                         # nobody fits: anything the level allows
        for i in pool:
            if len(picks) >= count:
                break
            if (i["id"], None) not in seen and not i.get("attune_by") and not i.get("bases"):
                seen.add((i["id"], None)); picks.append((i, ["for anyone"], None, ""))
    return picks


class Market:
    def __init__(self, path, catalog_path=CATALOG, clock=time.time):
        self.path = Path(path)
        self.catalog_path = Path(catalog_path)
        self.clock = clock
        self.lock = threading.Lock()
        self._catalog, self.state = None, None
        self.announce = None

    # ------------------------------------------------------------------ storage
    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = load_catalog(self.catalog_path)
        return self._catalog

    def _load(self):
        if self.state is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                assert data.get("version") == 1 and isinstance(data.get("shops"), dict)
                self.state = data
            except (OSError, ValueError, AssertionError, AttributeError):
                self.state = {"version": 1, "rev": 0, "open": None, "shops": {}, "purses": {}, "carts": {}, "log": []}
        return self.state

    def _write(self):
        st = self.state
        st["rev"] += 1
        st["log"] = st["log"][-MAX_LOG:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=0), encoding="utf-8")
        tmp.replace(self.path)

    def _log(self, text):
        self.state["log"].append({"at": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.clock())), "text": text})

    def _purse(self, name, make=True):
        st, k = self.state, key(name)
        p = st["purses"].get(k)
        if p is None and make:
            p = st["purses"][k] = {"name": clean_name(name, "A character's name"), "cp": 0, "bag": []}
        return p

    def _cart(self, name):
        k = key(name)
        c = self.state["carts"].get(k)
        if c is None:
            c = self.state["carts"][k] = {"name": clean_name(name, "A character's name"), "shop": None, "lines": [],
                                          "sent": False, "by": "", "at": 0, "answer": None}
        return c

    # ------------------------------------------------------------------ GM 2026-10-23: what a character carries
    # (sim/requirements.py Bag): Play live counts a character's items here and takes the ones it uses, logged here.
    def holdings(self, character):
        with self.lock:
            p = self._load()["purses"].get(key(character))
            return [dict(b) for b in (p or {}).get("bag", [])]

    def take(self, character, item, qty=1, why=""):
        """qty of a catalog item out of the character's bag (refused when it is not there). -> how many are left."""
        with self.lock:
            p = self._load()["purses"].get(key(character))
            have = [b for b in (p or {}).get("bag", []) if b.get("item") == item and b["qty"] > 0]
            if sum(b["qty"] for b in have) < qty:
                raise ValueError("%s has not %s in the bag." % (character, _count(item, qty)))
            left, name = qty, have[0]["name"]
            for b in have:
                n = min(left, b["qty"]); b["qty"] -= n; left -= n
            p["bag"] = [b for b in p["bag"] if b["qty"] > 0]
            self._log("%s: %s used%s." % (p["name"], _count(name, qty), " (%s)" % why if why else ""))
            self._write()
            return sum(b["qty"] for b in p["bag"] if b.get("item") == item)

    def use_charge(self, character, item, per_item, why=""):
        """One use of an item with uses (a Healer's Kit: ten); the emptied one leaves the bag. -> uses left in it."""
        with self.lock:
            p = self._load()["purses"].get(key(character))
            b = next((b for b in (p or {}).get("bag", []) if b.get("item") == item and b["qty"] > 0), None)
            if not b:
                raise ValueError("%s has no %s in the bag." % (character, item))
            left = int(b.get("uses_left", per_item)) - 1
            if left <= 0:
                b["qty"] -= 1
                left = per_item
                p["bag"] = [x for x in p["bag"] if x["qty"] > 0]
                self._log("%s: the last use of a %s%s; it is used up." % (p["name"], b["name"], " (%s)" % why if why else ""))
            else:
                self._log("%s: one use of a %s%s (%d left in it)." % (p["name"], b["name"], " (%s)" % why if why else "", left))
            b["uses_left"] = left
            self._write()
            return left

    # ------------------------------------------------------------------ GM 2026-10-26: downtime (sim/downtime.py)
    def gold(self, character):
        """The character's gold, in copper pieces (0 without a purse)."""
        with self.lock:
            p = self._load()["purses"].get(key(character))
            return int((p or {}).get("cp", 0))

    def spend(self, character, cp, why=""):
        """Gold out of the purse (refused when it is short). -> what is left, in copper pieces."""
        with self.lock:
            p = self._load()["purses"].get(key(character))
            if cp > 0 and (not p or p["cp"] < cp):
                raise ValueError("%s has only %s." % (character, money((p or {}).get("cp", 0))))
            if cp > 0:
                p["cp"] -= cp
                self._log("%s spends %s%s (now %s)." % (p["name"], money(cp), " (%s)" % why if why else "", money(p["cp"])))
                self._write()
            return (p or {}).get("cp", 0)

    def give(self, character, item, qty=1, why="", name=None, value_cp=None, base=None):
        """A catalog item (made from base) into the character's bag; a crafted one may carry its own name, such as a
        scribed scroll."""
        with self.lock:
            p = self._purse(character)
            entry = self._new_entry({"item": item, "qty": qty, "base": base})
            if name:
                entry["name"] = clean_name(name[:60], "An item's name")
            if value_cp is not None:
                entry["value_cp"] = int(value_cp)
            self._into_bag(p, entry)
            self._log("%s gets %s%s." % (p["name"], _count(entry["name"], entry["qty"]), " (%s)" % why if why else ""))
            self._write()

    def close_pack(self, pack):
        """An adventure was unloaded: its open shop closes (its shops stay for the next time it is loaded)."""
        with self.lock:
            st = self._load()
            shop = st["shops"].get(st["open"])
            if shop and shop["pack"] == pack:
                st["open"] = None
                self._log("Closed %s: its adventure was unloaded." % shop["name"])
                self._write()

    # ------------------------------------------------------------------ views
    def _price(self, line):
        return {"price_cp": line["price_cp"], "price": money(line["price_cp"])}

    def _stock_view(self, shop, gm=False):
        out = []
        for line in shop["stock"]:
            item = self.catalog.get(line.get("item")) or {}
            v = {"id": line["id"], "name": line["name"], "qty": line.get("qty"), "kind": item.get("kind", "homebrew"),
                 "rarity": item.get("rarity"), "attunement": bool(line.get("attunement", item.get("attunement"))),
                 "homebrew": bool(line.get("homebrew")), "note": line.get("note", ""), **self._price(line)}
            if item.get("attune_by"):
                v["attune_by"] = item["attune_by"]
            if item.get("classes"):
                v["classes"] = item["classes"]
            if gm:
                v.update(item=line.get("item"), base=line.get("base"), list_cp=self._list_price(line.get("item"), line.get("base")),
                         why=line.get("why", ""))
            out.append(v)
        return out

    def _list_price(self, item_id, base=None):
        item = self.catalog.get(item_id)
        if not item:
            return None
        cost = item["cost_cp"]
        if base:
            cost += self.catalog[_slug(base)]["cost_cp"]
        return cost

    def _shop_public(self, shop):
        return {"id": shop["id"], "name": shop["name"], "kind": shop["kind"], "kind_name": KINDS[shop["kind"]],
                "where": shop["where"], "buyback": shop["buyback"], "stock": self._stock_view(shop)}

    def _bag_view(self, purse):
        return [dict(b, value=money(b["value_cp"])) for b in purse["bag"]]

    def _warnings(self, name, cart, cls):
        """Per cart line: what the GM should know before approving (never a block)."""
        purse = self._purse(name, make=False) or {"bag": [], "cp": 0}
        attuned = sum(b["qty"] for b in purse["bag"] if b.get("attunement"))
        out = {}
        for line in cart["lines"]:
            w = []
            if line["op"] == "buy":
                item = self.catalog.get(line.get("item")) or {}
                if line.get("homebrew"):
                    w.append("Homebrew (not SRD 5.2.1).")
                if line.get("attunement"):
                    attuned += line["qty"]
                    if attuned > ATTUNE_MAX:
                        w.append("%s would hold %d items that need attunement: only %d can be attuned at once." % (name, attuned, ATTUNE_MAX))
                who = item.get("attune_by") or []
                if who and cls and not (cls in who or ("Spellcaster" in who and cls in CASTERS)):
                    w.append("Requires attunement by a %s; %s is a %s." % (_either(who), name, cls))
                if item.get("kind") == "scroll" and cls and cls not in item.get("classes", []):
                    w.append("%s is not on the %s spell list: %s can't cast it from the scroll." % (item["spell"], cls, name))
                listed = self._list_price(line.get("item"), line.get("base"))
                if listed is not None and listed != line["price_cp"]:
                    w.append("Price set by the GM (list price %s)." % money(listed))
            out[line["id"]] = w
        return out

    def _cart_view(self, cart, cls=None, gm=False):
        buy = sum(l["price_cp"] * l["qty"] for l in cart["lines"] if l["op"] == "buy")
        sell = sum(l["price_cp"] * l["qty"] for l in cart["lines"] if l["op"] == "sell")
        warn = self._warnings(cart["name"], cart, cls) if gm else {}
        shop = self.state["shops"].get(cart["shop"])
        return {"name": cart["name"], "shop": cart["shop"], "shop_name": shop["name"] if shop else "",
                "sent": cart["sent"], "by": cart["by"], "answer": cart["answer"],
                "lines": [dict(l, price=money(l["price_cp"]), total=money(l["price_cp"] * l["qty"]), warnings=warn.get(l["id"], []))
                          for l in cart["lines"]],
                "buy_cp": buy, "sell_cp": sell, "net": money(buy - sell)}

    def _purse_view(self, p):
        return {"name": p["name"], "cp": p["cp"], "gold": money(p["cp"]), "bag": self._bag_view(p),
                "attuned": sum(b["qty"] for b in p["bag"] if b.get("attunement"))}

    # ------------------------------------------------------------------ LOOT-01: the party loot
    def _loot(self):
        return self.state.setdefault("loot", {"finds": [], "who": None})

    def _sharers(self, names):
        if not isinstance(names, list) or not 0 < len(names) <= MAX_SHARERS:
            raise ValueError("Share the loot among 1 to %d characters." % MAX_SHARERS)
        return list({key(n): clean_name(n, "A character's name") for n in names}.values())

    def loot_view(self, who=None):
        """The party loot: each find (coins or an item), the coins' total, and the shares among `who` (the GM's
        sharers, else the party): each share in copper (a purse holds one sum), and what doesn't divide evenly."""
        loot = self._loot()
        who = loot["who"] or who or []
        coins, finds = dict.fromkeys(COINS, 0), []
        for f in loot["finds"]:
            got = find_coins(f["text"])
            for c, n in (got or {}).items():
                coins[c] += n
            finds.append(dict(f, coins=got is not None))
        total = sum(n * COINS[c] for c, n in coins.items())
        each, left = divmod(total, len(who)) if who else (0, total)
        return {"finds": finds, "coins": {c: n for c, n in coins.items() if n}, "total_cp": total, "total": money(total),
                "who": list(who), "chosen": bool(loot["who"]), "each_cp": each, "each": money(each), "left_cp": left, "left": money(left)}

    def gm_view(self, ctx):
        st = self._load()
        places = ctx.get("places") or {}
        classes = {key(n): c for n, c in (ctx.get("classes") or {}).items()}
        names = {key(n): n for n in list(ctx.get("characters") or [])}
        names.update({k: p["name"] for k, p in st["purses"].items()})
        shops = []
        for s in sorted(st["shops"].values(), key=lambda s: (s["pack"], s["where"].lower(), s["name"].lower())):
            shops.append(dict(s, kind_name=KINDS[s["kind"]], available=s["pack"] in places, stock=self._stock_view(s, gm=True)))
        carts = [self._cart_view(c, classes.get(k), gm=True) for k, c in sorted(st["carts"].items()) if c["lines"] or c["answer"]]
        return {"ok": True, "rev": st["rev"], "open": st["open"], "shops": shops, "kinds": KINDS,
                "purses": [self._purse_view(st["purses"][k]) if k in st["purses"] else {"name": n, "cp": 0, "gold": "0 GP", "bag": [], "attuned": 0}
                           for k, n in sorted(names.items())],
                "carts": carts, "asked": sum(1 for c in st["carts"].values() if c["sent"] and c["lines"]),
                "log": st["log"][-80:], "places": places, "level": ctx.get("level"),
                "party": [m["name"] for m in ctx.get("party") or []], "attune_max": ATTUNE_MAX,
                "loot": self.loot_view([m["name"] for m in ctx.get("party") or []])}   # LOOT-01

    def public_view(self):
        """What anyone at the table may see: the open shop, or nothing (the players' window on the GM's PC)."""
        st = self._load()
        shop = st["shops"].get(st["open"])
        return {"ok": True, "open": bool(shop), "shop": self._shop_public(shop) if shop else None,
                "loot": self.loot_view()}                          # LOOT-01: the party loot and its shares, to read

    def player_view(self, character):
        st = self._load()
        out = self.public_view()
        if not character:
            return dict(out, character="", note="You are watching: the GM gives you a character to shop for.")
        p = self._purse(character, make=False) or {"name": character, "cp": 0, "bag": []}
        cart = st["carts"].get(key(character))
        out.update(character=character, purse=self._purse_view(p),
                   cart=self._cart_view(cart) if cart else {"name": character, "lines": [], "sent": False, "answer": None,
                                                            "buy_cp": 0, "sell_cp": 0, "net": "0 GP"})
        return out

    # ------------------------------------------------------------------ the GM's requests
    def gm(self, req, ctx):
        op = req.get("op", "state")
        self.announce = None                                       # a line for the table chat after a decision
        with self.lock:
            st = self._load()
            if op == "state":
                return self.gm_view(ctx)
            if op == "view":
                return self.public_view()
            if op == "catalog":
                return {"ok": True, "items": list(self.catalog.values()), "kinds": KINDS}
            if op == "template":
                return dict(self.template(req.get("kind"), ctx, req.get("seed", 1)), ok=True)
            if op == "shop_save":
                if req.get("rev") != st["rev"]:
                    raise Conflict("The market was changed on another screen. Close the shop editor, open it again, then make the change.")
                shop = self._clean_shop(req.get("shop"), ctx)
                old = st["shops"].get(shop["id"])
                if not old and len(st["shops"]) >= MAX_SHOPS:
                    raise ValueError("At most %d shops: delete one first." % MAX_SHOPS)
                st["shops"][shop["id"]] = shop
                self._log("%s %s (%s, %s)." % ("Changed" if old else "Made", shop["name"], KINDS[shop["kind"]], shop["where"]))
            elif op == "shop_delete":
                shop = self._shop(req.get("id"))
                del st["shops"][shop["id"]]
                if st["open"] == shop["id"]:
                    st["open"] = None
                self._log("Deleted %s." % shop["name"])
            elif op == "open":
                shop = self._shop(req.get("id"))
                if shop["pack"] not in (ctx.get("places") or {}):
                    raise ValueError("%s belongs to an adventure that is not loaded: load it on the Adventure page first." % shop["name"])
                st["open"] = shop["id"]
                self._log("Opened %s (%s)." % (shop["name"], shop["where"]))
            elif op == "close":
                if st["open"] in st["shops"]:
                    self._log("Closed %s." % st["shops"][st["open"]]["name"])
                st["open"] = None
            elif op == "purse":
                name = clean_name(req.get("character"), "A character's name")
                p = self._purse(name)
                if "set_gp" in req:
                    cp = to_cp(req["set_gp"])
                    if cp < 0:
                        raise ValueError("A purse can't hold less than nothing.")
                    p["cp"] = cp
                    self._log("%s's gold set to %s%s." % (p["name"], money(cp), _why(req)))
                else:
                    cp = to_cp(req.get("add_gp"))
                    if p["cp"] + cp < 0:
                        raise ValueError("%s has only %s." % (p["name"], money(p["cp"])))
                    p["cp"] += cp
                    self._log("%s %s %s%s (now %s)." % (p["name"], "gains" if cp >= 0 else "spends", money(abs(cp)), _why(req), money(p["cp"])))
            elif op == "loot_add":                                 # LOOT-01: finds into the party loot
                loot, finds = self._loot(), loot_finds(req.get("text"))
                if not finds:
                    raise ValueError("Type what the party found: coins (120 gp, 35 sp) or items, one per line.")
                if len(loot["finds"]) + len(finds) > MAX_FINDS:
                    raise ValueError("The party loot holds at most %d finds: share or give some first." % MAX_FINDS)
                loot["finds"] += [{"id": secrets.token_hex(5), "text": f} for f in finds]
                if not loot["who"] and ctx.get("party"):           # the party shares, until the GM ticks others
                    loot["who"] = self._sharers([m["name"] for m in ctx["party"]])
                self._log("Party loot: found %s%s." % ("; ".join(finds), _why(req)))
            elif op == "loot_remove":
                loot = self._loot()
                f = next((f for f in loot["finds"] if f["id"] == req.get("id")), None)
                if not f:
                    raise ValueError("That find is no longer in the party loot.")
                loot["finds"].remove(f)
                self._log("Party loot: %s taken off the list%s." % (f["text"], _why(req)))
            elif op == "loot_who":                                 # who shares the coins (the players see it)
                self._loot()["who"] = self._sharers(req.get("characters"))
            elif op == "loot_give":                                # each share into each purse; the coins leave the list
                loot = self._loot()
                loot["who"] = self._sharers(req.get("characters", loot["who"]))
                v = self.loot_view()
                if not v["each_cp"]:
                    raise ValueError("No coins to share: %s." % ("the party loot has none" if not v["total_cp"]
                                                                  else "fewer copper pieces than people"))
                for name in v["who"]:
                    p = self._purse(name)
                    p["cp"] += v["each_cp"]
                    self._log("%s gains %s (a share of the party loot) (now %s)." % (p["name"], v["each"], money(p["cp"])))
                loot["finds"] = [f for f in loot["finds"] if find_coins(f["text"]) is None]
                if v["left_cp"]:                                   # what doesn't divide evenly stays in the loot
                    loot["finds"].append({"id": secrets.token_hex(5), "text": v["left"].lower()})
                self._log("Party loot shared %d ways: %s, %s each%s." % (
                    len(v["who"]), v["total"], v["each"], " (%s left in the party loot)" % v["left"] if v["left_cp"] else ""))
            elif op == "loot_item":                                # an item find into one character's bag
                loot = self._loot()
                f = next((f for f in loot["finds"] if f["id"] == req.get("id")), None)
                if not f:
                    raise ValueError("That find is no longer in the party loot.")
                p = self._purse(clean_name(req.get("character"), "A character's name"))
                item = next((i for i in self.catalog.values() if i["name"].casefold() == f["text"].casefold() and not i.get("bases")), None)
                entry = self._new_entry({"item": item["id"]} if item else {"name": f["text"][:60], "value_gp": 0})
                self._into_bag(p, entry)
                loot["finds"].remove(f)
                self._log("%s gets %s from the party loot." % (p["name"], entry["name"]))
            elif op == "bag_add":
                p = self._purse(clean_name(req.get("character"), "A character's name"))
                entry = self._new_entry(req)
                self._into_bag(p, entry)
                self._log("%s gets %s%s." % (p["name"], _count(entry["name"], entry["qty"]), _why(req)))
            elif op == "bag_remove":
                p = self._purse(clean_name(req.get("character"), "A character's name"), make=False)
                entry = next((b for b in (p or {}).get("bag", []) if b["id"] == req.get("entry")), None)
                if not entry:
                    raise ValueError("That item is no longer in the bag.")
                qty = _qty(req.get("qty", entry["qty"]))
                entry["qty"] -= min(qty, entry["qty"])
                p["bag"] = [b for b in p["bag"] if b["qty"] > 0]
                self._log("%s: %s taken out of the bag%s." % (p["name"], _count(entry["name"], qty), _why(req)))
            elif op in ("cart_add", "cart_sell", "cart_remove"):
                name = clean_name(req.get("character"), "A character's name")
                self._cart_change(name, op, req, "GM")
                cart = self._cart(name)                             # the GM's own lines wait in Requests like a player's
                if not cart["sent"]:
                    cart.update(by="GM", at=self.clock())
                cart["sent"] = bool(cart["lines"])
            elif op == "decide":
                self._decide(clean_name(req.get("character"), "A character's name"), req, ctx)
            elif op == "refuse":
                self._refuse(clean_name(req.get("character"), "A character's name"), req.get("reason", ""))
            elif op == "dismiss":
                cart = self.state["carts"].get(key(req.get("character")))
                if cart:
                    cart["answer"] = None
            else:
                raise ValueError("op is state, view, catalog, template, shop_save, shop_delete, open, close, purse, loot_add, "
                                 "loot_remove, loot_who, loot_give, loot_item, bag_add, bag_remove, cart_add, cart_sell, "
                                 "cart_remove, decide, refuse or dismiss.")
            self._write()
            return self.gm_view(ctx)

    # ------------------------------------------------------------------ a seat's requests (its own character only)
    def player(self, character, req):
        op = req.get("op", "view")
        with self.lock:
            st = self._load()
            if op != "view":
                if not character:
                    raise ValueError("You are watching: the GM gives you a character to shop for.")
                if not st["open"]:
                    raise ValueError("The market is closed.")
                cart = self._cart(character)
                if op in ("cart_add", "cart_sell", "cart_remove"):
                    if cart["sent"]:
                        raise ValueError("Your cart is with the GM: wait for the answer, or take it back to change it.")
                    self._cart_change(character, op, req, "player")
                elif op == "send":
                    if not cart["lines"]:
                        raise ValueError("Your cart is empty.")
                    cart.update(sent=True, by=req.get("seat", ""), at=self.clock(), answer=None)
                    self._log("%s sent a cart to the GM (%d line%s)." % (cart["name"], len(cart["lines"]), "" if len(cart["lines"]) == 1 else "s"))
                elif op == "take_back":
                    if not cart["sent"]:
                        raise ValueError("Your cart is not with the GM.")
                    cart["sent"] = False
                elif op == "dismiss":
                    cart["answer"] = None
                else:
                    raise ValueError("op is view, cart_add, cart_sell, cart_remove, send, take_back or dismiss.")
                self._write()
            return self.player_view(character)

    # ------------------------------------------------------------------ helpers
    def _shop(self, sid):
        shop = self.state["shops"].get(sid) if isinstance(sid, str) else None
        if not shop:
            raise ValueError("No such shop (it may have been deleted on another screen).")
        return shop

    def _clean_shop(self, s, ctx):
        if not isinstance(s, dict):
            raise ValueError("A shop is {name, kind, pack, place or where, stock}.")
        sid = s.get("id") if isinstance(s.get("id"), str) and s.get("id") in self.state["shops"] else secrets.token_hex(6)
        if s.get("kind") not in KINDS:
            raise ValueError("A shop's kind is one of %s." % ", ".join(KINDS.values()))
        places = ctx.get("places") or {}
        old = self.state["shops"].get(sid)
        pack = s.get("pack")
        if not isinstance(pack, str) or (pack not in places and not (old and old["pack"] == pack)):
            raise ValueError("A shop belongs to a place in a loaded adventure: load the adventure first.")
        place = s.get("place") or ""
        where = s.get("where") or ""
        if place:
            found = next((p for p in places.get(pack, {}).get("places", []) if p["key"] == place), None)
            if not found and not (old and old["place"] == place):
                raise ValueError("That place is not in the adventure.")
            where = found["title"] if found else old["where"]
        where = clean_name(where, "The shop's place")
        buyback = s.get("buyback", 50)
        if isinstance(buyback, bool) or not isinstance(buyback, int) or not 0 <= buyback <= 100:
            raise ValueError("Buy-back is 0 to 100 percent of an item's value.")
        stock = s.get("stock") or []
        if not isinstance(stock, list) or len(stock) > MAX_STOCK:
            raise ValueError("A shop has at most %d lines of stock." % MAX_STOCK)
        return {"id": sid, "name": clean_name(s.get("name"), "A shop's name"), "kind": s["kind"], "pack": pack, "place": place,
                "where": where, "buyback": buyback, "note": _text(s.get("note"), 300), "stock": [self._clean_line(l) for l in stock]}

    def _clean_line(self, l):
        if not isinstance(l, dict):
            raise ValueError("A line of stock is {item or name, price_gp, qty}.")
        qty = l.get("qty")
        if qty is not None:
            qty = _qty(qty, allow_zero=True)
        line = {"id": l["id"] if isinstance(l.get("id"), str) and re.fullmatch(r"[a-f0-9]{8,16}", l["id"]) else secrets.token_hex(5),
                "qty": qty, "note": _text(l.get("note"), 200), "why": _text(l.get("why"), 200)}
        if l.get("item") is not None:
            item = self.catalog.get(l["item"])
            if not item:
                raise ValueError("%s is not in the SRD 5.2.1 list; add it as homebrew." % l["item"])
            base = l.get("base") or None
            if base is not None and base not in (item.get("bases") or []):
                raise ValueError("%s can't be made from %s." % (item["name"], base))
            if item.get("bases") and not base:
                raise ValueError("Choose what %s is made from." % item["name"])
            listed = self._list_price(item["id"], base)
            price = to_cp(l["price_gp"]) if l.get("price_gp") is not None else listed
            line.update(item=item["id"], name=item["name"] + (" (%s)" % base if base else ""), price_cp=price,
                        attunement=bool(item.get("attunement")))
            if base:
                line["base"] = base
        else:
            if l.get("price_gp") is None:
                raise ValueError("A homebrew line needs a price.")
            line.update(item=None, name=clean_name(l.get("name"), "An item's name"), price_cp=to_cp(l["price_gp"]),
                        homebrew=True, attunement=l.get("attunement") is True)
        if line["price_cp"] < 0:
            raise ValueError("A price can't be below nothing.")
        return line

    def _cart_change(self, name, op, req, by):
        st = self.state
        cart = self._cart(name)
        shop = st["shops"].get(st["open"]) if by == "player" else st["shops"].get(req.get("shop") or st["open"])
        if not shop:
            raise ValueError("Open a shop first." if by == "GM" else "The market is closed.")
        if cart["shop"] != shop["id"]:                            # a cart is for one shop: another shop starts it again
            if cart["sent"] and cart["lines"] and by == "player":
                raise ValueError("Your cart for %s is with the GM." % (st["shops"].get(cart["shop"]) or {}).get("name", "another shop"))
            cart.update(shop=shop["id"], lines=[], sent=False)
        if op == "cart_remove":
            cart["lines"] = [l for l in cart["lines"] if l["id"] != req.get("line")]
            return
        if len(cart["lines"]) >= MAX_CART:
            raise ValueError("A cart holds at most %d lines." % MAX_CART)
        qty = _qty(req.get("qty", 1))
        if op == "cart_add":
            line = next((l for l in shop["stock"] if l["id"] == req.get("stock")), None)
            if not line:
                raise ValueError("That is no longer in stock.")
            if line.get("qty") is not None and qty > line["qty"]:
                raise ValueError("%s has only %d %s." % (shop["name"], line["qty"], line["name"]))
            mine = next((l for l in cart["lines"] if l["op"] == "buy" and l["stock"] == line["id"]), None)
            if mine:
                mine.update(qty=qty, price_cp=line["price_cp"])
            else:
                cart["lines"].append({"id": secrets.token_hex(5), "op": "buy", "stock": line["id"], "item": line.get("item"),
                                      "base": line.get("base"), "name": line["name"], "qty": qty, "price_cp": line["price_cp"],
                                      "homebrew": bool(line.get("homebrew")), "attunement": bool(line.get("attunement"))})
        else:
            p = self._purse(name, make=False)
            entry = next((b for b in (p or {}).get("bag", []) if b["id"] == req.get("entry")), None)
            if not entry:
                raise ValueError("That item is not in %s's bag." % name)
            qty = min(qty, entry["qty"])
            price = entry["value_cp"] * shop["buyback"] // 100
            mine = next((l for l in cart["lines"] if l["op"] == "sell" and l["entry"] == entry["id"]), None)
            if mine:
                mine.update(qty=qty, price_cp=price)
            else:
                cart["lines"].append({"id": secrets.token_hex(5), "op": "sell", "entry": entry["id"], "name": entry["name"],
                                      "qty": qty, "price_cp": price})

    def _decide(self, name, req, ctx):
        """Approve the chosen lines (at the GM's price, if given), refuse the others; all or nothing on the gold."""
        st = self.state
        cart = st["carts"].get(key(name))
        if not cart or not cart["lines"]:
            raise ValueError("%s has nothing waiting." % name)
        chosen, prices = req.get("lines"), req.get("prices") or {}
        if not isinstance(chosen, list) or not all(isinstance(x, str) for x in chosen) or not isinstance(prices, dict):
            raise ValueError("Approve names the chosen lines (lines: [...]) and any changed prices (prices: {line: GP}).")
        if req.get("rev") is not None and req["rev"] != st["rev"]:
            raise Conflict("The cart changed since you looked: check it again, then approve.")
        shop = st["shops"].get(cart["shop"])
        purse = self._purse(name)
        yes = [l for l in cart["lines"] if l["id"] in chosen]
        no = [l for l in cart["lines"] if l["id"] not in chosen]
        for l in yes:
            if l["id"] in prices:
                cp = to_cp(prices[l["id"]])
                if cp < 0:
                    raise ValueError("A price can't be below nothing.")
                l["price_cp"] = cp
        # check everything before changing anything
        buy = sell = 0
        for l in yes:
            if l["op"] == "buy":
                stock = next((s for s in (shop or {}).get("stock", []) if s["id"] == l["stock"]), None)
                if not stock:
                    raise ValueError("%s is no longer in stock: untick it." % l["name"])
                if stock.get("qty") is not None and l["qty"] > stock["qty"]:
                    raise ValueError("%s has only %d %s: untick it or change the stock." % (shop["name"], stock["qty"], l["name"]))
                buy += l["price_cp"] * l["qty"]
            else:
                entry = next((b for b in purse["bag"] if b["id"] == l["entry"]), None)
                if not entry or entry["qty"] < l["qty"]:
                    raise ValueError("%s no longer has %s: untick it." % (purse["name"], _count(l["name"], l["qty"])))
                sell += l["price_cp"] * l["qty"]
        if purse["cp"] + sell - buy < 0:
            raise ValueError("%s has %s; the ticked lines cost %s%s. Untick some, or give %s gold first."
                             % (purse["name"], money(purse["cp"]), money(buy), " less %s from selling" % money(sell) if sell else "", purse["name"]))
        for l in yes:
            if l["op"] == "buy":
                stock = next(s for s in shop["stock"] if s["id"] == l["stock"])
                if stock.get("qty") is not None:
                    stock["qty"] -= l["qty"]
                item = self.catalog.get(l.get("item")) or {}
                value = self._list_price(l.get("item"), l.get("base"))
                self._into_bag(purse, {"item": l.get("item"), "base": l.get("base"), "name": l["name"], "qty": l["qty"],
                                       "value_cp": value if value is not None else l["price_cp"], "kind": item.get("kind", "homebrew"),
                                       "rarity": item.get("rarity"), "attunement": bool(l.get("attunement")),
                                       "homebrew": bool(l.get("homebrew"))})
            else:
                entry = next(b for b in purse["bag"] if b["id"] == l["entry"])
                entry["qty"] -= l["qty"]
        purse["bag"] = [b for b in purse["bag"] if b["qty"] > 0]
        purse["cp"] += sell - buy
        shop_name = shop["name"] if shop else "the market"
        bought = [_count(l["name"], l["qty"]) + " (%s)" % money(l["price_cp"] * l["qty"]) for l in yes if l["op"] == "buy"]
        sold = [_count(l["name"], l["qty"]) + " (%s)" % money(l["price_cp"] * l["qty"]) for l in yes if l["op"] == "sell"]
        refused = [_count(l["name"], l["qty"]) for l in no]
        if bought:
            self._log("%s bought at %s: %s." % (purse["name"], shop_name, ", ".join(bought)))
        if sold:
            self._log("%s sold at %s: %s." % (purse["name"], shop_name, ", ".join(sold)))
        if refused:
            self._log("%s: refused by the GM: %s." % (purse["name"], ", ".join(refused)))
        cart.update(lines=[], sent=False, answer={"at": self.clock(), "bought": bought, "sold": sold, "refused": refused,
                                                   "reason": _text(req.get("reason"), 200), "gold": money(purse["cp"])})
        self.announce = "%s at %s: %s" % (purse["name"], shop_name, "; ".join(
            x for x in ("bought " + ", ".join(_count(l["name"], l["qty"]) for l in yes if l["op"] == "buy") if bought else "",
                        "sold " + ", ".join(_count(l["name"], l["qty"]) for l in yes if l["op"] == "sell") if sold else "",
                        "refused " + ", ".join(refused) if refused else "") if x))

    def _refuse(self, name, reason):
        cart = self.state["carts"].get(key(name))
        if not cart or not cart["lines"]:
            raise ValueError("%s has nothing waiting." % name)
        refused = [_count(l["name"], l["qty"]) for l in cart["lines"]]
        self._log("%s: refused by the GM: %s." % (cart["name"], ", ".join(refused)))
        purse = self._purse(name, make=False)
        cart.update(lines=[], sent=False, answer={"at": self.clock(), "bought": [], "sold": [], "refused": refused,
                                                   "reason": _text(reason, 200), "gold": money(purse["cp"] if purse else 0)})

    def _new_entry(self, req):
        if req.get("item") is not None:
            item = self.catalog.get(req["item"])
            if not item:
                raise ValueError("%s is not in the SRD 5.2.1 list." % req["item"])
            base = req.get("base") or None
            if base is not None and base not in (item.get("bases") or []):
                raise ValueError("%s can't be made from %s." % (item["name"], base))
            return {"item": item["id"], "base": base, "name": item["name"] + (" (%s)" % base if base else ""), "qty": _qty(req.get("qty", 1)),
                    "value_cp": self._list_price(item["id"], base), "kind": item["kind"], "rarity": item.get("rarity"),
                    "attunement": bool(item.get("attunement")), "homebrew": False}
        value = to_cp(req.get("value_gp", 0))
        return {"item": None, "base": None, "name": clean_name(req.get("name"), "An item's name"), "qty": _qty(req.get("qty", 1)),
                "value_cp": max(0, value), "kind": "homebrew", "rarity": None, "attunement": req.get("attunement") is True,
                "homebrew": True}

    def _into_bag(self, purse, entry):
        same = next((b for b in purse["bag"] if b.get("item") == entry.get("item") and b["name"] == entry["name"]
                     and b.get("value_cp") == entry["value_cp"]), None)
        if same:
            same["qty"] = min(MAX_QTY * 10, same["qty"] + entry["qty"])
            return
        if len(purse["bag"]) >= MAX_BAG:
            raise ValueError("%s's bag is full (%d different items)." % (purse["name"], MAX_BAG))
        purse["bag"].append(dict(entry, id=secrets.token_hex(5)))

    # ------------------------------------------------------------------ a new shop's stock, for the GM to change
    def template(self, kind, ctx, seed=1):
        if kind not in KINDS:
            raise ValueError("A shop's kind is one of %s." % ", ".join(KINDS.values()))
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed is a number.")
        cat, level, party = self.catalog, ctx.get("level") or 1, ctx.get("party") or []
        rng = random.Random(seed)
        lines, notes = [], []
        if kind == "smith":
            ids = [i for i, v in cat.items() if v["kind"] in ("weapon", "armor") and v["name"] not in ("Musket", "Pistol")]
            ids += [i for i, v in cat.items() if v["kind"] == "ammunition" and "Firearm" not in v["name"]] + ["smiths-tools"]
        else:
            ids = list(EVERYDAY[kind])
        for i in ids:
            if i in cat:
                lines.append({"item": i, "qty": LIMITED.get(i)})
        if kind == "alchemist":                                    # one to three potions the party's level allows
            allowed = rarities_for(level)
            pots = [v for v in cat.values() if v["kind"] == "potion" and v["rarity"] in allowed and v["id"] != "potion-of-healing"]
            rng.shuffle(pots)
            pots.sort(key=lambda v: 0 if v["name"].startswith("Potion of Healing") else 1)
            for v in pots[:rng.randint(1, 3)]:
                lines.append({"item": v["id"], "qty": rng.randint(1, 3)})
                notes.append("%s (%s)" % (v["name"], v["rarity"].lower()))
        if kind in SCROLL_CLASSES:                                 # three to six scrolls the party could use
            top = max_scroll_level(level)
            classes = {m.get("class") for m in party if m.get("class")}
            want = [c for c in SCROLL_CLASSES[kind] if not classes or c in classes] or list(SCROLL_CLASSES[kind])
            pool = [v for v in cat.values() if v["kind"] == "scroll" and v["level"] <= top and any(c in v["classes"] for c in want)]
            rng.shuffle(pool)
            pool.sort(key=lambda v: v["level"])
            for v in sorted(pool[:rng.randint(3, 6)], key=lambda v: (v["level"], v["spell"])):
                lines.append({"item": v["id"], "qty": 1})
                notes.append("%s (level %d)" % (v["name"], v["level"]))
        if kind == "broker":                                       # one to three magic items picked for the party
            for item, why, base, who in party_picks(cat, party, level, rng.randint(1, 3), seed):
                lines.append({"item": item["id"], "qty": 1, "base": base,      # why: for the GM only, never the players
                              "why": ("for %s: %s" % (who, ", ".join(why))) if who else ", ".join(why)})
                notes.append("%s%s (%s)" % (item["name"], " (%s)" % base if base else "", item["rarity"].lower()))
        for l in lines:
            l["price_gp"] = None
            l["name"] = cat[l["item"]]["name"] + (" (%s)" % l["base"] if l.get("base") else "")
            l["list_cp"] = self._list_price(l["item"], l.get("base"))
            l["list"] = money(l["list_cp"])
        return {"kind": kind, "name": KINDS[kind], "stock": lines, "level": level, "rarities": rarities_for(level),
                "picked": notes, "party": [m.get("name") for m in party]}


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("’", "")).strip("-")


def _qty(q, allow_zero=False):
    if isinstance(q, bool) or not isinstance(q, int) or not (0 if allow_zero else 1) <= q <= MAX_QTY:
        raise ValueError("A quantity is a whole number from %d to %d." % (0 if allow_zero else 1, MAX_QTY))
    return q


def _text(v, n):
    return v.strip()[:n] if isinstance(v, str) else ""


def _why(req):
    r = _text(req.get("reason"), 120)
    return " (%s)" % r if r else ""


def _either(names):
    return names[0] if len(names) == 1 else "%s or %s" % (", ".join(names[:-1]), names[-1])


def _count(name, qty):
    return name if qty == 1 else "%s x%d" % (name, qty)
