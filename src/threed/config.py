"""Project path configuration.

Resolves the location of the ``designs`` directory, which holds one folder per
design. The location can be overridden with the ``THREED_DESIGNS_DIR``
environment variable (useful for tests or custom layouts).
"""

from __future__ import annotations

import os
from pathlib import Path

# src/threed/config.py -> parents[2] is the repository root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def get_designs_dir() -> Path:
    """Return the directory that contains all design folders."""
    override = os.environ.get("THREED_DESIGNS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "designs"


DESIGNS_DIR: Path = get_designs_dir()
