from __future__ import annotations

import json
from pathlib import Path

import src.ppt_routes as routes


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_infer_progress_uses_step4_runtime_hint(tmp_path: Path) -> None:
    project_path = tmp_path / "ppt_project"
    project_path.mkdir(parents=True, exist_ok=True)
    _write_json(project_path / "runtime_request.json", {"total_pages": 12})
    _write_json(
        project_path / "_runtime_inputs" / "runtime_progress.json",
        {
            "stage": "step4",
            "substage": "design_spec",
            "detail": "Generating design specification",
            "percent": 22.0,
            "total_pages": 12,
        },
    )
    job = {
        "status": "running",
        "project_path": str(project_path),
        "total_pages": 12,
    }
    progress = routes._infer_ppt_prompt_job_progress(job)
    assert progress["stage"] == "step4"
    assert "design specification" in str(progress["detail"]).lower()
    assert float(progress["percent"]) >= 22.0


def test_infer_progress_uses_step6_runtime_hint_page(tmp_path: Path) -> None:
    project_path = tmp_path / "ppt_project"
    project_path.mkdir(parents=True, exist_ok=True)
    _write_json(project_path / "runtime_request.json", {"total_pages": 10})
    _write_json(
        project_path / "_runtime_inputs" / "runtime_progress.json",
        {
            "stage": "step6",
            "detail": "Generating slides 4/10",
            "current_page": 4,
            "percent": 51.0,
            "total_pages": 10,
        },
    )
    job = {
        "status": "running",
        "project_path": str(project_path),
        "total_pages": 10,
    }
    progress = routes._infer_ppt_prompt_job_progress(job)
    assert progress["stage"] == "step6"
    assert int(progress["current_page"]) == 4
    assert float(progress["percent"]) >= 51.0
