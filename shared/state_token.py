"""
State token: authenticated-encrypted crawl state carried in URL query parameters.

Every link Templeton serves has ?state=<token> appended. The harness proxy
validates the token before forwarding to the web server. The web server decodes
it to read visit_count (adaptive difficulty), visit_history (content shifting),
depth, and taint status.

Tokens are encrypted + authenticated with Fernet (AES-128-CBC + HMAC-SHA256).
A forged or tampered token raises StateTokenError. A token issued by a different
run (different secret) also raises StateTokenError — run isolation is automatic.
"""

import hashlib
import json
from typing import Union

from cryptography.fernet import Fernet, InvalidToken

__all__ = [
    "StateTokenError",
    "generate_secret",
    "make_initial_token",
    "encode",
    "decode",
    "advance",
    "taint",
    "url_hash",
]


class StateTokenError(Exception):
    """Raised when a state token is invalid, forged, or from the wrong run."""


def generate_secret() -> str:
    """Generate a new Fernet key string. Use as TEMPLETON_SECRET."""
    return Fernet.generate_key().decode()


def _fernet(secret: Union[str, bytes]) -> Fernet:
    key = secret.encode() if isinstance(secret, str) else secret
    return Fernet(key)


def encode(payload: dict, secret: str) -> str:
    """Serialize and encrypt a state token payload to a URL-safe string."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return _fernet(secret).encrypt(raw).decode()


def decode(token: Union[str, bytes], secret: str) -> dict:
    """
    Decrypt and deserialize a state token.

    Raises StateTokenError if the token is invalid, tampered, expired, or from
    a different run (wrong secret).
    """
    try:
        raw = _fernet(secret).decrypt(
            token.encode() if isinstance(token, str) else token
        )
        return json.loads(raw)
    except (InvalidToken, json.JSONDecodeError, ValueError) as exc:
        raise StateTokenError("invalid or forged state token") from exc


def url_hash(url: str) -> str:
    """SHA-256 hex digest of a URL — used in visit_history."""
    return hashlib.sha256(url.encode()).hexdigest()


def make_initial_token(run_id: str, secret: str) -> str:
    """Create the first state token for a new run (depth 0, no history)."""
    payload = {
        "run_id": run_id,
        "visit_count": 0,
        "visit_history": [],
        "depth": 0,
        "tainted": False,
    }
    return encode(payload, secret)


def advance(token: str, visited_url: str, next_depth: int, secret: str) -> str:
    """
    Return an updated token after the agent visits visited_url and moves to
    a page at next_depth.

    - Increments visit_count
    - Appends visited_url hash to visit_history (deduped)
    - Sets depth to next_depth
    """
    p = decode(token, secret)
    p["visit_count"] += 1
    h = url_hash(visited_url)
    if h not in p["visit_history"]:
        p["visit_history"].append(h)
    p["depth"] = next_depth
    return encode(p, secret)


def taint(token: str, secret: str) -> str:
    """Return a tainted copy of the token. Used by the proxy after a bang."""
    p = decode(token, secret)
    p["tainted"] = True
    return encode(p, secret)
