"""Shared MiniMax PPTX export helper."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from src.ppt_failure_classifier import FailureClassification, classify_failure
from src.ppt_template_catalog import (
    list_template_ids,
    resolve_template_for_slide,
    template_profiles,
)

logger = logging.getLogger("minimax_exporter")

_TEMPLATE_ID_SET = set(list_template_ids())


def _allow_legacy_mode() -> bool:
    return str(os.getenv("PPT_ALLOW_LEGACY_MODE", "false")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _extract_json_from_stdout(stdout: str) -> Dict[str, Any]:
    for line in reversed((stdout or "").splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


class MiniMaxExportError(RuntimeError):
    """Structured export error with retry classification metadata."""

    def __init__(
        self,
        *,
        message: str,
        classification: FailureClassification,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": str(self),
            "failure_code": self.classification.code,
            "retryable": self.classification.retryable,
            "max_attempts": self.classification.max_attempts,
            "base_delay_ms": self.classification.base_delay_ms,
            "failure_detail": self.detail[:1200],
        }


def _stable_slide_id(slide: Dict[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "page_number"):
        value = slide.get(key)
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate:
            return candidate
    return f"slide-{index + 1}"


def _normalize_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, raw in enumerate(slides):
        slide = dict(raw or {})
        slide["slide_id"] = _stable_slide_id(slide, idx)
        elements = slide.get("elements")
        if isinstance(elements, list):
            fixed_elements = []
            for block_idx, item in enumerate(elements):
                if not isinstance(item, dict):
                    fixed_elements.append(item)
                    continue
                el = dict(item)
                if not str(el.get("block_id") or "").strip():
                    fallback = str(el.get("id") or "").strip() or f"{slide['slide_id']}-block-{block_idx + 1}"
                    el["block_id"] = fallback
                fixed_elements.append(el)
            slide["elements"] = fixed_elements
        normalized.append(slide)
    return normalized


def _normalize_generator_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "legacy" and _allow_legacy_mode():
        return "legacy"
    return "official"


def _normalize_render_channel(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"local", "remote"}:
        return normalized
    return "local"


def _infer_slide_type(slide: Dict[str, Any], index: int, total: int) -> str:
    explicit = str(slide.get("slide_type") or slide.get("type") or "").strip().lower()
    if explicit:
        return explicit
    if index == 0:
        return "cover"
    if index == max(0, total - 1):
        return "summary"
    return "content"


def _infer_template_family(slide: Dict[str, Any], *, slide_type: str, layout_grid: str) -> str:
    explicit = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
    if explicit in _TEMPLATE_ID_SET:
        return explicit
    return resolve_template_for_slide(
        slide=slide,
        slide_type=slide_type,
        layout_grid=layout_grid,
        requested_template="",
        desired_density=str(slide.get("content_density") or "balanced"),
    )


def _template_profiles(template_family: str) -> Dict[str, str]:
    return template_profiles(template_family)


def _normalize_contract_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = _normalize_slides(slides)
    total = len(normalized)
    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(normalized):
        slide = dict(raw)
        slide_type = _infer_slide_type(slide, idx, total)
        layout_grid = (
            str(slide.get("layout_grid") or slide.get("layout") or "").strip()
            or ("hero_1" if slide_type in {"cover", "summary"} else "split_2")
        )
        page_number = slide.get("page_number")
        if page_number is None:
            page_number = idx + 1
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            blocks = []

        slide["page_number"] = int(page_number)
        slide["slide_type"] = slide_type
        slide["layout_grid"] = layout_grid
        template_family = _infer_template_family(slide, slide_type=slide_type, layout_grid=layout_grid)
        profiles = _template_profiles(template_family)
        slide["template_family"] = profiles["template_id"]
        slide["template_id"] = str(slide.get("template_id") or profiles["template_id"])
        slide["skill_profile"] = str(slide.get("skill_profile") or profiles["skill_profile"])
        slide["hardness_profile"] = str(slide.get("hardness_profile") or profiles["hardness_profile"])
        slide["schema_profile"] = str(slide.get("schema_profile") or profiles["schema_profile"])
        slide["contract_profile"] = str(slide.get("contract_profile") or profiles["contract_profile"])
        slide["quality_profile"] = str(slide.get("quality_profile") or profiles["quality_profile"])
        slide["blocks"] = blocks
        slide["bg_style"] = str(slide.get("bg_style") or "light")
        keywords = slide.get("image_keywords")
        if not isinstance(keywords, list):
            keywords = []
        slide["image_keywords"] = [str(item).strip() for item in keywords if str(item).strip()]
        out.append(slide)
    return out


def build_payload(
    *,
    slides: List[Dict[str, Any]],
    title: str,
    author: str,
    style_variant: str = "auto",
    palette_key: str = "auto",
    verbatim_content: bool = False,
    deck_id: str = "",
    retry_scope: str = "deck",
    target_slide_ids: List[str] | None = None,
    target_block_ids: List[str] | None = None,
    retry_hint: str = "",
    idempotency_key: str = "",
    render_channel: str = "local",
    generator_mode: str = "official",
    enable_legacy_fallback: bool = False,
    original_style: bool = True,
    disable_local_style_rewrite: bool = True,
    visual_priority: bool = True,
    visual_preset: str = "auto",
    visual_density: str = "balanced",
    constraint_hardness: str = "minimal",
    svg_mode: str = "on",
    template_family: str = "auto",
    template_id: str = "",
    skill_profile: str = "",
    hardness_profile: str = "",
    schema_profile: str = "",
    contract_profile: str = "",
    quality_profile: str = "",
    enforce_visual_contract: bool = True,
) -> Dict[str, Any]:
    mode = _normalize_generator_mode(generator_mode)
    channel = _normalize_render_channel(render_channel)
    preserve_original = bool(original_style)
    disable_rewrite = bool(disable_local_style_rewrite) or preserve_original
    normalized_slides = _normalize_contract_slides(slides)
    primary_template = (
        str(normalized_slides[0].get("template_family") or "dashboard_dark")
        if normalized_slides
        else "dashboard_dark"
    )
    deck_profiles = _template_profiles(primary_template)
    theme = {
        "palette": str(palette_key or "auto").strip() or "auto",
        "style": str(style_variant or "auto").strip() or "auto",
    }
    resolved_template_id = str(template_id or deck_profiles["template_id"]).strip() or deck_profiles["template_id"]
    return {
        "slides": normalized_slides,
        "title": title,
        "author": author,
        "theme": theme,
        "render_channel": channel,
        "generator_mode": mode,
        "enable_legacy_fallback": bool(enable_legacy_fallback),
        "minimax_style_variant": theme["style"],
        "minimax_palette_key": theme["palette"],
        "verbatim_content": bool(verbatim_content),
        "deck_id": deck_id,
        "retry_scope": retry_scope,
        "target_slide_ids": [s for s in (target_slide_ids or []) if str(s).strip()],
        "target_block_ids": [s for s in (target_block_ids or []) if str(s).strip()],
        "retry_hint": retry_hint,
        "idempotency_key": idempotency_key,
        "original_style": preserve_original,
        "disable_local_style_rewrite": disable_rewrite,
        "visual_priority": bool(visual_priority),
        "visual_preset": str(visual_preset or "auto"),
        "visual_density": str(visual_density or "balanced"),
        "constraint_hardness": str(constraint_hardness or "minimal"),
        "svg_mode": str(svg_mode or "on"),
        "template_family": str(template_family or resolved_template_id or "auto"),
        "template_id": resolved_template_id,
        "skill_profile": str(skill_profile or deck_profiles["skill_profile"]),
        "hardness_profile": str(hardness_profile or deck_profiles["hardness_profile"]),
        "schema_profile": str(schema_profile or deck_profiles["schema_profile"]),
        "contract_profile": str(contract_profile or deck_profiles["contract_profile"]),
        "quality_profile": str(quality_profile or deck_profiles["quality_profile"]),
        "enforce_visual_contract": bool(enforce_visual_contract),
    }


def export_minimax_pptx(
    *,
    slides: List[Dict[str, Any]],
    title: str,
    author: str,
    style_variant: str = "auto",
    palette_key: str = "auto",
    verbatim_content: bool = False,
    deck_id: str = "",
    retry_scope: str = "deck",
    target_slide_ids: List[str] | None = None,
    target_block_ids: List[str] | None = None,
    retry_hint: str = "",
    idempotency_key: str = "",
    render_channel: str = "local",
    generator_mode: str = "official",
    enable_legacy_fallback: bool = False,
    original_style: bool = True,
    disable_local_style_rewrite: bool = True,
    visual_priority: bool = True,
    visual_preset: str = "auto",
    visual_density: str = "balanced",
    constraint_hardness: str = "minimal",
    svg_mode: str = "on",
    template_family: str = "auto",
    template_id: str = "",
    skill_profile: str = "",
    hardness_profile: str = "",
    schema_profile: str = "",
    contract_profile: str = "",
    quality_profile: str = "",
    enforce_visual_contract: bool = True,
    timeout: int = 180,
) -> Dict[str, Any]:
    scripts_root = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_root / "generate-pptx-minimax.mjs"
    if not script_path.exists():
        raise FileNotFoundError(f"MiniMax PPTX script not found: {script_path}")

    payload = build_payload(
        slides=slides,
        title=title,
        author=author,
        style_variant=style_variant,
        palette_key=palette_key,
        verbatim_content=verbatim_content,
        deck_id=deck_id,
        retry_scope=retry_scope,
        target_slide_ids=target_slide_ids,
        target_block_ids=target_block_ids,
        retry_hint=retry_hint,
        idempotency_key=idempotency_key,
        render_channel=render_channel,
        generator_mode=generator_mode,
        enable_legacy_fallback=enable_legacy_fallback,
        original_style=original_style,
        disable_local_style_rewrite=disable_local_style_rewrite,
        visual_priority=visual_priority,
        visual_preset=visual_preset,
        visual_density=visual_density,
        constraint_hardness=constraint_hardness,
        svg_mode=svg_mode,
        template_family=template_family,
        template_id=template_id,
        skill_profile=skill_profile,
        hardness_profile=hardness_profile,
        schema_profile=schema_profile,
        contract_profile=contract_profile,
        quality_profile=quality_profile,
        enforce_visual_contract=enforce_visual_contract,
    )

    requested_channel = _normalize_render_channel(payload.get("render_channel"))
    effective_channel = "local"
    channel_fallback_reason = ""
    if requested_channel == "remote":
        channel_fallback_reason = (
            "remote_channel_not_configured: current deployment uses local pptx-plugin rendering"
        )
        logger.warning("[minimax_exporter] %s", channel_fallback_reason)

    input_path: Path | None = None
    output_path: Path | None = None
    render_spec_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as f:
            json.dump(payload, f, ensure_ascii=False)
            input_path = Path(f.name)

        output_path = input_path.with_suffix(".pptx")
        render_spec_path = input_path.with_suffix(".render.json")

        cmd = [
            "node",
            str(script_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--render-output",
            str(render_spec_path),
            "--retry-scope",
            str(retry_scope or "deck"),
            "--generator-mode",
            payload["generator_mode"],
        ]
        if deck_id:
            cmd.extend(["--deck-id", deck_id])
        if target_slide_ids:
            cmd.extend(["--target-slide-ids", ",".join(target_slide_ids)])
        if target_block_ids:
            cmd.extend(["--target-block-ids", ",".join(target_block_ids)])
        if retry_hint:
            cmd.extend(["--retry-hint", retry_hint[:1500]])
        if idempotency_key:
            cmd.extend(["--idempotency-key", idempotency_key])
        if verbatim_content:
            cmd.append("--verbatim-content")
        if original_style:
            cmd.append("--original-style")
        if disable_local_style_rewrite:
            cmd.append("--disable-local-style-rewrite")
        if visual_priority:
            cmd.append("--visual-priority")
        if str(visual_preset or "").strip():
            cmd.extend(["--visual-preset", str(visual_preset).strip()])
        if str(visual_density or "").strip():
            cmd.extend(["--visual-density", str(visual_density).strip()])
        if str(constraint_hardness or "").strip():
            cmd.extend(["--constraint-hardness", str(constraint_hardness).strip()])

        def _run(export_cmd: List[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                export_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        result = _run(cmd)
        effective_mode = payload["generator_mode"]
        fallback_used = False
        legacy_fallback_enabled = bool(enable_legacy_fallback) and _allow_legacy_mode()
        if (
            result.returncode != 0
            and payload["generator_mode"] == "official"
            and legacy_fallback_enabled
        ):
            fallback_cmd: List[str] = []
            skip_next = False
            for part in cmd:
                if skip_next:
                    skip_next = False
                    continue
                if part == "--generator-mode":
                    skip_next = True
                    continue
                fallback_cmd.append(part)
            fallback_cmd.extend(["--generator-mode", "legacy"])
            result = _run(fallback_cmd)
            effective_mode = "legacy"
            fallback_used = True

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            classification = classify_failure(detail)
            raise MiniMaxExportError(
                message=f"MiniMax PPTX export failed: {detail[:800]}",
                classification=classification,
                detail=detail,
            )
        if not output_path.exists():
            detail = "MiniMax PPTX export reported success but file was not created"
            classification = classify_failure(detail)
            raise MiniMaxExportError(
                message=detail,
                classification=classification,
                detail=detail,
            )

        render_spec: Dict[str, Any] = {}
        if render_spec_path.exists():
            try:
                parsed = json.loads(render_spec_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    render_spec = parsed
            except Exception as exc:
                logger.warning("failed to parse minimax render spec: %s", exc)

        generator_meta = _extract_json_from_stdout(result.stdout)
        if fallback_used:
            generator_meta["fallback_used"] = True
            generator_meta["generator_mode"] = effective_mode
        if channel_fallback_reason:
            generator_meta["channel_fallback_used"] = True
            generator_meta["channel_fallback_reason"] = channel_fallback_reason
        generator_meta["render_channel"] = effective_channel

        return {
            "pptx_bytes": output_path.read_bytes(),
            "generator_meta": generator_meta,
            "render_spec": render_spec,
            "input_payload": {
                **payload,
                "generator_mode": effective_mode,
                "render_channel": effective_channel,
                "requested_render_channel": requested_channel,
            },
            "generator_mode": effective_mode,
            "render_channel": effective_channel,
        }
    except subprocess.TimeoutExpired as exc:
        detail = f"subprocess.TimeoutExpired: {exc}"
        classification = classify_failure(detail)
        raise MiniMaxExportError(
            message=f"MiniMax PPTX export timeout after {timeout}s",
            classification=classification,
            detail=detail,
        ) from exc
    except MiniMaxExportError:
        raise
    except Exception as exc:
        detail = str(exc)
        classification = classify_failure(detail)
        raise MiniMaxExportError(
            message=f"MiniMax PPTX export failed: {detail[:800]}",
            classification=classification,
            detail=detail,
        ) from exc
    finally:
        for path in (input_path, output_path, render_spec_path):
            if path and path.exists():
                try:
                    path.unlink()
                except Exception:
                    logger.debug("failed to cleanup temp file: %s", path, exc_info=True)

