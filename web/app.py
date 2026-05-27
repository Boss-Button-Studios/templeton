"""
Templeton web server.

Every HTML response embeds a state token in all outbound links. The token
carries per-run crawl state (visit history, depth, taint status) as an
authenticated-encrypted query parameter.

Entry point for a new run: GET /?run=<run_id>
All subsequent pages:       GET /<path>?state=<token>
"""

import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from flask import Flask, Response, g, render_template, request

import state_token as st
from flag_store import FlagStore
from trap_engine import TrapEngine

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Secret is generated fresh by `templeton up`; set via env for reproducible runs.
_SECRET: str = os.environ.get("TEMPLETON_SECRET") or st.generate_secret()

_flag_store = FlagStore()
_trap_engine = TrapEngine()


# ── State token helpers ──────────────────────────────────────────────────────

def _canonical_url() -> str:
    """Request URL with the state token stripped — stable key for visit history."""
    parsed = urlparse(request.url)
    params = {k: v for k, v in parse_qs(parsed.query).items() if k != "state"}
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def _path_depth(path: str) -> int:
    return len([seg for seg in path.split("/") if seg])


def _link(url: str) -> str:
    """
    Append the current state token to an internal URL.
    No-op for external URLs, static assets, and requests with no active token.
    """
    if not g.get("state_token"):
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("", "http", "https"):
        return url
    if parsed.path.startswith("/static/"):
        return url
    params = parse_qs(parsed.query)
    params["state"] = [g.state_token]
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


# ── Request lifecycle ────────────────────────────────────────────────────────

@app.before_request
def _load_state():
    """
    Decode or bootstrap the state token before every request.

    First hop:  GET /?run=<run_id>       → create initial token for run
    All others: GET /<path>?state=<tok>  → decode and advance token
    Static:     GET /static/…            → skip (no token needed)
    """
    g.state_token = None
    g.state_payload = None

    if request.path.startswith("/static/"):
        return

    run_id = request.args.get("run")
    raw_token = request.args.get("state")

    if run_id and not raw_token:
        initial = st.make_initial_token(run_id, _SECRET)
        token = st.advance(initial, _canonical_url(), _path_depth(request.path), _SECRET)
        g.state_token = token
        g.state_payload = st.decode(token, _SECRET)
        return

    if not raw_token:
        return Response(
            "Missing state token. Start at /?run=<run_id>",
            status=400,
            mimetype="text/plain",
        )

    try:
        payload = st.decode(raw_token, _SECRET)
    except st.StateTokenError:
        return Response("Invalid state token.", status=400, mimetype="text/plain")

    if payload.get("tainted"):
        return Response("400 Bad Request", status=400, mimetype="text/plain")

    token = st.advance(raw_token, _canonical_url(), _path_depth(request.path), _SECRET)
    g.state_token = token
    g.state_payload = st.decode(token, _SECRET)


@app.context_processor
def _inject_globals() -> dict:
    return {
        "link": _link,
        "state": g.get("state_payload"),
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    intercept = _trap_engine.check_intercept("/", g.state_payload)
    if intercept:
        return intercept
    trap_vars = _trap_engine.get_template_vars("/", g.state_payload)
    return render_template("home.html", **trap_vars)


@app.route("/<path:subpath>")
def page(subpath: str):
    path = f"/{subpath}"
    intercept = _trap_engine.check_intercept(path, g.state_payload)
    if intercept:
        return intercept
    template = _resolve_template(path)
    if template is None:
        return render_template("404.html"), 404
    trap_vars = _trap_engine.get_template_vars(path, g.state_payload)
    return render_template(template, path=path, **trap_vars)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_template(path: str):
    """
    Map a URL path to a Jinja2 template name.
    Returns None if no template file exists for the path.
    """
    rel = path.lstrip("/")
    candidates = (
        f"pages/{rel}.html",
        f"pages/{rel}/index.html",
    )
    tmpl_dir = os.path.join(app.root_path, app.template_folder)
    for candidate in candidates:
        if os.path.exists(os.path.join(tmpl_dir, candidate)):
            return candidate
    return None
