"""Post-render visual QA for PPT exports."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from typing import Any, Dict, List


def _clamp_100(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _normalize_issue_code(value: str) -> str:
    code = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "title_multi": "multi_title_bar",
        "multi_title": "multi_title_bar",
        "title_overlap": "title_crowded",
        "overlay": "occlusion",
        "image_mismatch": "irrelevant_image",
        "image_irrelevant": "irrelevant_image",
        "layout_repetitive": "layout_monotony",
        "blank_space_high": "excessive_whitespace",
        "card_collision": "card_overlap",
    }
    return aliases.get(code, code)


_MM_ALLOWED_ISSUES = {
    "occlusion",
    "text_overlap",
    "card_overlap",
    "low_contrast",
    "multi_title_bar",
    "title_crowded",
    "text_overflow",
    "irrelevant_image",
    "image_distortion",
    "layout_monotony",
    "style_inconsistent",
    "excessive_whitespace",
}

_TEXT_PLACEHOLDER_RE = re.compile(
    r"(?:\b(?:xxxx|lorem|ipsum|placeholder|todo|tbd)\b|[?？]{3,}|待补充|请填写|占位符)",
    re.IGNORECASE,
)
_TEXT_MATCH_SPLIT_RE = re.compile(r"[;；,\n，。.!?、:：]+")


def extract_text_with_markitdown(
    pptx_bytes: bytes,
    *,
    timeout_sec: int = 25,
) -> Dict[str, Any]:
    if not isinstance(pptx_bytes, (bytes, bytearray)) or not pptx_bytes:
        return {
            "enabled": False,
            "ok": False,
            "error": "empty_pptx_bytes",
            "text": "",
            "text_length": 0,
        }
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as fp:
            fp.write(bytes(pptx_bytes))
            temp_path = fp.name
        proc = subprocess.run(
            [sys.executable, "-m", "markitdown", temp_path],
            capture_output=True,
            text=True,
            timeout=max(5, int(timeout_sec)),
        )
        text = str(proc.stdout or "").strip()
        if proc.returncode != 0:
            detail = str(proc.stderr or proc.stdout or "").strip()
            return {
                "enabled": True,
                "ok": False,
                "error": detail[:280] or f"markitdown_exit_{proc.returncode}",
                "text": "",
                "text_length": 0,
            }
        return {
            "enabled": True,
            "ok": True,
            "error": "",
            "text": text,
            "text_length": len(text),
        }
    except FileNotFoundError as exc:
        return {
            "enabled": True,
            "ok": False,
            "error": f"markitdown_not_found: {exc}",
            "text": "",
            "text_length": 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "enabled": True,
            "ok": False,
            "error": f"markitdown_timeout: {exc}",
            "text": "",
            "text_length": 0,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "error": f"markitdown_failed: {exc}",
            "text": "",
            "text_length": 0,
        }
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                pass


def summarize_markitdown_text(markdown_text: str) -> Dict[str, Any]:
    text = str(markdown_text or "")
    lines = [str(line).strip() for line in text.splitlines() if str(line).strip()]
    placeholder_hits = len(_TEXT_PLACEHOLDER_RE.findall(text))
    lines_with_placeholder = sum(1 for line in lines if _TEXT_PLACEHOLDER_RE.search(line))
    placeholder_ratio = float(lines_with_placeholder) / float(max(1, len(lines)))
    issue_codes: List[str] = []
    if not text.strip():
        issue_codes.append("markitdown_empty_output")
    if placeholder_hits > 0:
        issue_codes.append("markitdown_placeholder_text")
    return {
        "line_count": len(lines),
        "text_length": len(text.strip()),
        "placeholder_hits": int(placeholder_hits),
        "placeholder_ratio": placeholder_ratio,
        "issue_codes": issue_codes,
    }


def run_markitdown_text_qa(
    pptx_bytes: bytes,
    *,
    timeout_sec: int = 25,
) -> Dict[str, Any]:
    extracted = extract_text_with_markitdown(pptx_bytes, timeout_sec=timeout_sec)
    if not bool(extracted.get("ok")):
        return {
            "enabled": bool(extracted.get("enabled")),
            "ok": False,
            "error": str(extracted.get("error") or "markitdown_failed"),
            "issue_codes": ["markitdown_extraction_failed"],
        }
    summary = summarize_markitdown_text(str(extracted.get("text") or ""))
    return {
        "enabled": bool(extracted.get("enabled")),
        "ok": True,
        "error": "",
        **summary,
    }


def _analyze_png_local(png_bytes: bytes) -> Dict[str, float | List[float]]:
    try:
        from io import BytesIO

        from PIL import Image, ImageFilter, ImageStat  # type: ignore
    except Exception:
        return {
            "mean_luminance": 128.0,
            "contrast": 24.0,
            "blank_like": 0.0,
            "edge_density": 0.08,
            "signature": [0.0] * 12,
        }
    try:
        image_rgb = Image.open(BytesIO(png_bytes)).convert("RGB")
        gray = image_rgb.convert("L")
        stat = ImageStat.Stat(gray)
        mean_luminance = float(stat.mean[0]) if stat.mean else 128.0
        contrast = float(stat.stddev[0]) if stat.stddev else 0.0
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        edge_density = float(edge_stat.mean[0] or 0.0) / 255.0
        blank_like = 1.0 if contrast <= 2.5 and edge_density <= 0.02 else 0.0

        thumb = image_rgb.resize((24, 12))
        bins = [0.0] * 12
        raw_pixels = thumb.tobytes()
        for idx in range(0, len(raw_pixels), 3):
            r = raw_pixels[idx]
            g = raw_pixels[idx + 1]
            b = raw_pixels[idx + 2]
            section = int(max(r, g, b) / 86)
            section = min(max(section, 0), 2)
            channel = 0 if r >= g and r >= b else (1 if g >= r and g >= b else 2)
            bins[(section * 4) + channel] += 1.0
        total = float(sum(bins) or 1.0)
        signature = [value / total for value in bins]
        return {
            "mean_luminance": mean_luminance,
            "contrast": contrast,
            "blank_like": blank_like,
            "edge_density": edge_density,
            "signature": signature,
        }
    except Exception:
        return {
            "mean_luminance": 128.0,
            "contrast": 24.0,
            "blank_like": 0.0,
            "edge_density": 0.08,
            "signature": [0.0] * 12,
        }


def _signature_distance(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    return math.sqrt(sum((float(a[idx]) - float(b[idx])) ** 2 for idx in range(size)))


def _local_slide_issue_codes(metrics: Dict[str, float | List[float]]) -> List[str]:
    issues: List[str] = []
    contrast = float(metrics.get("contrast") or 0.0)
    edge_density = float(metrics.get("edge_density") or 0.0)
    if contrast < 16.0:
        issues.append("low_contrast")
    if edge_density < 0.02:
        issues.append("excessive_whitespace")
    return issues


async def _multimodal_slide_audit(
    *,
    png_bytes: bytes,
    deck_title: str,
    model: str,
    slide_index: int,
    slide_count: int,
) -> Dict[str, Any]:
    from src.openrouter_client import OpenRouterClient

    content_parts: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "You are reviewing ONE business PPT slide. Return strict JSON only with keys: "
                "score(0-100), issues(string[]), summary(string). "
                "Allowed issue codes only: occlusion,text_overlap,card_overlap,low_contrast,"
                "multi_title_bar,title_crowded,text_overflow,irrelevant_image,image_distortion,"
                "layout_monotony,style_inconsistent,excessive_whitespace. "
                f"Deck title: {deck_title or 'Untitled'}. "
                f"Slide position: {slide_index + 1}/{slide_count}."
            ),
        }
    ]
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    content_parts.append({"type": "image_url", "image_url": {"url": data_uri}})
    client = OpenRouterClient()
    raw = await client.chat_completions(
        model=model,
        messages=[
            {"role": "system", "content": "You are a strict visual QA reviewer for commercial PPT slides."},
            {"role": "user", "content": content_parts},
        ],
        temperature=0.0,
        max_tokens=260,
        response_format={"type": "json_object"},
    )
    text = str(raw or "").strip()
    if not text:
        return {"score": 0.0, "issues": [], "summary": "empty_multimodal_response", "error": True}
    try:
        parsed = json.loads(text)
    except Exception:
        return {"score": 0.0, "issues": [], "summary": "invalid_multimodal_json", "error": True}

    score = _clamp_100(float(parsed.get("score") or 0.0))
    raw_issues = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    issues = []
    for item in raw_issues:
        code = _normalize_issue_code(str(item or ""))
        if code in _MM_ALLOWED_ISSUES:
            issues.append(code)
    summary = str(parsed.get("summary") or "").strip()
    return {"score": score, "issues": issues, "summary": summary, "error": False}


def _sample_indices(slide_count: int, limit: int) -> List[int]:
    if slide_count <= 0 or limit <= 0:
        return []
    if limit >= slide_count:
        return list(range(slide_count))
    if limit == 1:
        return [0]
    picked = set()
    out: List[int] = []
    for i in range(limit):
        idx = round(i * (slide_count - 1) / (limit - 1))
        if idx in picked:
            continue
        picked.add(idx)
        out.append(int(idx))
    return sorted(out)


async def _multimodal_audit(
    *,
    png_bytes_list: List[bytes],
    deck_title: str,
    model: str,
    route_mode: str,
) -> Dict[str, Any]:
    try:
        from src.openrouter_client import OpenRouterClient
    except Exception as exc:
        return {"enabled": False, "error": f"openrouter_client_unavailable: {exc}"}
    if not os.getenv("OPENROUTER_API_KEY") and not os.getenv("LLM_API_KEY"):
        return {"enabled": False, "error": "openrouter_key_missing"}

    slide_count = len(png_bytes_list)
    default_max = slide_count if str(route_mode or "").strip().lower() == "refine" else min(slide_count, 8)
    max_mm_slides = max(
        1,
        min(
            slide_count,
            int(os.getenv("PPT_VISUAL_QA_MAX_MM_SLIDES", str(default_max))),
        ),
    )
    sampled_indexes = _sample_indices(slide_count, max_mm_slides)
    if not sampled_indexes:
        return {"enabled": False, "error": "no_slide_images"}

    try:
        OpenRouterClient()
    except Exception as exc:
        return {"enabled": False, "error": f"openrouter_client_init_failed: {exc}"}

    semaphore = asyncio.Semaphore(3)

    async def _review(index: int) -> Dict[str, Any]:
        async with semaphore:
            return await _multimodal_slide_audit(
                png_bytes=png_bytes_list[index],
                deck_title=deck_title,
                model=model,
                slide_index=index,
                slide_count=slide_count,
            )

    audits = await asyncio.gather(*(_review(idx) for idx in sampled_indexes), return_exceptions=True)
    rows: List[Dict[str, Any]] = []
    issue_counter: Counter[str] = Counter()
    score_values: List[float] = []
    for mapped_idx, item in zip(sampled_indexes, audits):
        if isinstance(item, Exception):
            rows.append(
                {
                    "slide": mapped_idx + 1,
                    "score": 0.0,
                    "issues": [],
                    "summary": str(item)[:180],
                    "error": True,
                }
            )
            continue
        score_values.append(float(item.get("score") or 0.0))
        issues = [str(code) for code in (item.get("issues") or []) if str(code)]
        issue_counter.update(issues)
        rows.append(
            {
                "slide": mapped_idx + 1,
                "score": float(item.get("score") or 0.0),
                "issues": issues,
                "summary": str(item.get("summary") or ""),
                "error": bool(item.get("error")),
            }
        )
    ratio_den = float(max(1, len(sampled_indexes)))
    issue_ratios = {code: float(count) / ratio_den for code, count in issue_counter.items()}
    mean_score = _clamp_100(sum(score_values) / max(1, len(score_values)))
    return {
        "enabled": True,
        "score": mean_score,
        "issues": sorted(issue_counter.keys()),
        "issue_counts": dict(issue_counter),
        "issue_ratios": issue_ratios,
        "slides": rows,
        "sampled_slide_indexes": sampled_indexes,
        "sampled_slide_count": len(sampled_indexes),
    }


def _collect_text_fields_from_obj(value: Any, out: List[str], *, depth: int = 0) -> None:
    if depth > 3:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            out.append(text)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_fields_from_obj(item, out, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key in (
            "title",
            "subtitle",
            "content",
            "text",
            "body",
            "label",
            "description",
            "narration",
            "speaker_notes",
        ):
            if key in value:
                _collect_text_fields_from_obj(value.get(key), out, depth=depth + 1)
        return


def _extract_slide_title(slide: Dict[str, Any]) -> str:
    title = str(slide.get("title") or "").strip()
    if title:
        return title
    for block_key in ("blocks", "elements"):
        raw = slide.get(block_key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            block_type = str(item.get("block_type") or item.get("type") or "").strip().lower()
            if block_type != "title":
                continue
            text_parts: List[str] = []
            _collect_text_fields_from_obj(item.get("content"), text_parts)
            if text_parts:
                return str(text_parts[0]).strip()
    return ""


def _extract_slide_body_text(slide: Dict[str, Any]) -> str:
    chunks: List[str] = []
    for key in ("narration", "speaker_notes"):
        value = str(slide.get(key) or "").strip()
        if value:
            chunks.append(value)
    for block_key in ("elements", "blocks"):
        raw = slide.get(block_key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            block_type = str(item.get("block_type") or item.get("type") or "").strip().lower()
            if block_type == "title":
                continue
            _collect_text_fields_from_obj(item, chunks)
    return "\n".join(chunks).strip()


def _normalize_text_match_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _contains_text_evidence(haystack: str, needle: str) -> bool:
    haystack_key = _normalize_text_match_key(haystack)
    needle_key = _normalize_text_match_key(needle)
    if not haystack_key or not needle_key:
        return False
    if needle_key in haystack_key:
        return True
    for token in _TEXT_MATCH_SPLIT_RE.split(str(needle or "")):
        part = _normalize_text_match_key(token)
        if len(part) >= 4 and part in haystack_key:
            return True
    return False


def audit_textual_slides(
    slides: List[Dict[str, Any]],
    *,
    render_spec: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    slide_rows: List[Dict[str, Any]] = []
    issue_counter: Counter[str] = Counter()
    placeholder_hits = 0
    missing_title_count = 0
    missing_body_count = 0
    assertion_total = 0
    assertion_missing_count = 0
    evidence_total = 0
    evidence_missing_count = 0

    normalized_slides = [item for item in (slides or []) if isinstance(item, dict)]
    for idx, slide in enumerate(normalized_slides):
        title = _extract_slide_title(slide)
        body_text = _extract_slide_body_text(slide)
        title_missing = not bool(title)
        body_missing = len(body_text) < 8
        text_blob = "\n".join(part for part in [title, body_text] if part).strip()
        placeholder_count = len(_TEXT_PLACEHOLDER_RE.findall(text_blob)) if text_blob else 0

        row_issues: List[str] = []
        if title_missing:
            row_issues.append("missing_assertion_title")
            missing_title_count += 1
        if body_missing:
            row_issues.append("missing_evidence_body")
            missing_body_count += 1
        if placeholder_count > 0:
            row_issues.append("placeholder_text")
            placeholder_hits += placeholder_count

        strategy = (
            slide.get("content_strategy")
            if isinstance(slide.get("content_strategy"), dict)
            else {}
        )
        strategy_assertion = str(strategy.get("assertion") or "").strip()
        strategy_evidence = [
            str(item or "").strip()
            for item in (strategy.get("evidence") if isinstance(strategy.get("evidence"), list) else [])
            if str(item or "").strip()
        ]
        slide_text = "\n".join(part for part in [title, body_text] if part).strip()
        assertion_covered = True
        if strategy_assertion:
            assertion_total += 1
            assertion_covered = _contains_text_evidence(slide_text, strategy_assertion)
            if not assertion_covered:
                assertion_missing_count += 1
                row_issues.append("assertion_not_covered")
        evidence_hit_count = 0
        if strategy_evidence:
            evidence_total += len(strategy_evidence)
            for item in strategy_evidence:
                if _contains_text_evidence(slide_text, item):
                    evidence_hit_count += 1
                else:
                    evidence_missing_count += 1
            if evidence_hit_count < len(strategy_evidence):
                row_issues.append("evidence_not_fully_covered")

        issue_counter.update(row_issues)
        slide_rows.append(
            {
                "slide": idx + 1,
                "title_present": not title_missing,
                "body_present": not body_missing,
                "placeholder_hits": placeholder_count,
                "assertion_covered": assertion_covered,
                "evidence_expected": len(strategy_evidence),
                "evidence_hit_count": evidence_hit_count,
                "issues": row_issues,
            }
        )

    slide_count = len(normalized_slides)
    placeholder_ratio = float(sum(1 for row in slide_rows if int(row.get("placeholder_hits") or 0) > 0)) / float(
        max(1, slide_count)
    )
    missing_title_ratio = float(missing_title_count) / float(max(1, slide_count))
    missing_body_ratio = float(missing_body_count) / float(max(1, slide_count))
    assertion_coverage_ratio = (
        1.0 - (float(assertion_missing_count) / float(max(1, assertion_total)))
        if assertion_total > 0
        else 1.0
    )
    evidence_coverage_ratio = (
        1.0 - (float(evidence_missing_count) / float(max(1, evidence_total)))
        if evidence_total > 0
        else 1.0
    )

    render_obj = render_spec if isinstance(render_spec, dict) else {}
    render_slides = render_obj.get("slides") if isinstance(render_obj.get("slides"), list) else []
    page_numbers: List[int] = []
    for item in render_slides:
        if not isinstance(item, dict):
            continue
        raw_num = item.get("page_number")
        try:
            num = int(raw_num)
        except Exception:
            continue
        if num > 0:
            page_numbers.append(num)
    page_number_discontinuous = False
    if page_numbers:
        expected = list(range(1, len(page_numbers) + 1))
        page_number_discontinuous = page_numbers != expected
        if page_number_discontinuous:
            issue_counter.update(["page_number_discontinuous"])

    score = _clamp_100(
        100.0
        - (placeholder_ratio * 42.0)
        - (missing_title_ratio * 28.0)
        - (missing_body_ratio * 24.0)
        - ((1.0 - assertion_coverage_ratio) * 18.0)
        - ((1.0 - evidence_coverage_ratio) * 18.0)
        - (10.0 if page_number_discontinuous else 0.0)
    )
    return {
        "slide_count": slide_count,
        "placeholder_hits": int(placeholder_hits),
        "placeholder_ratio": placeholder_ratio,
        "missing_title_count": int(missing_title_count),
        "missing_body_count": int(missing_body_count),
        "assertion_total": int(assertion_total),
        "assertion_missing_count": int(assertion_missing_count),
        "assertion_coverage_ratio": assertion_coverage_ratio,
        "evidence_total": int(evidence_total),
        "evidence_missing_count": int(evidence_missing_count),
        "evidence_coverage_ratio": evidence_coverage_ratio,
        "page_number_discontinuous": bool(page_number_discontinuous),
        "page_numbers": page_numbers,
        "score": score,
        "issue_codes": sorted(issue_counter.keys()),
        "slides": slide_rows,
    }


async def audit_rendered_slides(
    png_bytes_list: List[bytes],
    *,
    deck_title: str = "",
    route_mode: str = "standard",
    enable_multimodal: bool | None = None,
    multimodal_model: str | None = None,
) -> Dict[str, Any]:
    local_metrics = await asyncio.gather(
        *(asyncio.to_thread(_analyze_png_local, item) for item in png_bytes_list)
    )
    slide_count = len(local_metrics)
    if slide_count <= 0:
        return {
            "slide_count": 0,
            "blank_slide_ratio": 0.0,
            "low_contrast_ratio": 0.0,
            "mean_luminance": 128.0,
            "mean_contrast": 24.0,
            "local_score": 100.0,
            "multimodal_enabled": False,
        }

    blank_count = sum(1 for m in local_metrics if float(m.get("blank_like") or 0.0) >= 1.0)
    low_contrast_count = sum(1 for m in local_metrics if float(m.get("contrast") or 0.0) < 16.0)
    low_edge_count = sum(1 for m in local_metrics if float(m.get("edge_density") or 0.0) < 0.02)
    extreme_count = sum(
        1
        for m in local_metrics
        if float(m.get("mean_luminance") or 128.0) < 22.0 or float(m.get("mean_luminance") or 128.0) > 238.0
    )
    blank_ratio = blank_count / slide_count
    low_contrast_ratio = low_contrast_count / slide_count
    blank_area_ratio = low_edge_count / slide_count
    extreme_ratio = extreme_count / slide_count
    mean_luminance = sum(float(m.get("mean_luminance") or 0.0) for m in local_metrics) / slide_count
    mean_contrast = sum(float(m.get("contrast") or 0.0) for m in local_metrics) / slide_count
    mean_edge_density = sum(float(m.get("edge_density") or 0.0) for m in local_metrics) / slide_count

    style_switches = 0
    signatures = [m.get("signature") if isinstance(m.get("signature"), list) else [] for m in local_metrics]
    for idx in range(1, len(signatures)):
        distance = _signature_distance(
            signatures[idx - 1] if isinstance(signatures[idx - 1], list) else [],
            signatures[idx] if isinstance(signatures[idx], list) else [],
        )
        if distance > 0.52:
            style_switches += 1
    style_drift_ratio = style_switches / max(1, slide_count - 1)

    local_score = _clamp_100(
        100.0
        - (blank_ratio * 42.0)
        - (low_contrast_ratio * 26.0)
        - (blank_area_ratio * 18.0)
        - (extreme_ratio * 12.0)
        - (style_drift_ratio * 20.0)
    )
    local_issue_counter: Counter[str] = Counter()
    per_slide_rows: List[Dict[str, Any]] = []
    for idx, metrics in enumerate(local_metrics):
        slide_issues = _local_slide_issue_codes(metrics)
        local_issue_counter.update(slide_issues)
        per_slide_rows.append(
            {
                "slide": idx + 1,
                "local_issues": slide_issues,
                "mean_luminance": float(metrics.get("mean_luminance") or 128.0),
                "contrast": float(metrics.get("contrast") or 24.0),
                "edge_density": float(metrics.get("edge_density") or 0.08),
            }
        )
    out: Dict[str, Any] = {
        "slide_count": slide_count,
        "blank_slide_ratio": blank_ratio,
        "low_contrast_ratio": low_contrast_ratio,
        "blank_area_ratio": blank_area_ratio,
        "style_drift_ratio": style_drift_ratio,
        "extreme_luminance_ratio": extreme_ratio,
        "mean_luminance": mean_luminance,
        "mean_contrast": mean_contrast,
        "mean_edge_density": mean_edge_density,
        "local_score": local_score,
        "slides": per_slide_rows,
        "local_issue_counts": dict(local_issue_counter),
        "local_issue_ratios": {
            code: float(count) / float(max(1, slide_count))
            for code, count in local_issue_counter.items()
        },
        "issue_counts": dict(local_issue_counter),
        "issue_ratios": {
            code: float(count) / float(max(1, slide_count))
            for code, count in local_issue_counter.items()
        },
        "multimodal_enabled": False,
    }

    multimodal_flag = (
        str(os.getenv("PPT_VISUAL_QA_MULTIMODAL", "true")).strip().lower() not in {"0", "false", "no", "off"}
    )
    if enable_multimodal is not None:
        multimodal_flag = bool(enable_multimodal)
    if route_mode == "fast":
        multimodal_flag = False

    if multimodal_flag:
        model = str(multimodal_model or os.getenv("CONTENT_LLM_MODEL", "openai/gpt-4o-mini")).strip()
        mm = await _multimodal_audit(
            png_bytes_list=png_bytes_list,
            deck_title=deck_title,
            model=model,
            route_mode=route_mode,
        )
        out["multimodal_enabled"] = bool(mm.get("enabled"))
        out["multimodal"] = mm
        mm_score = mm.get("score")
        mm_issue_counts = mm.get("issue_counts") if isinstance(mm.get("issue_counts"), dict) else {}
        mm_issue_ratios_raw = mm.get("issue_ratios") if isinstance(mm.get("issue_ratios"), dict) else {}
        mm_issue_ratios: Dict[str, float] = {}
        for code, raw_ratio in mm_issue_ratios_raw.items():
            normalized = _normalize_issue_code(str(code))
            if not normalized:
                continue
            ratio = max(0.0, min(1.0, float(raw_ratio or 0.0)))
            if ratio <= 0.0:
                continue
            mm_issue_ratios[normalized] = ratio
        out["multimodal_issue_counts"] = {
            str(code): int(value)
            for code, value in mm_issue_counts.items()
            if str(code).strip()
        }
        out["multimodal_issue_ratios"] = mm_issue_ratios

        # Fuse local and multimodal issue estimates without additive double-counting.
        local_issue_ratios = (
            out.get("local_issue_ratios") if isinstance(out.get("local_issue_ratios"), dict) else {}
        )
        fused_codes = set(local_issue_ratios.keys()) | set(mm_issue_ratios.keys())
        fused_issue_ratios: Dict[str, float] = {}
        fused_issue_counts: Dict[str, int] = {}
        for code in fused_codes:
            local_ratio = max(0.0, min(1.0, float(local_issue_ratios.get(code) or 0.0)))
            mm_ratio = max(0.0, min(1.0, float(mm_issue_ratios.get(code) or 0.0)))
            fused_ratio = max(local_ratio, mm_ratio)
            if fused_ratio <= 0.0:
                continue
            fused_issue_ratios[code] = fused_ratio
            fused_issue_counts[code] = int(round(fused_ratio * float(slide_count)))
        if fused_issue_ratios:
            out["issue_ratios"] = fused_issue_ratios
            out["issue_counts"] = fused_issue_counts
        row_map: Dict[int, Dict[str, Any]] = {}
        for row in (mm.get("slides") or []):
            if not isinstance(row, dict):
                continue
            slide_no = int(row.get("slide") or 0)
            if slide_no > 0:
                row_map[slide_no] = row
        for row in out["slides"]:
            if not isinstance(row, dict):
                continue
            slide_no = int(row.get("slide") or 0)
            mm_row = row_map.get(slide_no)
            if isinstance(mm_row, dict):
                row["multimodal_issues"] = [str(code) for code in (mm_row.get("issues") or [])]
                row["multimodal_summary"] = str(mm_row.get("summary") or "")
                row["multimodal_score"] = float(mm_row.get("score") or 0.0)
        if isinstance(mm_score, (int, float)):
            out["multimodal_score"] = _clamp_100(float(mm_score))
            out["combined_score"] = _clamp_100((local_score * 0.55) + (float(mm_score) * 0.45))
        else:
            out["combined_score"] = local_score
    else:
        out["combined_score"] = local_score

    return out
