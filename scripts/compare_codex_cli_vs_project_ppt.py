#!/usr/bin/env python3
"""Compare Codex CLI + SKILL.md planning vs project main-path planning."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPO_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src import ppt_service_v2 as ppt_service  # type: ignore  # noqa: E402
from src.minimax_exporter import export_minimax_pptx  # type: ignore  # noqa: E402
from src.ppt_codex_skill_bridge import (  # type: ignore  # noqa: E402
    build_skill_specs_block,
    dedupe_skills,
    invoke_codex_cli_json,
    load_skill_specs,
    normalize_codex_cli_model_id,
    normalize_text,
)
from src.pptx_comparator import compare_pptx_files  # type: ignore  # noqa: E402


@dataclass(frozen=True)
class SkillCase:
    label: str
    skill_names: List[str]
    skill_roots: List[Path]


SKILL_CASES: Dict[str, SkillCase] = {
    "anthropic_pptx": SkillCase(
        label="anthropic_pptx",
        skill_names=["pptx"],
        skill_roots=[AGENT_ROOT / "tests" / "fixtures" / "skills_reference" / "anthropic" / "skills"],
    ),
    "minimax_pptx_generator": SkillCase(
        label="minimax_pptx_generator",
        skill_names=["pptx-generator"],
        skill_roots=[REPO_ROOT / "vendor" / "minimax-skills" / "skills"],
    ),
    "minimax_pptx_plugin": SkillCase(
        label="minimax_pptx_plugin",
        skill_names=[
            "ppt-orchestra-skill",
            "slide-making-skill",
            "design-style-skill",
            "color-font-skill",
            "ppt-editing-skill",
        ],
        skill_roots=[REPO_ROOT / "vendor" / "minimax-skills" / "plugins" / "pptx-plugin" / "skills"],
    ),
    "ppt_master": SkillCase(
        label="ppt_master",
        skill_names=["ppt-master"],
        skill_roots=[AGENT_ROOT / "tests" / "fixtures" / "skills_reference" / "ppt-master" / "skills"],
    ),
}


def _sample_payload() -> Dict[str, Any]:
    return {
        "title": "AI Product Strategy 2026",
        "author": "AutoViralVid",
        "slides": [
            {
                "slide_id": "s1",
                "page_number": 1,
                "slide_type": "cover",
                "title": "AI Product Strategy 2026",
                "blocks": [
                    {"block_type": "title", "content": "AI Product Strategy 2026"},
                    {"block_type": "subtitle", "content": "Roadmap, Execution, and KPIs"},
                ],
            },
            {
                "slide_id": "s2",
                "page_number": 2,
                "slide_type": "content",
                "title": "Strategic Goals",
                "blocks": [
                    {"block_type": "title", "content": "Strategic Goals"},
                    {"block_type": "body", "content": "Increase conversion by 20% through workflow automation."},
                    {"block_type": "body", "content": "Reduce support response time by 35%."},
                    {
                        "block_type": "chart",
                        "content": {"labels": ["Q1", "Q2", "Q3"], "datasets": [{"label": "Target", "data": [60, 75, 88]}]},
                    },
                ],
            },
            {
                "slide_id": "s3",
                "page_number": 3,
                "slide_type": "content",
                "title": "Execution Timeline",
                "blocks": [
                    {"block_type": "title", "content": "Execution Timeline"},
                    {"block_type": "workflow", "content": "Plan -> Build -> Validate -> Scale"},
                    {"block_type": "body", "content": "Each phase has measurable exit criteria."},
                ],
            },
            {
                "slide_id": "s4",
                "page_number": 4,
                "slide_type": "content",
                "title": "Capability Matrix",
                "blocks": [
                    {"block_type": "title", "content": "Capability Matrix"},
                    {"block_type": "matrix", "content": "Data, Model, Product, Ops capability dimensions."},
                    {"block_type": "body", "content": "Prioritize high-impact and high-feasibility items."},
                ],
            },
            {
                "slide_id": "s5",
                "page_number": 5,
                "slide_type": "summary",
                "title": "Summary and Next Steps",
                "blocks": [
                    {"block_type": "list", "content": "Finalize scope; lock milestones; launch pilot."},
                ],
            },
        ],
    }


def _read_payload(path: Path | None) -> Dict[str, Any]:
    if path is None:
        return _sample_payload()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("input payload must be a JSON object")
    slides = raw.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("input payload must contain non-empty slides[]")
    return raw


def _dedupe_skill_list(values: Any) -> List[str]:
    return dedupe_skills(values)


def _inject_case_skills(payload: Dict[str, Any], skill_names: List[str]) -> Dict[str, Any]:
    out = copy.deepcopy(payload)
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        existing = slide.get("load_skills") if isinstance(slide.get("load_skills"), list) else []
        slide["load_skills"] = _dedupe_skill_list([*existing, *skill_names])
    return out


def _project_plan_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    work = copy.deepcopy(payload)
    slides = work.get("slides") if isinstance(work.get("slides"), list) else []
    layer1 = ppt_service._run_layer1_design_skill_chain(  # type: ignore[attr-defined]
        deck_title=str(work.get("title") or "Untitled"),
        slides=[dict(item) for item in slides if isinstance(item, dict)],
        requested_style_variant=str(work.get("minimax_style_variant") or work.get("style_variant") or "auto"),
        requested_palette_key=str(work.get("minimax_palette_key") or work.get("palette_key") or "auto"),
        requested_template_family=str(work.get("template_family") or "auto"),
        requested_skill_profile=str(work.get("skill_profile") or "auto"),
    )
    style_variant = str(layer1.get("style_variant") or work.get("style_variant") or "auto")
    palette_key = str(layer1.get("palette_key") or work.get("palette_key") or "auto")
    template_family = str(layer1.get("template_family") or work.get("template_family") or "auto")
    skill_profile = str(layer1.get("skill_profile") or work.get("skill_profile") or "auto")
    work["style_variant"] = style_variant
    work["palette_key"] = palette_key
    work["template_family"] = template_family
    work["skill_profile"] = skill_profile
    work["theme"] = {"style": style_variant, "palette": palette_key}
    planned = ppt_service._apply_skill_planning_to_render_payload(work)  # type: ignore[attr-defined]
    return planned if isinstance(planned, dict) else work


def _build_codex_plan_prompt(
    *,
    payload: Dict[str, Any],
    case: SkillCase,
) -> str:
    docs = load_skill_specs(
        requested_skills=case.skill_names,
        skill_roots=case.skill_roots,
        aliases={"pptx": "pptx-generator"},
    )
    skill_block = build_skill_specs_block(
        docs,
        max_chars=max(4000, int(str(os.getenv("PPT_CODEX_SKILL_DOC_MAX_CHARS", "160000")).strip() or "160000")),
    )
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "You are a PPT planning specialist. Use the loaded SKILL.md specs as strict constraints.\n"
        "Return JSON only. No markdown.\n"
        "Output schema:\n"
        "{\n"
        '  "deck_patch": {"style_variant"?: string, "palette_key"?: string, "template_family"?: string, "skill_profile"?: string},\n'
        '  "slides": [\n'
        '    {"slide_id": string, "slide_patch": object, "load_skills": string[], "notes"?: string}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        f"- slides[] must cover each input slide_id exactly once in order.\n"
        "- slide_patch only includes planning keys: slide_type, layout_grid, render_path, template_family, "
        "skill_profile, style_variant, palette_key, agent_type, skill_directives, text_constraints, image_policy, page_design_intent.\n"
        "- load_skills must include all requested case skills.\n\n"
        "Loaded skills:\n\n"
        f"{skill_block}\n\n"
        "Input payload:\n"
        f"{payload_text}\n"
    )


def _codex_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["deck_patch", "slides"],
        "properties": {
            "deck_patch": {"type": "object"},
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["slide_id", "slide_patch", "load_skills"],
                    "properties": {
                        "slide_id": {"type": "string"},
                        "slide_patch": {"type": "object"},
                        "load_skills": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    }


def _apply_codex_plan(payload: Dict[str, Any], plan: Dict[str, Any], case_skills: List[str]) -> Dict[str, Any]:
    out = copy.deepcopy(payload)
    deck_patch = plan.get("deck_patch") if isinstance(plan.get("deck_patch"), dict) else {}
    for key in ("style_variant", "palette_key", "template_family", "skill_profile"):
        value = normalize_text(deck_patch.get(key), "")
        if value:
            out[key] = value
    if normalize_text(out.get("style_variant"), "") or normalize_text(out.get("palette_key"), ""):
        out["theme"] = {
            "style": normalize_text(out.get("style_variant"), "auto"),
            "palette": normalize_text(out.get("palette_key"), "auto"),
        }

    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    plan_rows = plan.get("slides") if isinstance(plan.get("slides"), list) else []
    by_id: Dict[str, Dict[str, Any]] = {}
    for row in plan_rows:
        if not isinstance(row, dict):
            continue
        slide_id = normalize_text(row.get("slide_id"), "")
        if not slide_id:
            continue
        by_id[slide_id] = row

    allowed_patch_keys = {
        "slide_type",
        "layout_grid",
        "render_path",
        "template_family",
        "skill_profile",
        "style_variant",
        "palette_key",
        "agent_type",
        "skill_directives",
        "text_constraints",
        "image_policy",
        "page_design_intent",
    }
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        slide_id = normalize_text(slide.get("slide_id") or slide.get("id"), f"slide-{idx + 1}")
        row = by_id.get(slide_id, {})
        slide_patch = row.get("slide_patch") if isinstance(row.get("slide_patch"), dict) else {}
        for key, value in slide_patch.items():
            if key not in allowed_patch_keys:
                continue
            slide[key] = value
        load_skills = row.get("load_skills") if isinstance(row.get("load_skills"), list) else []
        existing = slide.get("load_skills") if isinstance(slide.get("load_skills"), list) else []
        slide["load_skills"] = _dedupe_skill_list([*existing, *case_skills, *load_skills])
    return out


def _codex_plan_payload(
    payload: Dict[str, Any],
    *,
    case: SkillCase,
    model_id: str,
    timeout_sec: int,
) -> Dict[str, Any]:
    prompt = _build_codex_plan_prompt(payload=payload, case=case)
    invoked = invoke_codex_cli_json(
        prompt=prompt,
        schema=None,
        model_id=normalize_codex_cli_model_id(model_id),
        timeout_sec=timeout_sec,
        bin_name=normalize_text(os.getenv("PPT_CODEX_CLI_BIN", ""), "codex"),
        extra_args=[],
        cwd=REPO_ROOT,
    )
    if not bool(invoked.get("ok")):
        raise RuntimeError(normalize_text(invoked.get("reason"), "codex_plan_failed"))
    plan = invoked.get("data") if isinstance(invoked.get("data"), dict) else {}
    if not plan:
        raise RuntimeError("codex_plan_empty")
    return _apply_codex_plan(payload, plan, case.skill_names)


def _render_pptx_bytes(payload: Dict[str, Any], *, timeout_sec: int) -> Dict[str, Any]:
    safe_payload = copy.deepcopy(payload)
    safe_slides = safe_payload.get("slides") if isinstance(safe_payload.get("slides"), list) else []
    for idx, slide in enumerate(safe_slides):
        if not isinstance(slide, dict):
            continue
        blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
        has_title = False
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = normalize_text(block.get("block_type") or block.get("type"), "").lower()
            if block_type == "title":
                has_title = True
                break
        if not has_title:
            title_text = normalize_text(slide.get("title"), f"Slide {idx + 1}")
            blocks = [{"block_type": "title", "content": title_text}, *blocks]
            slide["blocks"] = blocks

    slides = safe_payload.get("slides") if isinstance(safe_payload.get("slides"), list) else []
    result = export_minimax_pptx(
        slides=[dict(item) for item in slides if isinstance(item, dict)],
        title=str(safe_payload.get("title") or "Untitled"),
        author=str(safe_payload.get("author") or "AutoViralVid"),
        style_variant=str(safe_payload.get("style_variant") or safe_payload.get("minimax_style_variant") or "auto"),
        palette_key=str(safe_payload.get("palette_key") or safe_payload.get("minimax_palette_key") or "auto"),
        template_family=str(safe_payload.get("template_family") or "auto"),
        skill_profile=str(safe_payload.get("skill_profile") or "auto"),
        route_mode="standard",
        render_channel="local",
        generator_mode="official",
        timeout=max(120, int(timeout_sec)),
    )
    return result


def _save_case_artifacts(
    *,
    output_dir: Path,
    case: SkillCase,
    project_payload: Dict[str, Any],
    codex_payload: Dict[str, Any],
    project_bytes: bytes,
    codex_bytes: bytes,
    report: Dict[str, Any],
) -> None:
    case_dir = output_dir / case.label
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "project.payload.json").write_text(json.dumps(project_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (case_dir / "codex.payload.json").write_text(json.dumps(codex_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (case_dir / "project.pptx").write_bytes(project_bytes)
    (case_dir / "codex.pptx").write_bytes(codex_bytes)
    (case_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_case(
    *,
    payload: Dict[str, Any],
    case: SkillCase,
    model_id: str,
    codex_timeout_sec: int,
    export_timeout_sec: int,
    output_dir: Path,
) -> Dict[str, Any]:
    seeded = _inject_case_skills(payload, case.skill_names)
    project_payload = _project_plan_payload(seeded)
    codex_payload = _codex_plan_payload(
        seeded,
        case=case,
        model_id=model_id,
        timeout_sec=codex_timeout_sec,
    )
    project_result = _render_pptx_bytes(project_payload, timeout_sec=export_timeout_sec)
    codex_result = _render_pptx_bytes(codex_payload, timeout_sec=export_timeout_sec)
    project_bytes = project_result.get("pptx_bytes") if isinstance(project_result.get("pptx_bytes"), (bytes, bytearray)) else b""
    codex_bytes = codex_result.get("pptx_bytes") if isinstance(codex_result.get("pptx_bytes"), (bytes, bytearray)) else b""
    if not project_bytes or not codex_bytes:
        raise RuntimeError("pptx_bytes_missing")

    tmp_project = output_dir / case.label / "tmp_project.pptx"
    tmp_codex = output_dir / case.label / "tmp_codex.pptx"
    tmp_project.parent.mkdir(parents=True, exist_ok=True)
    tmp_project.write_bytes(project_bytes)
    tmp_codex.write_bytes(codex_bytes)
    compare = compare_pptx_files(str(tmp_project), str(tmp_codex))
    report = asdict(compare)
    report_summary = {
        "case": case.label,
        "overall_score": report.get("overall_score"),
        "structure_score": report.get("structure_score"),
        "content_score": report.get("content_score"),
        "visual_style_score": report.get("visual_style_score"),
        "geometry_score": report.get("geometry_score"),
        "metadata_score": report.get("metadata_score"),
        "issues": (report.get("issues") or [])[:12],
    }
    _save_case_artifacts(
        output_dir=output_dir,
        case=case,
        project_payload=project_payload,
        codex_payload=codex_payload,
        project_bytes=project_bytes,
        codex_bytes=codex_bytes,
        report=report,
    )
    try:
        tmp_project.unlink(missing_ok=True)  # type: ignore[arg-type]
        tmp_codex.unlink(missing_ok=True)  # type: ignore[arg-type]
    except Exception:
        pass
    return report_summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="", help="Optional JSON payload path containing slides[]")
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        default=[],
        help=f"Case label. Repeatable. Available: {', '.join(sorted(SKILL_CASES.keys()))}",
    )
    parser.add_argument("--model", default=str(os.getenv("CONTENT_LLM_MODEL", "")).strip(), help="Codex model id")
    parser.add_argument("--codex-timeout-sec", type=int, default=120)
    parser.add_argument("--export-timeout-sec", type=int, default=240)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--output-dir", default="")
    parser.add_argument(
        "--enable-module-subagent",
        action="store_true",
        help="Enable module subagent execution during PPT export (default off for deterministic parity runs).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input).resolve() if str(args.input).strip() else None
    payload = _read_payload(input_path)
    if not bool(args.enable_module_subagent):
        os.environ["PPT_MODULE_SUBAGENT_EXEC_ENABLED"] = "false"
    selected = args.cases or list(SKILL_CASES.keys())
    cases: List[SkillCase] = []
    for label in selected:
        key = normalize_text(label, "")
        if key not in SKILL_CASES:
            raise ValueError(f"unknown case: {label}")
        cases.append(SKILL_CASES[key])

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = (REPO_ROOT / "test_reports" / f"codex_cli_parity_{stamp}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model_id = normalize_text(args.model, "")
    summaries: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for case in cases:
        try:
            summary = _run_case(
                payload=payload,
                case=case,
                model_id=model_id,
                codex_timeout_sec=int(args.codex_timeout_sec),
                export_timeout_sec=int(args.export_timeout_sec),
                output_dir=output_dir,
            )
            summaries.append(summary)
            print(f"[ok] {case.label}: overall={summary['overall_score']:.2f}")
        except Exception as exc:
            fail = {"case": case.label, "error": str(exc)}
            failures.append(fail)
            print(f"[fail] {case.label}: {exc}")

    report = {
        "input": str(input_path) if input_path else "<built-in sample>",
        "model": model_id or "<codex default>",
        "cases": summaries,
        "failures": failures,
        "generated_at": datetime.now().isoformat(),
    }
    report_path = output_dir / "summary.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {report_path}")

    min_score = float(args.min_score or 0.0)
    if failures:
        return 2
    if min_score > 0:
        for row in summaries:
            score = float(row.get("overall_score") or 0.0)
            if score < min_score:
                return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


