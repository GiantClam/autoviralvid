#!/usr/bin/env python
"""Visual QA from export_result video_slides with native-PPT rasterization.

Preferred path:
1) Native PPTX rasterization (PowerPoint COM / soffice) via `src.pptx_rasterizer`
2) Fallback to Marp preview screenshots when native rasterization is unavailable

The inspection rules remain identical across both paths.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_slide_type(slide: Dict[str, Any]) -> str:
    return str(slide.get("slide_type") or "content").strip().lower() or "content"


def _layout_token(slide: Dict[str, Any]) -> str:
    for key in ("layout_grid", "layout", "subtype", "layout_type"):
        value = str(slide.get(key) or "").strip().lower()
        if value:
            return value
    return ""


def _safe_markdown(slide: Dict[str, Any]) -> str:
    return str(slide.get("markdown") or "").strip()


def _blocks_to_markdown(blocks: List[Dict[str, Any]], title: str) -> str:
    lines = [f"# {title}"]
    title_key = _normalize_text_key(title)
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = str(block.get("content") or "").strip()
        if not text:
            continue
        if title_key and _normalize_text_key(text) == title_key:
            continue
        lines.append(f"- {text}")
    return "\n".join(lines).strip()


def _coerce_video_slides(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct = payload.get("video_slides")
    if isinstance(direct, list) and direct:
        return [item for item in direct if isinstance(item, dict)]

    render_slides = payload.get("slides")
    if isinstance(render_slides, list) and render_slides:
        has_markdown = any(
            isinstance(item, dict) and str(item.get("markdown") or "").strip()
            for item in render_slides
        )
        if has_markdown:
            return [item for item in render_slides if isinstance(item, dict)]

    official = payload.get("official_input") if isinstance(payload.get("official_input"), dict) else {}
    source_slides = official.get("slides") if isinstance(official.get("slides"), list) else []
    if not source_slides:
        return []

    default_family = str(payload.get("template_family") or "").strip()
    default_svg_mode = str(payload.get("svg_mode") or "").strip().lower()
    converted: List[Dict[str, Any]] = []
    for idx, slide in enumerate(source_slides):
        if not isinstance(slide, dict):
            continue
        title = str(slide.get("title") or f"Slide {idx + 1}").strip()
        blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
        converted.append(
            {
                "slide_id": str(slide.get("slide_id") or f"slide-{idx + 1}"),
                "title": title,
                "slide_type": str(slide.get("page_type") or "content"),
                "template_family": default_family,
                "svg_mode": default_svg_mode,
                "markdown": _blocks_to_markdown(blocks, title),
            }
        )
    return converted


def _sidecar_slides(export_result_path: Path) -> List[Dict[str, Any]]:
    candidate = export_result_path.parent / "slides.json"
    if not candidate.exists():
        return []
    data = _load_json(candidate)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _extract_script_text(slide: Dict[str, Any]) -> str:
    script = slide.get("script")
    if isinstance(script, list):
        parts: List[str] = []
        for item in script:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return " ".join(parts).strip()
    if isinstance(script, dict):
        return str(script.get("text") or "").strip()
    return ""


def _guess_slide_type(*, title: str, index: int, total: int) -> str:
    if index == 0:
        return "cover"
    if index == total - 1:
        return "summary"
    text = str(title or "").lower()
    if any(token in text for token in ("时间", "里程碑", "路线图", "roadmap", "timeline", "阶段")):
        return "timeline"
    if any(token in text for token in ("目录", "agenda", "toc")):
        return "toc"
    return "content"


def _merge_sidecar_metadata(
    *,
    export_result_path: Path,
    payload: Dict[str, Any],
    video_slides: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    sidecar = _sidecar_slides(export_result_path)
    final_contract = payload.get("final_slide_contract")
    if not isinstance(final_contract, list):
        final_contract = []
    deck_svg_mode = str(
        (payload.get("generator_meta") or {}).get("svg_mode")
        or payload.get("svg_mode")
        or ""
    ).strip().lower()
    merged: List[Dict[str, Any]] = []
    total = len(video_slides)
    for idx, item in enumerate(video_slides):
        row = dict(item)
        src = sidecar[idx] if idx < len(sidecar) else {}
        contract_row = final_contract[idx] if idx < len(final_contract) and isinstance(final_contract[idx], dict) else {}
        if isinstance(contract_row, dict):
            if not str(row.get("slide_id") or "").strip():
                row["slide_id"] = str(contract_row.get("slide_id") or f"slide-{idx + 1}")
            if not str(row.get("slide_type") or "").strip():
                row["slide_type"] = str(contract_row.get("slide_type") or "").strip().lower()
            if not str(row.get("layout_grid") or "").strip():
                row["layout_grid"] = str(contract_row.get("layout_grid") or "").strip().lower()
            if not str(row.get("template_family") or "").strip():
                row["template_family"] = str(contract_row.get("template_family") or "").strip().lower()
        if isinstance(src, dict):
            title = str(row.get("title") or src.get("title") or f"Slide {idx + 1}").strip()
            if title:
                row["title"] = title
            if not str(row.get("markdown") or "").strip():
                blocks = src.get("blocks") if isinstance(src.get("blocks"), list) else []
                if blocks:
                    row["markdown"] = _blocks_to_markdown(blocks, title or f"Slide {idx + 1}")
                else:
                    text_lines: List[str] = []
                    for el in src.get("elements") if isinstance(src.get("elements"), list) else []:
                        if not isinstance(el, dict):
                            continue
                        if str(el.get("type") or "").strip().lower() != "text":
                            continue
                        content = str(el.get("content") or "").strip()
                        if content:
                            text_lines.append(content)
                    title_key = _normalize_text_key(title)
                    if title_key:
                        text_lines = [
                            line for line in text_lines if _normalize_text_key(line) != title_key
                        ]
                    if text_lines:
                        row["markdown"] = f"# {title}\n" + "\n".join(f"- {line}" for line in text_lines[:8])
            if not str(row.get("slide_type") or "").strip():
                row["slide_type"] = _guess_slide_type(title=title, index=idx, total=total)
            if not str(row.get("layout_grid") or "").strip():
                layout_grid = str(src.get("layout_grid") or src.get("layout") or "").strip().lower()
                if layout_grid:
                    row["layout_grid"] = layout_grid
            if not _extract_script_text(row):
                narration = str(src.get("narration") or src.get("speaker_notes") or "").strip()
                if narration:
                    row["script"] = [{"role": "host", "text": narration}]
        if deck_svg_mode and not str(row.get("svg_mode") or "").strip():
            row["svg_mode"] = deck_svg_mode
        merged.append(row)
    return merged


def _build_preview_markdown(video_slides: List[Dict[str, Any]]) -> str:
    frontmatter = "---\nmarp: true\ntheme: default\npaginate: true\nsize: 16:9\n---\n\n"
    pages: List[str] = []
    for idx, slide in enumerate(video_slides):
        markdown = _safe_markdown(slide)
        if not markdown:
            title = str(slide.get("title") or slide.get("slide_id") or f"Slide {idx + 1}").strip()
            markdown = f"# {title}"
        pages.append(markdown)
    return frontmatter + "\n\n---\n\n".join(pages) + "\n"


def _run_marp_images(markdown_path: Path, output_png_path: Path) -> None:
    npx_bin = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
    cmd = [
        npx_bin,
        "@marp-team/marp-cli@latest",
        str(markdown_path),
        "--images",
        "png",
        "--output",
        str(output_png_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _resolve_pptx_path(export_result_path: Path, explicit_path: str) -> Path | None:
    if str(explicit_path or "").strip():
        candidate = Path(explicit_path).expanduser().resolve()
        return candidate if candidate.exists() else None
    sibling_default = export_result_path.parent / "lingchuang_ppt.pptx"
    if sibling_default.exists():
        return sibling_default.resolve()
    all_pptx = sorted(export_result_path.parent.glob("*.pptx"))
    if all_pptx:
        return all_pptx[0].resolve()
    return None


def _native_rasterize_images(*, pptx_path: Path, output_dir: Path) -> Dict[str, Any]:
    try:
        from src.pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes
    except Exception as exc:
        return {"ok": False, "error": f"rasterizer_import_failed: {exc}", "images": []}

    try:
        pptx_bytes = pptx_path.read_bytes()
    except Exception as exc:
        return {"ok": False, "error": f"pptx_read_failed: {exc}", "images": []}

    png_bytes_list = rasterize_pptx_bytes_to_png_bytes(pptx_bytes)
    if not png_bytes_list:
        return {"ok": False, "error": "native_rasterization_no_output", "images": []}

    native_dir = output_dir / "native_slides"
    native_dir.mkdir(parents=True, exist_ok=True)
    image_paths: List[Path] = []
    for idx, data in enumerate(png_bytes_list):
        path = native_dir / f"slide_{idx + 1:03d}.png"
        try:
            path.write_bytes(data)
            image_paths.append(path)
        except Exception:
            continue
    if not image_paths:
        return {"ok": False, "error": "native_rasterization_write_failed", "images": []}
    return {"ok": True, "error": "", "images": image_paths}


def _image_metrics(image_path: Path) -> Dict[str, float]:
    try:
        from PIL import Image, ImageStat  # type: ignore
    except Exception:
        return {"mean_luminance": 128.0, "contrast": 24.0}
    try:
        image = Image.open(image_path).convert("L")
        stat = ImageStat.Stat(image)
        return {
            "mean_luminance": float(stat.mean[0]) if stat.mean else 128.0,
            "contrast": float(stat.stddev[0]) if stat.stddev else 0.0,
        }
    except Exception:
        return {"mean_luminance": 128.0, "contrast": 24.0}


def _normalize_text_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _title_multi(slide: Dict[str, Any]) -> bool:
    markdown = _safe_markdown(slide).lower()
    title = str(slide.get("title") or "").strip()
    if not markdown or not title:
        return False
    key = _normalize_text_key(title)
    if not key:
        return False
    return markdown.count(title.lower()) >= 3


def _copy_not_expanded(slide: Dict[str, Any]) -> bool:
    markdown = _safe_markdown(slide)
    script_text = _extract_script_text(slide)
    title_text = str(slide.get("title") or "").strip()
    st = _safe_slide_type(slide)
    if st in {"cover", "summary", "toc", "divider"}:
        return False
    merged_text = " ".join(part for part in [title_text, markdown, script_text] if part).strip()
    lowered = merged_text.lower()
    placeholder_tokens = ["supporting point", "supporting argument", "todo", "tbd", "placeholder", "tbc"]
    if any(token in lowered for token in placeholder_tokens):
        return True
    bullets = len(re.findall(r"^\s*(?:[-*]|\d+[.)])\s+", markdown, flags=re.MULTILINE))
    if len(merged_text) >= 140:
        return False
    return bullets <= 1 and len(merged_text) < 70


def _overflow_risk(slide: Dict[str, Any]) -> bool:
    markdown = _safe_markdown(slide)
    bullets = len(re.findall(r"^\s*(?:[-*]|\d+[.)])\s+", markdown, flags=re.MULTILINE))
    return bullets >= 10 or len(markdown) >= 950


def _issues_for_slide(
    *,
    slide: Dict[str, Any],
    prev_layout: str,
    same_layout_run: int,
    metrics: Dict[str, float],
) -> List[str]:
    issues: List[str] = []
    st = _safe_slide_type(slide)
    layout = _layout_token(slide)
    contrast = float(metrics.get("contrast") or 0.0)
    if contrast < 18.0:
        issues.append("low_contrast")
    if _copy_not_expanded(slide):
        issues.append("copy_not_expanded")
    if _title_multi(slide):
        issues.append("title_multi")
    if _overflow_risk(slide):
        issues.append("text_overflow_risk")
    if (
        st not in {"cover", "summary", "toc", "divider"}
        and layout
        and prev_layout
        and prev_layout == layout
        and same_layout_run >= 3
    ):
        issues.append("layout_monotony")
    svg_raw = str(slide.get("svg_mode") or "").strip().lower()
    if st not in {"cover", "summary"} and svg_raw and svg_raw != "on":
        issues.append("svg_missing")
    return issues


_FIX_MAP = {
    "low_contrast": "Increase text/background contrast to at least WCAG AA (4.5:1).",
    "copy_not_expanded": "Expand short copy into claim-evidence-action structure with concrete facts.",
    "title_multi": "Keep one primary title and move duplicates into subtitle or bullets.",
    "text_overflow_risk": "Reduce per-slide text density or split into continuation pages.",
    "layout_monotony": "Switch to a different layout pattern on adjacent slides.",
    "svg_missing": "Add one SVG process/architecture visual for structural clarity.",
    "raster_missing": "Ensure PPT native rasterization exports one image per slide.",
}


def _deck_summary(video_slides: List[Dict[str, Any]]) -> Dict[str, Any]:
    types = [_layout_token(item) or _safe_slide_type(item) for item in video_slides]
    has_real_layout = any(bool(_layout_token(item)) for item in video_slides)
    families = [str(item.get("template_family") or "unknown").strip().lower() for item in video_slides]
    counts = Counter(types)
    family_counts = Counter(families)
    switches = 0
    for i in range(1, len(families)):
        if families[i] != families[i - 1]:
            switches += 1
    switch_ratio = (switches / max(1, len(families) - 1)) if families else 0.0

    issues: List[str] = []
    if counts and has_real_layout:
        top_ratio = counts.most_common(1)[0][1] / max(1, len(types))
        if top_ratio > 0.45:
            issues.append("layout_homogeneous")
    if len(family_counts) >= 8 or switch_ratio > 0.85:
        issues.append("style_inconsistent")

    return {
        "issues": issues,
        "layout_types": dict(sorted(counts.items(), key=lambda kv: kv[0])),
        "template_families": dict(sorted(family_counts.items(), key=lambda kv: kv[0])),
        "family_switch_ratio": switch_ratio,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-result", required=True)
    parser.add_argument("--mode", choices=["auto", "native", "preview"], default="auto")
    parser.add_argument("--pptx-path", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--output-file", default="visual_review_report.json")
    args = parser.parse_args()

    export_result_path = Path(args.export_result).resolve()
    payload = _load_json(export_result_path)
    video_slides = _merge_sidecar_metadata(
        export_result_path=export_result_path,
        payload=payload,
        video_slides=_coerce_video_slides(payload),
    )
    if not video_slides:
        print(json.dumps({"ok": False, "error": "video_slides/official_input.slides missing"}, ensure_ascii=False))
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if str(args.output_dir).strip()
        else export_result_path.parent / "visual_review"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = str(args.mode or "auto").strip().lower()
    chosen_source = "marp_preview_screenshot_audit"
    warning = ""
    raster_error = ""
    png_paths: List[Path] = []

    if mode in {"auto", "native"}:
        pptx_path = _resolve_pptx_path(export_result_path, str(args.pptx_path or ""))
        if pptx_path and pptx_path.exists():
            native = _native_rasterize_images(pptx_path=pptx_path, output_dir=output_dir)
            if native.get("ok"):
                png_paths = list(native.get("images") or [])
                chosen_source = "native_pptx_rasterization_audit"
            else:
                raster_error = str(native.get("error") or "native_rasterization_failed")
        else:
            raster_error = "pptx_not_found_for_native_rasterization"

        if mode == "native" and not png_paths:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": raster_error or "native_rasterization_failed",
                        "source": "native_pptx_rasterization_audit",
                    },
                    ensure_ascii=False,
                )
            )
            return 3

    if not png_paths:
        markdown_path = output_dir / "preview.marp.md"
        markdown_path.write_text(_build_preview_markdown(video_slides), encoding="utf-8")
        preview_prefix = output_dir / "preview.png"
        _run_marp_images(markdown_path, preview_prefix)
        png_paths = sorted(output_dir.glob("preview.*.png"))
        chosen_source = "marp_preview_screenshot_audit"
        warning = "Fallback to preview screenshots; native PPT rasterization unavailable."
        if raster_error:
            warning = f"{warning} reason={raster_error}"

    slide_rows: List[Dict[str, Any]] = []
    prev_layout = ""
    same_layout_run = 0
    for idx, slide in enumerate(video_slides):
        st = _safe_slide_type(slide)
        layout = _layout_token(slide)
        if layout and layout == prev_layout:
            same_layout_run += 1
        else:
            same_layout_run = 1
        has_image = idx < len(png_paths)
        metrics = _image_metrics(png_paths[idx]) if has_image else {"mean_luminance": 128.0, "contrast": 24.0}
        issues = _issues_for_slide(
            slide=slide,
            prev_layout=prev_layout,
            same_layout_run=same_layout_run,
            metrics=metrics,
        )
        if not has_image:
            issues.append("raster_missing")
        if layout:
            prev_layout = layout
        slide_rows.append(
            {
                "slide": idx + 1,
                "slide_id": str(slide.get("slide_id") or f"slide-{idx + 1}"),
                "slide_type": st,
                "layout_grid": layout,
                "template_family": str(slide.get("template_family") or ""),
                "image_file": str(png_paths[idx]) if has_image else "",
                "metrics": metrics,
                "issues": issues,
                "fixes": [_FIX_MAP[code] for code in issues if code in _FIX_MAP],
            }
        )

    has_slide_issues = any(bool(item.get("issues")) for item in slide_rows)
    deck_summary = _deck_summary(video_slides)
    report = {
        "ok": (not has_slide_issues) and (not bool(deck_summary.get("issues"))),
        "source": chosen_source,
        "warning": warning,
        "slide_count": len(video_slides),
        "rasterized_slide_count": len(png_paths),
        "rasterization_mode": mode,
        "slides": slide_rows,
        "deck": deck_summary,
    }
    output_path = output_dir / str(args.output_file)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": bool(report.get("ok")), "report": str(output_path)}, ensure_ascii=False))
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
