"""
Templeton harness proxy — mitmproxy addon.

Sits between the agent and the web server. On every request it:
  1. Extracts the run_id from ?run= (first hop) or the decoded state token.
  2. Registers new runs on first sight.
  3. Checks for bangs via BangEnforcer; if triggered, taints the run and returns
     a bare HTTP 400 without forwarding to the web server.
  4. On clean requests, records the page visit in the run's ReportAssembler.

A monitor HTTP server runs on port 8081 (configurable via TEMPLETON_MONITOR_PORT)
and serves live report JSON — consumed by `templeton monitor`.

Environment variables:
  TEMPLETON_SECRET          Fernet key matching the web server's secret.
  TEMPLETON_TIER_CONFIG     Path to tier YAML config for honeypot URL list.
                            Default: /web-config/tier1.yaml (Docker path).
  TEMPLETON_MONITOR_PORT    Port for the monitor HTTP endpoint. Default: 8081.
"""

import functools
import http.server
import json
import logging
import os
import threading
from urllib.parse import parse_qs, urlparse

import mitmproxy.http

import state_token as st
from bang_enforcer import BangEnforcer, load_honeypot_paths
from report_assembler import ReportAssembler

_logger = logging.getLogger(__name__)

_TERMINAL_BODY = b"400 Bad Request"
_TERMINAL_HEADERS = {"Content-Type": "text/plain; charset=utf-8"}

# Default tier config path inside the Docker container.
_DEFAULT_TIER_CONFIG = "/web-config/tier1.yaml"


# ── Monitor HTTP server ───────────────────────────────────────────────────────

class _MonitorHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler that serves live run report JSON."""

    def __init__(self, registry: dict, lock: threading.Lock, *args, **kwargs):
        self._registry = registry
        self._lock = lock
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        segments = [s for s in parsed.path.split("/") if s]

        if not segments or segments[0] != "status":
            self._respond(404, {"error": "not found"})
            return

        with self._lock:
            if len(segments) == 1:
                # /status → all runs
                payload = {
                    rid: state["report"].to_dict()
                    for rid, state in self._registry.items()
                }
            elif len(segments) == 2:
                # /status/<run_id>
                run_id = segments[1]
                if run_id not in self._registry:
                    self._respond(404, {"error": f"run {run_id!r} not found"})
                    return
                payload = self._registry[run_id]["report"].to_dict()
            else:
                self._respond(404, {"error": "not found"})
                return

        self._respond(200, payload)

    def _respond(self, status: int, body: dict) -> None:
        data = json.dumps(body, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # suppress default CLF output
        pass


def _start_monitor_server(registry: dict, lock: threading.Lock, port: int) -> None:
    handler = functools.partial(_MonitorHandler, registry, lock)
    server = http.server.HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="monitor")
    thread.start()
    _logger.info("Monitor server listening on :%d", port)


# ── Addon ─────────────────────────────────────────────────────────────────────

class TempletonAddon:

    def __init__(self) -> None:
        self._secret: str | None = os.environ.get("TEMPLETON_SECRET")
        if not self._secret:
            _logger.warning(
                "TEMPLETON_SECRET not set — state token decoding disabled. "
                "Run attribution and taint checks will not function."
            )

        tier_config = os.environ.get("TEMPLETON_TIER_CONFIG", _DEFAULT_TIER_CONFIG)
        honeypot_paths = load_honeypot_paths(tier_config)

        self._enforcer = BangEnforcer(honeypot_paths)

        # run_id → {"tainted": bool, "report": ReportAssembler}
        self._registry: dict[str, dict] = {}
        self._lock = threading.Lock()

        monitor_port = int(os.environ.get("TEMPLETON_MONITOR_PORT", "8081"))
        _start_monitor_server(self._registry, self._lock, monitor_port)

    # ── mitmproxy hooks ───────────────────────────────────────────────────────

    def request(self, flow: mitmproxy.http.HTTPFlow) -> None:
        run_id, state_payload = self._extract_run_info(flow.request)

        # Bootstrap registry entry on first sight of a run.
        if run_id:
            with self._lock:
                if run_id not in self._registry:
                    self._registry[run_id] = {
                        "tainted": False,
                        "report": ReportAssembler(run_id),
                    }

        with self._lock:
            registry_snapshot = {
                rid: {"tainted": s["tainted"]}
                for rid, s in self._registry.items()
            }

        bang_type = self._enforcer.check(
            host=flow.request.pretty_host,
            path=flow.request.path,
            run_id=run_id,
            registry=registry_snapshot,
        )

        if bang_type:
            _logger.info(
                "Bang [%s] run=%s url=%s",
                bang_type,
                run_id or "<unknown>",
                flow.request.pretty_url,
            )
            if run_id:
                self._record_bang(run_id, bang_type, flow.request.pretty_url)
            flow.response = mitmproxy.http.Response.make(
                400, _TERMINAL_BODY, _TERMINAL_HEADERS
            )

    def response(self, flow: mitmproxy.http.HTTPFlow) -> None:
        # Skip our own terminal responses — they have no state token.
        if flow.response and flow.response.content == _TERMINAL_BODY:
            return

        run_id, state_payload = self._extract_run_info(flow.request)
        if not run_id:
            return

        with self._lock:
            if run_id not in self._registry:
                return
            report = self._registry[run_id]["report"]

        report.record_page(
            url=flow.request.pretty_url,
            status_code=flow.response.status_code,
            state_payload=state_payload,
        )

    # ── internal helpers ──────────────────────────────────────────────────────

    def _extract_run_info(
        self, request: mitmproxy.http.Request
    ) -> tuple[str | None, dict | None]:
        """
        Return (run_id, state_payload) from an incoming request.

        First hop  (?run=<id>): returns (run_id, None).
        Later hops (?state=<token>): decodes token → (run_id, payload dict).
        Unknown:   returns (None, None).
        """
        raw_token = request.query.get("state")
        run_param = request.query.get("run")

        if run_param and not raw_token:
            return run_param, None

        if raw_token and self._secret:
            try:
                payload = st.decode(raw_token, self._secret)
                return payload.get("run_id"), payload
            except st.StateTokenError:
                pass

        return None, None

    def _record_bang(self, run_id: str, bang_type: str, url: str) -> None:
        with self._lock:
            if run_id not in self._registry:
                return
            self._registry[run_id]["tainted"] = True
            self._registry[run_id]["report"].record_bang(bang_type, url, run_id)


addons = [TempletonAddon()]
