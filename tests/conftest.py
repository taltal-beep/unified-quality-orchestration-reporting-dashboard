"""Pytest configuration for the orchestrator package."""

from __future__ import annotations

import sys
from pathlib import Path

# Project root is parent of ``tests/``; ``pythonpath = .`` in pytest.ini also applies.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
