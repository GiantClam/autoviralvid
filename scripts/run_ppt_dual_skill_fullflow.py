"""
Run end-to-end PPT -> Remotion video generation for two MiniMax style variants.

Flow per variant:
1) Generate PPTX from the same slides input.
2) Parse generated PPTX back into SlideContent[].
3) Render video via scripts/render-local.mjs (Remotion).

Usage:
  python scripts/run_ppt_dual_skill_fullflow.py \
    --slides test_outputs/ppt_generation/slides.json \
    --output-dir test_outputs/ppt_dual_skill_fullflow
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLIDES = ROOT / "test_outputs" / "ppt_generation" / "slides.json"
DEFAULT_OUTPUT = ROOT / "test_outputs" / "ppt_dual_skill_fullflow"

MINIMAX_GEN = ROOT / "scripts" / "generate-pptx-minimax.mjs"
RENDER_LOCAL = ROOT / "scripts" / "render-local.mjs"


def load_slides(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"slides JSON must be an array: {path}")
    return data


def run_command(cmd: list[str], cwd: Path, timeout_sec: int) -> tuple[int, str, str]:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return elapsed_ms, proc.stdout.strip(), proc.stderr.strip()


def parse_pptx_to_slides(pptx_path: Path) -> list[dict[str, Any]]:
    agent_root = ROOT / "agent"
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    from src.document_parser import _parse_pptx_sync  # type: ignore

    parsed = _parse_pptx_sync(str(pptx_path))
    return [s.model_dump() for s in parsed.slides]


def generate_skill_outputs(
    skill: str,
    slides: list[dict[str, Any]],
    output_dir: Path,
    title: str,
    author: str,
    render_width: int,
    render_height: int,
    render_fps: int,
    minimax_style: str,
    minimax_palette: str,
) -> dict[str, Any]:
    skill_dir = output_dir / skill
    skill_dir.mkdir(parents=True, exist_ok=True)

    export_req = skill_dir / "export_req.json"
    export_req.write_text(
        json.dumps(
            {
                "slides": slides,
                "title": title,
                "author": author,
                "minimax_style_variant": minimax_style,
                "minimax_palette_key": minimax_palette,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    pptx_path = skill_dir / f"{skill}.pptx"
    render_spec_path = skill_dir / "render_spec.json"
    effective_style = minimax_style
    if skill == "minimax_auto":
        effective_style = "auto"
    elif skill == "minimax_sharp":
        effective_style = "sharp"

    gen_cmd = [
        "node",
        str(MINIMAX_GEN),
        "--input",
        str(export_req),
        "--output",
        str(pptx_path),
        "--style",
        effective_style,
        "--palette",
        minimax_palette,
        "--render-output",
        str(render_spec_path),
    ]
    gen_ms, gen_stdout, _ = run_command(gen_cmd, ROOT, timeout_sec=240)

    render_source = "parsed_pptx"
    parsed_slides: list[dict[str, Any]]
    if render_spec_path.exists():
        try:
            render_spec = json.loads(render_spec_path.read_text(encoding="utf-8"))
            generated_slides = render_spec.get("slides") if isinstance(render_spec, dict) else None
            if isinstance(generated_slides, list) and generated_slides:
                parsed_slides = generated_slides
                render_source = "generator_render_spec"
            else:
                parsed_slides = parse_pptx_to_slides(pptx_path)
        except Exception:
            parsed_slides = parse_pptx_to_slides(pptx_path)
    else:
        parsed_slides = parse_pptx_to_slides(pptx_path)

    parsed_json = skill_dir / "parsed_slides.json"
    parsed_json.write_text(json.dumps(parsed_slides, ensure_ascii=False, indent=2), encoding="utf-8")

    render_input = skill_dir / "render_input.json"
    render_input.write_text(
        json.dumps(
            {
                "slides": parsed_slides,
                "config": {
                    "width": render_width,
                    "height": render_height,
                    "fps": render_fps,
                    "transition": "fade",
                    "include_narration": False,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    mp4_path = skill_dir / f"{skill}.mp4"
    render_cmd = ["node", str(RENDER_LOCAL), "--input", str(render_input), "--output", str(mp4_path)]
    render_ms, render_stdout, _ = run_command(render_cmd, ROOT, timeout_sec=900)

    return {
        "skill": skill,
        "pptx": str(pptx_path),
        "pptx_size_bytes": pptx_path.stat().st_size if pptx_path.exists() else 0,
        "parsed_slides": str(parsed_json),
        "parsed_slide_count": len(parsed_slides),
        "video_source": render_source,
        "video": str(mp4_path),
        "video_size_bytes": mp4_path.stat().st_size if mp4_path.exists() else 0,
        "style_variant": effective_style,
        "timing_ms": {
            "pptx_generation": gen_ms,
            "video_render": render_ms,
        },
        "generator_stdout": gen_stdout,
        "render_stdout_tail": render_stdout[-1200:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slides", default=str(DEFAULT_SLIDES), help="Path to slides.json array")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--title", default="PPT Skill Fullflow Compare")
    parser.add_argument("--author", default="AutoViralVid")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--minimax-style", default="auto")
    parser.add_argument("--minimax-palette", default="auto")
    args = parser.parse_args()

    slides_path = Path(args.slides).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not slides_path.exists():
        raise FileNotFoundError(f"slides file not found: {slides_path}")

    slides = load_slides(slides_path)
    if not slides:
        raise ValueError("slides file is empty")

    started = time.perf_counter()
    results = []
    for skill in ("minimax_auto", "minimax_sharp"):
        print(f"[fullflow] running skill={skill}")
        result = generate_skill_outputs(
            skill=skill,
            slides=slides,
            output_dir=output_dir,
            title=args.title,
            author=args.author,
            render_width=args.width,
            render_height=args.height,
            render_fps=args.fps,
            minimax_style=args.minimax_style,
            minimax_palette=args.minimax_palette,
        )
        results.append(result)
        print(
            f"[fullflow] done skill={skill} pptx={result['pptx_size_bytes']}B "
            f"video={result['video_size_bytes']}B"
        )

    total_ms = int((time.perf_counter() - started) * 1000)
    report = {
        "input_slides": str(slides_path),
        "input_slide_count": len(slides),
        "render_config": {"width": args.width, "height": args.height, "fps": args.fps},
        "results": results,
        "generated_at": datetime.now().isoformat(),
        "total_elapsed_ms": total_ms,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[fullflow] report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
