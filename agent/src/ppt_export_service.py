"""Thin export service wrapper for MiniMax PPTX generation."""

from __future__ import annotations

from typing import Any, Dict

import src.minimax_exporter as minimax_exporter


class PPTExportService:
    """Facade for one export attempt."""

    def export_once(self, **kwargs: Any) -> Dict[str, Any]:
        return minimax_exporter.export_minimax_pptx(**kwargs)
