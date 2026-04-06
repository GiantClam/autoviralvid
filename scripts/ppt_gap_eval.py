"""CLI wrapper for src.ppt_gap_eval (run from repo root)."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.ppt_gap_eval import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
