"""Reference-reconstruct input contract helpers.

Phase-1 objective: make required_facts / anchors / theme / media_manifest
explicit and fail-fast when critical fields are missing in strict mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence


_REQUIRED_REFERENCE_KEYS = ("slides", "theme", "media_manifest")
_REQUIRED_THEME_KEYS = ("primary", "secondary", "accent", "bg")


def _dedup_strings(values: Sequence[Any], *, limit: int) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def derive_anchors_from_slides(slides: Sequence[Any], *, limit: int = 8) -> List[str]:
    anchors: List[str] = []
    for slide in slides:
        if not isinstance(slide, Mapping):
            continue
        title = str(slide.get("title") or "").strip()
        if title:
            anchors.append(title)
    return _dedup_strings(anchors, limit=limit)


def derive_required_facts_from_slides(
    slides: Sequence[Any], *, limit: int = 20
) -> List[str]:
    facts: List[str] = []
    for idx, slide in enumerate(slides, start=1):
        if not isinstance(slide, Mapping):
            continue
        title = str(slide.get("title") or "").strip()
        if title:
            facts.append(f"第{idx}页必须体现：{title}")
        blocks = slide.get("blocks")
        if not isinstance(blocks, Sequence):
            continue
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            content = str(block.get("content") or "").strip()
            if len(content) >= 4:
                facts.append(f"保留关键文本片段：{content}")
        if len(facts) >= limit:
            break
    return _dedup_strings(facts, limit=limit)


@dataclass
class ReferenceContractAudit:
    reference_desc: Dict[str, Any]
    required_facts: List[str]
    anchors: List[str]
    errors: List[str]
    warnings: List[str]


def audit_reference_contract(
    *,
    reference_desc: Mapping[str, Any] | None,
    required_facts: Sequence[Any] | None = None,
    anchors: Sequence[Any] | None = None,
    strict: bool = True,
) -> ReferenceContractAudit:
    errors: List[str] = []
    warnings: List[str] = []

    ref: Dict[str, Any] = dict(reference_desc or {})
    if not isinstance(reference_desc, Mapping):
        errors.append("reference_desc must be an object")

    for key in _REQUIRED_REFERENCE_KEYS:
        if key not in ref:
            message = f"reference_desc.{key} is required"
            if key == "media_manifest" and not strict:
                warnings.append(message)
            else:
                errors.append(message)

    slides = ref.get("slides")
    if not isinstance(slides, list):
        errors.append("reference_desc.slides must be a list")
        slides = []

    theme = ref.get("theme")
    if not isinstance(theme, Mapping):
        errors.append("reference_desc.theme must be an object")
        theme = {}

    normalized_theme: Dict[str, Any] = dict(theme or {})
    missing_theme_keys: List[str] = []
    for key in _REQUIRED_THEME_KEYS:
        if key not in normalized_theme:
            missing_theme_keys.append(key)
            normalized_theme[key] = ""
        else:
            normalized_theme[key] = str(normalized_theme.get(key) or "").strip()
    if missing_theme_keys:
        message = "reference_desc.theme missing keys: " + ",".join(missing_theme_keys)
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    media_manifest = ref.get("media_manifest")
    if not isinstance(media_manifest, list):
        message = "reference_desc.media_manifest must be a list"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
        media_manifest = []

    derived_anchors = derive_anchors_from_slides(slides)
    derived_required_facts = derive_required_facts_from_slides(slides)

    normalized_anchors = _dedup_strings(
        anchors
        if anchors is not None
        else (
            ref.get("anchors")
            if isinstance(ref.get("anchors"), Sequence)
            and not isinstance(ref.get("anchors"), (str, bytes))
            else derived_anchors
        ),
        limit=12,
    )
    normalized_required_facts = _dedup_strings(
        required_facts
        if required_facts is not None
        else (
            ref.get("required_facts")
            if isinstance(ref.get("required_facts"), Sequence)
            and not isinstance(ref.get("required_facts"), (str, bytes))
            else derived_required_facts
        ),
        limit=20,
    )

    if not normalized_anchors:
        message = "anchors is empty"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)
    if not normalized_required_facts:
        message = "required_facts is empty"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    normalized_ref = dict(ref)
    normalized_ref["slides"] = slides
    normalized_ref["theme"] = normalized_theme
    normalized_ref["media_manifest"] = media_manifest
    normalized_ref["anchors"] = normalized_anchors
    normalized_ref["required_facts"] = normalized_required_facts
    if "theme_manifest" not in normalized_ref:
        normalized_ref["theme_manifest"] = []

    return ReferenceContractAudit(
        reference_desc=normalized_ref,
        required_facts=normalized_required_facts,
        anchors=normalized_anchors,
        errors=errors,
        warnings=warnings,
    )
