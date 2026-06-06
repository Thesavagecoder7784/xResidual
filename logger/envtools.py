"""Minimal .env loader (no external dependency).

Reads KEY=VALUE lines from the repo-root .env into a dict, layered over the real
process environment. Values are never logged, and callers must not print them.
"""

from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    path = path or os.path.join(REPO_ROOT, ".env")
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_path(p: str) -> str:
    """Resolve a possibly-relative path against the repo root."""
    return p if os.path.isabs(p) else os.path.join(REPO_ROOT, p)
