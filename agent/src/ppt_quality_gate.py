"""Quality gate checks for PPT slide integrity."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ppt_scene_rulebook import normalize_scene_rule_profile
from src.ppt_template_catalog import (
    quality_profile as load_quality_profile,
    template_capabilities as template_catalog_capabilities,
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
    "\u5360\u4f4d\u6587\u6848",
    "\u793a\u4f8b\u6587\u6848",
    "\u9ed8\u8ba4\u6587\u6848",
    "\u8bf7\u66ff\u6362",
    "\u6b64\u5904\u63d2\u5165\u5185\u5bb9",
    r"\bto be filled\b",
    r"\breplace me\b",
    r"\bdefault copy\b",
    r"(?:^|[\n\r])\s*(?:\u5148\u8bf4\u660e|\u518d\u4ea4\u4ee3|\u6700\u540e\u89e3\u91ca|\u56f4\u7ed5.{0,24}\u63d0\u70bc|\u907f\u514d\u53ea\u7f57\u5217\u6807\u9898)",
)

_PLACEHOLDER_EXPLANATION_PATTERNS = {
    r"\bplaceholder\b",
    r"\[placeholder\]",
    "\u5360\u4f4d\u7b26",
    "\u5360\u4f4d\u6587\u6848",
    "\u793a\u4f8b\u6587\u6848",
    "\u9ed8\u8ba4\u6587\u6848",
}
_PLACEHOLDER_EXPLANATION_HINTS = (
    "definition",
    "means",
    "refers to",
    "concept",
    "\u5b9a\u4e49",
    "\u6982\u5ff5",
    "\u6307\u7684\u662f",
    "\u4e0d\u662f\u5360\u4f4d",
    "\u975e\u5360\u4f4d",
    "\u8bf7\u52ff\u4f7f\u7528",
    "\u4e0d\u8981\u4f7f\u7528",
    "\u7981\u6b62\u4f7f\u7528",
    "do not use",
    "avoid using",
)


def _is_placeholder_false_positive(*, pattern: str, text: str) -> bool:
    normalized_pattern = str(pattern or "").strip()
    if normalized_pattern not in _PLACEHOLDER_EXPLANATION_PATTERNS:
        return False
    blob = str(text or "")
    lowered = blob.lower()
    return any(hint in lowered or hint in blob for hint in _PLACEHOLDER_EXPLANATION_HINTS)


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


@dataclass(frozen=True)
class QualityScoreResult:
    score: float
    passed: bool
    threshold: float
    warn_threshold: float
    dimensions: Dict[str, float]
    issue_counts: Dict[str, int]
    diagnostics: Dict[str, Any]


@dataclass(frozen=True)
class VisualProfessionalScoreResult:
    color_consistency_score: float
    layout_order_score: float
    hierarchy_clarity_score: float
    visual_avg_score: float
    accuracy_gate_passed: bool
    abnormal_tags: List[str]
    diagnostics: Dict[str, Any]


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


def _slide_supports_image_block(slide: Dict[str, Any]) -> bool:
    template_id = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
    if not template_id:
        return True
    capabilities = template_catalog_capabilities(template_id)
    supported = {
        str(item or "").strip().lower()
        for item in (capabilities.get("supported_block_types") or [])
        if str(item or "").strip()
    }
    if not supported:
        return True
    return "image" in supported


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


def _clamp_100(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _issue_counter(issues: List[QualityIssue]) -> Counter:
    return Counter(str(issue.code or "").strip().lower() for issue in issues if str(issue.code or "").strip())


def _slide_type_values(slides: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            values.append(f"unknown_{idx}")
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
            values.append(slide_type)
            continue
        raw_type = slide.get("layout_grid") or slide.get("layout") or slide_type or "unknown"
        values.append(str(raw_type).strip().lower() or "unknown")
    return values


def _template_family_values(slides: List[Dict[str, Any]]) -> List[str]:
    values: List[str] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
            continue
        family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if family:
            values.append(family)
    return values


def _switch_ratio(values: List[str]) -> float:
    if len(values) <= 1:
        return 0.0
    switches = 0
    for idx in range(1, len(values)):
        if values[idx] != values[idx - 1]:
            switches += 1
    return switches / max(1, len(values) - 1)


_STATUS_REPORT_SUMMARY_RE = re.compile(r"(执行摘要|摘要|核心结论|决策请求)")
_STATUS_REPORT_GENERIC_TITLE_TOKENS = {
    "销售分析",
    "市场分析",
    "财务分析",
    "运营分析",
    "项目汇报",
    "工作汇报",
    "项目进展",
    "市场情况",
    "销售情况",
    "用户情况",
    "问题分析",
    "解决方案",
    "行动计划",
    "行动项",
    "总结",
    "概览",
    "复盘",
    "计划",
    "策略",
}
_PITCH_MODULE_KEYWORDS = {
    "problem": ("problem", "pain", "痛点", "问题"),
    "solution": ("solution", "产品", "解决方案", "demo", "截图"),
    "market": ("market", "tam", "sam", "som", "市场"),
    "traction": ("traction", "增长", "用户增长", "arr", "gmv", "营收"),
    "model": ("model", "商业模式", "ltv", "cac", "毛利"),
    "competition": ("competition", "竞品", "竞争", "壁垒"),
    "team": ("team", "founder", "团队", "创始人"),
    "ask": ("ask", "融资", "募资", "用途", "milestone", "里程碑"),
}
_TRAINING_OBJECTIVE_RE = re.compile(r"(学习目标|课程目标|你将能够|能够)")
_TRAINING_MEASURABLE_VERBS = ("能够", "写出", "分析", "判断", "设计", "搭建", "识别", "完成", "运用")
_TRAINING_KNOWLEDGE_MAP_RE = re.compile(r"(知识地图|知识框架|课程地图|课程结构|本课结构|目录)")
_TRAINING_INTERACTION_RE = re.compile(r"(互动|讨论|练习|小测|测验|思考题|挑战)")
_INVESTOR_ASK_DETAIL_RE = re.compile(r"(\d+\s*(万|亿|m|million)|用途|里程碑|18个月|months?)", re.IGNORECASE)


def _resolve_scene_profile(profile: Optional[str | Dict[str, Any]] = None, *, slides: Optional[List[Dict[str, Any]]] = None) -> str:
    if isinstance(profile, str):
        normalized = normalize_scene_rule_profile(profile)
        if normalized:
            return normalized
    for slide in slides or []:
        if not isinstance(slide, dict):
            continue
        normalized = normalize_scene_rule_profile(slide.get("quality_profile"))
        if normalized:
            return normalized
    return ""


def _slide_text_blob(slide: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.extend(_text_values(slide))
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        text = _extract_block_text(block)
        if text:
            parts.append(text)
    return " ".join(part.strip() for part in parts if str(part).strip()).strip()


def _find_status_report_summary_slide(slides: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for slide in slides[:3]:
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type == "summary":
            return slide
        title_blob = _slide_text_blob(slide)
        if _STATUS_REPORT_SUMMARY_RE.search(title_blob):
            return slide
    return None


def _generic_status_report_title(title: str) -> bool:
    normalized = str(title or "").strip()
    if not normalized:
        return False
    if normalized in _STATUS_REPORT_GENERIC_TITLE_TOKENS:
        return True
    compact = normalized.replace(" ", "")
    if len(compact) <= 8 and any(token in compact for token in ("分析", "情况", "总结", "计划", "汇报", "概览", "策略")):
        return True
    return False


def _scene_hard_gate_issues(slides: List[Dict[str, Any]], *, profile: Optional[str | Dict[str, Any]] = None) -> List[QualityIssue]:
    scene = _resolve_scene_profile(profile, slides=slides)
    if not scene:
        return []
    issues: List[QualityIssue] = []
    if scene == "status_report":
        summary_slide = _find_status_report_summary_slide(slides)
        if summary_slide is None:
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="scene_status_report_exec_summary_missing",
                    message="Status report deck should include an executive summary within the first 3 slides.",
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
        elif _non_title_block_count(summary_slide) < 4:
            sid = _slide_id(summary_slide, 1)
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="scene_status_report_exec_summary_incomplete",
                    message="Executive summary should cover at least 4 independent items.",
                    retry_scope="deck",
                    retry_target_ids=[sid],
                )
            )
    elif scene == "investor_pitch":
        blob = " ".join(_slide_text_blob(slide).lower() for slide in slides if isinstance(slide, dict))
        missing = [
            module
            for module, keywords in _PITCH_MODULE_KEYWORDS.items()
            if not any(keyword.lower() in blob for keyword in keywords)
        ]
        if missing:
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="scene_investor_pitch_modules_missing",
                    message="Investor pitch is missing core modules: " + ", ".join(missing),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
    elif scene == "training_deck":
        early_slides = [slide for slide in slides[:2] if isinstance(slide, dict)]
        has_objectives = False
        for slide in early_slides:
            blob = _slide_text_blob(slide)
            if _TRAINING_OBJECTIVE_RE.search(blob) and any(verb in blob for verb in _TRAINING_MEASURABLE_VERBS):
                has_objectives = True
                break
        if not has_objectives:
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="scene_training_deck_learning_goals_missing",
                    message="Training deck should introduce measurable learning goals within the first 2 slides.",
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
        map_slides = [slide for slide in slides[:4] if isinstance(slide, dict)]
        has_map = any(
            str(slide.get("slide_type") or "").strip().lower() == "toc" or _TRAINING_KNOWLEDGE_MAP_RE.search(_slide_text_blob(slide))
            for slide in map_slides
        )
        if not has_map:
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="scene_training_deck_knowledge_map_missing",
                    message="Training deck should include a knowledge map / agenda view within the first 4 slides.",
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
    return issues


def _scene_advisory_issue_counts(slides: List[Dict[str, Any]], *, profile: Optional[str | Dict[str, Any]] = None) -> Counter:
    scene = _resolve_scene_profile(profile, slides=slides)
    counts: Counter = Counter()
    if not scene:
        return counts
    if scene == "status_report":
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type in {"cover", "summary", "toc", "divider"}:
                continue
            if _generic_status_report_title(str(slide.get("title") or "")):
                counts["scene_status_report_title_generic"] += 1
    elif scene == "investor_pitch":
        ask_blobs = [
            _slide_text_blob(slide)
            for slide in slides
            if isinstance(slide, dict) and any(token in _slide_text_blob(slide).lower() for token in ("ask", "融资", "募资", "里程碑"))
        ]
        if ask_blobs and not any(_INVESTOR_ASK_DETAIL_RE.search(blob) for blob in ask_blobs):
            counts["scene_investor_pitch_ask_blurry"] += 1
        elif not ask_blobs:
            counts["scene_investor_pitch_ask_blurry"] += 1
    elif scene == "training_deck":
        if not any(_TRAINING_INTERACTION_RE.search(_slide_text_blob(slide)) for slide in slides if isinstance(slide, dict)):
            counts["scene_training_deck_interaction_missing"] += 1
    return counts


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
                retry_scope="deck",
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
                retry_scope="deck",
                retry_target_ids=[sid],
            )
        )

    joined = "\n".join(texts)
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, joined, flags=re.IGNORECASE):
            if _is_placeholder_false_positive(pattern=pattern, text=joined):
                continue
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="placeholder_pollution",
                    message=f"Placeholder content detected by pattern: {pattern}",
                    retry_scope="deck",
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
                    retry_scope="deck",
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
                        retry_scope="deck",
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
                        retry_scope="deck",
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
                retry_scope="deck",
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
                    retry_scope="deck",
                    retry_target_ids=[sid],
                )
            )
        if bool(active_profile.get("forbid_duplicate_text", True)) and _has_duplicate_non_title_block_text(slide):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="duplicate_text",
                    message="Content slide contains duplicated non-title block text.",
                    retry_scope="deck",
                    retry_target_ids=[sid],
                )
            )
        if bool(active_profile.get("forbid_title_echo", True)) and _has_title_echo_in_non_title_blocks(slide):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="title_echo",
                    message="Content slide repeats title text in non-title blocks.",
                    retry_scope="deck",
                    retry_target_ids=[sid],
                )
            )
        if bool(active_profile.get("require_emphasis_signal", True)) and not _has_emphasis_signal(slide):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="weak_emphasis",
                    message="Content slide lacks emphasis signal (emphasis markers or numeric focus).",
                    retry_scope="deck",
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
                retry_scope="deck",
                retry_target_ids=[sid],
            )
        )

    # Visual QA: missing image assets
    if bool(active_profile.get("require_image_url", True)):
        image_blocks: List[Dict[str, Any]] = []
        for block in slide.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
            if btype != "image":
                continue
            image_blocks.append(block)
            if not _resolve_image_url(block):
                issues.append(
                    QualityIssue(
                        slide_id=sid,
                        code="image_missing",
                        message="Image block is missing url/src/imageUrl.",
                        retry_scope="deck",
                        retry_target_ids=[sid],
                    )
                )
                break
        # Strict image anchor requirement is orchestration-profile driven.
        orchestration = (
            active_profile.get("orchestration")
            if isinstance(active_profile.get("orchestration"), dict)
            else {}
        )
        strict_image_anchor = bool(orchestration.get("require_image_anchor", False))
        if (
            strict_image_anchor
            and slide_type == "content"
            and _slide_supports_image_block(slide)
            and not image_blocks
        ):
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="image_missing",
                    message="Content slide lacks image anchor block.",
                    retry_scope="deck",
                    retry_target_ids=[sid],
                )
            )

    # Visual QA: chart readability (font size baseline)
    min_chart_font = _min_chart_font_size(slide)
    chart_min_font_size = float(active_profile.get("chart_min_font_size") or 9)
    if min_chart_font is not None and min_chart_font < chart_min_font_size:
        issues.append(
            QualityIssue(
                slide_id=sid,
                code="chart_readability_low",
                message=f"Chart font size too small ({min_chart_font:.1f} < {chart_min_font_size:g}).",
                retry_scope="deck",
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
    all_issues.extend(_scene_hard_gate_issues(slides, profile=profile))
    return QualityResult(ok=len(all_issues) == 0, issues=all_issues)


_DENSITY_HIGH_LAYOUTS = {"grid_4", "bento_5", "bento_6"}
_DENSITY_LOW_LAYOUTS = {"hero_1"}
_DENSITY_BREATHING_LAYOUTS = {"section", "cover", "summary", "divider", "toc"}


def _density_level(layout_or_type: str) -> str:
    normalized = str(layout_or_type or "").strip().lower()
    if normalized in _DENSITY_HIGH_LAYOUTS:
        return "high"
    if normalized in _DENSITY_LOW_LAYOUTS:
        return "low"
    if normalized in _DENSITY_BREATHING_LAYOUTS:
        return "breathing"
    return "medium"


def validate_layout_diversity(
    render_spec: Dict[str, Any],
    *,
    profile: Optional[str | Dict[str, Any]] = None,
    max_type_ratio: Optional[float] = None,
    max_top2_ratio: Optional[float] = None,
    max_adjacent_repeat: Optional[int] = None,
    abab_max_run: Optional[int] = None,
    min_slide_count: Optional[int] = None,
    min_layout_variety: Optional[int] = None,
    enforce_terminal_slide_types: Optional[bool] = None,
    template_family_max_type_ratio: Optional[float] = None,
    template_family_max_top2_ratio: Optional[float] = None,
    template_family_max_switch_ratio: Optional[float] = None,
    template_family_abab_max_run: Optional[int] = None,
    template_family_min_slide_count: Optional[int] = None,
) -> QualityResult:
    active_profile = _resolve_quality_profile(profile)
    if max_type_ratio is None:
        max_type_ratio = float(active_profile.get("layout_max_type_ratio") or 0.45)
    if max_top2_ratio is None:
        max_top2_ratio = float(active_profile.get("layout_max_top2_ratio") or 0.65)
    if max_adjacent_repeat is None:
        max_adjacent_repeat = int(active_profile.get("layout_max_adjacent_repeat") or 1)
    if abab_max_run is None:
        abab_max_run = int(active_profile.get("layout_abab_max_run") or 4)
    if min_slide_count is None:
        min_slide_count = int(active_profile.get("layout_min_slide_count") or 6)
    if min_layout_variety is None:
        min_layout_variety = int(active_profile.get("layout_min_variety_long_deck") or 4)
    density_max_consecutive_high = max(1, int(active_profile.get("density_max_consecutive_high") or 2))
    density_window_size = max(3, int(active_profile.get("density_window_size") or 5))
    density_required_low_or_breathing = max(
        1, int(active_profile.get("density_require_low_or_breathing_per_window") or 1)
    )
    if enforce_terminal_slide_types is None:
        enforce_terminal_slide_types = bool(active_profile.get("enforce_terminal_slide_types", False))
    if template_family_max_type_ratio is None:
        template_family_max_type_ratio = float(active_profile.get("template_family_max_type_ratio") or 0.55)
    if template_family_max_top2_ratio is None:
        template_family_max_top2_ratio = float(active_profile.get("template_family_max_top2_ratio") or 0.8)
    if template_family_max_switch_ratio is None:
        template_family_max_switch_ratio = float(active_profile.get("template_family_max_switch_ratio") or 0.75)
    if template_family_abab_max_run is None:
        template_family_abab_max_run = int(active_profile.get("template_family_abab_max_run") or 6)
    if template_family_min_slide_count is None:
        template_family_min_slide_count = int(active_profile.get("template_family_min_slide_count") or 8)
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
    density_tokens: List[str] = []
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            density_tokens.append(normalized_types[idx])
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in _DENSITY_BREATHING_LAYOUTS:
            density_tokens.append(slide_type)
            continue
        density_tokens.append(
            str(slide.get("layout_grid") or slide.get("layout") or normalized_types[idx]).strip().lower()
        )

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

    top2 = counts.most_common(2)
    if len(top2) >= 2:
        top2_count = int(top2[0][1]) + int(top2[1][1])
        top2_limit = max(2, math.floor(total * max(0.1, min(1.0, max_top2_ratio))))
        if top2_count > top2_limit:
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="layout_top2_homogeneous",
                    message=(
                        f"Top-2 layout types '{top2[0][0]}' + '{top2[1][0]}' dominate deck "
                        f"({top2_count}/{total}, limit={top2_limit})."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )

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

    if total >= max(4, int(abab_max_run)):
        for start in range(0, total - 3):
            first = normalized_types[start]
            second = normalized_types[start + 1]
            if first == second:
                continue
            run = 2
            expected = first
            cursor = start + 2
            while cursor < total and normalized_types[cursor] == expected:
                run += 1
                expected = second if expected == first else first
                cursor += 1
            if run >= int(abab_max_run):
                sid = _slide_id(slides[min(cursor - 1, total - 1)], min(cursor - 1, total - 1))
                issues.append(
                    QualityIssue(
                        slide_id=sid,
                        code="layout_abab_repeat",
                        message=(
                            f"Alternating ABAB layout pattern detected for {run} slides "
                            f"('{first}' <-> '{second}')."
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

    if total > 2:
        middle_start = 1
        middle_end = total - 1
        seq = 0
        for idx in range(middle_start, middle_end):
            level = _density_level(density_tokens[idx])
            if level == "high":
                seq += 1
            else:
                seq = 0
            if seq <= density_max_consecutive_high:
                continue
            sid = _slide_id(slides[idx], idx) if isinstance(slides[idx], dict) else f"slide-{idx + 1}"
            issues.append(
                QualityIssue(
                    slide_id=sid,
                    code="layout_density_consecutive_high",
                    message=(
                        f"Density rhythm violation: high-density run={seq} exceeds "
                        f"limit={density_max_consecutive_high}."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )
            break

        if middle_end - middle_start >= density_window_size:
            for start in range(middle_start, middle_end):
                end = min(middle_end, start + density_window_size)
                if end - start < density_window_size:
                    break
                levels = [_density_level(density_tokens[pos]) for pos in range(start, end)]
                low_or_breathing = sum(1 for item in levels if item in {"low", "breathing"})
                if low_or_breathing >= density_required_low_or_breathing:
                    continue
                sid_idx = end - 1
                sid = (
                    _slide_id(slides[sid_idx], sid_idx)
                    if isinstance(slides[sid_idx], dict)
                    else f"slide-{sid_idx + 1}"
                )
                issues.append(
                    QualityIssue(
                        slide_id=sid,
                        code="layout_density_window_missing_breathing",
                        message=(
                            f"Density rhythm violation: each {density_window_size}-slide window must include "
                            f">= {density_required_low_or_breathing} low/breathing slide(s)."
                        ),
                        retry_scope="deck",
                        retry_target_ids=[],
                    )
                )
                break

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

    family_values = _template_family_values(slides)
    family_total = len(family_values)
    if family_total >= max(2, int(template_family_min_slide_count)):
        family_counts = Counter(family_values)
        family_limit = max(1, math.floor(family_total * max(0.1, min(1.0, template_family_max_type_ratio))))
        dominant_family, dominant_count = family_counts.most_common(1)[0]
        if dominant_count > family_limit:
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="template_family_homogeneous",
                    message=(
                        f"Template family '{dominant_family}' dominates deck "
                        f"({dominant_count}/{family_total}, limit={family_limit})."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )

        family_top2 = family_counts.most_common(2)
        if len(family_top2) >= 2:
            family_top2_count = int(family_top2[0][1]) + int(family_top2[1][1])
            family_top2_limit = max(
                2, math.floor(family_total * max(0.1, min(1.0, template_family_max_top2_ratio)))
            )
            if family_top2_count > family_top2_limit:
                issues.append(
                    QualityIssue(
                        slide_id="deck",
                        code="template_family_top2_homogeneous",
                        message=(
                            f"Top-2 template families '{family_top2[0][0]}' + '{family_top2[1][0]}' dominate deck "
                            f"({family_top2_count}/{family_total}, limit={family_top2_limit})."
                        ),
                        retry_scope="deck",
                        retry_target_ids=[],
                    )
                )

        family_switch_ratio = _switch_ratio(family_values)
        if family_switch_ratio > max(0.0, min(1.0, template_family_max_switch_ratio)):
            issues.append(
                QualityIssue(
                    slide_id="deck",
                    code="template_family_switch_frequent",
                    message=(
                        f"Template-family switch ratio too high "
                        f"({family_switch_ratio:.2f}, limit={template_family_max_switch_ratio:.2f})."
                    ),
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            )

        if family_total >= max(4, int(template_family_abab_max_run)):
            for start in range(0, family_total - 3):
                first = family_values[start]
                second = family_values[start + 1]
                if first == second:
                    continue
                run = 2
                expected = first
                cursor = start + 2
                while cursor < family_total and family_values[cursor] == expected:
                    run += 1
                    expected = second if expected == first else first
                    cursor += 1
                if run >= int(template_family_abab_max_run):
                    issues.append(
                        QualityIssue(
                            slide_id="deck",
                            code="template_family_abab_repeat",
                            message=(
                                f"Alternating ABAB template-family pattern detected for {run} slides "
                                f"('{first}' <-> '{second}')."
                            ),
                            retry_scope="deck",
                            retry_target_ids=[],
                        )
                    )
                    break

    return QualityResult(ok=len(issues) == 0, issues=issues)


def validate_visual_audit(
    *,
    visual_audit: Optional[Dict[str, Any]],
    slides: List[Dict[str, Any]],
    profile: Optional[str | Dict[str, Any]] = None,
    layout_diversity_ok: Optional[bool] = None,
) -> QualityResult:
    active_profile = _resolve_quality_profile(profile)
    require_visual_audit = bool(active_profile.get("require_visual_audit", True))
    if not isinstance(visual_audit, dict):
        if not require_visual_audit:
            return QualityResult(ok=True, issues=[])
        return QualityResult(
            ok=False,
            issues=[
                QualityIssue(
                    slide_id="deck",
                    code="visual_audit_missing",
                    message="visual_audit payload is required for quality pass.",
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            ],
        )
    audit_error = str(visual_audit.get("error") or "").strip()
    if audit_error:
        return QualityResult(
            ok=False,
            issues=[
                QualityIssue(
                    slide_id="deck",
                    code="visual_audit_unavailable",
                    message=f"visual_audit unavailable: {audit_error[:200]}",
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            ],
        )
    issue_ratios = (
        visual_audit.get("issue_ratios")
        if isinstance(visual_audit.get("issue_ratios"), dict)
        else {}
    )
    local_issue_ratios = (
        visual_audit.get("local_issue_ratios")
        if isinstance(visual_audit.get("local_issue_ratios"), dict)
        else {}
    )
    multimodal_issue_ratios = (
        visual_audit.get("multimodal_issue_ratios")
        if isinstance(visual_audit.get("multimodal_issue_ratios"), dict)
        else {}
    )

    blank_slide_ratio = max(0.0, min(1.0, float(visual_audit.get("blank_slide_ratio") or 0.0)))
    low_contrast_ratio = max(0.0, min(1.0, float(visual_audit.get("low_contrast_ratio") or 0.0)))
    blank_area_ratio = max(0.0, min(1.0, float(visual_audit.get("blank_area_ratio") or 0.0)))
    style_drift_ratio = max(0.0, min(1.0, float(visual_audit.get("style_drift_ratio") or 0.0)))

    slide_count = len(slides)
    sid = "deck"
    issues: List[QualityIssue] = []
    visual_rows = visual_audit.get("slides") if isinstance(visual_audit.get("slides"), list) else []
    index_to_slide_id: Dict[int, str] = {}
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        index_to_slide_id[idx + 1] = _slide_id(slide, idx)

    issue_to_slide_ids: Dict[str, List[str]] = {}
    row_metrics: Dict[str, Dict[str, float]] = {}
    for row in visual_rows:
        if not isinstance(row, dict):
            continue
        raw_idx = int(row.get("slide") or 0)
        if raw_idx <= 0:
            continue
        target_sid = index_to_slide_id.get(raw_idx) or f"slide-{raw_idx}"
        local_issues = row.get("local_issues") if isinstance(row.get("local_issues"), list) else []
        mm_issues = row.get("multimodal_issues") if isinstance(row.get("multimodal_issues"), list) else []
        for code in [*local_issues, *mm_issues]:
            key = str(code or "").strip().lower()
            if not key:
                continue
            bucket = issue_to_slide_ids.setdefault(key, [])
            if target_sid not in bucket:
                bucket.append(target_sid)
        row_metrics[target_sid] = {
            "contrast": float(row.get("contrast") or 0.0),
            "edge_density": float(row.get("edge_density") or 0.0),
            "mean_luminance": float(row.get("mean_luminance") or 128.0),
        }

    all_slide_ids = [
        _slide_id(slide, idx)
        for idx, slide in enumerate(slides)
        if isinstance(slide, dict)
    ]

    def _rank_slide_ids(metric_key: str, *, reverse: bool = False) -> List[str]:
        ranked = sorted(
            all_slide_ids,
            key=lambda item: row_metrics.get(item, {}).get(metric_key, 0.0),
            reverse=reverse,
        )
        return ranked

    def _target_slide_ids_for_issue(
        *,
        issue_key: str,
        ratio: float,
        fallback_metric: str = "contrast",
        fallback_reverse: bool = False,
    ) -> List[str]:
        estimated = max(1, math.ceil(max(0.0, min(1.0, ratio)) * max(1, slide_count)))
        direct = list(issue_to_slide_ids.get(str(issue_key or "").strip().lower(), []))
        if direct:
            return direct[:estimated]
        ranked = _rank_slide_ids(fallback_metric, reverse=fallback_reverse)
        if ranked:
            return ranked[:estimated]
        return []

    def _threshold(name: str, fallback: float) -> float:
        return max(0.0, min(1.0, float(active_profile.get(name) or fallback)))

    blank_slide_limit = _threshold("visual_blank_slide_max_ratio", 0.05)
    low_contrast_limit = _threshold("visual_low_contrast_max_ratio", 0.22)
    blank_area_limit = _threshold("visual_blank_area_max_ratio", 0.55)
    style_drift_limit = _threshold("visual_style_drift_max_ratio", 1.0)

    if blank_slide_ratio > blank_slide_limit:
        target_ids = _target_slide_ids_for_issue(
            issue_key="blank_slide",
            ratio=blank_slide_ratio,
            fallback_metric="edge_density",
            fallback_reverse=False,
        )
        issues.append(
            QualityIssue(
                slide_id=target_ids[0] if target_ids else sid,
                code="visual_blank_slide_ratio_high",
                message=f"blank_slide_ratio={blank_slide_ratio:.2f} exceeds limit={blank_slide_limit:.2f}",
                retry_scope="deck",
                retry_target_ids=target_ids,
            )
        )
    if low_contrast_ratio > low_contrast_limit:
        target_ids = _target_slide_ids_for_issue(
            issue_key="low_contrast",
            ratio=low_contrast_ratio,
            fallback_metric="contrast",
            fallback_reverse=False,
        )
        issues.append(
            QualityIssue(
                slide_id=target_ids[0] if target_ids else sid,
                code="visual_low_contrast_ratio_high",
                message=f"low_contrast_ratio={low_contrast_ratio:.2f} exceeds limit={low_contrast_limit:.2f}",
                retry_scope="deck",
                retry_target_ids=target_ids,
            )
        )
    if blank_area_ratio > blank_area_limit:
        target_ids = _target_slide_ids_for_issue(
            issue_key="excessive_whitespace",
            ratio=blank_area_ratio,
            fallback_metric="edge_density",
            fallback_reverse=False,
        )
        issues.append(
            QualityIssue(
                slide_id=target_ids[0] if target_ids else sid,
                code="visual_blank_area_ratio_high",
                message=f"blank_area_ratio={blank_area_ratio:.2f} exceeds limit={blank_area_limit:.2f}",
                retry_scope="deck",
                retry_target_ids=target_ids,
            )
        )
    if style_drift_ratio > style_drift_limit:
        target_ids = _target_slide_ids_for_issue(
            issue_key="style_inconsistent",
            ratio=style_drift_ratio,
            fallback_metric="mean_luminance",
            fallback_reverse=False,
        )
        issues.append(
            QualityIssue(
                slide_id=target_ids[0] if target_ids else sid,
                code="visual_style_drift_ratio_high",
                message=f"style_drift_ratio={style_drift_ratio:.2f} exceeds limit={style_drift_limit:.2f}",
                retry_scope="deck",
                retry_target_ids=target_ids,
            )
        )

    ratio_checks = [
        ("text_overlap", "visual_text_overlap_max_ratio", 0.75, "visual_text_overlap_ratio_high"),
        ("occlusion", "visual_occlusion_max_ratio", 0.75, "visual_occlusion_ratio_high"),
        ("card_overlap", "visual_card_overlap_max_ratio", 0.65, "visual_card_overlap_ratio_high"),
        ("title_crowded", "visual_title_crowded_max_ratio", 0.65, "visual_title_crowded_ratio_high"),
        ("multi_title_bar", "visual_multi_title_max_ratio", 0.50, "visual_multi_title_ratio_high"),
        ("text_overflow", "visual_text_overflow_max_ratio", 0.65, "visual_text_overflow_ratio_high"),
        ("irrelevant_image", "visual_irrelevant_image_max_ratio", 0.25, "visual_irrelevant_image_ratio_high"),
        ("image_distortion", "visual_image_distortion_max_ratio", 0.25, "visual_image_distortion_ratio_high"),
        ("excessive_whitespace", "visual_whitespace_max_ratio", 0.45, "visual_whitespace_ratio_high"),
        ("layout_monotony", "visual_layout_monotony_max_ratio", 0.45, "visual_layout_monotony_ratio_high"),
        ("style_inconsistent", "visual_style_inconsistent_max_ratio", 0.45, "visual_style_inconsistent_ratio_high"),
    ]
    for issue_code, threshold_key, default_limit, gate_code in ratio_checks:
        ratio = max(0.0, min(1.0, float(issue_ratios.get(issue_code) or 0.0)))
        limit = _threshold(threshold_key, default_limit)

        # Whitespace hard gate needs local corroboration; pure multimodal suspicion
        # should become score penalty rather than hard fail.
        if issue_code == "excessive_whitespace":
            local_ratio = max(0.0, min(1.0, float(local_issue_ratios.get(issue_code) or 0.0)))
            mm_ratio = max(0.0, min(1.0, float(multimodal_issue_ratios.get(issue_code) or 0.0)))
            if (
                ratio > limit
                and local_ratio <= max(0.15, limit * 0.45)
                and blank_area_ratio <= max(blank_area_limit, 0.45)
                and mm_ratio >= ratio
            ):
                continue

        # text_overlap must fail at boundary value too (>= limit).
        if issue_code == "text_overlap":
            if ratio < limit:
                continue
        elif ratio <= limit:
            continue
        affected = max(1, math.ceil(ratio * max(1, slide_count)))
        fallback_metric = "contrast"
        fallback_reverse = False
        if issue_code in {"excessive_whitespace", "layout_monotony"}:
            fallback_metric = "edge_density"
        elif issue_code in {"style_inconsistent"}:
            fallback_metric = "mean_luminance"
        target_ids = _target_slide_ids_for_issue(
            issue_key=issue_code,
            ratio=ratio,
            fallback_metric=fallback_metric,
            fallback_reverse=fallback_reverse,
        )
        issues.append(
            QualityIssue(
                slide_id=target_ids[0] if target_ids else sid,
                code=gate_code,
                message=(
                    f"{issue_code}_ratio={ratio:.2f} exceeds limit={limit:.2f} "
                    f"(estimated_affected_slides={affected})."
                ),
                retry_scope="deck",
                retry_target_ids=target_ids,
            )
        )

    return QualityResult(ok=len(issues) == 0, issues=issues)


def score_deck_quality(
    *,
    slides: List[Dict[str, Any]],
    render_spec: Optional[Dict[str, Any]] = None,
    profile: Optional[str | Dict[str, Any]] = None,
    content_issues: Optional[List[QualityIssue]] = None,
    layout_issues: Optional[List[QualityIssue]] = None,
    visual_audit: Optional[Dict[str, Any]] = None,
    enforce_visual_audit_presence: bool = False,
) -> QualityScoreResult:
    active_profile = _resolve_quality_profile(profile)
    content_result = (
        QualityResult(ok=not content_issues, issues=list(content_issues or []))
        if content_issues is not None
        else validate_deck(slides, profile=active_profile)
    )
    layout_result = (
        QualityResult(ok=not layout_issues, issues=list(layout_issues or []))
        if layout_issues is not None
        else validate_layout_diversity(
            render_spec if isinstance(render_spec, dict) else {"slides": slides},
            profile=active_profile,
        )
    )
    all_issues = [*content_result.issues, *layout_result.issues]
    issue_counts = _issue_counter(all_issues)
    scene_advisory_counts = _scene_advisory_issue_counts(slides, profile=profile)
    issue_counts.update(scene_advisory_counts)

    structure_penalties = {
        "blank_slide": 45,
        "encoding_invalid": 40,
        "placeholder_pollution": 22,
        "placeholder_chart_data": 16,
        "placeholder_kpi_data": 14,
        "image_missing": 12,
        "low_content_density": 10,
    }
    layout_penalties = {
        "layout_homogeneous": 32,
        "layout_top2_homogeneous": 24,
        "layout_adjacent_repeat": 14,
        "layout_abab_repeat": 16,
        "layout_variety_low": 12,
        "layout_density_consecutive_high": 18,
        "layout_density_window_missing_breathing": 18,
        "layout_terminal_cover_missing": 10,
        "layout_terminal_summary_missing": 10,
    }
    family_penalties = {
        "template_family_homogeneous": 26,
        "template_family_top2_homogeneous": 20,
        "template_family_switch_frequent": 20,
        "template_family_abab_repeat": 16,
    }
    visual_penalties = {
        "blank_area_high": 16,
        "chart_readability_low": 10,
        "visual_blank_slide_ratio_high": 22,
        "visual_low_contrast_ratio_high": 20,
        "visual_blank_area_ratio_high": 16,
        "visual_style_drift_ratio_high": 14,
        "visual_text_overlap_ratio_high": 24,
        "visual_occlusion_ratio_high": 22,
        "visual_card_overlap_ratio_high": 22,
        "visual_title_crowded_ratio_high": 14,
        "visual_multi_title_ratio_high": 16,
        "visual_text_overflow_ratio_high": 18,
        "visual_irrelevant_image_ratio_high": 16,
        "visual_image_distortion_ratio_high": 14,
        "visual_whitespace_ratio_high": 14,
        "visual_layout_monotony_ratio_high": 12,
        "visual_style_inconsistent_ratio_high": 14,
    }
    consistency_penalties = {
        "duplicate_text": 18,
        "title_echo": 16,
        "weak_emphasis": 12,
        "flat_typography": 12,
        "scene_status_report_title_generic": 10,
        "scene_investor_pitch_ask_blurry": 8,
        "scene_training_deck_interaction_missing": 8,
    }

    def _dimension_score(penalty_map: Dict[str, int]) -> float:
        penalty = 0.0
        for code, count in issue_counts.items():
            penalty += float(penalty_map.get(code, 0)) * float(count)
        return _clamp_100(100.0 - penalty)

    structure_score = _dimension_score(structure_penalties)
    layout_score = _dimension_score(layout_penalties)
    family_score = _dimension_score(family_penalties)
    visual_score = _dimension_score(visual_penalties)
    consistency_score = _dimension_score(consistency_penalties)

    layout_values = _slide_type_values(slides)
    if layout_values:
        variety_ratio = len(set(layout_values)) / max(1, len(layout_values))
        layout_score = _clamp_100(min(layout_score, 40.0 + 60.0 * variety_ratio))

    family_values = _template_family_values(slides)
    family_counts = Counter(family_values)
    if family_values:
        dominant_family_ratio = max(family_counts.values()) / max(1, len(family_values))
        top2_family_ratio = (
            sum(count for _, count in family_counts.most_common(2)) / max(1, len(family_values))
        )
        family_switch_ratio = _switch_ratio(family_values)
        family_score = _clamp_100(
            min(
                family_score,
                100.0
                - max(0.0, (dominant_family_ratio - float(active_profile.get("template_family_max_type_ratio") or 0.55)) * 120.0)
                - max(0.0, (top2_family_ratio - float(active_profile.get("template_family_max_top2_ratio") or 0.8)) * 90.0)
                - max(0.0, (family_switch_ratio - float(active_profile.get("template_family_max_switch_ratio") or 0.75)) * 80.0),
            )
        )
    else:
        dominant_family_ratio = 1.0
        top2_family_ratio = 1.0
        family_switch_ratio = 0.0

    visual_payload = visual_audit if isinstance(visual_audit, dict) else {}
    require_visual_audit = bool(active_profile.get("require_visual_audit", True))
    visual_audit_error = str(visual_payload.get("error") or "").strip() if isinstance(visual_payload, dict) else ""
    visual_audit_present = isinstance(visual_audit, dict) and bool(visual_payload) and not visual_audit_error
    visual_audit_missing_blocker = bool(
        enforce_visual_audit_presence
        and require_visual_audit
        and (not visual_audit_present)
    )
    if visual_audit_missing_blocker:
        issue_key = "visual_audit_unavailable" if visual_audit_error else "visual_audit_missing"
        issue_counts[issue_key] = int(issue_counts.get(issue_key, 0)) + 1
    blank_slide_ratio = max(0.0, min(1.0, float(visual_payload.get("blank_slide_ratio") or 0.0)))
    low_contrast_ratio = max(0.0, min(1.0, float(visual_payload.get("low_contrast_ratio") or 0.0)))
    blank_area_ratio = max(0.0, min(1.0, float(visual_payload.get("blank_area_ratio") or 0.0)))
    style_drift_ratio = max(0.0, min(1.0, float(visual_payload.get("style_drift_ratio") or 0.0)))
    mean_luminance = float(visual_payload.get("mean_luminance") or 128.0)
    multimodal_score = visual_payload.get("multimodal_score")
    multimodal_numeric = _to_number(multimodal_score)
    issue_ratios = visual_payload.get("issue_ratios") if isinstance(visual_payload.get("issue_ratios"), dict) else {}
    visual_issue_pressure = (
        max(0.0, min(1.0, float(issue_ratios.get("text_overlap") or 0.0))) * 0.22
        + max(0.0, min(1.0, float(issue_ratios.get("occlusion") or 0.0))) * 0.20
        + max(0.0, min(1.0, float(issue_ratios.get("card_overlap") or 0.0))) * 0.18
        + max(0.0, min(1.0, float(issue_ratios.get("title_crowded") or 0.0))) * 0.14
        + max(0.0, min(1.0, float(issue_ratios.get("multi_title_bar") or 0.0))) * 0.14
        + max(0.0, min(1.0, float(issue_ratios.get("text_overflow") or 0.0))) * 0.16
        + max(0.0, min(1.0, float(issue_ratios.get("irrelevant_image") or 0.0))) * 0.16
        + max(0.0, min(1.0, float(issue_ratios.get("image_distortion") or 0.0))) * 0.12
        + max(0.0, min(1.0, float(issue_ratios.get("excessive_whitespace") or 0.0))) * 0.12
        + max(0.0, min(1.0, float(issue_ratios.get("layout_monotony") or 0.0))) * 0.10
        + max(0.0, min(1.0, float(issue_ratios.get("style_inconsistent") or 0.0))) * 0.10
    )
    visual_score = _clamp_100(
        visual_score
        - (blank_slide_ratio * 40.0)
        - (low_contrast_ratio * 30.0)
        - (blank_area_ratio * 22.0)
        - (style_drift_ratio * 20.0)
        - (visual_issue_pressure * 80.0)
    )
    if mean_luminance < 25.0 or mean_luminance > 245.0:
        visual_score = _clamp_100(visual_score - 8.0)
    if multimodal_numeric is not None:
        visual_score = _clamp_100((visual_score * 0.7) + (_clamp_100(multimodal_numeric) * 0.3))

    weights = active_profile.get("quality_score_weights") or {}
    weighted_score = _clamp_100(
        (float(weights.get("structure", 0.26)) * structure_score)
        + (float(weights.get("layout", 0.20)) * layout_score)
        + (float(weights.get("family", 0.16)) * family_score)
        + (float(weights.get("visual", 0.22)) * visual_score)
        + (float(weights.get("consistency", 0.16)) * consistency_score)
    )
    threshold = float(active_profile.get("quality_score_threshold") or 72.0)
    warn_threshold = float(active_profile.get("quality_score_warn_threshold") or 80.0)
    fatal_codes = {"blank_slide", "encoding_invalid"}
    has_fatal = any(code in fatal_codes for code in issue_counts.keys())
    passed = (weighted_score >= threshold) and (not has_fatal) and (not visual_audit_missing_blocker)

    return QualityScoreResult(
        score=weighted_score,
        passed=passed,
        threshold=threshold,
        warn_threshold=warn_threshold,
        dimensions={
            "structure": structure_score,
            "layout": layout_score,
            "family": family_score,
            "visual": visual_score,
            "consistency": consistency_score,
        },
        issue_counts={code: int(count) for code, count in issue_counts.items()},
        diagnostics={
            "fatal_codes_present": sorted([code for code in issue_counts.keys() if code in fatal_codes]),
            "scene_rule_profile": _resolve_scene_profile(profile, slides=slides),
            "scene_rule_advisories": {code: int(count) for code, count in scene_advisory_counts.items()},
            "layout_variety_ratio": (
                len(set(layout_values)) / max(1, len(layout_values)) if layout_values else 0.0
            ),
            "template_family_dominant_ratio": dominant_family_ratio,
            "template_family_top2_ratio": top2_family_ratio,
            "template_family_switch_ratio": family_switch_ratio,
            "visual_blank_slide_ratio": blank_slide_ratio,
            "visual_low_contrast_ratio": low_contrast_ratio,
            "visual_blank_area_ratio": blank_area_ratio,
            "visual_style_drift_ratio": style_drift_ratio,
            "visual_issue_pressure": visual_issue_pressure,
            "visual_mean_luminance": mean_luminance,
            "visual_multimodal_score": multimodal_numeric,
            "visual_audit_required": require_visual_audit,
            "visual_audit_present": visual_audit_present,
            "visual_audit_error": visual_audit_error,
            "visual_audit_missing_blocker": visual_audit_missing_blocker,
        },
    )


_HIERARCHY_ISSUE_WEIGHTS: Dict[str, float] = {
    "visual_title_crowded_ratio_high": 1.0,
    "visual_multi_title_ratio_high": 1.0,
    "visual_text_overlap_ratio_high": 1.3,
    "visual_text_overflow_ratio_high": 1.0,
    "weak_emphasis": 0.9,
    "flat_typography": 0.9,
    "title_echo": 1.0,
}

_LAYOUT_ORDER_ABNORMAL_CODES = {
    "layout_homogeneous",
    "layout_top2_homogeneous",
    "layout_adjacent_repeat",
    "layout_abab_repeat",
    "layout_variety_low",
    "layout_density_consecutive_high",
    "layout_density_window_missing_breathing",
    "template_family_switch_frequent",
}

_ACCURACY_HARD_FAIL_CODES = {
    "encoding_invalid",
    "placeholder_pollution",
    "placeholder_chart_data",
    "placeholder_kpi_data",
}

_ACCURACY_TEXT_CODE_HINTS = (
    "fact",
    "accuracy",
    "halluc",
    "contrad",
    "mismatch",
    "incorrect",
    "fabricat",
)


def _clamp_10(value: float) -> float:
    return max(0.0, min(10.0, float(value)))


def _normalized_issue_codes(issue_codes: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for raw in issue_codes or []:
        code = str(raw or "").strip().lower()
        if code:
            out.append(code)
    return out


def _text_accuracy_failed(text_issue_codes: Optional[List[str]]) -> bool:
    for code in _normalized_issue_codes(text_issue_codes):
        if any(hint in code for hint in _ACCURACY_TEXT_CODE_HINTS):
            return True
    return False


def score_visual_professional_metrics(
    *,
    slides: Optional[List[Dict[str, Any]]] = None,
    quality_score: Optional[QualityScoreResult] = None,
    issue_codes: Optional[List[str]] = None,
    text_issue_codes: Optional[List[str]] = None,
    visual_audit: Optional[Dict[str, Any]] = None,
    profile: Optional[str | Dict[str, Any]] = None,
) -> VisualProfessionalScoreResult:
    """Canonical 0-10 visual-professional scoring used by online/offline flows."""
    if quality_score is None:
        quality_score = score_deck_quality(
            slides=list(slides or []),
            render_spec={"slides": list(slides or [])},
            profile=profile,
            visual_audit=visual_audit,
        )

    dims = quality_score.dimensions if isinstance(quality_score.dimensions, dict) else {}
    diags = quality_score.diagnostics if isinstance(quality_score.diagnostics, dict) else {}
    counts = quality_score.issue_counts if isinstance(quality_score.issue_counts, dict) else {}

    visual_score_10 = _clamp_10(float(dims.get("visual") or 0.0) / 10.0)
    layout_score_10 = _clamp_10(float(dims.get("layout") or 0.0) / 10.0)
    consistency_score_10 = _clamp_10(float(dims.get("consistency") or 0.0) / 10.0)
    style_drift_ratio = max(0.0, min(1.0, float(diags.get("visual_style_drift_ratio") or 0.0)))
    low_contrast_ratio = max(0.0, min(1.0, float(diags.get("visual_low_contrast_ratio") or 0.0)))
    issue_pressure = max(0.0, min(1.0, float(diags.get("visual_issue_pressure") or 0.0)))

    color_consistency_score = _clamp_10(
        (visual_score_10 * 0.60)
        + (consistency_score_10 * 0.40)
        - (style_drift_ratio * 2.50)
        - (low_contrast_ratio * 1.00)
    )
    layout_order_score = _clamp_10(
        (layout_score_10 * 0.70)
        + (visual_score_10 * 0.30)
        - (issue_pressure * 2.00)
    )

    hierarchy_penalty = 0.0
    for code, weight in _HIERARCHY_ISSUE_WEIGHTS.items():
        hierarchy_penalty += float(weight) * float(counts.get(code, 0))
    hierarchy_clarity_score = _clamp_10(
        (consistency_score_10 * 0.65)
        + (visual_score_10 * 0.35)
        - min(4.0, hierarchy_penalty * 0.60)
    )

    visual_avg_score = round(
        (color_consistency_score + layout_order_score + hierarchy_clarity_score) / 3.0,
        4,
    )

    normalized_issue_codes = _normalized_issue_codes(
        [*list(counts.keys()), *list(issue_codes or [])]
    )
    abnormal_tags: List[str] = []
    if style_drift_ratio >= 0.25:
        abnormal_tags.append("style_drift_high")
    if low_contrast_ratio >= 0.25:
        abnormal_tags.append("contrast_low")
    if issue_pressure >= 0.35:
        abnormal_tags.append("visual_issue_pressure_high")
    if any(code in _LAYOUT_ORDER_ABNORMAL_CODES for code in normalized_issue_codes):
        abnormal_tags.append("layout_order_risk")
    if _text_accuracy_failed(text_issue_codes):
        abnormal_tags.append("accuracy_risk")

    accuracy_gate_passed = (
        not any(code in _ACCURACY_HARD_FAIL_CODES for code in normalized_issue_codes)
        and not _text_accuracy_failed(text_issue_codes)
    )

    return VisualProfessionalScoreResult(
        color_consistency_score=round(color_consistency_score, 4),
        layout_order_score=round(layout_order_score, 4),
        hierarchy_clarity_score=round(hierarchy_clarity_score, 4),
        visual_avg_score=round(visual_avg_score, 4),
        accuracy_gate_passed=bool(accuracy_gate_passed),
        abnormal_tags=sorted(set(abnormal_tags)),
        diagnostics={
            "quality_dimensions": {
                "visual": round(visual_score_10, 4),
                "layout": round(layout_score_10, 4),
                "consistency": round(consistency_score_10, 4),
            },
            "style_drift_ratio": round(style_drift_ratio, 4),
            "low_contrast_ratio": round(low_contrast_ratio, 4),
            "visual_issue_pressure": round(issue_pressure, 4),
            "hierarchy_penalty": round(hierarchy_penalty, 4),
            "source_issue_codes": sorted(set(normalized_issue_codes)),
            "source_text_issue_codes": sorted(set(_normalized_issue_codes(text_issue_codes))),
        },
    )
