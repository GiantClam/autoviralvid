#!/usr/bin/env python3
"""Build archetype x slot clusters from regression artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _infer_archetype(slide: Dict[str, Any]) -> str:
    explicit = _normalize(slide.get("archetype"))
    if explicit:
        return explicit
    semantic = _normalize(
        slide.get("semantic_type")
        or slide.get("semantic_subtype")
        or slide.get("content_subtype")
        or slide.get("subtype")
    )
    layout = _normalize(slide.get("layout_grid") or slide.get("layout"))
    page_type = _normalize(slide.get("page_type") or slide.get("slide_type"))
    if semantic in {"workflow", "diagram"}:
        return "process_flow_4step"
    if semantic in {"comparison"}:
        return "comparison_2col"
    if semantic in {"roadmap", "timeline"}:
        return "timeline_horizontal"
    if page_type in {"cover"}:
        return "cover_hero"
    if page_type in {"summary"}:
        return "summary_action"
    if layout in {"grid_4", "bento_6"}:
        return "dashboard_kpi_4"
    if layout in {"grid_3"}:
        return "evidence_cards_3"
    if layout in {"timeline"}:
        return "timeline_horizontal"
    return "thesis_assertion"


def _slot_signature(slide: Dict[str, Any]) -> str:
    blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
    counts: Dict[str, int] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bt = _normalize(block.get("block_type") or block.get("type"))
        if not bt:
            continue
        counts[bt] = counts.get(bt, 0) + 1
    if not counts:
        return "no_blocks"
    rows = [f"{key}:{counts[key]}" for key in sorted(counts.keys())]
    return "|".join(rows)


def _collect_similarity_by_page(issues_json: Dict[str, Any]) -> Dict[int, float]:
    rows = issues_json.get("issues") if isinstance(issues_json.get("issues"), list) else []
    out: Dict[int, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        page = int(row.get("page") or 0)
        if page <= 0:
            continue
        similarity = row.get("similarity")
        try:
            score = float(similarity)
        except Exception:
            continue
        out[page] = score
    return out


def _collect_slides(render_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(render_json.get("official_input"), dict):
        slides = render_json["official_input"].get("slides")
        if isinstance(slides, list):
            return [row for row in slides if isinstance(row, dict)]
    slides = render_json.get("slides")
    if isinstance(slides, list):
        return [row for row in slides if isinstance(row, dict)]
    return []


def _collect_input_slides(input_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    slides = input_json.get("slides")
    if isinstance(slides, list):
        return [row for row in slides if isinstance(row, dict)]
    return []


def _iter_phase_summaries(nightly_dir: Path) -> List[Tuple[str, Dict[str, Any], Path]]:
    out: List[Tuple[str, Dict[str, Any], Path]] = []
    for summary_path in sorted(nightly_dir.glob("round_summary.*.json")):
        phase = summary_path.name[len("round_summary.") : -len(".json")]
        summary = _load_json(summary_path)
        out.append((phase, summary, summary_path))
    return out


def build_clusters_for_directory(nightly_dir: Path) -> Dict[str, Any]:
    cluster_map: Dict[str, Dict[str, Any]] = {}
    phase_rows = _iter_phase_summaries(nightly_dir)
    for phase, summary, _summary_path in phase_rows:
        phase_artifacts = summary.get("phase_artifacts") if isinstance(summary.get("phase_artifacts"), dict) else {}
        paths = summary.get("paths") if isinstance(summary.get("paths"), dict) else {}
        issues_path = (
            Path(phase_artifacts.get("issues_json"))
            if phase_artifacts.get("issues_json")
            else (
                Path(paths.get("issues_json"))
                if paths.get("issues_json")
                else nightly_dir / f"issues.{phase}.json"
            )
        )
        render_path = (
            Path(phase_artifacts.get("render_json"))
            if phase_artifacts.get("render_json")
            else (
                Path(paths.get("render_json"))
                if paths.get("render_json")
                else nightly_dir / f"generated.{phase}.render.json"
            )
        )
        if not render_path.exists():
            # fallback to shared render output path in one-off runs
            render_path = nightly_dir / "generated.render.json"
        input_path = (
            Path(paths.get("input_json"))
            if paths.get("input_json")
            else nightly_dir / "reference_extracted.json"
        )
        issues_json = _load_json(issues_path)
        render_json = _load_json(render_path)
        input_json = _load_json(input_path)
        slides = _collect_slides(render_json)
        if not slides:
            slides = _collect_input_slides(input_json)
        if not slides:
            continue
        sim_by_page = _collect_similarity_by_page(issues_json)
        for idx, slide in enumerate(slides):
            page = idx + 1
            archetype = _infer_archetype(slide)
            layout = _normalize(slide.get("layout_grid") or slide.get("layout") or "split_2") or "split_2"
            slot = _slot_signature(slide)
            key = f"{archetype}||{layout}||{slot}"
            bucket = cluster_map.setdefault(
                key,
                {
                    "archetype": archetype,
                    "layout_grid": layout,
                    "slot_signature": slot,
                    "count": 0,
                    "similarity_sum": 0.0,
                    "similarity_count": 0,
                    "low_similarity_count": 0,
                    "pages": [],
                },
            )
            bucket["count"] += 1
            bucket["pages"].append({"phase": phase, "page": page})
            similarity = sim_by_page.get(page)
            if similarity is None:
                continue
            bucket["similarity_sum"] += float(similarity)
            bucket["similarity_count"] += 1
            if float(similarity) < 70.0:
                bucket["low_similarity_count"] += 1

    clusters: List[Dict[str, Any]] = []
    for row in cluster_map.values():
        similarity_count = int(row.get("similarity_count") or 0)
        avg_similarity = (
            float(row.get("similarity_sum") or 0.0) / float(similarity_count)
            if similarity_count > 0
            else 0.0
        )
        low_count = int(row.get("low_similarity_count") or 0)
        count = int(row.get("count") or 0)
        row["avg_similarity"] = round(avg_similarity, 4)
        row["low_similarity_ratio"] = round(low_count / float(max(1, count)), 4)
        row.pop("similarity_sum", None)
        clusters.append(row)
    clusters.sort(
        key=lambda row: (
            int(row.get("count") or 0),
            -float(row.get("avg_similarity") or 0.0),
            str(row.get("archetype") or ""),
        ),
        reverse=True,
    )
    return {
        "cluster_count": len(clusters),
        "clusters": clusters,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build archetype x slot clusters from nightly artifacts")
    parser.add_argument("--nightly-dir", required=True, help="Nightly output directory")
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON path (default: <nightly-dir>/archetype_slot_clusters.json)",
    )
    args = parser.parse_args()

    nightly_dir = Path(args.nightly_dir)
    if not nightly_dir.exists():
        raise FileNotFoundError(f"nightly directory not found: {nightly_dir}")
    output_path = Path(args.output) if str(args.output).strip() else nightly_dir / "archetype_slot_clusters.json"
    clusters = build_clusters_for_directory(nightly_dir)
    payload = {
        "nightly_dir": str(nightly_dir.resolve()),
        **clusters,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[CLUSTER] output={output_path}")
    print(f"[CLUSTER] cluster_count={payload.get('cluster_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
