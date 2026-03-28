"""Quality gate checks for PPT slide integrity."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ppt_template_catalog import (
    quality_profile as load_quality_profile,
    template_profiles as template_catalog_profiles,
)


_PLACEHOLDER_PATTERNS = (
    r"\?\?\?",
    r"\bxxxx\b",
    r"\bTODO\b",
    r"\bTBD\b",
    r"lorem ipsum",
    r"\bplaceholder\b",
    r"\[placeholder\]",
    "\u5f85\u8865\u5145",
    "\u8bf7\u586b\u5199",
    "\u5360\u4f4d\u7b26",
)


@dataclass(frozen=True)
class QualityIssue:
    slide_id: str
    code: str
    message: str
    retry_scope: str
    retry_target_ids: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class QualityResult:
    ok: bool
    issues: List[QualityIssue]


def _resolve_quality_profile(
    profile: Optional[str | Dict[str, Any]] = None,
    *,
    slide: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = load_quality_profile("default")
    if isinstance(profile, str) and profile.strip():
        return load_quality_profile(profile)
    if isinstance(profile, dict):
        merged = dict(base)
        for key, value in profile.items():
            if key in merged:
                merged[key] = value
        return merged
    profile_id = ""
    if isinstance(slide, dict):
        profile_id = str(slide.get("quality_profile") or "").strip().lower()
        if not profile_id:
            template_id = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            if template_id:
                profile_id = str(template_catalog_profiles(template_id).get("quality_profile") or "").strip().lower()
    return load_quality_profile(profile_id or "default")


def _slide_id(slide: Dict[str, Any], index: int) -> str:
    for field in ("slide_id", "id", "page_number"):
        value = slide.get(field)
        if value is None:
            continue
        key = str(value).strip()
        if key:
            return key
    return f"slide-{index + 1}"


def _text_values(slide: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    title = str(slide.get("title") or "").strip()
    if title:
        texts.append(title)
    narration = str(slide.get("narration") or slide.get("speaker_notes") or "").strip()
    if narration:
        texts.append(narration)
    for element in slide.get("elements") or []:
        if not isinstance(element, dict):
            continue
        if str(element.get("type") or "").lower() != "text":
            continue
        content = str(element.get("content") or "").strip()
        if content:
            texts.append(content)
    return texts


def _is_garbled(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if "\ufffd" in s:
        return True
    mojibake_tokens = ("鈥", "锛", "鍙", "鐨", "銆", "闄")
    if sum(s.count(token) for token in mojibake_tokens) >= 2 and len(s) >= 6:
        return True
    q_ratio = s.count("?") / max(1, len(s))
    return s.count("?") >= 3 and q_ratio >= 0.15


def _to_number(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _has_placeholder_data(data: Dict[str, Any]) -> bool:
    labels = data.get("labels") if isinstance(data, dict) else []
    if not isinstance(labels, list):
        labels = []
    normalized = {str(label or "").strip().lower() for label in labels if str(label or "").strip()}
    placeholder_labels = {
        "\u6307\u6807a",
        "\u6307\u6807b",
        "\u6307\u6807c",
        "\u6307\u6807d",
        "\u6307\u6807e",
        "\u6570\u636ea",
        "\u9879\u76eea",
        "category a",
        "item 1",
    }
    if len(normalized & placeholder_labels) >= 2:
        return True
    if not labels:
        return True
    datasets = data.get("datasets")
    if isinstance(datasets, list) and datasets:
        values: List[float] = []
        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            series = ds.get("data") or ds.get("values") or []
            if not isinstance(series, list):
                continue
            for item in series:
                num = _to_number(item)
                if num is not None:
                    values.append(num)
        if values and all(v == 0 for v in values):
            return True
    return False


def _collect_font_sizes(slide: Dict[str, Any]) -> List[float]:
    sizes: List[float] = []
    for element in slide.get("elements") or []:
        if not isinstance(element, dict):
            continue
        style = element.get("style")
        if not isinstance(style, dict):
            continue
        num = _to_number(style.get("fontSize"))
        if num is not None and num > 0:
            sizes.append(num)
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        style = block.get("style")
        if isinstance(style, dict):
            num = _to_number(style.get("fontSize"))
            if num is not None and num > 0:
                sizes.append(num)
        content = block.get("content")
        if isinstance(content, dict):
            num = _to_number(content.get("fontSize"))
            if num is not None and num > 0:
                sizes.append(num)
    return sizes


def _normalized_text_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _extract_block_text(block: Dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        parts: List[str] = []
        for key in ("title", "body", "text", "label", "caption", "description"):
            value = str(content.get(key) or "").strip()
            if value:
                parts.append(value)
        if parts:
            return " ".join(parts).strip()
    data = block.get("data")
    if isinstance(data, dict):
        for key in ("title", "label", "description"):
            value = str(data.get(key) or "").strip()
            if value:
                return value
    return ""


def _has_duplicate_non_title_block_text(slide: Dict[str, Any]) -> bool:
    seen = set()
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype == "title":
            continue
        text = _normalized_text_key(_extract_block_text(block))
        if not text:
            continue
        if text in seen:
            return True
        seen.add(text)
    return False


def _has_title_echo_in_non_title_blocks(slide: Dict[str, Any]) -> bool:
    title = _normalized_text_key(str(slide.get("title") or ""))
    if not title:
        return False
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype == "title":
            continue
        text = _normalized_text_key(_extract_block_text(block))
        if text and text == title:
            return True
    return False


def _has_emphasis_signal(slide: Dict[str, Any]) -> bool:
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype == "title":
            continue
        emphasis = block.get("emphasis")
        if isinstance(emphasis, list) and any(str(item or "").strip() for item in emphasis):
            return True
        if re.search(r"\d+(?:\.\d+)?%?", _extract_block_text(block)):
            return True
    return False


def _non_title_block_count(slide: Dict[str, Any]) -> int:
    blocks = slide.get("blocks")
    if isinstance(blocks, list) and blocks:
        return len(
            [
                block
                for block in blocks
                if isinstance(block, dict)
                and str(block.get("block_type") or block.get("type") or "").strip().lower() != "title"
            ]
        )
    elements = slide.get("elements")
    if isinstance(elements, list):
        return len(
            [
                element
                for element in elements
                if isinstance(element, dict)
                and str(element.get("type") or "").strip().lower() != "title"
            ]
        )
    return 0


_LAYOUT_CARD_COUNTS = {
    "hero_1": 1,
    "split_2": 2,
    "asymmetric_2": 2,
    "grid_3": 3,
    "grid_4": 4,
    "bento_5": 5,
    "bento_6": 6,
    "timeline": 5,
}


def _resolve_image_url(block: Dict[str, Any]) -> str:
    content = block.get("content")
    data = block.get("data")
    if not isinstance(content, dict):
        content = {}
    if not isinstance(data, dict):
        data = {}
    for key in ("url", "src", "imageUrl", "image_url"):
        value = str(content.get(key) or data.get(key) or block.get(key) or "").strip()
        if value:
            return value
    return ""


def _estimate_blank_ratio(slide: Dict[str, Any]) -> float:
    blocks = slide.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return 0.0
    layout = str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower()
    card_count = _LAYOUT_CARD_COUNTS.get(layout, max(1, len(blocks)))
    non_title_blocks = [
        block
        for block in blocks
        if isinstance(block, dict)
        and str(block.get("block_type") or block.get("type") or "").strip().lower() != "title"
    ]
    if card_count <= 0:
        return 0.0
    filled = min(card_count, len(non_title_blocks))
    return max(0.0, 1.0 - (filled / card_count))


def _min_chart_font_size(slide: Dict[str, Any]) -> float | None:
    values: List[float] = []
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype != "chart":
            continue
        style = block.get("style")
        content = block.get("content")
        if isinstance(style, dict):
            for key in ("fontSize", "axisFontSize", "dataLabelFontSize", "legendFontSize"):
                num = _to_number(style.get(key))
                if num is not None:
                    values.append(num)
        if isinstance(content, dict):
            for key in ("fontSize", "axisFontSize", "dataLabelFontSize", "legendFontSize"):
                num = _to_number(content.get(key))
                if num is not None:
                    values.append(num)
    if not values:
        return None
    return min(values)


def validate_slide(
    slide: Dict[str, Any],
    index: int = 0,
    *,
    profile: Optional[str | Dict[str, Any]] = None,
) -> QualityResult:
    sid = _slide_id(slide, index)
    issues: List[QualityIssue] = []
    active_profile = _resolve_quality_profile(profile, slide=slide)
    texts = _text_values(slide)

    has_any_text = any(t.strip() for t in texts)
    has_elements = bool(slide.get("elements"))
    if not has_any_text and not has_elements:
        issues.append(
            QualityIssue(
                slide_id=sid,
                code="blank_slide",
                message="Slide is blank (no title/text/elements).",
                retry_scope="slide",
                retry_target_ids=[sid],
            )
        )

    garbled_fields = [t for t in texts if _is_garbled(t)]
    if garbled_fields:
        issues.append(
            QualityIssue(
                slide_id=sid,
                code="encoding_invalid",
                message="Slide contains likely garbled text.",
                retry_scope="block",
                retry_target_ids=[sid],
            )
        )

    joined = "\n".join(texts)
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, joined, flags=re.IGNORECASE):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="placeholder_pollution",
                    message=f"Placeholder content detected by pattern: {pattern}",
                    retry_scope="block",
                    retry_target_ids=[sid],
                )
            )
            break

    # Data completeness checks for chart/kpi blocks
    for element in slide.get("elements") or []:
        if not isinstance(element, dict):
            continue
        if str(element.get("type") or "").strip().lower() != "chart":
            continue
        data = element.get("chart_data")
        if _has_placeholder_data(data if isinstance(data, dict) else {}):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="placeholder_chart_data",
                    message="Chart contains placeholder or empty data.",
                    retry_scope="slide",
                    retry_target_ids=[sid],
                )
            )
            break

    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if str(block.get("block_type") or block.get("type") or "").strip().lower() == "chart":
            data = block.get("data")
            if not isinstance(data, dict) and isinstance(block.get("content"), dict):
                data = block.get("content")
            if _has_placeholder_data(data if isinstance(data, dict) else {}):
                issues.append(
                    QualityIssue(
                        slide_id=sid,
                        code="placeholder_chart_data",
                        message="Chart block contains placeholder or empty data.",
                        retry_scope="slide",
                        retry_target_ids=[sid],
                    )
                )
                break
        if str(block.get("block_type") or block.get("type") or "").strip().lower() == "kpi":
            payload = block.get("data")
            if not isinstance(payload, dict) and isinstance(block.get("content"), dict):
                payload = block.get("content")
            payload = payload if isinstance(payload, dict) else {}
            number = payload.get("number")
            text = str(number).strip().lower() if number is not None else ""
            num = _to_number(number)
            if (
                number is None
                or text in {"0", "0.0", "???", "xx", "--", "n/a"}
                or (num is not None and num == 0)
            ):
                issues.append(
                    QualityIssue(
                        slide_id=sid,
                        code="placeholder_kpi_data",
                        message="KPI block contains placeholder number.",
                        retry_scope="slide",
                        retry_target_ids=[sid],
                    )
                )
                break

    # Visual hierarchy and content density checks
    slide_type = str(slide.get("slide_type") or "").strip().lower()
    font_sizes = _collect_font_sizes(slide)
    min_typography_levels = int(active_profile.get("min_typography_levels") or 2)
    if (
        font_sizes
        and len({round(size, 2) for size in font_sizes}) < max(1, min_typography_levels)
        and slide_type != "divider"
    ):
        issues.append(
            QualityIssue(
                slide_id=sid,
                code="flat_typography",
                message=f"Slide lacks font size hierarchy (need >={max(1, min_typography_levels)} distinct sizes).",
                retry_scope="slide",
                retry_target_ids=[sid],
            )
        )

    if slide_type == "content":
        content_blocks = _non_title_block_count(slide)
        min_content_blocks = max(1, int(active_profile.get("min_content_blocks") or 2))
        if content_blocks < min_content_blocks:
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="low_content_density",
                    message=(
                        f"Content slide has only {content_blocks} non-title blocks "
                        f"(need >={min_content_blocks})."
                    ),
                    retry_scope="slide",
                    retry_target_ids=[sid],
                )
            )
        if bool(active_profile.get("forbid_duplicate_text", True)) and _has_duplicate_non_title_block_text(slide):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="duplicate_text",
                    message="Content slide contains duplicated non-title block text.",
                    retry_scope="slide",
                    retry_target_ids=[sid],
                )
            )
        if bool(active_profile.get("forbid_title_echo", True)) and _has_title_echo_in_non_title_blocks(slide):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="title_echo",
                    message="Content slide repeats title text in non-title blocks.",
                    retry_scope="slide",
                    retry_target_ids=[sid],
                )
            )
        if bool(active_profile.get("require_emphasis_signal", True)) and not _has_emphasis_signal(slide):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="weak_emphasis",
                    message="Content slide lacks emphasis signal (emphasis markers or numeric focus).",
                    retry_scope="slide",
                    retry_target_ids=[sid],
                )
            )

    # Visual QA: blank-area proxy from layout occupancy
    blank_ratio = _estimate_blank_ratio(slide)
    blank_area_max_ratio = float(active_profile.get("blank_area_max_ratio") or 0.45)
    if (
        slide_type in {"content", "split_2", "asymmetric_2", "grid_3", "grid_4", "bento_5", "bento_6", "timeline"}
        and blank_ratio > blank_area_max_ratio
    ):
        issues.append(
            QualityIssue(
                slide_id=sid,
                code="blank_area_high",
                message=(
                    f"Estimated blank area ratio too high "
                    f"({blank_ratio:.2f}, limit={blank_area_max_ratio:.2f})."
                ),
                retry_scope="slide",
                retry_target_ids=[sid],
            )
        )

    # Visual QA: missing image assets
    if bool(active_profile.get("require_image_url", True)):
        for block in slide.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
            if btype != "image":
                continue
            if not _resolve_image_url(block):
                issues.append(
                    QualityIssue(
                        slide_id=sid,
                        code="image_missing",
                        message="Image block is missing url/src/imageUrl.",
                        retry_scope="slide",
                        retry_target_ids=[sid],
                    )
                )
                break

    # Visual QA: chart readability (font size baseline)
    min_chart_font = _min_chart_font_size(slide)
    chart_min_font_size = float(active_profile.get("chart_min_font_size") or 9)
    if min_chart_font is not None and min_chart_font < chart_min_font_size:
        issues.append(
            QualityIssue(
                slide_id=sid,
                code="chart_readability_low",
                message=f"Chart font size too small ({min_chart_font:.1f} < {chart_min_font_size:g}).",
                retry_scope="slide",
                retry_target_ids=[sid],
            )
        )

    return QualityResult(ok=len(issues) == 0, issues=issues)


def validate_deck(
    slides: List[Dict[str, Any]],
    *,
    profile: Optional[str | Dict[str, Any]] = None,
) -> QualityResult:
    all_issues: List[QualityIssue] = []
    for idx, slide in enumerate(slides):
        result = validate_slide(slide, index=idx, profile=profile)
        all_issues.extend(result.issues)
    return QualityResult(ok=len(all_issues) == 0, issues=all_issues)


def validate_layout_diversity(
    render_spec: Dict[str, Any],
    *,
    profile: Optional[str | Dict[str, Any]] = None,
    max_type_ratio: Optional[float] = None,
    max_adjacent_repeat: Optional[int] = None,
    min_slide_count: Optional[int] = None,
    min_layout_variety: Optional[int] = None,
    enforce_terminal_slide_types: Optional[bool] = None,
) -> QualityResult:
    active_profile = _resolve_quality_profile(profile)
    if max_type_ratio is None:
        max_type_ratio = float(active_profile.get("layout_max_type_ratio") or 0.45)
    if max_adjacent_repeat is None:
        max_adjacent_repeat = int(active_profile.get("layout_max_adjacent_repeat") or 1)
    if min_slide_count is None:
        min_slide_count = int(active_profile.get("layout_min_slide_count") or 6)
    if min_layout_variety is None:
        min_layout_variety = int(active_profile.get("layout_min_variety_long_deck") or 4)
    if enforce_terminal_slide_types is None:
        enforce_terminal_slide_types = bool(active_profile.get("enforce_terminal_slide_types", False))
    long_deck_threshold = int(active_profile.get("layout_long_deck_threshold") or 10)

    slides = (
        render_spec.get("slides")
        if isinstance(render_spec, dict)
        else []
    )
    if not isinstance(slides, list) or len(slides) < min_slide_count:
        return QualityResult(ok=True, issues=[])

    normalized_types: List[str] = []
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            normalized_types.append(f"unknown_{idx}")
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
            raw_type = slide_type
        else:
            raw_type = slide.get("layout_grid") or slide.get("layout") or slide_type or "unknown"
        st = str(raw_type).strip().lower() or "unknown"
        normalized_types.append(st)

    total = len(normalized_types)
    counts = Counter(normalized_types)
    ratio_limit = max(1, math.floor(total * max(0.1, min(1.0, max_type_ratio))))

    issues: List[QualityIssue] = []
    for slide_type, count in counts.items():
        if count <= ratio_limit:
            continue
        issues.append(
            QualityIssue(
                slide_id="deck",
                code="layout_homogeneous",
                message=(
                    f"Layout type '{slide_type}' dominates deck "
                    f"({count}/{total}, limit={ratio_limit})."
                ),
                retry_scope="deck",
                retry_target_ids=[],
            )
        )
        break

    run_length = 1
    for idx in range(1, total):
        if normalized_types[idx] == normalized_types[idx - 1]:
            run_length += 1
        else:
            run_length = 1
        if run_length > max_adjacent_repeat:
            sid = _slide_id(slides[idx], idx) if isinstance(slides[idx], dict) else f"slide-{idx + 1}"
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="layout_adjacent_repeat",
                    message=(
                        f"Adjacent layout repetition detected: '{normalized_types[idx]}' "
                        f"repeated {run_length} times."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
            break

    if total >= max(4, long_deck_threshold) and len(set(normalized_types)) < max(1, int(min_layout_variety)):
        issues.append(
            QualityIssue(
                slide_id="deck",
                code="layout_variety_low",
                message=(
                    f"Layout variety too low ({len(set(normalized_types))}/{total}); "
                    f"requires >= {max(1, int(min_layout_variety))} distinct types for long decks."
                ),
                retry_scope="deck",
                retry_target_ids=[],
            )
        )

    if enforce_terminal_slide_types and total >= 2:
        first_type = normalized_types[0]
        last_type = normalized_types[-1]
        if first_type not in {"cover", "hero_1"}:
            issues.append(
                QualityIssue(
                    slide_id=_slide_id(slides[0], 0) if isinstance(slides[0], dict) else "slide-1",
                    code="layout_terminal_cover_missing",
                    message=(
                        f"First slide should be cover/hero_1, got '{first_type}'."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
        if last_type not in {"summary", "hero_1"}:
            issues.append(
                QualityIssue(
                    slide_id=(
                        _slide_id(slides[-1], total - 1)
                        if isinstance(slides[-1], dict)
                        else f"slide-{total}"
                    ),
                    code="layout_terminal_summary_missing",
                    message=(
                        f"Last slide should be summary/hero_1, got '{last_type}'."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )

    return QualityResult(ok=len(issues) == 0, issues=issues)


