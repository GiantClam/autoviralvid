"""
Legacy compatibility wrapper for the old src/main.py entrypoint.

Railway and local production should run ``agent/main.py`` instead:

    uvicorn main:app --host 0.0.0.0 --port ${PORT}

This wrapper exists so that accidental references to ``src/main.py`` do not
boot the retired LangGraph application or fail with missing imports.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import app, main as run_main  # noqa: E402


def main() -> None:
    """Start the production FastAPI app from the canonical entrypoint."""
    run_main()


if __name__ == "__main__":
    main()
