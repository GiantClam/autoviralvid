from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "build_archetype_slot_clusters.py"
    spec = importlib.util.spec_from_file_location("build_archetype_slot_clusters", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_clusters_prefer_phase_artifacts_render_json(tmp_path: Path):
    mod = _load_module()
    nightly_dir = tmp_path
    render_shared = nightly_dir / "generated.render.json"
    render_shared.write_text(json.dumps({"slides": []}, ensure_ascii=False), encoding="utf-8")

    render_phase = nightly_dir / "generated.p1.render.json"
    render_phase.write_text(
        json.dumps(
            {
                "official_input": {
                    "slides": [
                        {
                            "archetype": "comparison_2col",
                            "layout_grid": "split_2",
                            "blocks": [
                                {"block_type": "title", "content": "A"},
                                {"block_type": "body", "content": "B"},
                            ],
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    issues_phase = nightly_dir / "issues.p1.json"
    issues_phase.write_text(
        json.dumps({"issues": [{"page": 1, "similarity": 72.5}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = {
        "paths": {
            "render_json": str(render_shared),
            "issues_json": str(issues_phase),
        },
        "phase_artifacts": {
            "render_json": str(render_phase),
            "issues_json": str(issues_phase),
        },
    }
    (nightly_dir / "round_summary.p1.json").write_text(
        json.dumps(summary, ensure_ascii=False),
        encoding="utf-8",
    )

    out = mod.build_clusters_for_directory(nightly_dir)
    assert int(out.get("cluster_count") or 0) == 1
    cluster = out["clusters"][0]
    assert cluster["archetype"] == "comparison_2col"
    assert cluster["layout_grid"] == "split_2"
    assert float(cluster["avg_similarity"]) > 70


def test_clusters_fallback_to_phase_render_file(tmp_path: Path):
    mod = _load_module()
    nightly_dir = tmp_path
    render_phase = nightly_dir / "generated.p2.render.json"
    render_phase.write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "layout_grid": "grid_4",
                        "blocks": [{"block_type": "kpi", "content": {"label": "M1"}}],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    issues_phase = nightly_dir / "issues.p2.json"
    issues_phase.write_text(
        json.dumps({"issues": [{"page": 1, "similarity": 65.0}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (nightly_dir / "round_summary.p2.json").write_text(
        json.dumps({"paths": {"issues_json": str(issues_phase)}}, ensure_ascii=False),
        encoding="utf-8",
    )

    out = mod.build_clusters_for_directory(nightly_dir)
    assert int(out.get("cluster_count") or 0) == 1
    cluster = out["clusters"][0]
    assert cluster["archetype"] == "dashboard_kpi_4"
    assert cluster["layout_grid"] == "grid_4"
    assert float(cluster["low_similarity_ratio"]) == 1.0


def test_clusters_fallback_to_input_json_when_render_has_no_slide_rows(tmp_path: Path):
    mod = _load_module()
    nightly_dir = tmp_path
    render_phase = nightly_dir / "generated.p3.render.json"
    render_phase.write_text(
        json.dumps(
            {
                "mode": "reconstruct",
                "slides": 20,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_json = nightly_dir / "reference_extracted.p3.json"
    input_json.write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "slide_type": "content",
                        "layout_grid": "timeline",
                        "semantic_type": "workflow",
                        "blocks": [{"block_type": "workflow", "content": "A -> B"}],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    issues_phase = nightly_dir / "issues.p3.json"
    issues_phase.write_text(
        json.dumps({"issues": [{"page": 1, "similarity": 68.0}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (nightly_dir / "round_summary.p3.json").write_text(
        json.dumps(
            {
                "paths": {
                    "render_json": str(render_phase),
                    "issues_json": str(issues_phase),
                    "input_json": str(input_json),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out = mod.build_clusters_for_directory(nightly_dir)
    assert int(out.get("cluster_count") or 0) == 1
    cluster = out["clusters"][0]
    assert cluster["archetype"] == "process_flow_4step"
