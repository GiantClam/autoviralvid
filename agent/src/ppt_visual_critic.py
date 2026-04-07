"""Visual critic patch builder and applier for PPT retry loops."""

from __future__ import annotations

from typing import Any, Dict, List

from src.ppt_render_path_policy import allow_visual_critic_svg_fallback

def _slide_id(slide: Dict[str, Any], index: int) -> str:
    value = slide.get("slide_id") or slide.get("id") or slide.get("page_number")
    key = str(value or "").strip()
    return key or f"slide-{index + 1}"


def _collect_target_slide_ids(gate_issues: List[Any]) -> List[str]:
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


def _collect_issue_codes_by_slide(
    *,
    visual_audit: Dict[str, Any],
    gate_issues: List[Any],
    slides: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    codes_by_slide: Dict[str, List[str]] = {}
    slide_id_by_index: Dict[int, str] = {
        idx + 1: _slide_id(slide, idx)
        for idx, slide in enumerate(slides)
        if isinstance(slide, dict)
    }

    for row in visual_audit.get("slides") if isinstance(visual_audit.get("slides"), list) else []:
        if not isinstance(row, dict):
            continue
        raw_idx = int(row.get("slide") or 0)
        sid = slide_id_by_index.get(raw_idx)
        if not sid:
            continue
        local_issues = row.get("local_issues") if isinstance(row.get("local_issues"), list) else []
        mm_issues = row.get("multimodal_issues") if isinstance(row.get("multimodal_issues"), list) else []
        bucket = codes_by_slide.setdefault(sid, [])
        for item in [*local_issues, *mm_issues]:
            code = str(item or "").strip().lower()
            if code and code not in bucket:
                bucket.append(code)

    for issue in gate_issues or []:
        sid = str(getattr(issue, "slide_id", "") or "").strip()
        if not sid or sid.lower() == "deck":
            retry_ids = getattr(issue, "retry_target_ids", None)
            if isinstance(retry_ids, list):
                for raw in retry_ids:
                    rsid = str(raw or "").strip()
                    if rsid and rsid.lower() != "deck":
                        sid = rsid
                        break
        if not sid:
            continue
        code = str(getattr(issue, "code", "") or "").strip().lower()
        if not code:
            continue
        bucket = codes_by_slide.setdefault(sid, [])
        if code not in bucket:
            bucket.append(code)
    return codes_by_slide


def _derive_actions(issue_codes: List[str], slide: Dict[str, Any]) -> Dict[str, Any]:
    codes = {str(item or "").strip().lower() for item in issue_codes if str(item or "").strip()}
    actions: Dict[str, Any] = {
        "layout_grid": "",
        "render_path": "",
        "visual_patch": {},
        "semantic_constraints_patch": {},
        "compact_text": False,
        "limit_elements": 0,
        "ensure_image_block": False,
        "ensure_chart_block": False,
    }

    if {
        "visual_layout_monotony_ratio_high",
        "layout_monotony",
        "visual_whitespace_ratio_high",
        "excessive_whitespace",
        "visual_blank_area_ratio_high",
    } & codes:
        actions["layout_grid"] = "split_2"
        actions["limit_elements"] = 4

    if {
        "text_overlap",
        "text_overflow",
        "title_crowded",
        "visual_text_overlap_ratio_high",
        "visual_text_overflow_ratio_high",
        "occlusion",
    } & codes:
        actions["compact_text"] = True
        actions["visual_patch"]["text_compact_mode"] = True

    if {
        "low_contrast",
        "visual_low_contrast_ratio_high",
        "style_inconsistent",
        "visual_style_inconsistent_ratio_high",
    } & codes:
        actions["visual_patch"]["force_high_contrast"] = True
        actions["render_path"] = "svg"

    if {"irrelevant_image", "image_distortion", "visual_irrelevant_image_ratio_high"} & codes:
        actions["ensure_image_block"] = True
        actions["semantic_constraints_patch"]["media_required"] = True

    if {"chart_readability_low"} & codes:
        actions["ensure_chart_block"] = True
        actions["semantic_constraints_patch"]["chart_required"] = True

    if allow_visual_critic_svg_fallback(slide, list(codes)) and not actions["render_path"]:
        actions["render_path"] = "svg"

    return actions


def build_visual_critic_patch(
    *,
    visual_audit: Dict[str, Any],
    gate_issues: List[Any],
    slides: List[Dict[str, Any]],
    max_target_slides: int = 6,
) -> Dict[str, Any]:
    if not isinstance(visual_audit, dict) or not isinstance(slides, list) or not slides:
        return {"enabled": False, "targets": [], "summary": {"target_count": 0}}

    target_ids = _collect_target_slide_ids(gate_issues)
    if not target_ids:
        return {"enabled": False, "targets": [], "summary": {"target_count": 0}}

    issue_codes_by_slide = _collect_issue_codes_by_slide(
        visual_audit=visual_audit,
        gate_issues=gate_issues,
        slides=slides,
    )
    slide_by_id: Dict[str, Dict[str, Any]] = {
        _slide_id(slide, idx): slide
        for idx, slide in enumerate(slides)
        if isinstance(slide, dict)
    }
    target_rows: List[Dict[str, Any]] = []
    for sid in target_ids[: max(1, int(max_target_slides))]:
        codes = issue_codes_by_slide.get(sid, [])
        source_slide = slide_by_id.get(sid, {})
        actions = _derive_actions(codes, source_slide if isinstance(source_slide, dict) else {})
        target_rows.append(
            {
                "slide_id": sid,
                "issue_codes": codes,
                "actions": actions,
            }
        )

    return {
        "enabled": bool(target_rows),
        "targets": target_rows,
        "summary": {
            "target_count": len(target_rows),
            "visual_issue_count": sum(len(row.get("issue_codes") or []) for row in target_rows),
        },
    }


def _element_list_and_key(slide: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
    blocks = slide.get("blocks")
    if isinstance(blocks, list):
        return "blocks", [row for row in blocks if isinstance(row, dict)]
    elements = slide.get("elements")
    if isinstance(elements, list):
        return "elements", [row for row in elements if isinstance(row, dict)]
    return "elements", []


def _has_type(rows: List[Dict[str, Any]], target_type: str) -> bool:
    for row in rows:
        if str(row.get("type") or row.get("block_type") or "").strip().lower() == target_type:
            return True
    return False


def apply_visual_critic_patch(
    *,
    slides: List[Dict[str, Any]],
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(slides, list) or not slides:
        return {"applied": False, "updated_slide_ids": [], "updated_fields": 0, "inserted_elements": 0}
    if not isinstance(patch, dict) or not bool(patch.get("enabled")):
        return {"applied": False, "updated_slide_ids": [], "updated_fields": 0, "inserted_elements": 0}
    targets = patch.get("targets") if isinstance(patch.get("targets"), list) else []
    target_map: Dict[str, Dict[str, Any]] = {}
    for row in targets:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("slide_id") or "").strip()
        if sid:
            target_map[sid] = row
    if not target_map:
        return {"applied": False, "updated_slide_ids": [], "updated_fields": 0, "inserted_elements": 0}

    updated_slide_ids: List[str] = []
    updated_fields = 0
    inserted_elements = 0

    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        sid = _slide_id(slide, idx)
        row = target_map.get(sid)
        if not row:
            continue
        actions = row.get("actions") if isinstance(row.get("actions"), dict) else {}
        slide_changed = False

        layout_grid = str(actions.get("layout_grid") or "").strip().lower()
        if layout_grid and str(slide.get("layout_grid") or "").strip().lower() != layout_grid:
            slide["layout_grid"] = layout_grid
            updated_fields += 1
            slide_changed = True

        render_path = str(actions.get("render_path") or "").strip().lower()
        if render_path and str(slide.get("render_path") or "").strip().lower() != render_path:
            slide["render_path"] = render_path
            updated_fields += 1
            slide_changed = True

        visual_patch = actions.get("visual_patch") if isinstance(actions.get("visual_patch"), dict) else {}
        if visual_patch:
            visual = slide.get("visual")
            if not isinstance(visual, dict):
                visual = {}
                slide["visual"] = visual
            for key, value in visual_patch.items():
                if visual.get(key) != value:
                    visual[key] = value
                    updated_fields += 1
                    slide_changed = True
            visual["critic_repair"] = {"enabled": True, "issue_codes": list(row.get("issue_codes") or [])}

        semantic_patch = (
            actions.get("semantic_constraints_patch")
            if isinstance(actions.get("semantic_constraints_patch"), dict)
            else {}
        )
        if semantic_patch:
            semantic = slide.get("semantic_constraints")
            if not isinstance(semantic, dict):
                semantic = {}
                slide["semantic_constraints"] = semantic
            for key, value in semantic_patch.items():
                if semantic.get(key) != value:
                    semantic[key] = value
                    updated_fields += 1
                    slide_changed = True

        element_key, rows = _element_list_and_key(slide)
        if int(actions.get("limit_elements") or 0) > 0 and len(rows) > int(actions.get("limit_elements") or 0):
            slide[element_key] = rows[: int(actions.get("limit_elements") or 0)]
            rows = slide[element_key]
            updated_fields += 1
            slide_changed = True

        if bool(actions.get("compact_text")):
            compact_changed = False
            for row_item in rows:
                row_type = str(row_item.get("type") or row_item.get("block_type") or "").strip().lower()
                if row_type not in {"text", "title", "subtitle", "body", "list"}:
                    continue
                raw_content = str(row_item.get("content") or "")
                if len(raw_content) <= 180:
                    continue
                row_item["content"] = raw_content[:177].rstrip() + "..."
                compact_changed = True
            if compact_changed:
                updated_fields += 1
                slide_changed = True

        if bool(actions.get("ensure_image_block")) and not _has_type(rows, "image"):
            rows.append(
                {
                    "type": "image",
                    "card_id": "visual-critic-image",
                    "content": {"query": str(slide.get("title") or "business visual"), "source": "critic_patch"},
                }
            )
            slide[element_key] = rows
            inserted_elements += 1
            slide_changed = True

        if bool(actions.get("ensure_chart_block")) and not _has_type(rows, "chart"):
            rows.append(
                {
                    "type": "chart",
                    "card_id": "visual-critic-chart",
                    "content": {
                        "chart_type": "bar",
                        "series": [{"name": "A", "values": [60, 72, 85]}],
                        "categories": ["Q1", "Q2", "Q3"],
                    },
                }
            )
            slide[element_key] = rows
            inserted_elements += 1
            slide_changed = True

        if slide_changed:
            visual = slide.get("visual")
            if not isinstance(visual, dict):
                visual = {}
                slide["visual"] = visual
            prior = visual.get("critic_repair")
            critic_repair = dict(prior) if isinstance(prior, dict) else {}
            critic_repair["enabled"] = True
            critic_repair["issue_codes"] = list(row.get("issue_codes") or [])
            visual["critic_repair"] = critic_repair

        if slide_changed:
            updated_slide_ids.append(sid)

    return {
        "applied": bool(updated_slide_ids),
        "updated_slide_ids": updated_slide_ids,
        "updated_fields": updated_fields,
        "inserted_elements": inserted_elements,
        "target_count": len(target_map),
    }
