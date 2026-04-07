"""Utility helpers for export retry scope and render-path degradation."""

from __future__ import annotations

from typing import Any, Dict, List


def degrade_render_paths_for_retry(
    *,
    seed_slides: List[Dict[str, Any]],
    failure_code: str,
    scope: str,
    scoped_slide_ids: List[str],
) -> Dict[str, Any]:
    _ = (scope, scoped_slide_ids)
    if not isinstance(seed_slides, list) or not seed_slides:
        return {
            "applied": False,
            "failure_code": str(failure_code or ""),
            "changed_slide_ids": [],
            "transitions": [],
        }
    changed_slide_ids: List[str] = []
    transitions: List[str] = []
    for idx, slide in enumerate(seed_slides):
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
        current_path = str(slide.get("render_path") or "svg").strip().lower()
        next_path = "svg"
        if current_path == next_path:
            continue
        slide["render_path"] = next_path
        changed_slide_ids.append(slide_id)
        transitions.append(f"{slide_id}:{current_path}->{next_path}")
    return {
        "applied": bool(changed_slide_ids),
        "failure_code": str(failure_code or ""),
        "changed_slide_ids": changed_slide_ids,
        "transitions": transitions,
    }


def collect_issue_retry_target_slides(gate_issues: List[Any]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for issue in gate_issues or []:
        retry_ids = getattr(issue, "retry_target_ids", None)
        if isinstance(retry_ids, list):
            for raw in retry_ids:
                sid = str(raw or "").strip()
                if not sid or sid.lower() == "deck" or sid in seen:
                    continue
                seen.add(sid)
                ordered.append(sid)
        sid = str(getattr(issue, "slide_id", "") or "").strip()
        if sid and sid.lower() != "deck" and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered

