"""Wi-Fi fleet status page — remote dashboard over the local network (v1.3).

A tiny ``ThreadingHTTPServer`` (stdlib only) that exposes the running fleet
to any browser on the same Wi-Fi:

- ``GET /``                    → dark, phone-friendly HTML dashboard (auto-refresh)
- ``GET /api/status``          → JSON: host stats + full bot list
- ``GET /api/bots/<id>/logs``  → JSON: last N log records of one bot

Optional shared-secret protection: pass ``token`` and every request must
present ``?key=...`` or an ``Authorization: Bearer ...`` header, otherwise it
gets 401. The server binds an explicit host (default ``0.0.0.0``) and an
explicit port (``0`` = OS-assigned, reported back as ``port``).

Optional TLS (v1.4): pass both ``certfile`` and ``keyfile`` (PEM) and the
socket is wrapped with an ``ssl`` context — the dashboard is then served
over ``https://``. Certificates are *user-supplied*: generating them needs
a third-party library that the embedded Android runtime does not ship, so
the honest default stays plain HTTP inside the local network.

The server is opt-in: nothing listens until ``web_status_start`` is called
(from the app's settings or the CLI's ``serve-status`` command).
"""

from __future__ import annotations

import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DEFAULT_PORT = 8090
MAX_LOG_LIMIT = 1000

_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>DRS Bot Host — Fleet Status</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px 16px; font:15px/1.5 system-ui, sans-serif;
         background:#0a0e1a; color:#e8ecf4; }
  h1 { font-size:20px; margin:0 0 4px; }
  h1 span { color:#22d3ee; }
  .sub { color:#8b93a7; font-size:13px; margin-bottom:20px; }
  .tiles { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:22px; }
  .tile { background:#111827; border:1px solid #1f2937; border-radius:12px;
          padding:12px 18px; min-width:104px; }
  .tile b { display:block; font-size:24px; color:#22d3ee; }
  .tile small { color:#8b93a7; }
  table { width:100%; border-collapse:collapse; background:#111827;
          border:1px solid #1f2937; border-radius:12px; overflow:hidden; }
  th, td { text-align:left; padding:9px 12px; border-bottom:1px solid #1f2937;
           font-size:14px; }
  th { color:#8b93a7; font-weight:600; font-size:12px; text-transform:uppercase; }
  tr:last-child td { border-bottom:none; }
  .st { font-weight:700; font-size:12px; padding:2px 10px; border-radius:999px;
        border:1px solid; }
  .RUNNING,.STARTING,.BACKOFF { color:#34d399; border-color:#34d39955; }
  .FAILED { color:#f87171; border-color:#f8717155; }
  .STOPPING { color:#fbbf24; border-color:#fbbf2455; }
  .STOPPED,.COMPLETED,.FORCE_STOPPED { color:#8b93a7; border-color:#8b93a755; }
  code { color:#a5b4fc; font-size:12px; }
  .foot { margin-top:18px; color:#8b93a7; font-size:12px; }
</style></head><body>
<h1>DRS Bot Host <span>›</span> fleet status</h1>
<div class="sub">host __HOST_VERSION__ · python __PY_VERSION__ · uptime __UPTIME__ · refreshes every 5s</div>
<div class="tiles">
  <div class="tile"><b>__TOTAL__</b><small>bots</small></div>
  <div class="tile"><b>__RUNNING__</b><small>running</small></div>
  <div class="tile"><b>__FAILED__</b><small>failed</small></div>
  <div class="tile"><b>__RESTARTS__</b><small>restarts</small></div>
  <div class="tile"><b>__RUNS__</b><small>runs</small></div>
</div>
<table>
<tr><th>bot</th><th>state</th><th>runs</th><th>uptime</th><th>cpu</th></tr>
__ROWS__
</table>
<div class="foot">JSON API: <code>/api/status</code> · logs per bot: <code>/api/bots/&lt;id&gt;/logs?limit=100</code></div>
</body></html>"""

_STATE_CELL = '<td><span class="st {state}">{state}</span></td>'


class _FleetSnapshot:
    """Adapter: pulls JSON-safe data out of a live Supervisor."""

    def __init__(self, supervisor, host_version: str, python_version: str):
        self.supervisor = supervisor
        self.host_version = host_version
        self.python_version = python_version

    def status_document(self) -> dict:
        with self.supervisor.lock:
            bots = [bot.status() for bot in self.supervisor.bots.values()]
        stats = self.supervisor.host_stats()
        return {
            "ok": True,
            "host": {
                "drs_host": self.host_version,
                "python": self.python_version,
                "uptime_seconds": stats.get("uptime_seconds"),
                "process_rss_bytes": stats.get("process_rss_bytes"),
            },
            "stats": {k: v for k, v in stats.items() if k != "ok"},
            "bots": bots,
        }

    def bot_logs(self, bot_id: str, limit: int):
        records = self.supervisor.recent_logs(bot_id, limit)
        return {"ok": True, "id": bot_id, "count": len(records), "records": records}


class FleetStatusServer:
    """Start/stop the status web server. Never raises on start failures —
    it returns a structured result instead."""

    def __init__(self, snapshot: _FleetSnapshot, host: str = "0.0.0.0",
                 port: int = DEFAULT_PORT, token: str | None = None,
                 certfile: str | None = None, keyfile: str | None = None):
        self.snapshot = snapshot
        self.host = host
        self.requested_port = int(port)
        self.token = (str(token).strip() or None) if token else None
        self.certfile = (str(certfile).strip() or None) if certfile else None
        self.keyfile = (str(keyfile).strip() or None) if keyfile else None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _validate_tls(self) -> list:
        """Both-or-neither cert/key; files must exist when given."""
        errors = []
        if bool(self.certfile) != bool(self.keyfile):
            errors.append("TLS needs both certfile and keyfile (or neither)")
        for label, value in (("certfile", self.certfile), ("keyfile", self.keyfile)):
            if value is not None:
                try:
                    open(value, "rb").close()
                except OSError as exc:
                    errors.append(f"cannot read {label}: {exc}")
        return errors

    # -- lifecycle -------------------------------------------------------

    def start(self) -> dict:
        with self._lock:
            if self._server is not None:
                return {"ok": True, "port": self.actual_port(), "already": True}
            tls_errors = self._validate_tls()
            if tls_errors:
                return {"ok": False, "errors": tls_errors}
            outer = self

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    outer._handle(self)

                def log_message(self, *args):  # keep app logs clean
                    return

            try:
                server = ThreadingHTTPServer((self.host, self.requested_port), Handler)
                server.daemon_threads = True
            except OSError as exc:
                return {"ok": False, "errors": [f"cannot bind {self.host}:{self.requested_port}: {exc}"]}
            if self.certfile and self.keyfile:
                try:
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    context.load_cert_chain(self.certfile, self.keyfile)
                    server.socket = context.wrap_socket(server.socket, server_side=True)
                except (OSError, ssl.SSLError) as exc:
                    server.server_close()
                    return {"ok": False, "errors": [f"cannot enable TLS: {exc}"]}
            self._server = server
            self._thread = threading.Thread(
                target=server.serve_forever,
                name="drs-webstatus",
                daemon=True,
            )
            self._thread.start()
            return {"ok": True, "host": self.host, "port": self.actual_port()}

    def stop(self) -> dict:
        with self._lock:
            server, thread = self._server, self._thread
            self._server, self._thread = None, None
        if server is None:
            return {"ok": True, "stopped": False}
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        return {"ok": True, "stopped": True}

    def running(self) -> bool:
        return self._server is not None

    def actual_port(self) -> int:
        server = self._server
        if server is None:
            return 0
        try:
            return int(server.server_address[1])
        except (TypeError, IndexError, ValueError):
            return 0

    # -- request routing ---------------------------------------------------

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        if self.token is not None and not self._authorized(handler, parsed):
            self._send_json(handler, 401, {"ok": False, "errors": ["unauthorized"]})
            return
        parts = [segment for segment in parsed.path.split("/") if segment]
        try:
            if parsed.path in ("/", ""):
                self._send_html(handler, self._render_page())
            elif parsed.path == "/api/status":
                self._send_json(handler, 200, self.snapshot.status_document())
            elif (
                len(parts) == 4
                and parts[0] == "api"
                and parts[1] == "bots"
                and parts[3] == "logs"
            ):
                query = parse_qs(parsed.query)
                try:
                    limit = min(max(int(query.get("limit", ["200"])[0]), 1), MAX_LOG_LIMIT)
                except ValueError:
                    limit = 200
                self._send_json(handler, 200, self.snapshot.bot_logs(parts[2], limit))
            else:
                self._send_json(handler, 404, {"ok": False, "errors": ["not found"]})
        except Exception as exc:  # noqa: BLE001 - handler must never crash the server
            try:
                self._send_json(handler, 500, {"ok": False, "errors": [str(exc)]})
            except Exception:  # noqa: BLE001
                pass

    def _authorized(self, handler: BaseHTTPRequestHandler, parsed) -> bool:
        query = parse_qs(parsed.query)
        supplied = (query.get("key", [None])[0]) or None
        if supplied is None:
            header = handler.headers.get("Authorization", "")
            if header.lower().startswith("bearer "):
                supplied = header[7:].strip()
        return supplied is not None and supplied == self.token

    # -- rendering ---------------------------------------------------------

    def _render_page(self) -> str:
        document = self.snapshot.status_document()
        stats = document["stats"]
        by_state = stats.get("by_state", {})
        running = stats.get("running", 0)
        rows = []
        for bot in document["bots"]:
            state = str(bot.get("state", "?"))
            uptime = bot.get("uptime_seconds")
            uptime_text = "-" if uptime is None else "%.0fs" % float(uptime)
            cpu = bot.get("cpu_seconds", 0.0) or 0.0
            rows.append(
                "<tr><td><b>%s</b><br><code>%s</code></td>%s<td>%d</td><td>%s</td><td>%.1fs</td></tr>"
                % (
                    _escape(str(bot.get("name", bot.get("id", "?")))),
                    _escape(str(bot.get("id", "?"))),
                    _STATE_CELL.format(state=_escape(state)),
                    int(bot.get("run_count", 0) or 0),
                    uptime_text,
                    float(cpu),
                )
            )
        if not rows:
            rows.append('<tr><td colspan="5" style="color:#8b93a7">no bots installed yet</td></tr>')
        uptime = stats.get("uptime_seconds")
        uptime_text = "-" if uptime is None else "%.0fs" % float(uptime)
        replacements = {
            "__HOST_VERSION__": _escape(self.snapshot.host_version),
            "__PY_VERSION__": _escape(self.snapshot.python_version),
            "__UPTIME__": uptime_text,
            "__TOTAL__": str(stats.get("total", 0)),
            "__RUNNING__": str(running),
            "__FAILED__": str(stats.get("failed", 0)),
            "__RESTARTS__": str(stats.get("restarts", 0)),
            "__RUNS__": str(stats.get("runs", 0)),
            "__ROWS__": "\n".join(rows),
        }
        page = _PAGE
        for key, value in replacements.items():
            page = page.replace(key, value)
        return page

    def _send_html(self, handler: BaseHTTPRequestHandler, html: str) -> None:
        payload = html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def _send_json(self, handler: BaseHTTPRequestHandler, code: int, document: dict) -> None:
        payload = json.dumps(document, ensure_ascii=False).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
