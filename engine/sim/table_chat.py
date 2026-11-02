"""TABLE-CHAT-01 (GM 2026-10-19: "there needs to be a small chat window for text messages, output all dice rolls with
outcomes and the player making the rolls ... The rolling tool also needs a private roll only seen by the DM"). The
reference for the ports, like sim/stage.py and sim/dice_tool.py: plain JSON state, no I/O, no clock and no dice of its
own (the caller passes `now` and `rng(sides)`).

CHAT-FUN-01 (GM 2026-10-21: "private messages are unnecessary. They can be done with 3rd party apps. Let's use chat for
fun stuff like gifs, sharing music, etc."): whispers are gone. A line that is a link to a picture (.gif .png .jpg .webp)
or to music (YouTube, Spotify, Bandcamp, SoundCloud, or an audio file) is shared as a picture or a music card; words
after the link are its caption. A picture or an audio file from the PC is checked here (media_kind: by its first bytes,
never its name) and stored by the service (tools/sim_service.py, sim/chat_media); share_file adds it to the chat.
Nothing plays by itself: the page shows a link card with an Open button, or the browser's own player.

What each seat sees is decided here, never by a page:
- a message, a share or a roll: everyone;
- a private roll for the GM: the GM sees the whole roll; the player who rolled sees only that they rolled privately
  (not the result); nobody else sees anything.
Seats are names (one PC, hotseat): this is a courtesy screen, not security, until players have their own logins.

Messaging code, typed in the chat line:
  text                       a message to everyone
  https://...gif  caption    a picture or music shared with everyone (the caption is optional)
  /r 1d20+5 Stealth          a roll everyone sees (also /roll); the first word is the dice, the rest the label
  /gmr 1d20+5 Stealth        a private roll only the GM sees (also /gmroll)
  /help                      the list (only to the one who asks)
"""
import re
from urllib.parse import urlsplit
import dice_tool

CASES_FORMAT = "table-chat-cases/1"
MAX_TEXT, MAX_ENTRIES, MAX_URL, MAX_CAPTION = 500, 300, 500, 120
GM = "GM"
HELP = ("Chat: type to talk to everyone. Paste a link to a picture (.gif .png .jpg .webp) or to music (YouTube, Spotify, "
        "Bandcamp, SoundCloud, an audio file) to share it; words after the link are its caption. /r 1d20+5 Stealth: a "
        "roll everyone sees. /gmr 1d20+5 Stealth: a private roll only the GM sees.")
NO_WHISPERS = "Chat: private messages are not part of the chat any more; use your own messaging app."
URL = re.compile(r"^https?://[^\s<>\"'`\\]+$", re.I)
PICTURE_EXT = (".gif", ".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXT = (".mp3", ".ogg", ".oga", ".wav", ".m4a", ".flac", ".opus")
MUSIC_SITES = (("youtube.com", "YouTube"), ("youtu.be", "YouTube"), ("spotify.com", "Spotify"),
               ("bandcamp.com", "Bandcamp"), ("soundcloud.com", "SoundCloud"))
# CHAT-FUN-01: files from the PC: what the first bytes say, the file name the service gives it, and the size limit
PICTURE_MAX, AUDIO_MAX = 5 * 1024 * 1024, 20 * 1024 * 1024
FILE_NAME = re.compile(r"^[0-9a-f]{32}\.(gif|png|jpg|webp|mp3|ogg|wav)$")
MEDIA_TYPES = {"gif": "image/gif", "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
               "mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav"}


class ChatError(ValueError):
    pass


def new():
    return {"entries": [], "n": 0}


def _same(a, b):
    return (a or "").lower() == (b or "").lower()


def _add(chat, entry):
    chat["n"] += 1
    entry["n"] = chat["n"]
    chat["entries"] = (chat["entries"] + [entry])[-MAX_ENTRIES:]
    return entry


def say(chat, seat, text, now):
    text = (text or "").strip()
    if not text:
        raise ChatError("Chat: nothing to send.")
    return _add(chat, {"kind": "say", "from": seat, "at": now, "text": text[:MAX_TEXT]})


def link_kind(url):
    """CHAT-FUN-01: ('picture', '') or ('music', site name) for a link worth showing, else (None, '')."""
    if not isinstance(url, str) or len(url) > MAX_URL or not URL.match(url):
        return None, ""
    try:
        parts = urlsplit(url)
        host, path = (parts.hostname or "").lower(), parts.path.lower()
    except ValueError:
        return None, ""
    if not host:
        return None, ""
    if path.endswith(PICTURE_EXT):
        return "picture", ""
    if path.endswith(AUDIO_EXT):
        return "music", "Audio file"
    for domain, site in MUSIC_SITES:
        if host == domain or host.endswith("." + domain):
            return "music", site
    return None, ""


def share_link(chat, seat, url, caption, now):
    kind, site = link_kind(url)
    if not kind:
        raise ChatError("Chat: share a link to a picture (.gif .png .jpg .webp) or to music.")
    caption = (caption or "").strip()[:MAX_CAPTION]
    entry = {"kind": kind, "from": seat, "at": now, "url": url, "caption": caption, "text": caption or url}
    if site:
        entry["site"] = site
    return _add(chat, entry)


def media_kind(data):
    """CHAT-FUN-01: a file from the PC by its first bytes: ('picture'|'audio', extension) or (None, None)."""
    head = bytes(data[:16])
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "picture", "gif"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "picture", "png"
    if head[:3] == b"\xff\xd8\xff":
        return "picture", "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "picture", "webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "wav"
    if head[:4] == b"OggS":
        return "audio", "ogg"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio", "mp3"
    return None, None


def check_file(data):
    """The kind and extension of a file the PC sends, or ChatError with the reason (type, then size)."""
    kind, ext = media_kind(data)
    if not kind:
        raise ChatError("Chat: share a picture (GIF, PNG, JPEG, WebP) or an audio file (MP3, Ogg, WAV).")
    limit = PICTURE_MAX if kind == "picture" else AUDIO_MAX
    if len(data) > limit:
        raise ChatError("Chat: a %s can be %d MB at most." % ("picture" if kind == "picture" else "sound file", limit // (1024 * 1024)))
    return kind, ext


def share_file(chat, seat, kind, url, name, caption, now):
    """A file the service has stored (url: /chat-media/<FILE_NAME>); name is the PC's file name, shown, never used."""
    name = re.sub(r"[\x00-\x1f]", "", (name or "").strip())[:80]
    caption = (caption or "").strip()[:MAX_CAPTION]
    return _add(chat, {"kind": "picture" if kind == "picture" else "audio", "from": seat, "at": now, "url": url,
                       "name": name, "caption": caption, "text": caption or name or "a file"})


def roll(chat, seat, expr, label, rng, now, private=False):
    try:
        r = dice_tool.roll(expr, rng, seat, label)
    except dice_tool.DiceError as e:
        raise ChatError(str(e))
    return _add(chat, {"kind": "gmroll" if private else "roll", "from": seat, "at": now, "text": r["text"],
                       "expr": r["expr"], "label": r["label"], "total": r["total"], "natural": r["natural"],
                       "terms": r["terms"]})


def _words(rest):
    """'"Old Hero 3" hello there' -> ('Old Hero 3', 'hello there'); 'Hero 3 hi' -> ('Hero 3', 'hi')."""
    rest = rest.strip()
    m = re.match(r'^"([^"]*)"\s*(.*)$', rest, re.S) or re.match(r"^(\S+)\s*(.*)$", rest, re.S)
    return (m.group(1).strip(), m.group(2)) if m else ("", "")


def post(chat, seat, line, rng, now):
    """A line typed in the chat. Returns (entry or None, a private answer for the one who typed or None)."""
    if not isinstance(line, str):
        raise ChatError("Chat: messages are text.")
    line = line.strip()
    if len(line) > MAX_TEXT:
        raise ChatError("Chat: %d characters at most." % MAX_TEXT)
    if not line.startswith("/"):
        first, _, rest = line.partition(" ")
        if link_kind(first)[0]:                                  # CHAT-FUN-01: a picture or music link
            return share_link(chat, seat, first, rest, now), None
        return say(chat, seat, line, now), None
    cmd, _, rest = line.partition(" ")
    cmd = cmd.lower()
    if cmd in ("/w", "/whisper", "/msg"):
        raise ChatError(NO_WHISPERS)
    if cmd in ("/r", "/roll", "/gmr", "/gmroll"):
        expr, label = _words(rest)
        if not expr:
            raise ChatError("Chat: %s and then the dice, e.g. %s 1d20+5 Stealth" % (cmd, cmd))
        return roll(chat, seat, expr, label, rng, now, private=cmd in ("/gmr", "/gmroll")), None
    if cmd == "/help":
        return None, HELP
    raise ChatError("Chat: unknown command %s. Type /help." % cmd)


def view(entry, seat):
    """What `seat` sees of one entry, or None."""
    gm, mine = _same(seat, GM), _same(entry["from"], seat)
    k = entry["kind"]
    if k in ("say", "roll", "picture", "music", "audio"):
        return dict(entry)
    if k == "gmroll":
        if gm:
            return dict(entry)
        if mine:
            label = " (%s)" % entry["label"] if entry.get("label") else ""
            return {"n": entry["n"], "kind": "gmroll", "from": entry["from"], "at": entry["at"], "hidden": True,
                    "text": "%s rolls %s%s privately for the GM." % (entry["from"], entry["expr"], label)}
        return None
    return None


def visible(chat, seat):
    return [v for v in (view(e, seat) for e in chat["entries"]) if v]


def run_case(case):
    """Play one case from table_chat_cases.json; returns a list of mismatches."""
    chat, faces, problems = new(), list(case.get("dice", [])), []
    rng = lambda sides: faces.pop(0)
    for i, step in enumerate(case["steps"]):
        if "post" in step:
            try:
                entry, answer = post(chat, step["seat"], step["post"], rng, step.get("now", 0))
                got = {"answer": answer, "kind": entry and entry["kind"], "site": entry and entry.get("site")}
            except ChatError as e:
                got = {"error": str(e)}
            for k, want in step.get("expect", {}).items():
                if got.get(k) != want:
                    problems.append("%s step %d %s: want %r, got %r" % (case["name"], i + 1, k, want, got.get(k)))
        if "sees" in step:
            got = [e["text"] for e in visible(chat, step["sees"])]
            if got != step["expect_texts"]:
                problems.append("%s step %d %s sees: want %r, got %r" % (case["name"], i + 1, step["sees"], step["expect_texts"], got))
    return problems
