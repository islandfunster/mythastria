"""BETA-B part 1 (GM 2026-10-22, before the players' door goes on the internet for a blind playability test): the
players' door counts each visitor's requests and wrong codes, slows down or blocks the ones that go too far, and keeps a
short door log for the GM (Play live, Players...). Protocol: docs/development/JOIN_PROTOCOL.md "Guarding the door".

A visitor is the connection's address (behind the Cloudflare Tunnel: CF-Connecting-IP, see sim_service
make_players_door). Addresses are kept in memory only, for at most the counting windows below, and never written to the
door log: the log names the player's typed name, or an anonymous visitor tag that changes at every restart.
"""
import hashlib, secrets, threading, time
from collections import deque

LIMITS = {"any": (1200, 60), "ask": (5, 60), "key": (5, 60)}      # requests per window (seconds), per visitor
WRONG, WRONG_WINDOW, BLOCK = 10, 300, 300                          # 10 wrong codes in 5 minutes: blocked 5 minutes
LOG_KEEP = 100


class DoorGuard:
    def __init__(self, clock=time.time):
        self.lock = threading.Lock()
        self.clock = clock
        self.salt = secrets.token_bytes(16)                        # visitor tags change at every restart
        self.hits, self.wrong, self.blocked, self.slowed = {}, {}, {}, {}
        self.log = deque(maxlen=LOG_KEEP)

    def tag(self, visitor):
        return "visitor " + hashlib.sha256(self.salt + str(visitor).encode("utf-8")).hexdigest()[:4]

    def _note(self, who, text):
        self.log.append({"t": int(self.clock()), "who": who, "text": text})

    def _prune(self, now):
        if len(self.hits) + len(self.wrong) < 5000:
            return
        for d, keep in ((self.hits, max(w for _, w in LIMITS.values())), (self.wrong, WRONG_WINDOW)):
            for k in [k for k, q in d.items() if not q or now - q[-1] > keep]:
                del d[k]
        for k in [k for k, until in self.blocked.items() if until <= now]:
            del self.blocked[k]

    def check(self, visitor, kind="any"):
        """None, or (429, message) when the visitor is blocked or over a limit (the request is not counted again)."""
        with self.lock:
            now = self.clock()
            self._prune(now)
            until = self.blocked.get(visitor, 0)
            if until > now:
                return 429, "Too many wrong codes from here. Wait %d minutes, then try again." % max(1, round((until - now) / 60))
            for k in ("any", kind) if kind != "any" else ("any",):
                n, window = LIMITS[k]
                q = self.hits.setdefault((visitor, k), deque())
                while q and now - q[0] > window:
                    q.popleft()
                if len(q) >= n:
                    if now - self.slowed.get((visitor, k), 0) > window:   # one log line per window, not one per request
                        self.slowed[(visitor, k)] = now
                        self._note(self.tag(visitor), "slowed down (%s)" % ("too many requests" if k == "any" else "too many tries"))
                    return 429, "Slow down: that was too many tries in a short time. Wait a minute, then try again."
                q.append(now)
            return None

    def missed(self, visitor, what):
        """A wrong invite code or stand-in key: 10 in 5 minutes block the visitor for 5 minutes."""
        with self.lock:
            now = self.clock()
            q = self.wrong.setdefault(visitor, deque())
            while q and now - q[0] > WRONG_WINDOW:
                q.popleft()
            q.append(now)
            self._note(self.tag(visitor), "wrong %s" % what)
            if len(q) >= WRONG:
                self.blocked[visitor] = now + BLOCK
                q.clear()
                self._note(self.tag(visitor), "blocked for %d minutes (too many wrong codes)" % (BLOCK // 60))

    def note(self, who, text):
        with self.lock:
            self._note(who, text)

    def recent(self, n=40):
        with self.lock:
            return list(self.log)[-n:][::-1]
