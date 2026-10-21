#!/usr/bin/env python3
"""Candy Call: refill requests from harvest-party booths to the candy team.

Standard library only (Python 3.8+). Run:  python3 server.py
Then open http://<this-computer>:8000/ on phones and the iPad.

Environment variables (all optional):
  PORT        port to listen on (default 8000)
  TEAM_PIN    if set, the team dashboard asks for this PIN before it can act
  ACK_SECONDS how long a booth shows "Candy is on its way" (default 45)
  DATA_FILE   where state is saved between restarts (default data.json)
"""

import json
import os
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
PORT = int(os.environ.get("PORT", "8000"))
TEAM_PIN = os.environ.get("TEAM_PIN", "").strip()
ACK_SECONDS = int(os.environ.get("ACK_SECONDS", "45"))
DATA_FILE = Path(os.environ.get("DATA_FILE", str(ROOT / "data.json")))

BOOTH_ID = re.compile(r"^[A-Z0-9]{1,6}$")

lock = threading.Lock()
listeners = set()  # one queue.Queue per open event stream

# booths: id -> {"status": "ok"|"requested"|"in_progress",
#                "requestedAt": float|None, "ackAt": float|None,
#                "count": int,   (refills delivered tonight)
#                "manual": int}  (how many of those were logged as given in person)
# log: [{"t": float, "type": "request"|"ack"|"refill", "booth": id,
#        "wait": seconds (ack only), "manual": bool (refill only)}]
# inventory: candy on hand for the event overview page
state = {"order": [], "booths": {}, "log": [], "inventory": {}}
LOG_LIMIT = 20000


def load():
    global state
    try:
        state = json.loads(DATA_FILE.read_text())
        state.setdefault("order", [])
        state.setdefault("booths", {})
    except (OSError, ValueError):
        pass
    state.setdefault("log", [])
    inv = state.setdefault("inventory", {})
    inv.setdefault("unit", "bags")
    inv.setdefault("perRefill", 1)
    inv.setdefault("starting", 0)
    inv.setdefault("restocks", [])


def save():
    try:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(DATA_FILE)
    except OSError:
        pass


def snapshot():
    return {
        "now": time.time(),
        "ackSeconds": ACK_SECONDS,
        "pinRequired": bool(TEAM_PIN),
        "order": state["order"],
        "booths": state["booths"],
    }


def log_event(kind, bid, **extra):
    """Call with the lock held."""
    state["log"].append(dict(t=time.time(), type=kind, booth=bid, **extra))
    del state["log"][:-LOG_LIMIT]


def number(value, default=0.0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return n if 0 <= n <= 1_000_000 else default


def broadcast():
    """Call with the lock held."""
    save()
    msg = json.dumps(snapshot())
    for q in list(listeners):
        q.put(msg)


def ensure_booth(bid):
    if bid not in state["booths"]:
        state["booths"][bid] = {"status": "ok", "requestedAt": None, "ackAt": None, "count": 0}
        state["order"].append(bid)
    return state["booths"][bid]


def natural_key(s):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def expand_booth_list(text):
    """'A1-A10, B1-B4, 12' -> ['A1', ..., 'A10', 'B1', ..., 'B4', '12']"""
    out = []
    for part in re.split(r"[,\s]+", text.upper()):
        if not part:
            continue
        m = re.fullmatch(r"([A-Z]*)(\d+)-\1?(\d+)", part)
        if m:
            prefix, a, b = m.group(1), int(m.group(2)), int(m.group(3))
            if a <= b and b - a < 200:
                out += [f"{prefix}{n}" for n in range(a, b + 1)]
                continue
        if BOOTH_ID.match(part):
            out.append(part)
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # keep the console quiet; actions are logged below

    # ---- helpers -------------------------------------------------------
    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 10000:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    def team_ok(self, data):
        return not TEAM_PIN or str(data.get("pin", "")) == TEAM_PIN

    # ---- routes --------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/events":
            return self.stream()
        if path == "/api/state":
            with lock:
                return self.send_json(snapshot())
        if path == "/api/overview":
            with lock:
                return self.send_json(dict(snapshot(), log=state["log"], inventory=state["inventory"]))
        pages = {"/": "index.html", "/booth": "booth.html", "/team": "team.html", "/admin": "admin.html"}
        name = pages.get(path, path.lstrip("/"))
        f = (PUBLIC / name).resolve()
        if PUBLIC not in f.parents or not f.is_file():
            return self.send_json({"error": "Not found"}, 404)
        types = {".html": "text/html; charset=utf-8", ".css": "text/css",
                 ".js": "application/javascript", ".svg": "image/svg+xml",
                 ".json": "application/json", ".png": "image/png",
                 ".webmanifest": "application/manifest+json"}
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", types.get(f.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def stream(self):
        q = queue.Queue()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        with lock:
            listeners.add(q)
            q.put(json.dumps(snapshot()))
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(f"data: {msg}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")  # keeps proxies and phones connected
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with lock:
                listeners.discard(q)

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.read_json()
        bid = str(data.get("booth", "")).strip().upper()

        if path == "/api/team/check":
            return self.send_json({"ok": self.team_ok(data)})

        if path == "/api/request":
            if not BOOTH_ID.match(bid):
                return self.send_json({"error": "Booth numbers are 1-6 letters or digits."}, 400)
            with lock:
                b = ensure_booth(bid)
                if b["status"] != "requested":
                    b.update(status="requested", requestedAt=time.time(), ackAt=None)
                    log_event("request", bid)
                    print(f"{time.strftime('%H:%M:%S')}  booth {bid} requested a refill", flush=True)
                broadcast()
            return self.send_json({"ok": True})

        if path == "/api/join":
            if not BOOTH_ID.match(bid):
                return self.send_json({"error": "Booth numbers are 1-6 letters or digits."}, 400)
            with lock:
                if bid not in state["booths"]:
                    ensure_booth(bid)
                    broadcast()
            return self.send_json({"ok": True})

        # Everything below is team-only.
        if not self.team_ok(data):
            return self.send_json({"error": "Wrong team PIN."}, 403)

        with lock:
            if path in ("/api/ack", "/api/deliver", "/api/clear", "/api/remove", "/api/uncount"):
                b = state["booths"].get(bid)
                if not b:
                    return self.send_json({"error": "Unknown booth."}, 404)
                if path == "/api/ack":
                    if b["status"] == "requested" and b.get("requestedAt"):
                        log_event("ack", bid, wait=round(time.time() - b["requestedAt"], 1))
                    b.update(status="in_progress", ackAt=time.time())
                    print(f"{time.strftime('%H:%M:%S')}  booth {bid} acknowledged", flush=True)
                elif path == "/api/deliver":
                    b.update(status="ok", requestedAt=None, ackAt=None, count=b.get("count", 0) + 1)
                    log_event("refill", bid, manual=bool(data.get("manual")))
                    if data.get("manual"):
                        b["manual"] = b.get("manual", 0) + 1
                        print(f"{time.strftime('%H:%M:%S')}  booth {bid} refill logged in person", flush=True)
                elif path == "/api/uncount":
                    for i in range(len(state["log"]) - 1, -1, -1):
                        e = state["log"][i]
                        if e["type"] == "refill" and e["booth"] == bid:
                            if e.get("manual"):
                                b["manual"] = max(0, b.get("manual", 0) - 1)
                            del state["log"][i]
                            break
                    b["count"] = max(0, b.get("count", 0) - 1)
                    b["manual"] = min(b.get("manual", 0), b["count"])
                elif path == "/api/clear":
                    b.update(status="ok", requestedAt=None, ackAt=None)
                elif path == "/api/remove":
                    del state["booths"][bid]
                    state["order"].remove(bid)
            elif path == "/api/booths":
                ids = expand_booth_list(str(data.get("list", "")))
                for i in ids:
                    ensure_booth(i)
                if data.get("replace"):
                    for old in [x for x in state["order"] if x not in ids]:
                        del state["booths"][old]
                    state["order"] = ids[:]
            elif path == "/api/sort":
                state["order"].sort(key=natural_key)
            elif path == "/api/reset":
                for b in state["booths"].values():
                    b.update(status="ok", requestedAt=None, ackAt=None, count=0, manual=0)
                state["log"] = []
            elif path == "/api/inventory":
                inv = state["inventory"]
                unit = str(data.get("unit", inv["unit"])).strip()[:20]
                inv.update(unit=unit or "bags",
                           perRefill=number(data.get("perRefill"), inv["perRefill"]),
                           starting=number(data.get("starting"), inv["starting"]))
            elif path == "/api/restock":
                amount = number(data.get("amount"))
                if amount <= 0:
                    return self.send_json({"error": "Enter how much candy was added."}, 400)
                state["inventory"]["restocks"].append({"t": time.time(), "amount": amount})
            elif path == "/api/restock/undo":
                if state["inventory"]["restocks"]:
                    state["inventory"]["restocks"].pop()
            else:
                return self.send_json({"error": "Not found"}, 404)
            broadcast()
        return self.send_json({"ok": True})


def main():
    load()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print(f"Candy Call running on port {PORT}", flush=True)
    print(f"  Booths: http://localhost:{PORT}/booth", flush=True)
    print(f"  Team:   http://localhost:{PORT}/team" + ("  (PIN required)" if TEAM_PIN else ""), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
