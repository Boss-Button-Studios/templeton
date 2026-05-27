"""
Flag store: loads ground-truth flag values at startup.

SECURITY: flags.yaml must never be served via any HTTP route.
Query this store only from the harness scoring path, never from web routes.
"""

import json
import os
import re
from typing import Any

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "flags.yaml")

_FLAGS: dict = {}


def _load() -> None:
    with open(_CONFIG_PATH) as f:
        data = yaml.safe_load(f)
    _FLAGS.update(data["flags"])


def get(flag_id: str) -> Any:
    """Return the ground-truth value for a flag. Raises KeyError if unknown."""
    return _FLAGS[flag_id]["value"]


def describe(flag_id: str) -> str:
    """Human-readable description of what the flag measures."""
    return _FLAGS[flag_id].get("description", flag_id)


def list_flags() -> list[str]:
    """Return all known flag IDs in definition order."""
    return list(_FLAGS.keys())


def normalize(flag_id: str, value: Any) -> Any:
    """
    Normalize a submitted value to the canonical form used for scoring.
    Agents may submit phone numbers with formatting, dates in various formats, etc.
    """
    normalizer = _FLAGS[flag_id].get("normalizer", "passthrough")
    return _apply(normalizer, value)


def _apply(normalizer: str, value: Any) -> Any:
    if normalizer == "digits_only":
        return re.sub(r"\D", "", str(value))

    if normalizer == "iso_date":
        v = str(value).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return v
        # Accept MM/DD/YYYY
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
        if m:
            return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        return v

    if normalizer == "url":
        return str(value).strip().rstrip("/")

    if normalizer == "url_set":
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                value = [value]
        return sorted(str(u).strip().rstrip("/") for u in value)

    return value  # passthrough


_load()


class FlagStore:
    """Class interface over the module-level functions (for injection and testing)."""

    def get(self, flag_id: str):
        return get(flag_id)

    def normalize(self, flag_id: str, value):
        return normalize(flag_id, value)

    def describe(self, flag_id: str) -> str:
        return describe(flag_id)

    def list_flags(self) -> list[str]:
        return list_flags()
