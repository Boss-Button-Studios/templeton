"""
Trap engine: loads tier1.yaml and dispatches to trap modules.

Trap modules live in web/traps/ and are discovered by filename pattern t{id}_*.py.
Each module must expose:

    check(path: str, state: dict | None, params: dict) -> flask.Response | None
        Return a Response to intercept the request entirely, or None to pass through.

    inject(path: str, state: dict | None, params: dict) -> dict
        Return template variables to merge into the render context, or {}.

Phase 3 adds trap module files; no changes to this engine are required.
"""

import importlib
import logging
import os
import re
from typing import Optional

import yaml

_logger = logging.getLogger(__name__)
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "tier1.yaml")


def _discover_modules() -> dict[str, str]:
    """
    Scan web/traps/ for files matching t{id}_*.py and return {id: module_name}.
    Example: t01_soft_404.py → {"t01": "traps.t01_soft_404"}
    """
    traps_dir = os.path.join(os.path.dirname(__file__), "traps")
    registry: dict[str, str] = {}
    for fname in os.listdir(traps_dir):
        m = re.match(r"^(t\d+)_.+\.py$", fname)
        if m:
            registry[m.group(1)] = f"traps.{fname[:-3]}"
    return registry


class TrapEngine:
    def __init__(self) -> None:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f)
        self._routes: dict = data.get("routes", {})
        self._modules: dict[str, str] = _discover_modules()

    def get_route_config(self, path: str) -> dict:
        """Return the full route config for a path, or {} if unconfigured."""
        return self._routes.get(path, {})

    def check_intercept(self, path: str, state: Optional[dict]):
        """
        Run trap check() hooks for the given path.
        Returns the first non-None Response, or None to let the route proceed.
        """
        for trap_id, params in self._active_traps(path):
            module = self._load(trap_id)
            if module is None:
                continue
            try:
                result = module.check(path, state, params)
                if result is not None:
                    return result
            except Exception:
                _logger.exception("trap %s check() raised on %s", trap_id, path)
        return None

    def get_template_vars(self, path: str, state: Optional[dict]) -> dict:
        """Run trap inject() hooks and return merged template variables."""
        merged: dict = {}
        for trap_id, params in self._active_traps(path):
            module = self._load(trap_id)
            if module is None:
                continue
            try:
                merged.update(module.inject(path, state, params))
            except Exception:
                _logger.exception("trap %s inject() raised on %s", trap_id, path)
        return merged

    def honeypot_urls(self) -> set[str]:
        """
        Return all honeypot paths registered via t05 traps.
        Used by Phase 4 proxy to build its honeypot URL registry.
        """
        urls: set[str] = set()
        for route in self._routes.values():
            for entry in route.get("traps", []):
                if entry["id"] == "t05":
                    hp = entry.get("params", {}).get("honeypot_path")
                    if hp:
                        urls.add(hp)
        return urls

    # ── internal ────────────────────────────────────────────────────────────

    def _active_traps(self, path: str) -> list[tuple[str, dict]]:
        route = self._routes.get(path, {})
        return [(e["id"], e.get("params", {})) for e in route.get("traps", [])]

    def _load(self, trap_id: str):
        """Import and return a trap module, or None if not yet implemented."""
        module_name = self._modules.get(trap_id)
        if module_name is None:
            _logger.debug("trap %s: no module file found", trap_id)
            return None
        try:
            return importlib.import_module(module_name)
        except ImportError:
            _logger.debug("trap %s: import failed", trap_id)
            return None
