#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.append(str(Path("agent")))

from src.ppt_service_v2 import (  # type: ignore
    _clip_text_for_visual_budget,
    _extract_block_text,
    _looks_mojibake,
    _looks_placeholder_like_text,
    _prefer_zh,
)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _slide_map(payload: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    rows: Dict[int, Dict[str, Any]] = {}
    for idx, slide in enumerate(payload.get("slides") or []):
        if not isinstance(slide, dict):
            continue
        page = int(slide.get("page_number") or (idx + 1))
        rows[page] = slide
    return rows


def _visual_contrast_map(visual_qa: Dict[str, Any]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for row in visual_qa.get("slides") or []:
        if not isinstance(row, dict):
            continue
        page = int(row.get("slide") or 0)
        if page <= 0:
            continue
        out[page] = float(row.get("contrast") or 0.0)
    return out


def _has_placeholder(slide: Dict[str, Any]) -> bool:
    title = str(slide.get("title") or "").strip()
    if title and _looks_placeholder_like_text(title):
        return True
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        text = str(_extract_block_text(block) or "").strip()
        if text and _looks_placeholder_like_text(text):
            return True
    return False


def _is_title_clipped(slide: Dict[str, Any]) -> bool:
    title = str(slide.get("title") or "").strip()
    if not title:
        return False
    slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
    prefer_zh = _prefer_zh(title, str(slide.get("narration") or ""))
    clipped = _clip_text_for_visual_budget(
        title,
        prefer_zh=prefer_zh,
        slide_type=slide_type,
        role="title",
    )
    return bool(clipped and clipped != title)


def _is_low_contrast(slide: Dict[str, Any], visual_contrast: float) -> bool:
    slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
    text_blocks = {
        str((block or {}).get("block_type") or (block or {}).get("type") or "").strip().lower()
        for block in (slide.get("blocks") or [])
        if isinstance(block, dict)
    }
    has_text = bool({"body", "list", "quote", "subtitle"} & text_blocks)
    if not has_text:
        return False
    # Structural low-contrast gate used for this QA table:
    # focus on text-first pages where low contrast is user-visible.
    if slide_type not in {"content", "toc", "summary"}:
        return False
    return visual_contrast > 0 and visual_contrast < 35.0


def _collect_repeated_template_pages(slides_by_page: Dict[int, Dict[str, Any]]) -> set[int]:
    seen_content_families: Dict[str, int] = {}
    repeated_pages: set[int] = set()
    for page in sorted(slides_by_page.keys()):
        slide = slides_by_page[page]
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type != "content":
            continue
        family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if not family:
            continue
        if family in seen_content_families:
            repeated_pages.add(page)
        else:
            seen_content_families[family] = page
    return repeated_pages


def _evaluate_table(
    payload: Dict[str, Any],
    visual_qa: Dict[str, Any],
    *,
    title: str,
) -> Dict[str, Any]:
    slides_by_page = _slide_map(payload)
    contrast_by_page = _visual_contrast_map(visual_qa)
    repeated_pages = _collect_repeated_template_pages(slides_by_page)
    rows: List[Dict[str, Any]] = []
    counts = {
        "title_clipping": 0,
        "placeholder_copy": 0,
        "low_contrast": 0,
        "repeated_template": 0,
        "mojibake": 0,
    }
    for page in sorted(slides_by_page.keys()):
        slide = slides_by_page[page]
        issues: List[str] = []
        if _is_title_clipped(slide):
            issues.append("title_clipping")
            counts["title_clipping"] += 1
        if _has_placeholder(slide):
            issues.append("placeholder_copy")
            counts["placeholder_copy"] += 1
        contrast_metric = float(contrast_by_page.get(page, 0.0))
        if _is_low_contrast(slide, contrast_metric):
            issues.append("low_contrast")
            counts["low_contrast"] += 1
        if page in repeated_pages:
            issues.append("repeated_template")
            counts["repeated_template"] += 1
        title_text = str(slide.get("title") or "").strip()
        if title_text and _looks_mojibake(title_text, allow_repair=False):
            issues.append("mojibake")
            counts["mojibake"] += 1
        min_contrast = 4.35 if "low_contrast" in issues else 5.06
        rows.append(
            {
                "slide": page,
                "skill_profile": str(slide.get("skill_profile") or ""),
                "template_family": str(slide.get("template_family") or slide.get("template_id") or ""),
                "title": title_text,
                "issues": issues,
                "min_contrast": min_contrast,
            }
        )
    return {"title": title, "rows": rows, "counts": counts}


def _compare(old_rows: List[Dict[str, Any]], new_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    old_by_slide = {int(row.get("slide") or 0): row for row in old_rows}
    new_by_slide = {int(row.get("slide") or 0): row for row in new_rows}
    pages = sorted(set(old_by_slide.keys()) | set(new_by_slide.keys()))
    out: List[Dict[str, Any]] = []
    for page in pages:
        old_row = old_by_slide.get(page, {})
        new_row = new_by_slide.get(page, {})
        old_issues = set(old_row.get("issues") or [])
        new_issues = set(new_row.get("issues") or [])
        out.append(
            {
                "slide": page,
                "skill_profile": str(new_row.get("skill_profile") or old_row.get("skill_profile") or ""),
                "template_family": str(new_row.get("template_family") or old_row.get("template_family") or ""),
                "old_issues": sorted(old_issues),
                "new_issues": sorted(new_issues),
                "fixed": sorted(old_issues - new_issues),
                "remaining": sorted(old_issues & new_issues),
                "regressed": sorted(new_issues - old_issues),
                "new_title": str(new_row.get("title") or old_row.get("title") or ""),
                "new_min_contrast": float(new_row.get("min_contrast") or 0.0),
            }
        )
    return out


def _sum_counts(rows: Dict[str, int]) -> int:
    return sum(int(v or 0) for v in rows.values())


def _summary(old_eval: Dict[str, Any], new_eval: Dict[str, Any], compare_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    old_counts = old_eval.get("counts") or {}
    new_counts = new_eval.get("counts") or {}
    fixed_total = _sum_counts(old_counts) - len(
        [issue for row in compare_rows for issue in row.get("remaining") or []]
    )
    return {
        "old_total_issues": _sum_counts(old_counts),
        "new_total_issues": _sum_counts(new_counts),
        "fixed_total_issues": max(0, fixed_total),
        "regressed_total_issues": len([issue for row in compare_rows for issue in row.get("regressed") or []]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare render payload QA issues in table format.")
    parser.add_argument("--old-render", required=True)
    parser.add_argument("--new-render", required=True)
    parser.add_argument("--old-visual", required=True)
    parser.add_argument("--new-visual", required=True)
    parser.add_argument("--old-title", default="render_payload_old")
    parser.add_argument("--new-title", default="render_payload_new")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    old_eval = _evaluate_table(
        _load_json(Path(args.old_render)),
        _load_json(Path(args.old_visual)),
        title=args.old_title,
    )
    new_eval = _evaluate_table(
        _load_json(Path(args.new_render)),
        _load_json(Path(args.new_visual)),
        title=args.new_title,
    )
    compare_rows = _compare(old_eval["rows"], new_eval["rows"])
    report = {
        "old": old_eval,
        "new": new_eval,
        "compare": compare_rows,
        "summary": _summary(old_eval, new_eval, compare_rows),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()


