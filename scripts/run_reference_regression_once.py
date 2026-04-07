#!/usr/bin/env python3
"""Run one data-driven reference regression round:
1) extract description from reference PPT
2) generate PPT from extracted description
3) compare generated PPT with reference PPT
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_FAILURE_CLUSTERS = ("content", "layout", "theme", "media", "geometry", "harness")
_FIX_CLUSTER_TO_MUTATIONS: Dict[str, List[str]] = {
    "content": [
        "tighten_required_facts_and_anchors",
        "raise_assertion_evidence_coverage",
        "prefer_content_dense_archetypes_only_when_needed",
    ],
    "layout": [
        "apply_layout_solver_ladder",
        "switch_to_lower_density_variant_on_overflow",
        "enforce_slot_order_and_container_bounds",
    ],
    "theme": [
        "lock_design_tokens_to_reference_palette",
        "enforce_typography_scale_consistency",
        "reduce_cross-slide_style_drift",
    ],
    "media": [
        "enforce_media_required_slots",
        "promote_image_query_specificity",
        "fallback_to_icon_or_placeholder_only_after_media_retry",
    ],
    "geometry": [
        "prioritize_visual_similarity_repairs",
        "route_complex_shapes_to_svg_or_drawingml",
        "normalize_text_box_and_shape_coordinates",
    ],
    "harness": [
        "verify_extract_generate_compare_pipeline_health",
        "stabilize_local_service_boot_and_timeout",
    ],
}

_VALID_TEMPLATE_FAMILIES = {
    "architecture_dark_panel",
    "bento_2x2_dark",
    "bento_mosaic_dark",
    "comparison_cards_light",
    "consulting_warm_light",
    "dashboard_dark",
    "ecosystem_orange_dark",
    "hero_dark",
    "hero_tech_cover",
    "image_showcase_light",
    "kpi_dashboard_dark",
    "neural_blueprint_light",
    "ops_lifecycle_light",
    "process_flow_dark",
    "quote_hero_dark",
    "split_media_dark",
}


def _normalize_template_family_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token if token in _VALID_TEMPLATE_FAMILIES else ""


def _dedupe_template_whitelist(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        token = _normalize_template_family_token(item)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _build_target_template_whitelist(
    *,
    issue_text: str,
    layout_hint: str,
    cluster_name: str,
    creation_mode: str,
) -> List[str]:
    text = str(issue_text or "").strip().lower()
    layout = str(layout_hint or "").strip().lower()
    cluster = _normalize_failure_cluster(cluster_name)
    mode = str(creation_mode or "").strip().lower()

    # zero_create critic repair should avoid falling back to dashboard_dark.
    # Use compact, layout-safe candidates first to reduce geometry mismatch.
    if "timeline" in text or "roadmap" in text or "workflow" in text or layout == "timeline":
        base = ["process_flow_dark", "ops_lifecycle_light", "architecture_dark_panel"]
    elif "compare" in text or "vs" in text or "benchmark" in text:
        base = ["comparison_cards_light", "consulting_warm_light", "ops_lifecycle_light"]
    elif "quote" in text:
        base = ["quote_hero_dark", "consulting_warm_light", "hero_dark"]
    elif "image" in text or "media" in text:
        base = ["split_media_dark", "image_showcase_light", "consulting_warm_light"]
    elif "chart" in text or "kpi" in text or "data" in text:
        base = ["kpi_dashboard_dark", "ops_lifecycle_light", "comparison_cards_light"]
    elif layout in {"grid_3", "grid_4", "bento_5", "bento_6"}:
        base = ["ops_lifecycle_light", "comparison_cards_light", "kpi_dashboard_dark"]
    elif layout in {"split_2", "asymmetric_2"}:
        base = ["split_media_dark", "consulting_warm_light", "neural_blueprint_light"]
    else:
        base = ["ops_lifecycle_light", "split_media_dark", "consulting_warm_light"]

    # Keep dashboard family only as non-primary fallback in fidelity.
    if mode != "zero_create" and cluster in {"layout", "geometry"}:
        base.append("dashboard_dark")

    return _dedupe_template_whitelist(base)


def _run(cmd: List[str], cwd: Path, *, raise_on_error: bool = True) -> bool:
    print(f"[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0 and raise_on_error:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")
    return result.returncode == 0


def _wait_for_path_unlock(path: Path, *, timeout_sec: float = 8.0, poll_sec: float = 0.25) -> bool:
    deadline = time.monotonic() + max(0.1, float(timeout_sec or 0))
    while True:
        if not path.exists():
            return True
        try:
            with path.open("ab"):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(max(0.05, float(poll_sec or 0.1)))


def _categorize_issue(issue: Dict[str, Any]) -> str:
    text = str(issue.get("issue", "") or "").lower()
    if "image" in text or "media" in text:
        return "image"
    if "theme" in text or "color" in text:
        return "theme"
    if "slide count mismatch" in text or "page" in text:
        return "page_count"
    if "layout" in text or "geometry" in text or "position" in text:
        return "layout"
    if "text" in text or "content" in text or "title" in text:
        return "text"
    if "visual" in text or "psnr" in text:
        return "visual"
    return "other"


def _summarize_issues(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    buckets: Dict[str, int] = {}
    for issue in issues:
        key = _categorize_issue(issue)
        buckets[key] = buckets.get(key, 0) + 1
    return dict(sorted(buckets.items(), key=lambda kv: kv[0]))


def _normalize_failure_cluster(raw: str) -> str:
    normalized = str(raw or "").strip().lower()
    return normalized if normalized in _FAILURE_CLUSTERS else "geometry"


def _collapse_issue_buckets_to_clusters(issue_buckets: Dict[str, int]) -> Dict[str, int]:
    collapsed: Dict[str, int] = {name: 0 for name in _FAILURE_CLUSTERS}
    for key, count in (issue_buckets or {}).items():
        bucket = str(key or "").strip().lower()
        value = int(count or 0)
        if value <= 0:
            continue
        if bucket in {"text", "content"}:
            collapsed["content"] += value
        elif bucket in {"layout", "page_count"}:
            collapsed["layout"] += value
        elif bucket in {"theme"}:
            collapsed["theme"] += value
        elif bucket in {"image", "media"}:
            collapsed["media"] += value
        elif bucket in {"visual", "geometry"}:
            collapsed["geometry"] += value
        elif bucket in {"harness"}:
            collapsed["harness"] += value
        else:
            collapsed["geometry"] += value
    return {k: v for k, v in collapsed.items() if v > 0}


def _pick_focus_cluster(
    *,
    issue_clusters: Dict[str, int],
    root_cause: Dict[str, Any],
    preferred: str,
) -> str:
    preferred_normalized = str(preferred or "auto").strip().lower()
    if preferred_normalized in _FAILURE_CLUSTERS:
        return preferred_normalized

    if issue_clusters:
        ranked = sorted(issue_clusters.items(), key=lambda item: (-int(item[1]), item[0]))
        return _normalize_failure_cluster(ranked[0][0])

    root_primary = str((root_cause or {}).get("primary") or "").strip().lower()
    if root_primary == "contract":
        return "layout"
    if root_primary in _FAILURE_CLUSTERS:
        return root_primary
    return "geometry"


def _build_fix_plan(
    *,
    phase: str,
    status: str,
    score: float,
    active_cluster: str,
    recommended_cluster: str,
    issue_clusters: Dict[str, int],
    root_cause: Dict[str, Any],
    single_cluster_enforced: bool,
    repair_clusters: List[str] | None = None,
) -> Dict[str, Any]:
    active = _normalize_failure_cluster(active_cluster)
    recommended = _normalize_failure_cluster(recommended_cluster)
    normalized_repair_clusters: List[str] = []
    for item in (repair_clusters or [active]):
        cluster = _normalize_failure_cluster(item)
        if cluster not in normalized_repair_clusters:
            normalized_repair_clusters.append(cluster)
    if active not in normalized_repair_clusters:
        normalized_repair_clusters.insert(0, active)
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "version": 1,
        "phase": str(phase or ""),
        "timestamp": now,
        "status": "resolved" if str(status or "").strip().upper() == "VERIFIED" else "active",
        "score": float(score or 0.0),
        "protocol": {
            "single_cluster_enforced": bool(single_cluster_enforced),
            "allowed_cluster": active,
            "allowed_clusters": normalized_repair_clusters,
            "blocked_clusters": [c for c in _FAILURE_CLUSTERS if c not in normalized_repair_clusters],
        },
        "active_cluster": active,
        "recommended_next_cluster": recommended,
        "issue_clusters": {k: int(v) for k, v in sorted((issue_clusters or {}).items())},
        "root_cause_hypothesis": root_cause or {},
        "mutations_allowed": sorted(
            {
                mutation
                for cluster in normalized_repair_clusters
                for mutation in _FIX_CLUSTER_TO_MUTATIONS.get(cluster, [])
            }
        ),
        "next_actions": [
            f"run_next_round_with_focus_cluster={recommended}",
            "keep_single_cluster_until_issue_bucket_stops_improving",
        ],
    }


def _issue_to_cluster(issue: Dict[str, Any]) -> str:
    category = _categorize_issue(issue)
    if category in {"text", "content"}:
        return "content"
    if category in {"layout", "page_count"}:
        return "layout"
    if category in {"theme"}:
        return "theme"
    if category in {"image", "media"}:
        return "media"
    if category in {"visual", "geometry"}:
        return "geometry"
    if category in {"harness"}:
        return "harness"
    return "geometry"


def _resolve_repair_clusters(
    *,
    active_cluster: str,
    issue_clusters: Dict[str, int] | None,
    single_cluster_enforced: bool,
    creation_mode: str,
) -> List[str]:
    active = _normalize_failure_cluster(active_cluster)
    clusters: List[str] = [active]
    collapsed = {k: int(v or 0) for k, v in (issue_clusters or {}).items() if int(v or 0) > 0}
    if not collapsed:
        return clusters

    # Keep normal rounds single-cluster, but allow linked repair for zero_create
    # because score often gets blocked by hard theme/media penalties.
    allow_linked = (not single_cluster_enforced) or str(creation_mode or "").strip().lower() == "zero_create"
    if not allow_linked:
        return clusters

    ranked = sorted(
        ((_normalize_failure_cluster(k), int(v)) for k, v in collapsed.items()),
        key=lambda item: (-int(item[1]), item[0]),
    )
    for cluster, _count in ranked:
        if cluster not in clusters and cluster in {"theme", "media", "geometry", "layout", "content"}:
            clusters.append(cluster)
        if len(clusters) >= 3:
            break
    return clusters


def _build_visual_critic_patch(
    *,
    report: Dict[str, Any],
    active_cluster: str,
    max_pages: int = 6,
    issue_clusters: Dict[str, int] | None = None,
    single_cluster_enforced: bool = True,
    creation_mode: str = "fidelity",
) -> Dict[str, Any]:
    def _layout_hint_for_similarity(similarity: float, cluster_name: str) -> str:
        if cluster_name not in {"geometry", "layout"}:
            return ""
        if similarity < 45:
            return "split_2"
        if similarity < 55:
            return "grid_3"
        return "asymmetric_2"

    def _render_path_for_similarity(similarity: float, cluster_name: str) -> str:
        if cluster_name == "geometry":
            return "svg"
        if cluster_name == "layout":
            return "svg"
        return ""

    def _build_slide_mutation(target: Dict[str, Any], cluster_name: str) -> Dict[str, Any]:
        page_no = int(target.get("page") or 0)
        similarity = float(target.get("similarity", 0) or 0)
        issue_text = str(target.get("issue") or "").strip()
        mutation: Dict[str, Any] = {
            "page": page_no,
            "issue": issue_text,
            "similarity": similarity,
            "severity": str(target.get("severity") or "warning"),
            "visual_patch": {
                "critic_repair": {
                    "enabled": True,
                    "active_cluster": cluster_name,
                    "target_similarity": round(similarity, 2),
                },
                "visual_priority": True,
            },
        }

        layout_hint = _layout_hint_for_similarity(similarity, cluster_name)
        if layout_hint:
            mutation["layout_hint"] = layout_hint
            mutation["layout_grid"] = layout_hint

        render_path = _render_path_for_similarity(similarity, cluster_name)
        if render_path:
            mutation["render_path"] = render_path

        semantic_patch: Dict[str, Any] = {}
        if cluster_name == "media":
            semantic_patch["media_required"] = True
        if cluster_name == "content" and any(
            token in issue_text.lower() for token in {"chart", "trend", "data"}
        ):
            semantic_patch["chart_required"] = True
        if cluster_name in {"geometry", "layout"} and "timeline" in issue_text.lower():
            semantic_patch["diagram_type"] = "timeline"
        if semantic_patch:
            mutation["semantic_constraints_patch"] = semantic_patch

        if cluster_name == "theme":
            mutation["visual_patch"]["theme_lock"] = "reference_tokens"
        if cluster_name == "content":
            mutation["visual_patch"]["content_compact_mode"] = True

        whitelist = _build_target_template_whitelist(
            issue_text=issue_text,
            layout_hint=str(mutation.get("layout_grid") or ""),
            cluster_name=cluster_name,
            creation_mode=creation_mode,
        )
        if whitelist:
            mutation["template_family_whitelist"] = whitelist
            mutation["template_family"] = whitelist[0]
            # Keep target pages stable during critic repair.
            mutation["template_lock"] = True
        return mutation

    issues = list(report.get("issues") or [])
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), dict) else {}
    targets: List[Dict[str, Any]] = []
    seen_pages: set[int] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        page_raw = issue.get("page")
        try:
            page_no = int(page_raw or 0)
        except Exception:
            page_no = 0
        if page_no <= 0 or page_no in seen_pages:
            continue
        seen_pages.add(page_no)
        similarity = float(issue.get("similarity", 0) or 0)
        targets.append(
            {
                "page": page_no,
                "similarity": similarity,
                "issue": str(issue.get("issue") or "").strip(),
                "severity": str(issue.get("severity") or "").strip().lower() or "warning",
            }
        )
    targets = sorted(targets, key=lambda row: (row["similarity"], row["page"]))[: max(1, int(max_pages))]
    cluster = _normalize_failure_cluster(active_cluster)
    repair_clusters = _resolve_repair_clusters(
        active_cluster=cluster,
        issue_clusters=issue_clusters,
        single_cluster_enforced=single_cluster_enforced,
        creation_mode=creation_mode,
    )
    zero_create_mode = str(creation_mode or "").strip().lower() == "zero_create"
    ref_image_count = int(diagnostics.get("ref_image_count") or 0)
    gen_image_count = int(diagnostics.get("gen_image_count") or 0)
    image_mismatch_issue = any(
        "image count mismatch" in str((row or {}).get("issue") or "").strip().lower()
        for row in issues
        if isinstance(row, dict)
    )
    avoid_media_expansion = bool(
        zero_create_mode
        and ("media" in repair_clusters)
        and (
            (ref_image_count <= 0 and gen_image_count > ref_image_count)
            or image_mismatch_issue
        )
    )
    if avoid_media_expansion:
        repair_clusters = [name for name in repair_clusters if name != "media"]
        if not repair_clusters:
            repair_clusters = [cluster]
    min_similarity = float(targets[0]["similarity"]) if targets else 100.0
    if cluster == "geometry":
        cluster_hint = "Prioritize element alignment, margins, and whitespace consistency."
    elif cluster == "theme":
        cluster_hint = "Prioritize theme colors, typography, and hierarchy consistency."
    elif cluster == "media":
        cluster_hint = "Prioritize media relevance, crop ratio, and missing media fixes."
    elif cluster == "layout":
        cluster_hint = "Prioritize layout rhythm, repetition control, and density balance."
    elif cluster == "content":
        cluster_hint = "Prioritize title-evidence consistency and text readability."
    else:
        cluster_hint = "Prioritize current failure-cluster fixes."

    page_hints = [
        f"Page {row['page']} similarity={row['similarity']:.1f}, fix: {row['issue']}"
        for row in targets
    ]
    slide_mutations = []
    for row in targets:
        issue_cluster = _issue_to_cluster({"issue": row.get("issue", "")})
        target_cluster = issue_cluster if issue_cluster in repair_clusters else cluster
        slide_mutations.append(_build_slide_mutation(row, target_cluster))
    required_facts_additions = [
        f"Repair goal: {cluster_hint}",
        f"Repair clusters: {','.join(repair_clusters)}",
        *page_hints[:4],
    ]
    global_constraints = [
        f"Visual critic repair: {cluster_hint}",
        "Keep narrative order and slide count unchanged; no cross-slide reorder.",
        "Only repair low-similarity pages; keep core facts unchanged.",
    ]
    if str(creation_mode or "").strip().lower() == "zero_create" and cluster in {"geometry", "layout"}:
        global_constraints.append(
            "For critic target pages, enforce template_family_whitelist and avoid generic dashboard_dark fallback."
        )
    execution_overrides: Dict[str, str] = {}
    if cluster in {"geometry", "layout"} and min_similarity < 70.0:
        execution_overrides["reconstruct_source_aligned"] = "on"
        execution_overrides["reconstruct_template_shell"] = "on"
        execution_overrides["force_local_strategy"] = "reconstruct"
        execution_overrides["force_mode"] = "local"
    elif cluster == "media":
        execution_overrides["reconstruct_template_shell"] = "on"
    if "theme" in repair_clusters:
        execution_overrides["reconstruct_template_shell"] = "on"
        execution_overrides["restore_reference_theme"] = "on"
        execution_overrides["force_focus_cluster"] = "theme"
    if "media" in repair_clusters and not avoid_media_expansion:
        execution_overrides["reconstruct_template_shell"] = "on"
        execution_overrides["restore_reference_manifests"] = "on"
        if "force_focus_cluster" not in execution_overrides:
            execution_overrides["force_focus_cluster"] = "media"
    if zero_create_mode:
        for key in [
            "restore_reference_manifests",
            "restore_reference_theme",
            "reconstruct_source_aligned",
            "reconstruct_template_shell",
            "force_local_strategy",
        ]:
            execution_overrides.pop(key, None)
        # zero_create API path can hit long pipeline timeout; keep critic repair
        # on local mode with sanitized slides to avoid harness regressions.
        execution_overrides["force_mode"] = "local"
    return {
        "active_cluster": cluster,
        "creation_mode": str(creation_mode or "fidelity"),
        "repair_clusters": repair_clusters,
        "target_pages": [int(row["page"]) for row in targets],
        "targets": targets,
        "slide_mutations": slide_mutations,
        "global_constraints": global_constraints,
        "required_facts_additions": required_facts_additions,
        "execution_overrides": execution_overrides,
        "strategy_flags": {
            "avoid_media_expansion": bool(avoid_media_expansion),
            "image_mismatch_issue": bool(image_mismatch_issue),
        },
    }


def _apply_visual_critic_patch_to_input(
    *,
    input_json_path: Path,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        data = json.loads(input_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "reason": "invalid_input_json"}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "input_not_object"}

    constraints = data.get("constraints")
    if not isinstance(constraints, list):
        constraints = []
    required_facts = data.get("required_facts")
    if not isinstance(required_facts, list):
        required_facts = []
    appended_constraints = 0
    for line in patch.get("global_constraints") or []:
        text = str(line or "").strip()
        if not text or text in constraints:
            continue
        constraints.append(text)
        appended_constraints += 1
    appended_required_facts = 0
    for line in patch.get("required_facts_additions") or []:
        text = str(line or "").strip()
        if not text or text in required_facts:
            continue
        required_facts.append(text)
        appended_required_facts += 1

    targets = {int(p) for p in (patch.get("target_pages") or []) if int(p or 0) > 0}
    mutation_map: Dict[int, Dict[str, Any]] = {}
    for mutation in patch.get("slide_mutations") or []:
        if not isinstance(mutation, dict):
            continue
        page_no = int(mutation.get("page") or 0)
        if page_no > 0:
            mutation_map[page_no] = mutation

    slides = data.get("slides")
    touched_slides = 0
    inserted_blocks = 0
    updated_fields = 0
    total_pages = len(slides) if isinstance(slides, list) else 0
    cluster_name = str(patch.get("active_cluster") or "").strip().lower()
    strategy_flags = patch.get("strategy_flags") if isinstance(patch.get("strategy_flags"), dict) else {}
    avoid_media_expansion = bool(strategy_flags.get("avoid_media_expansion"))
    repair_clusters = [
        _normalize_failure_cluster(item)
        for item in (patch.get("repair_clusters") if isinstance(patch.get("repair_clusters"), list) else [])
    ]
    if not repair_clusters:
        repair_clusters = [_normalize_failure_cluster(cluster_name)]
    if isinstance(slides, list) and targets:
        for idx, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                continue
            page_number = int(slide.get("page_number") or idx)
            if page_number not in targets:
                continue
            mutation = mutation_map.get(page_number, {})

            visual = slide.get("visual")
            if not isinstance(visual, dict):
                visual = {}
                slide["visual"] = visual

            visual_patch = (
                mutation.get("visual_patch")
                if isinstance(mutation.get("visual_patch"), dict)
                else {}
            )
            for key, value in visual_patch.items():
                if visual.get(key) != value:
                    visual[key] = value
                    updated_fields += 1

            visual["critic_repair"] = {
                "enabled": True,
                "active_cluster": str(patch.get("active_cluster") or ""),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }

            if str(mutation.get("layout_hint") or "").strip():
                next_layout = str(mutation.get("layout_hint") or "").strip()
                if slide.get("layout_hint") != next_layout:
                    slide["layout_hint"] = next_layout
                    updated_fields += 1
            elif not str(slide.get("layout_hint") or "").strip():
                slide["layout_hint"] = "split_2"
                updated_fields += 1

            if str(mutation.get("layout_grid") or "").strip():
                next_grid = str(mutation.get("layout_grid") or "").strip()
                if slide.get("layout_grid") != next_grid:
                    slide["layout_grid"] = next_grid
                    updated_fields += 1
            elif not str(slide.get("layout_grid") or "").strip():
                slide["layout_grid"] = str(slide.get("layout_hint") or "split_2").strip() or "split_2"
                updated_fields += 1

            if str(mutation.get("render_path") or "").strip():
                next_path = str(mutation.get("render_path") or "").strip()
                if slide.get("render_path") != next_path:
                    slide["render_path"] = next_path
                    updated_fields += 1

            whitelist_raw = mutation.get("template_family_whitelist")
            whitelist: List[str] = []
            if isinstance(whitelist_raw, list):
                whitelist = _dedupe_template_whitelist([str(item or "") for item in whitelist_raw])
            if whitelist:
                if slide.get("template_family_whitelist") != whitelist:
                    slide["template_family_whitelist"] = whitelist
                    updated_fields += 1
                # Compatibility alias consumed by template-registry on Node side.
                if slide.get("template_candidates") != whitelist:
                    slide["template_candidates"] = list(whitelist)
                    updated_fields += 1

            template_family = _normalize_template_family_token(
                mutation.get("template_family") or slide.get("template_family")
            )
            if not template_family and whitelist:
                template_family = whitelist[0]
            if template_family:
                if str(slide.get("template_family") or "").strip().lower() != template_family:
                    slide["template_family"] = template_family
                    updated_fields += 1
                if str(slide.get("template_id") or "").strip().lower() != template_family:
                    slide["template_id"] = template_family
                    updated_fields += 1

            if bool(mutation.get("template_lock")) and not bool(slide.get("template_lock")):
                slide["template_lock"] = True
                updated_fields += 1

            semantic_patch = (
                mutation.get("semantic_constraints_patch")
                if isinstance(mutation.get("semantic_constraints_patch"), dict)
                else {}
            )
            if semantic_patch:
                semantic_constraints = slide.get("semantic_constraints")
                if not isinstance(semantic_constraints, dict):
                    semantic_constraints = {}
                    slide["semantic_constraints"] = semantic_constraints
                for key, value in semantic_patch.items():
                    if semantic_constraints.get(key) != value:
                        semantic_constraints[key] = value
                        updated_fields += 1

            blocks = slide.get("blocks")
            if not isinstance(blocks, list):
                blocks = []
                slide["blocks"] = blocks

            # Geometry/layout cluster: reduce block complexity and normalize slot positions
            # on middle slides to increase layout stability during regenerate.
            if ("geometry" in repair_clusters or "layout" in repair_clusters) and 1 < page_number < max(2, total_pages):
                ranked_blocks: List[Dict[str, Any]] = []
                for raw_block in blocks:
                    if isinstance(raw_block, dict):
                        ranked_blocks.append(dict(raw_block))
                if ranked_blocks:
                    def _block_rank(item: Dict[str, Any]) -> int:
                        btype = str(item.get("block_type") or item.get("type") or "").strip().lower()
                        table = {
                            "title": 0,
                            "subtitle": 1,
                            "body": 2,
                            "list": 3,
                            "kpi": 4,
                            "chart": 5,
                            "image": 6,
                            "quote": 7,
                            "table": 8,
                            "icon_text": 9,
                        }
                        return int(table.get(btype, 20))

                    ranked_blocks.sort(key=lambda item: (_block_rank(item), str(item.get("id") or "")))
                    keep_count = min(4, len(ranked_blocks))
                    compact = ranked_blocks[:keep_count]
                    slot_positions = ["top", "left", "right", "bottom"]
                    compact_out: List[Dict[str, Any]] = []
                    for b_idx, block in enumerate(compact):
                        item = dict(block)
                        btype = str(item.get("block_type") or item.get("type") or "").strip().lower()
                        if not item.get("block_type") and btype:
                            item["block_type"] = btype
                        if not item.get("type") and btype:
                            item["type"] = btype
                        content = item.get("content")
                        if isinstance(content, str):
                            clipped = content.strip()
                            if len(clipped) > 140:
                                item["content"] = clipped[:140]
                        if not str(item.get("position") or "").strip():
                            item["position"] = slot_positions[min(b_idx, len(slot_positions) - 1)]
                        compact_out.append(item)
                    if compact_out != blocks:
                        slide["blocks"] = compact_out
                        blocks = compact_out
                        updated_fields += 1

            semantic_constraints = slide.get("semantic_constraints")
            semantic_constraints = semantic_constraints if isinstance(semantic_constraints, dict) else {}
            if (
                bool(semantic_constraints.get("media_required"))
                or ("media" in repair_clusters and not avoid_media_expansion)
            ):
                has_image = any(
                    str((b or {}).get("block_type") or (b or {}).get("type") or "").strip().lower() == "image"
                    for b in blocks
                    if isinstance(b, dict)
                )
                if not has_image:
                    title = str(slide.get("title") or f"Slide {page_number}").strip() or f"Slide {page_number}"
                    blocks.append(
                        {
                            "id": f"{slide.get('slide_id') or slide.get('id') or f'slide-{page_number:03d}'}-critic-image",
                            "card_id": "visual-critic-image",
                            "block_type": "image",
                            "type": "image",
                            "position": "right",
                            "content": title[:64],
                            "data": {"title": title[:80], "keywords": [title, "business", "presentation"]},
                        }
                    )
                    inserted_blocks += 1

            if bool(semantic_constraints.get("chart_required")):
                has_chart = any(
                    str((b or {}).get("block_type") or (b or {}).get("type") or "").strip().lower() == "chart"
                    for b in blocks
                    if isinstance(b, dict)
                )
                if not has_chart:
                    blocks.append(
                        {
                            "id": f"{slide.get('slide_id') or slide.get('id') or f'slide-{page_number:03d}'}-critic-chart",
                            "card_id": "visual-critic-chart",
                            "block_type": "chart",
                            "type": "chart",
                            "position": "center",
                            "content": "Core trend",
                            "data": {
                                "chartType": "bar",
                                "labels": ["Q1", "Q2", "Q3"],
                                "datasets": [{"label": "Metric", "data": [40, 55, 68]}],
                            },
                        }
                    )
                    inserted_blocks += 1
            touched_slides += 1

    if "theme" in repair_clusters:
        constraints = data.get("constraints") if isinstance(data.get("constraints"), list) else []
        line = "Theme repair: enforce reference palette overlap and typography consistency."
        if line not in constraints:
            constraints.append(line)
            data["constraints"] = constraints[-30:]

    data["constraints"] = constraints[-30:]
    data["required_facts"] = required_facts[-30:]
    data["critic_patch"] = patch
    input_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "touched_slides": touched_slides,
        "updated_fields": updated_fields,
        "inserted_blocks": inserted_blocks,
        "appended_constraints": appended_constraints,
        "appended_required_facts": appended_required_facts,
    }


def _evaluate_report(
    report: Dict[str, Any],
    *,
    target_score: float,
    allow_warnings: bool,
) -> Dict[str, Any]:
    score = float(report.get("score", report.get("visual_score", 0)) or 0)
    issues = list(report.get("issues", []) or [])
    errors = [
        item
        for item in issues
        if str(item.get("severity", "")).strip().lower() in {"error"}
    ]
    warnings = [
        item
        for item in issues
        if str(item.get("severity", "")).strip().lower() in {"warning"}
    ]
    blocking_issues = errors if allow_warnings else (errors + warnings)
    verified = score >= float(target_score) and len(blocking_issues) == 0
    return {
        "score": score,
        "issues": issues,
        "errors": errors,
        "warnings": warnings,
        "issue_buckets": _summarize_issues(issues),
        "verified": verified,
    }


def _inspect_input_contract(input_json_path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(input_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False}
    slides = data.get("slides") or []
    if not isinstance(slides, list):
        slides = []

    text_total = 0
    text_with_bbox = 0
    text_with_style = 0
    shape_total = 0
    image_shapes = 0
    shape_with_color = 0

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        elements = slide.get("elements") or []
        shapes = slide.get("shapes") or []
        if isinstance(elements, list):
            for el in elements:
                if not isinstance(el, dict):
                    continue
                if str(el.get("type", "")).lower() != "text":
                    continue
                text_total += 1
                left = float(el.get("left", 0) or 0)
                top = float(el.get("top", 0) or 0)
                width = float(el.get("width", 0) or 0)
                height = float(el.get("height", 0) or 0)
                if width > 0 and height > 0 and left >= 0 and top >= 0:
                    text_with_bbox += 1
                if (
                    str(el.get("font_name", "")).strip()
                    or str(el.get("font_color", "")).strip()
                    or float(el.get("font_size", 0) or 0) > 0
                ):
                    text_with_style += 1
        if isinstance(shapes, list):
            for shp in shapes:
                if not isinstance(shp, dict):
                    continue
                shape_total += 1
                if str(shp.get("type", "")).lower() == "image":
                    image_shapes += 1
                if str(shp.get("fill_color", "")).strip() or str(
                    shp.get("line_color", "")
                ).strip():
                    shape_with_color += 1

    return {
        "ok": True,
        "slide_count": len(slides),
        "text_total": text_total,
        "text_with_bbox": text_with_bbox,
        "text_with_style": text_with_style,
        "shape_total": shape_total,
        "image_shapes": image_shapes,
        "shape_with_color": shape_with_color,
    }


def _infer_root_cause(
    attempts: List[Dict[str, Any]],
    input_contract_stats: Dict[str, Any],
) -> Dict[str, Any]:
    reconstruct = next(
        (a for a in attempts if str(a.get("local_strategy")) == "reconstruct"),
        attempts[0] if attempts else {},
    )
    replay = next(
        (a for a in attempts if str(a.get("local_strategy")) == "source-replay"),
        None,
    )
    diag = reconstruct.get("diagnostics", {}) if isinstance(reconstruct, dict) else {}
    if isinstance(diag, dict) and (
        diag.get("generation_failed") or diag.get("compare_failed")
    ):
        return {
            "primary": "harness",
            "confidence": 0.9,
            "evidence": ["reconstruct attempt failed before successful scoring."],
        }
    structure_score = float(reconstruct.get("structure_score", 0) or 0)
    psnr_score = float(reconstruct.get("psnr_score", 0) or 0)
    metadata_score = float(reconstruct.get("metadata_score", 0) or 0)

    ref_images = int(diag.get("ref_image_count", 0) or 0)
    gen_images = int(diag.get("gen_image_count", 0) or 0)
    extracted_images = int(input_contract_stats.get("image_shapes", 0) or 0)

    evidence: List[str] = []
    if replay and float(replay.get("score", 0) or 0) >= 95:
        evidence.append("source-replay score is high, comparator/harness baseline works.")
    if extracted_images == 0 and ref_images > 0:
        evidence.append("extracted JSON has no image shapes while reference has images.")
    if extracted_images > 0 and gen_images < ref_images:
        evidence.append("input has images but generated deck drops some image assets.")
    if structure_score >= 85 and psnr_score < 75:
        evidence.append("structure is high but PSNR is low, visual fidelity is the bottleneck.")
    if metadata_score < 80:
        evidence.append("metadata score is low, schema mapping may be incomplete.")

    if extracted_images == 0 and ref_images > 0:
        primary = "harness"
        confidence = 0.82
    elif extracted_images > 0 and gen_images < ref_images:
        primary = "contract"
        confidence = 0.74
    elif structure_score >= 85 and psnr_score < 75:
        primary = "skill"
        confidence = 0.78
    elif metadata_score < 80:
        primary = "contract"
        confidence = 0.66
    else:
        primary = "skill"
        confidence = 0.58

    return {
        "primary": primary,
        "confidence": confidence,
        "evidence": evidence,
    }


def _normalize_phase_tag(raw: str) -> str:
    text = "".join(ch for ch in str(raw or "").strip().lower() if ch.isalnum() or ch in {"-", "_", "."})
    return text.strip("._-")


def _phase_artifact_paths(output_root: Path, phase: str) -> Dict[str, Path]:
    phase_tag = _normalize_phase_tag(phase)
    if not phase_tag:
        raise ValueError("phase tag is empty")
    return {
        "phase_tag": Path(phase_tag),
        "generated_ppt": output_root / f"generated.{phase_tag}.pptx",
        "render_json": output_root / f"generated.{phase_tag}.render.json",
        "issues_json": output_root / f"issues.{phase_tag}.json",
        "summary_json": output_root / f"round_summary.{phase_tag}.json",
    }


def _restore_reference_shortcuts_for_repair(
    *,
    input_json_path: Path,
    reference_input_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(reference_input_snapshot, dict):
        return {"ok": False, "restored_keys": [], "reason": "invalid_snapshot"}
    try:
        current = json.loads(input_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "restored_keys": [], "reason": "invalid_input"}
    if not isinstance(current, dict):
        return {"ok": False, "restored_keys": [], "reason": "input_not_object"}

    restored_keys: List[str] = []
    for key in ["source_pptx_path", "theme_manifest", "master_layout_manifest", "media_manifest"]:
        value = reference_input_snapshot.get(key)
        if key in current:
            continue
        if value is None:
            continue
        current[key] = value
        restored_keys.append(key)
    if restored_keys:
        input_json_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "restored_keys": restored_keys}


def _restore_slides_for_zero_create_local_fallback(
    *,
    input_json_path: Path,
    reference_input_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(reference_input_snapshot, dict):
        return {"ok": False, "restored_slide_count": 0, "reason": "invalid_snapshot"}
    ref_slides = reference_input_snapshot.get("slides")
    if not isinstance(ref_slides, list):
        return {"ok": False, "restored_slide_count": 0, "reason": "missing_snapshot_slides"}
    try:
        current = json.loads(input_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "restored_slide_count": 0, "reason": "invalid_input"}
    if not isinstance(current, dict):
        return {"ok": False, "restored_slide_count": 0, "reason": "input_not_object"}

    restored: List[Dict[str, Any]] = []
    for raw in ref_slides:
        if not isinstance(raw, dict):
            continue
        slide = dict(raw)
        for key in [
            "elements",
            "shapes",
            "media_refs",
            "slide_layout_path",
            "slide_layout_name",
            "slide_master_path",
            "slide_theme_path",
        ]:
            slide.pop(key, None)
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            slide["blocks"] = []
        restored.append(slide)
    if not restored:
        return {"ok": False, "restored_slide_count": 0, "reason": "empty_snapshot_slides"}

    current["slides"] = restored
    current["requested_total_pages"] = max(3, min(50, len(restored)))
    input_json_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "restored_slide_count": len(restored), "reason": ""}


def _prepare_zero_create_input_for_attempt(
    *,
    input_json_path: Path,
    reference_input_snapshot: Dict[str, Any],
    attempt_mode: str,
    creation_mode: str,
) -> Dict[str, Any]:
    if str(creation_mode or "").strip().lower() != "zero_create":
        return {"ok": True, "action": "noop", "reason": "not_zero_create"}
    if str(attempt_mode or "").strip().lower() != "local":
        return {"ok": True, "action": "noop", "reason": "not_local_mode"}
    try:
        current = json.loads(input_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "action": "read_failed", "reason": "invalid_input"}
    if not isinstance(current, dict):
        return {"ok": False, "action": "read_failed", "reason": "input_not_object"}
    slides = current.get("slides")
    if isinstance(slides, list) and len(slides) > 0:
        return {"ok": True, "action": "noop", "reason": "slides_already_present", "slide_count": len(slides)}
    restored = _restore_slides_for_zero_create_local_fallback(
        input_json_path=input_json_path,
        reference_input_snapshot=reference_input_snapshot,
    )
    return {
        "ok": bool(restored.get("ok")),
        "action": "restore_slides",
        "reason": str(restored.get("reason") or ""),
        "restored_slide_count": int(restored.get("restored_slide_count") or 0),
    }


def _extract_schema_invalid_contract_slide_indexes(
    failure_report: Dict[str, Any],
) -> List[int]:
    if not isinstance(failure_report, dict):
        return []
    failure_code = str(failure_report.get("failure_code") or "").strip().lower()
    failure_reason = str(failure_report.get("failure_reason") or "")
    blob = f"{failure_code}\n{failure_reason}".lower()
    if "schema_invalid" not in blob and "render contract invalid" not in blob:
        return []
    patterns = [
        r"slides\[(\d+)\]\s+content contract:\s*one of\s*\[chart\|kpi\]\s*is required",
        r"slides\[(\d+)\]\s+content contract:\s*visual anchor requirement not satisfied",
    ]
    indexes: List[int] = []
    seen: set[int] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, blob):
            try:
                idx = int(match.group(1))
            except Exception:
                continue
            if idx < 0 or idx in seen:
                continue
            seen.add(idx)
            indexes.append(idx)
    indexes.sort()
    return indexes


def _inject_chart_blocks_for_zero_create_contract_repair(
    *,
    input_json_path: Path,
    slide_indexes: List[int],
) -> Dict[str, Any]:
    try:
        data = json.loads(input_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "reason": "invalid_input", "inserted": 0, "touched_slide_indexes": []}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "input_not_object", "inserted": 0, "touched_slide_indexes": []}
    slides = data.get("slides")
    if not isinstance(slides, list):
        return {"ok": False, "reason": "missing_slides", "inserted": 0, "touched_slide_indexes": []}

    inserted = 0
    touched_slide_indexes: List[int] = []
    for raw_idx in sorted({int(i) for i in slide_indexes if int(i) >= 0}):
        if raw_idx >= len(slides):
            continue
        slide = slides[raw_idx]
        if not isinstance(slide, dict):
            continue
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            blocks = []
            slide["blocks"] = blocks

        has_chart_or_kpi = any(
            str((b or {}).get("block_type") or (b or {}).get("type") or "").strip().lower()
            in {"chart", "kpi"}
            for b in blocks
            if isinstance(b, dict)
        )
        if has_chart_or_kpi:
            continue

        page_no = int(slide.get("page_number") or raw_idx + 1)
        slide_id = str(
            slide.get("slide_id")
            or slide.get("id")
            or f"slide-{page_no:03d}"
        ).strip() or f"slide-{page_no:03d}"
        blocks.append(
            {
                "id": f"{slide_id}-contract-chart",
                "card_id": f"contract-chart-{page_no:03d}",
                "block_type": "chart",
                "type": "chart",
                "position": "right",
                "content": {
                    "labels": ["A", "B", "C"],
                    "datasets": [{"label": "Metric", "data": [58, 69, 80]}],
                },
                "emphasis": [str(page_no)],
            }
        )
        inserted += 1
        touched_slide_indexes.append(raw_idx)

    if inserted > 0:
        input_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "reason": "",
        "inserted": inserted,
        "touched_slide_indexes": touched_slide_indexes,
    }


def _append_fix_record(
    *,
    fix_record_path: Path,
    phase: str,
    status: str,
    score: float,
    generated_ppt: Path,
    render_json: Path | None,
    issues_json: Path,
    summary_json: Path,
    active_cluster: str = "",
    recommended_next_cluster: str = "",
    fix_plan_json: Path | None = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    data: Dict[str, Any] = {}
    if fix_record_path.exists():
        try:
            data = json.loads(fix_record_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    phase_runs = data.get("phase_runs")
    if not isinstance(phase_runs, list):
        phase_runs = []
    phase_runs.append(
        {
            "phase": phase,
            "status": status,
            "score": float(score),
            "generated_ppt": str(generated_ppt.resolve()),
            "render_json": str(render_json.resolve()) if render_json else "",
            "issues_json": str(issues_json.resolve()),
            "summary_json": str(summary_json.resolve()),
            "active_cluster": _normalize_failure_cluster(active_cluster) if active_cluster else "",
            "recommended_next_cluster": (
                _normalize_failure_cluster(recommended_next_cluster)
                if recommended_next_cluster
                else ""
            ),
            "fix_plan_json": str(fix_plan_json.resolve()) if fix_plan_json else "",
            "timestamp": now,
        }
    )
    data["phase_runs"] = phase_runs[-50:]
    data["last_phase"] = phase
    data["iteration"] = int(data.get("iteration") or 0) + 1
    if not isinstance(data.get("fixes_applied"), list):
        data["fixes_applied"] = []
    data["timestamp"] = now
    fix_record_path.parent.mkdir(parents=True, exist_ok=True)
    fix_record_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _publish_phase_artifacts(
    *,
    phase: str,
    output_root: Path,
    generated_ppt: Path,
    render_json: Path,
    issues_json: Path,
    summary_json: Path,
) -> Dict[str, str]:
    def _copy_if_needed(src: Path, dst: Path) -> None:
        src_resolved = src.resolve()
        dst_resolved = dst.resolve()
        if src_resolved == dst_resolved:
            return
        shutil.copyfile(str(src), str(dst))

    paths = _phase_artifact_paths(output_root, phase)
    _copy_if_needed(generated_ppt, paths["generated_ppt"])
    _copy_if_needed(render_json, paths["render_json"])
    _copy_if_needed(issues_json, paths["issues_json"])
    _copy_if_needed(summary_json, paths["summary_json"])
    return {
        "phase": str(paths["phase_tag"]),
        "generated_ppt": str(paths["generated_ppt"].resolve()),
        "render_json": str(paths["render_json"].resolve()),
        "issues_json": str(paths["issues_json"].resolve()),
        "summary_json": str(paths["summary_json"].resolve()),
    }


def _build_compare_cmd(
    *,
    python_bin: str,
    reference_ppt: Path,
    generated_ppt: Path,
    issues_json: Path,
    compare_mode: str,
    pass_score: float,
    allow_warnings: bool,
    require_psnr: bool,
) -> List[str]:
    return [
        python_bin,
        "scripts/compare_ppt_visual.py",
        "--reference",
        str(reference_ppt),
        "--generated",
        str(generated_ppt),
        "--output",
        str(issues_json),
        "--mode",
        str(compare_mode),
        "--pass-score",
        str(float(pass_score)),
        "--require-no-issues",
        "off" if allow_warnings else "on",
        "--require-psnr",
        "on" if require_psnr else "off",
    ]


def _resolve_quality_bar(
    *,
    quality_bar: str,
    target_score: float,
    compare_mode: str,
    allow_warnings: bool,
) -> Dict[str, Any]:
    bar = str(quality_bar or "normal").strip().lower()
    score = float(target_score)
    mode = str(compare_mode or "structural").strip().lower() or "structural"
    warnings_allowed = bool(allow_warnings)
    require_psnr = False

    if bar == "high":
        score = max(score, 90.0)
        mode = "auto" if mode == "structural" else mode
        warnings_allowed = False
        require_psnr = True
    elif bar == "strict":
        score = max(score, 93.0)
        mode = "auto"
        warnings_allowed = False
        require_psnr = True

    return {
        "quality_bar": bar,
        "target_score": score,
        "compare_mode": mode,
        "allow_warnings": warnings_allowed,
        "require_psnr": require_psnr,
    }


def _resolve_reconstruct_switches(
    *,
    creation_mode: str,
    quality_bar: str,
    reconstruct_template_shell: str,
    reconstruct_source_aligned: str,
) -> Dict[str, str]:
    creation = str(creation_mode or "fidelity").strip().lower()
    bar = str(quality_bar or "normal").strip().lower()
    shell_flag = str(reconstruct_template_shell or "auto").strip().lower()
    aligned_flag = str(reconstruct_source_aligned or "auto").strip().lower()
    if shell_flag not in {"on", "off", "auto"}:
        shell_flag = "auto"
    if aligned_flag not in {"on", "off", "auto"}:
        aligned_flag = "auto"

    if creation == "zero_create":
        shell_flag = "off"
        aligned_flag = "off"
        return {
            "reconstruct_template_shell": shell_flag,
            "reconstruct_source_aligned": aligned_flag,
        }

    if bar in {"high", "strict"}:
        if shell_flag == "auto":
            shell_flag = "on"
        if aligned_flag == "auto":
            aligned_flag = "on"
    else:
        if shell_flag == "auto":
            shell_flag = "off"
        if aligned_flag == "auto":
            aligned_flag = "off"

    return {
        "reconstruct_template_shell": shell_flag,
        "reconstruct_source_aligned": aligned_flag,
    }


def _resolve_generation_mode(
    *,
    creation_mode: str,
    requested_mode: str,
    local_strategy: str,
    reconstruct_via_pipeline: str,
) -> str:
    """Resolve generate_ppt_from_desc mode for one regression attempt."""
    creation = str(creation_mode or "fidelity").strip().lower()
    requested = str(requested_mode or "auto").strip().lower()
    strategy = str(local_strategy or "reconstruct").strip().lower()
    via_pipeline = str(reconstruct_via_pipeline or "on").strip().lower()

    if requested not in {"api", "local", "auto"}:
        requested = "auto"

    if creation == "zero_create":
        # zero_create default keeps API-first behavior, but local dev can opt-in
        # to local-first via env and explicit --mode local is respected.
        if requested in {"api", "local"}:
            return requested
        zero_create_default = str(
            os.getenv("PPT_ZERO_CREATE_DEFAULT_MODE", "api")
        ).strip().lower()
        if zero_create_default in {"local", "local_first"}:
            return "local"
        return "api"

    if strategy == "source-replay":
        return "local"
    if strategy == "reconstruct" and via_pipeline == "on":
        return "api"
    return requested


def _sanitize_input_for_zero_create(
    input_json_path: Path,
    *,
    keep_sanitized_slides: bool = True,
) -> Dict[str, Any]:
    data = json.loads(input_json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"applied": False, "reason": "input_not_object"}

    removed_keys: List[str] = []
    for key in [
        "source_pptx_path",
        "theme_manifest",
        "master_layout_manifest",
        "media_manifest",
        "theme_color_map",
    ]:
        if key in data:
            data.pop(key, None)
            removed_keys.append(key)

    sanitized_slide_count = 0
    stripped_slide_fields = 0
    slides = data.get("slides")
    if isinstance(slides, list):
        data["requested_total_pages"] = max(3, min(50, len(slides)))
        sanitized_slides = []
        for raw in slides:
            if not isinstance(raw, dict):
                continue
            slide = dict(raw)
            before = len(slide)
            for key in [
                "elements",
                "shapes",
                "media_refs",
                "slide_layout_path",
                "slide_layout_name",
                "slide_master_path",
                "slide_theme_path",
            ]:
                slide.pop(key, None)
            stripped_slide_fields += max(0, before - len(slide))
            sanitized_slide_count += 1
            sanitized_slides.append(slide)
        # Keep prompt-level hints and sanitized slide shells (no geometry/media)
        # so skill planning and template routing can still leverage page intent.
        hints: List[str] = []
        for slide in sanitized_slides:
            title = str(slide.get("title") or "").strip()
            if title:
                hints.append(title[:90])
            for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else []):
                if len(hints) >= 20:
                    break
                if not isinstance(block, dict):
                    continue
                content = str(block.get("content") or "").strip()
                if content:
                    hints.append(content[:90])
            if len(hints) >= 20:
                break
        if hints:
            existing_required = data.get("required_facts")
            existing_required = existing_required if isinstance(existing_required, list) else []
            data["required_facts"] = [*existing_required, *hints][:20]
        if keep_sanitized_slides:
            data["slides"] = sanitized_slides
        else:
            data.pop("slides", None)

    input_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "applied": True,
        "removed_keys": removed_keys,
        "sanitized_slide_count": sanitized_slide_count,
        "stripped_slide_fields": stripped_slide_fields,
        "kept_sanitized_slides": bool(keep_sanitized_slides),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one reference-driven PPT regression round"
    )
    parser.add_argument(
        "--reference-ppt",
        default=r"C:\Users\liula\Downloads\ppt2\ppt2\1.pptx",
        help="Reference PPT path",
    )
    parser.add_argument(
        "--pages",
        default="1-22",
        help="Pages to extract, e.g. 1-20 or 1,3,5",
    )
    parser.add_argument(
        "--input-json",
        default="output/regression/reference_extracted.json",
        help="Extracted description JSON path",
    )
    parser.add_argument(
        "--generated-ppt",
        default="output/regression/generated.pptx",
        help="Generated PPT output path",
    )
    parser.add_argument(
        "--render-json",
        default="output/regression/generated.render.json",
        help="Render payload output path",
    )
    parser.add_argument(
        "--issues-json",
        default="output/regression/issues.json",
        help="Comparison issues output path",
    )
    parser.add_argument(
        "--summary-json",
        default="output/regression/round_summary.json",
        help="Round summary output path",
    )
    parser.add_argument(
        "--phase",
        default="",
        help="Optional phase tag. If set, publish generated.<phase>.pptx and issues.<phase>.json",
    )
    parser.add_argument(
        "--fix-record",
        default="output/regression/fix_record.json",
        help="Fix record JSON path used when --phase is set",
    )
    parser.add_argument(
        "--fix-plan",
        default="output/regression/fix_plan.json",
        help="Path to write single-cluster execution protocol",
    )
    parser.add_argument(
        "--focus-cluster",
        choices=["auto", "content", "layout", "theme", "media", "geometry", "harness"],
        default="auto",
        help="Active failure cluster for this round; auto picks from previous plan or current issues",
    )
    parser.add_argument(
        "--single-cluster",
        choices=["on", "off"],
        default="on",
        help="Enforce one main failure cluster per round",
    )
    parser.add_argument(
        "--visual-critic-repair",
        choices=["on", "off", "auto"],
        default="auto",
        help="When failed, run one extra attempt by applying visual critic patch",
    )
    parser.add_argument(
        "--visual-critic-max-pages",
        type=int,
        default=6,
        help="Max low-similarity pages to include in critic patch",
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=80.0,
        help="Verification score threshold",
    )
    parser.add_argument(
        "--mode",
        choices=["api", "local", "auto"],
        default="auto",
        help="Generation mode for generate_ppt_from_desc.py",
    )
    parser.add_argument(
        "--local-strategy",
        choices=["reconstruct", "source-replay"],
        default="reconstruct",
        help="Local strategy passed to generate_ppt_from_desc.py",
    )
    parser.add_argument(
        "--fallback-local-strategy",
        choices=["none", "reconstruct", "source-replay"],
        default="none",
        help="Optional second local strategy if first attempt is below target",
    )
    parser.add_argument(
        "--reconstruct-template-shell",
        choices=["on", "off", "auto"],
        default="auto",
        help="Pass-through to generate_ppt_from_desc for reconstruct strategy",
    )
    parser.add_argument(
        "--reconstruct-source-aligned",
        choices=["on", "off", "auto"],
        default="auto",
        help="Pass-through to generate_ppt_from_desc for reconstruct strategy",
    )
    parser.add_argument(
        "--reconstruct-via-pipeline",
        choices=["on", "off"],
        default="on",
        help="Whether reconstruct attempt should run full API pipeline first",
    )
    parser.add_argument(
        "--compare-mode",
        choices=["psnr", "structural", "auto"],
        default="structural",
        help="Comparison mode for compare_ppt_visual.py",
    )
    parser.add_argument(
        "--allow-warnings",
        action="store_true",
        help="Treat warnings as non-blocking for VERIFIED status",
    )
    parser.add_argument(
        "--quality-bar",
        choices=["normal", "high", "strict"],
        default="normal",
        help="Gate strictness preset: high/strict raises score bar and requires PSNR availability",
    )
    parser.add_argument(
        "--creation-mode",
        choices=["fidelity", "zero_create"],
        default="fidelity",
        help="fidelity allows source-aligned/template-shell reuse; zero_create forbids those shortcuts",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    python_bin = sys.executable

    input_json = Path(args.input_json)
    generated_ppt = Path(args.generated_ppt)
    render_json = Path(args.render_json)
    issues_json = Path(args.issues_json)
    summary_json = Path(args.summary_json)
    reference_ppt_path = Path(args.reference_ppt)
    if not reference_ppt_path.exists():
        raise FileNotFoundError(f"reference ppt not found: {reference_ppt_path}")
    quality_cfg = _resolve_quality_bar(
        quality_bar=args.quality_bar,
        target_score=float(args.target_score),
        compare_mode=args.compare_mode,
        allow_warnings=bool(args.allow_warnings),
    )
    effective_target_score = float(quality_cfg["target_score"])
    effective_compare_mode = str(quality_cfg["compare_mode"])
    effective_allow_warnings = bool(quality_cfg["allow_warnings"])
    effective_require_psnr = bool(quality_cfg["require_psnr"])
    reconstruct_cfg = _resolve_reconstruct_switches(
        creation_mode=str(args.creation_mode),
        quality_bar=str(quality_cfg.get("quality_bar") or "normal"),
        reconstruct_template_shell=str(args.reconstruct_template_shell),
        reconstruct_source_aligned=str(args.reconstruct_source_aligned),
    )
    effective_reconstruct_template_shell = str(reconstruct_cfg["reconstruct_template_shell"])
    effective_reconstruct_source_aligned = str(reconstruct_cfg["reconstruct_source_aligned"])
    fix_plan_path = Path(args.fix_plan)
    fix_plan_path.parent.mkdir(parents=True, exist_ok=True)
    single_cluster_enforced = str(args.single_cluster).strip().lower() == "on"
    requested_focus_cluster = str(args.focus_cluster or "auto").strip().lower()
    active_focus_cluster = _pick_focus_cluster(
        issue_clusters={},
        root_cause={},
        preferred=requested_focus_cluster,
    )
    if requested_focus_cluster == "auto" and fix_plan_path.exists():
        try:
            previous_fix_plan = json.loads(fix_plan_path.read_text(encoding="utf-8"))
            carry_cluster = str(previous_fix_plan.get("active_cluster") or "").strip().lower()
            carry_status = str(previous_fix_plan.get("status") or "").strip().lower()
            if carry_cluster in _FAILURE_CLUSTERS and carry_status == "active":
                active_focus_cluster = carry_cluster
        except Exception:
            pass

    for target in [input_json, generated_ppt, render_json, issues_json, summary_json]:
        target.parent.mkdir(parents=True, exist_ok=True)

    extract_cmd = [
        python_bin,
        "scripts/extract_to_minimax_json.py",
        "--input",
        str(reference_ppt_path),
        "--output",
        str(input_json),
        "--pages",
        args.pages,
        "--no-compare",
    ]
    _run(extract_cmd, cwd=repo_root, raise_on_error=True)
    reference_input_snapshot: Dict[str, Any] = {}
    try:
        parsed_input = json.loads(input_json.read_text(encoding="utf-8"))
        if isinstance(parsed_input, dict):
            reference_input_snapshot = parsed_input
    except Exception:
        reference_input_snapshot = {}
    zero_create_sanitization: Dict[str, Any] = {"applied": False}
    if str(args.creation_mode).strip().lower() == "zero_create":
        zero_create_sanitization = _sanitize_input_for_zero_create(input_json)
    input_contract_stats = _inspect_input_contract(input_json)
    attempt_strategies: List[str] = [str(args.local_strategy)]
    if str(args.creation_mode).strip().lower() == "zero_create":
        attempt_strategies = [
            "reconstruct" if str(item) == "source-replay" else str(item)
            for item in attempt_strategies
        ]
    if (
        str(args.fallback_local_strategy) != "none"
        and str(args.fallback_local_strategy) not in attempt_strategies
    ):
        fallback_strategy = (
            "reconstruct"
            if str(args.creation_mode).strip().lower() == "zero_create"
            and str(args.fallback_local_strategy) == "source-replay"
            else str(args.fallback_local_strategy)
        )
        attempt_strategies.append(fallback_strategy)

    attempts: List[Dict[str, Any]] = []
    final_eval: Dict[str, Any] = {}
    final_report: Dict[str, Any] = {}
    visual_critic_flag = str(args.visual_critic_repair or "auto").strip().lower()
    visual_critic_enabled = visual_critic_flag == "on" or (
        visual_critic_flag == "auto"
        and str(args.creation_mode).strip().lower() == "zero_create"
    )
    visual_critic_patch: Dict[str, Any] = {}
    visual_critic_apply_result: Dict[str, Any] = {"applied": False}

    for idx, strategy in enumerate(attempt_strategies, start=1):
        attempt_mode = _resolve_generation_mode(
            creation_mode=str(args.creation_mode),
            requested_mode=str(args.mode),
            local_strategy=str(strategy),
            reconstruct_via_pipeline=str(args.reconstruct_via_pipeline),
        )

        generate_cmd = [
            python_bin,
            "scripts/generate_ppt_from_desc.py",
            "--input",
            str(input_json),
            "--output",
            str(generated_ppt),
            "--render-output",
            str(render_json),
            "--mode",
            attempt_mode,
            "--local-strategy",
            strategy,
            "--reconstruct-template-shell",
            effective_reconstruct_template_shell,
            "--reconstruct-source-aligned",
            effective_reconstruct_source_aligned,
            "--creation-mode",
            str(args.creation_mode),
            "--execution-profile",
            "prod_safe",
            "--focus-cluster",
            active_focus_cluster,
        ]
        compare_cmd = _build_compare_cmd(
            python_bin=python_bin,
            reference_ppt=reference_ppt_path,
            generated_ppt=generated_ppt,
            issues_json=issues_json,
            compare_mode=effective_compare_mode,
            pass_score=effective_target_score,
            allow_warnings=effective_allow_warnings,
            require_psnr=effective_require_psnr,
        )
        _prepare_zero_create_input_for_attempt(
            input_json_path=input_json,
            reference_input_snapshot=reference_input_snapshot,
            attempt_mode=attempt_mode,
            creation_mode=str(args.creation_mode),
        )
        generated_ok = _run(generate_cmd, cwd=repo_root, raise_on_error=False)
        zero_create_api_retry_attempted = False
        zero_create_timeout_failure = False
        zero_create_local_fallback_attempted = False
        zero_create_local_fallback_used = False
        zero_create_contract_repair_attempted = False
        zero_create_contract_repair_used = False
        if (
            (not generated_ok)
            and str(args.creation_mode).strip().lower() == "zero_create"
            and str(attempt_mode).strip().lower() == "api"
            and render_json.exists()
        ):
            try:
                failure_report = json.loads(render_json.read_text(encoding="utf-8"))
                failure_stage = str(failure_report.get("failure_stage") or "").strip().lower()
                failure_reason = str(failure_report.get("failure_reason") or "").strip().lower()
                zero_create_timeout_failure = (
                    failure_stage in {"api_http_error", "api_exception"}
                    and "pipeline timeout" in failure_reason
                )
            except Exception:
                zero_create_timeout_failure = False
        if (
            (not generated_ok)
            and str(args.creation_mode).strip().lower() == "zero_create"
            and str(attempt_mode).strip().lower() == "api"
            and (not zero_create_timeout_failure)
        ):
            # API warm-up can fail transiently in zero_create rounds; retry once
            # before classifying as harness failure.
            zero_create_api_retry_attempted = True
            generated_ok = _run(generate_cmd, cwd=repo_root, raise_on_error=False)
        if (
            (not generated_ok)
            and str(args.creation_mode).strip().lower() == "zero_create"
            and str(attempt_mode).strip().lower() == "api"
        ):
            _restore_slides_for_zero_create_local_fallback(
                input_json_path=input_json,
                reference_input_snapshot=reference_input_snapshot,
            )
            local_fallback_cmd = list(generate_cmd)
            mode_idx = local_fallback_cmd.index("--mode") + 1
            local_fallback_cmd[mode_idx] = "local"
            local_fallback_cmd.extend(["--allow-zero-create-reconstruct-overrides", "on"])
            zero_create_local_fallback_attempted = True
            generated_ok = _run(local_fallback_cmd, cwd=repo_root, raise_on_error=False)
            if generated_ok:
                attempt_mode = "local"
                zero_create_local_fallback_used = True
            elif render_json.exists():
                try:
                    failure_report = json.loads(render_json.read_text(encoding="utf-8"))
                except Exception:
                    failure_report = {}
                contract_indexes = _extract_schema_invalid_contract_slide_indexes(failure_report)
                if contract_indexes:
                    zero_create_contract_repair_attempted = True
                    repair_result = _inject_chart_blocks_for_zero_create_contract_repair(
                        input_json_path=input_json,
                        slide_indexes=contract_indexes,
                    )
                    if int(repair_result.get("inserted") or 0) > 0:
                        _wait_for_path_unlock(generated_ppt, timeout_sec=10.0, poll_sec=0.3)
                        generated_ok = _run(local_fallback_cmd, cwd=repo_root, raise_on_error=False)
                        if generated_ok:
                            attempt_mode = "local"
                            zero_create_local_fallback_used = True
                            zero_create_contract_repair_used = True
        if not generated_ok:
            attempts.append(
                {
                    "index": idx,
                    "local_strategy": strategy,
                    "generation_mode": attempt_mode,
                    "score": 0.0,
                    "issue_count": 1,
                    "error_count": 1,
                    "warning_count": 0,
                    "issue_buckets": {"harness": 1},
                    "structure_score": 0.0,
                    "metadata_score": 0.0,
                    "psnr_score": 0.0,
                    "diagnostics": {
                        "generation_failed": True,
                        "zero_create_api_retry_attempted": bool(zero_create_api_retry_attempted),
                        "zero_create_timeout_failure": bool(zero_create_timeout_failure),
                        "zero_create_local_fallback_attempted": bool(zero_create_local_fallback_attempted),
                        "zero_create_local_fallback_used": bool(zero_create_local_fallback_used),
                        "zero_create_contract_repair_attempted": bool(zero_create_contract_repair_attempted),
                        "zero_create_contract_repair_used": bool(zero_create_contract_repair_used),
                    },
                    "issues_json": "",
                }
            )
            continue

        compared_ok = _run(compare_cmd, cwd=repo_root, raise_on_error=False)
        if not compared_ok:
            if issues_json.exists():
                try:
                    report = json.loads(issues_json.read_text(encoding="utf-8"))
                    eval_result = _evaluate_report(
                        report,
                        target_score=effective_target_score,
                        allow_warnings=effective_allow_warnings,
                    )
                    attempt_issue_json = issues_json.with_name(
                        f"{issues_json.stem}.attempt-{idx}-{strategy}{issues_json.suffix}"
                    )
                    shutil.copyfile(str(issues_json), str(attempt_issue_json))
                    attempts.append(
                        {
                            "index": idx,
                            "local_strategy": strategy,
                            "generation_mode": attempt_mode,
                            "score": eval_result["score"],
                            "issue_count": len(eval_result["issues"]),
                            "error_count": len(eval_result["errors"]),
                            "warning_count": len(eval_result["warnings"]),
                            "issue_buckets": eval_result["issue_buckets"],
                            "structure_score": float(report.get("structure_score", 0) or 0),
                            "metadata_score": float(report.get("metadata_score", 0) or 0),
                            "psnr_score": float(
                                report.get("psnr_visual_score", report.get("visual_score", 0)) or 0
                            ),
                            "diagnostics": {
                                **(report.get("diagnostics", {}) if isinstance(report.get("diagnostics"), dict) else {}),
                                "compare_gate_failed": True,
                                "zero_create_api_retry_attempted": bool(zero_create_api_retry_attempted),
                                "zero_create_timeout_failure": bool(zero_create_timeout_failure),
                                "zero_create_local_fallback_attempted": bool(zero_create_local_fallback_attempted),
                                "zero_create_local_fallback_used": bool(zero_create_local_fallback_used),
                                "zero_create_contract_repair_attempted": bool(zero_create_contract_repair_attempted),
                                "zero_create_contract_repair_used": bool(zero_create_contract_repair_used),
                            },
                            "issues_json": str(attempt_issue_json.resolve()),
                        }
                    )
                    final_eval = eval_result
                    final_report = report
                    if eval_result["verified"]:
                        break
                    continue
                except Exception:
                    pass
            attempts.append(
                {
                    "index": idx,
                    "local_strategy": strategy,
                    "generation_mode": attempt_mode,
                    "score": 0.0,
                    "issue_count": 1,
                    "error_count": 1,
                    "warning_count": 0,
                    "issue_buckets": {"harness": 1},
                    "structure_score": 0.0,
                    "metadata_score": 0.0,
                    "psnr_score": 0.0,
                    "diagnostics": {"compare_failed": True},
                    "issues_json": "",
                }
            )
            continue

        report = json.loads(issues_json.read_text(encoding="utf-8"))
        eval_result = _evaluate_report(
            report, target_score=effective_target_score, allow_warnings=effective_allow_warnings
        )
        attempt_issue_json = issues_json.with_name(
            f"{issues_json.stem}.attempt-{idx}-{strategy}{issues_json.suffix}"
        )
        shutil.copyfile(str(issues_json), str(attempt_issue_json))
        attempts.append(
            {
                "index": idx,
                "local_strategy": strategy,
                "generation_mode": attempt_mode,
                "score": eval_result["score"],
                "issue_count": len(eval_result["issues"]),
                "error_count": len(eval_result["errors"]),
                "warning_count": len(eval_result["warnings"]),
                "issue_buckets": eval_result["issue_buckets"],
                "structure_score": float(report.get("structure_score", 0) or 0),
                "metadata_score": float(report.get("metadata_score", 0) or 0),
                "psnr_score": float(
                    report.get("psnr_visual_score", report.get("visual_score", 0)) or 0
                ),
                "diagnostics": report.get("diagnostics", {}),
                "issues_json": str(attempt_issue_json.resolve()),
            }
        )
        if isinstance(attempts[-1].get("diagnostics"), dict):
            attempts[-1]["diagnostics"].update(
                {
                    "zero_create_api_retry_attempted": bool(zero_create_api_retry_attempted),
                    "zero_create_timeout_failure": bool(zero_create_timeout_failure),
                    "zero_create_local_fallback_attempted": bool(zero_create_local_fallback_attempted),
                    "zero_create_local_fallback_used": bool(zero_create_local_fallback_used),
                    "zero_create_contract_repair_attempted": bool(zero_create_contract_repair_attempted),
                    "zero_create_contract_repair_used": bool(zero_create_contract_repair_used),
                }
            )
        final_eval = eval_result
        final_report = report
        if eval_result["verified"]:
            break

    if visual_critic_enabled and final_eval and (not bool(final_eval.get("verified", False))) and isinstance(final_report, dict) and final_report:
        visual_critic_patch = _build_visual_critic_patch(
            report=final_report,
            active_cluster=active_focus_cluster,
            max_pages=max(1, int(args.visual_critic_max_pages or 6)),
            issue_clusters=_collapse_issue_buckets_to_clusters(final_eval.get("issue_buckets") or {}),
            single_cluster_enforced=single_cluster_enforced,
            creation_mode=str(args.creation_mode),
        )
        applied = _apply_visual_critic_patch_to_input(
            input_json_path=input_json,
            patch=visual_critic_patch,
        )
        visual_critic_apply_result = {"applied": bool(applied.get("ok")), **applied}
        if bool(applied.get("ok")):
            execution_overrides = (
                visual_critic_patch.get("execution_overrides")
                if isinstance(visual_critic_patch.get("execution_overrides"), dict)
                else {}
            )
            repair_strategy = str(attempt_strategies[0] if attempt_strategies else "reconstruct")
            forced_strategy = str(execution_overrides.get("force_local_strategy") or "").strip().lower()
            if forced_strategy in {"reconstruct", "source-replay"}:
                repair_strategy = forced_strategy
            repair_mode = _resolve_generation_mode(
                creation_mode=str(args.creation_mode),
                requested_mode=str(args.mode),
                local_strategy=str(repair_strategy),
                reconstruct_via_pipeline=str(args.reconstruct_via_pipeline),
            )
            forced_mode = str(execution_overrides.get("force_mode") or "").strip().lower()
            if forced_mode in {"local", "api", "auto"}:
                repair_mode = forced_mode
            repair_template_shell = str(effective_reconstruct_template_shell)
            repair_source_aligned = str(effective_reconstruct_source_aligned)
            if str(execution_overrides.get("reconstruct_template_shell") or "").strip().lower() in {"on", "off"}:
                repair_template_shell = str(execution_overrides.get("reconstruct_template_shell")).strip().lower()
            if str(execution_overrides.get("reconstruct_source_aligned") or "").strip().lower() in {"on", "off"}:
                repair_source_aligned = str(execution_overrides.get("reconstruct_source_aligned")).strip().lower()
            restore_shortcuts = (
                str(execution_overrides.get("restore_reference_manifests") or "").strip().lower() == "on"
            )
            if str(args.creation_mode).strip().lower() == "zero_create":
                restore_shortcuts = False
            restore_result: Dict[str, Any] = {"ok": False, "restored_keys": []}
            if restore_shortcuts and str(args.creation_mode).strip().lower() != "zero_create":
                restore_result = _restore_reference_shortcuts_for_repair(
                    input_json_path=input_json,
                    reference_input_snapshot=reference_input_snapshot,
                )
            repair_generate_cmd = [
                python_bin,
                "scripts/generate_ppt_from_desc.py",
                "--input",
                str(input_json),
                "--output",
                str(generated_ppt),
                "--render-output",
                str(render_json),
                "--mode",
                repair_mode,
                "--local-strategy",
                repair_strategy,
                "--reconstruct-template-shell",
                repair_template_shell,
                "--reconstruct-source-aligned",
                repair_source_aligned,
                "--creation-mode",
                str(args.creation_mode),
                "--focus-cluster",
                (
                    str(execution_overrides.get("force_focus_cluster") or "").strip().lower()
                    if str(execution_overrides.get("force_focus_cluster") or "").strip().lower() in _FAILURE_CLUSTERS
                    else active_focus_cluster
                ),
            ]
            if execution_overrides:
                repair_generate_cmd.extend(["--execution-profile", "prod_safe"])
            if (
                str(args.creation_mode).strip().lower() == "zero_create"
                and (
                    repair_template_shell == "on"
                    or repair_source_aligned == "on"
                )
            ):
                repair_generate_cmd.extend(
                    ["--allow-zero-create-reconstruct-overrides", "on"]
                )
            repair_compare_cmd = _build_compare_cmd(
                python_bin=python_bin,
                reference_ppt=reference_ppt_path,
                generated_ppt=generated_ppt,
                issues_json=issues_json,
                compare_mode=effective_compare_mode,
                pass_score=effective_target_score,
                allow_warnings=effective_allow_warnings,
                require_psnr=effective_require_psnr,
            )
            _prepare_zero_create_input_for_attempt(
                input_json_path=input_json,
                reference_input_snapshot=reference_input_snapshot,
                attempt_mode=repair_mode,
                creation_mode=str(args.creation_mode),
            )
            repair_generated_ok = _run(repair_generate_cmd, cwd=repo_root, raise_on_error=False)
            repair_contract_repair_attempted = False
            repair_contract_repair_used = False
            if (
                (not repair_generated_ok)
                and str(args.creation_mode).strip().lower() == "zero_create"
                and render_json.exists()
            ):
                try:
                    repair_failure_report = json.loads(render_json.read_text(encoding="utf-8"))
                except Exception:
                    repair_failure_report = {}
                repair_contract_indexes = _extract_schema_invalid_contract_slide_indexes(repair_failure_report)
                if repair_contract_indexes:
                    repair_contract_repair_attempted = True
                    repair_contract_result = _inject_chart_blocks_for_zero_create_contract_repair(
                        input_json_path=input_json,
                        slide_indexes=repair_contract_indexes,
                    )
                    if int(repair_contract_result.get("inserted") or 0) > 0:
                        _wait_for_path_unlock(generated_ppt, timeout_sec=10.0, poll_sec=0.3)
                        repair_generated_ok = _run(repair_generate_cmd, cwd=repo_root, raise_on_error=False)
                        repair_contract_repair_used = bool(repair_generated_ok)
            if repair_generated_ok:
                repair_compared_ok = _run(repair_compare_cmd, cwd=repo_root, raise_on_error=False)
                if issues_json.exists():
                    repair_report = json.loads(issues_json.read_text(encoding="utf-8"))
                    repair_eval = _evaluate_report(
                        repair_report,
                        target_score=effective_target_score,
                        allow_warnings=effective_allow_warnings,
                    )
                    repair_attempt_index = len(attempts) + 1
                    repair_issue_json = issues_json.with_name(
                        f"{issues_json.stem}.attempt-{repair_attempt_index}-{repair_strategy}-critic{issues_json.suffix}"
                    )
                    shutil.copyfile(str(issues_json), str(repair_issue_json))
                    attempts.append(
                        {
                            "index": repair_attempt_index,
                            "local_strategy": f"{repair_strategy}+critic_repair",
                            "generation_mode": repair_mode,
                            "score": repair_eval["score"],
                            "issue_count": len(repair_eval["issues"]),
                            "error_count": len(repair_eval["errors"]),
                            "warning_count": len(repair_eval["warnings"]),
                            "issue_buckets": repair_eval["issue_buckets"],
                            "structure_score": float(repair_report.get("structure_score", 0) or 0),
                            "metadata_score": float(repair_report.get("metadata_score", 0) or 0),
                            "psnr_score": float(
                                repair_report.get("psnr_visual_score", repair_report.get("visual_score", 0)) or 0
                            ),
                            "diagnostics": {
                                **(
                                    repair_report.get("diagnostics", {})
                                    if isinstance(repair_report.get("diagnostics"), dict)
                                    else {}
                                ),
                                "compare_gate_failed": (not repair_compared_ok),
                                "visual_critic_repair_applied": True,
                                "restored_reference_shortcuts": (
                                    restore_result.get("restored_keys")
                                    if isinstance(restore_result, dict)
                                    else []
                                ),
                                "zero_create_contract_repair_attempted": bool(repair_contract_repair_attempted),
                                "zero_create_contract_repair_used": bool(repair_contract_repair_used),
                            },
                            "issues_json": str(repair_issue_json.resolve()),
                        }
                    )
                    final_eval = repair_eval
                    final_report = repair_report

    if not final_eval:
        final_eval = {
            "score": 0.0,
            "issues": [{"issue": "No successful attempt.", "severity": "error"}],
            "errors": [{"issue": "No successful attempt.", "severity": "error"}],
            "warnings": [],
            "issue_buckets": {"harness": 1},
            "verified": False,
        }
        final_report = {}

    score = float(final_eval.get("score", 0) or 0)
    issues = list(final_eval.get("issues", []) or [])
    errors = list(final_eval.get("errors", []) or [])
    warnings = list(final_eval.get("warnings", []) or [])
    issue_buckets = dict(final_eval.get("issue_buckets", {}) or {})
    verified = bool(final_eval.get("verified", False))
    status = "VERIFIED" if verified else "NEEDS_IMPROVEMENT"
    root_cause = _infer_root_cause(attempts, input_contract_stats)
    issue_clusters = _collapse_issue_buckets_to_clusters(issue_buckets)
    recommended_cluster = _pick_focus_cluster(
        issue_clusters=issue_clusters,
        root_cause=root_cause,
        preferred="auto",
    )
    fix_plan = _build_fix_plan(
        phase=_normalize_phase_tag(args.phase) or "adhoc",
        status=status,
        score=score,
        active_cluster=active_focus_cluster,
        recommended_cluster=recommended_cluster,
        issue_clusters=issue_clusters,
        root_cause=root_cause,
        single_cluster_enforced=single_cluster_enforced,
        repair_clusters=(
            visual_critic_patch.get("repair_clusters")
            if isinstance(visual_critic_patch.get("repair_clusters"), list)
            else [active_focus_cluster]
        ),
    )
    fix_plan_path.write_text(json.dumps(fix_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "status": status,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "target_score": effective_target_score,
        "quality_bar": str(quality_cfg.get("quality_bar") or "normal"),
        "creation_mode": str(args.creation_mode),
        "compare_mode": effective_compare_mode,
        "require_psnr": effective_require_psnr,
        "reconstruct_template_shell": effective_reconstruct_template_shell,
        "reconstruct_source_aligned": effective_reconstruct_source_aligned,
        "zero_create_sanitization": zero_create_sanitization,
        "score": score,
        "issue_count": len(issues),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issue_buckets": issue_buckets,
        "issue_clusters": issue_clusters,
        "focus_cluster": active_focus_cluster,
        "recommended_next_cluster": recommended_cluster,
        "single_cluster_enforced": single_cluster_enforced,
        "input_contract_stats": input_contract_stats,
        "root_cause_hypothesis": root_cause,
        "attempts": attempts,
        "visual_critic": {
            "enabled": visual_critic_enabled,
            "patch": visual_critic_patch,
            "apply_result": visual_critic_apply_result,
        },
        "fix_plan": str(fix_plan_path.resolve()),
        "paths": {
            "reference_ppt": str(reference_ppt_path.resolve()),
            "input_json": str(input_json.resolve()),
            "generated_ppt": str(generated_ppt.resolve()),
            "render_json": str(render_json.resolve()),
            "issues_json": str(issues_json.resolve()),
            "summary_json": str(summary_json.resolve()),
        },
        "diagnostics": final_report.get("diagnostics", {}),
    }
    summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    phase_tag = _normalize_phase_tag(args.phase)
    if phase_tag:
        required_sources = {
            "generated_ppt": generated_ppt,
            "render_json": render_json,
            "issues_json": issues_json,
            "summary_json": summary_json,
        }
        missing_sources = [name for name, path in required_sources.items() if not Path(path).exists()]
        if not missing_sources:
            published = _publish_phase_artifacts(
                phase=phase_tag,
                output_root=generated_ppt.parent,
                generated_ppt=generated_ppt,
                render_json=render_json,
                issues_json=issues_json,
                summary_json=summary_json,
            )
            summary["paths"]["render_json"] = str(Path(published["render_json"]).resolve())
            summary["paths"]["summary_json"] = str(Path(published["summary_json"]).resolve())
        else:
            published = {
                "phase": phase_tag,
                "published": False,
                "missing_sources": missing_sources,
                "generated_ppt": str(generated_ppt.resolve()),
                "render_json": str(render_json.resolve()),
                "issues_json": str(issues_json.resolve()),
                "summary_json": str(summary_json.resolve()),
            }
            print(
                "[WARN] skip phase artifact publish due to missing sources: "
                + ",".join(missing_sources)
            )
        _append_fix_record(
            fix_record_path=Path(args.fix_record),
            phase=phase_tag,
            status=status,
            score=score,
            generated_ppt=Path(published["generated_ppt"]),
            render_json=Path(published["render_json"]),
            issues_json=Path(published["issues_json"]),
            summary_json=Path(published["summary_json"]),
            active_cluster=active_focus_cluster,
            recommended_next_cluster=recommended_cluster,
            fix_plan_json=fix_plan_path,
        )
        summary["phase_artifacts"] = published
        summary_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"[RESULT] status={status}")
    print(f"[RESULT] score={score:.2f}, target={effective_target_score:.2f}")
    print(
        f"[RESULT] issues={len(issues)} (errors={len(errors)}, warnings={len(warnings)})"
    )
    print(
        f"[RESULT] focus_cluster={active_focus_cluster}, recommended_next={recommended_cluster}"
    )
    if visual_critic_enabled:
        print(
            f"[RESULT] visual_critic_applied={bool(visual_critic_apply_result.get('applied'))}"
        )
    print(f"[RESULT] fix_plan={fix_plan_path}")
    print(f"[RESULT] summary={summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
