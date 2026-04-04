#!/usr/bin/env python3
"""PPT visual comparison with structural + mandatory PSNR scoring."""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.append(str(Path("agent/src")))


def rasterize_pptx(pptx_path):
    from pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes

    pptx_bytes = Path(pptx_path).read_bytes()
    return rasterize_pptx_bytes_to_png_bytes(pptx_bytes)


def calculate_image_similarity(img1_bytes, img2_bytes):
    try:
        img1 = Image.open(io.BytesIO(img1_bytes)).convert("RGB").resize((256, 144))
        img2 = Image.open(io.BytesIO(img2_bytes)).convert("RGB").resize((256, 144))

        arr1 = np.array(img1)
        arr2 = np.array(img2)

        mse = np.mean((arr1 - arr2) ** 2)
        max_pixel = 255.0
        psnr = 20 * np.log10(max_pixel / np.sqrt(mse)) if mse > 0 else 100
        return min(100, max(0, psnr * 100 / 50))
    except Exception as exc:
        print(f"PSNR similarity failed: {exc}")
        return 0


def compare_structural(reference_ppt, generated_ppt):
    from pptx_comparator import compare_pptx_files

    report = compare_pptx_files(reference_ppt, generated_ppt)

    issues = []
    for issue_text in report.issues:
        issues.append({"issue": issue_text, "severity": "warning"})

    for detail in report.slide_details:
        if detail.slide_score < 70:
            issues.append(
                {
                    "page": detail.ref_page,
                    "similarity": detail.slide_score,
                    "issue": f"Slide {detail.ref_page} structural similarity is low ({detail.slide_score:.1f}%)",
                    "severity": "warning" if detail.slide_score >= 50 else "error",
                    "details": {
                        "title_similarity": detail.title_similarity,
                        "body_similarity": detail.body_similarity,
                        "element_count_ratio": detail.element_count_ratio,
                    },
                }
            )

    return {
        "reference_ppt": reference_ppt,
        "generated_ppt": generated_ppt,
        "mode": "structural",
        "total_pages_reference": report.diagnostics.get("ref_slide_count", 0),
        "total_pages_generated": report.diagnostics.get("gen_slide_count", 0),
        "visual_score": report.overall_score,
        "structure_score": report.structure_score,
        "content_score": report.content_score,
        "visual_style_score": report.visual_style_score,
        "geometry_score": report.geometry_score,
        "metadata_score": report.metadata_score,
        "average_similarity": report.overall_score,
        "issues": issues,
        "summary": f"Structural score: {report.overall_score:.1f}%",
        "diagnostics": report.diagnostics,
    }


def compare_psnr(reference_ppt, generated_ppt, output_dir):
    print("Running PSNR rasterization for reference deck...")
    reference_pngs = rasterize_pptx(reference_ppt)
    print(f"Reference pages: {len(reference_pngs)}")

    print("Running PSNR rasterization for generated deck...")
    generated_pngs = rasterize_pptx(generated_ppt)
    print(f"Generated pages: {len(generated_pngs)}")

    if not reference_pngs or not generated_pngs:
        print("PSNR rasterization failed, cannot compare")
        return None

    for i, png_bytes in enumerate(reference_pngs):
        (output_dir / f"reference_slide_{i + 1:03d}.png").write_bytes(png_bytes)
    for i, png_bytes in enumerate(generated_pngs):
        (output_dir / f"generated_slide_{i + 1:03d}.png").write_bytes(png_bytes)

    issues = []
    total_similarity = 0.0
    page_count = min(len(reference_pngs), len(generated_pngs))

    for i in range(page_count):
        similarity = calculate_image_similarity(reference_pngs[i], generated_pngs[i])
        total_similarity += similarity
        if similarity < 80:
            issues.append(
                {
                    "page": i + 1,
                    "similarity": similarity,
                    "issue": f"Slide {i + 1} visual similarity is low ({similarity:.1f}%)",
                    "severity": "warning" if similarity >= 60 else "error",
                }
            )

    avg_similarity = total_similarity / page_count if page_count > 0 else 0.0
    count_gap = abs(len(reference_pngs) - len(generated_pngs))
    count_ratio = min(len(reference_pngs), len(generated_pngs)) / max(
        len(reference_pngs), len(generated_pngs), 1
    )
    page_count_penalty = (1 - count_ratio) * 30 + count_gap * 3
    visual_score = max(0.0, avg_similarity - page_count_penalty)

    if count_gap > 0:
        issues.append(
            {
                "issue": f"Slide count mismatch: {len(reference_pngs)} vs {len(generated_pngs)}",
                "severity": "error",
            }
        )

    return {
        "reference_ppt": reference_ppt,
        "generated_ppt": generated_ppt,
        "mode": "psnr",
        "total_pages_reference": len(reference_pngs),
        "total_pages_generated": len(generated_pngs),
        "average_similarity": avg_similarity,
        "visual_score": visual_score,
        "psnr_raw_similarity": avg_similarity,
        "page_count_penalty": page_count_penalty,
        "issues": issues,
        "summary": (
            f"PSNR score: {visual_score:.1f}% "
            f"(raw={avg_similarity:.1f}%, page_penalty={page_count_penalty:.1f})"
        ),
    }


def merge_structural_and_psnr(structural_report, psnr_report):
    report = dict(structural_report)
    report["mode"] = "hybrid_structural_psnr"
    report["structural_visual_score"] = structural_report.get("visual_score", 0)
    report["psnr_visual_score"] = psnr_report.get("visual_score", 0)
    report["psnr_raw_similarity"] = psnr_report.get("psnr_raw_similarity", 0)
    report["page_count_penalty"] = psnr_report.get("page_count_penalty", 0)
    report["visual_score"] = min(
        float(structural_report.get("visual_score", 0) or 0),
        float(psnr_report.get("visual_score", 0) or 0),
    )
    report["average_similarity"] = report["visual_score"]
    report["issues"] = list(structural_report.get("issues", [])) + list(
        psnr_report.get("issues", [])
    )
    report["summary"] = (
        "Hybrid score (min of structural and psnr): "
        f"{report['visual_score']:.1f}% | "
        f"structural={report['structural_visual_score']:.1f}% | "
        f"psnr={report['psnr_visual_score']:.1f}%"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="Compare two PPTX files visually")
    parser.add_argument(
        "--mode",
        choices=["psnr", "structural", "auto"],
        default="auto",
        help="Comparison mode: psnr, structural, or auto",
    )
    parser.add_argument(
        "--reference",
        default="C:/Users/liula/Downloads/ppt2/ppt2/1.pptx",
        help="Path to reference PPTX file",
    )
    parser.add_argument(
        "--generated",
        default="output/regression/generated.pptx",
        help="Path to generated PPTX file",
    )
    parser.add_argument(
        "--output-dir",
        default="output/regression",
        help="Output directory for reports and images",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON file path for report",
    )
    parser.add_argument(
        "--pass-score",
        type=float,
        default=80.0,
        help="Minimum score required to pass",
    )
    parser.add_argument(
        "--require-no-issues",
        choices=["on", "off"],
        default="on",
        help="Whether any issue should fail the check",
    )
    parser.add_argument(
        "--require-psnr",
        choices=["on", "off"],
        default="off",
        help="Fail when PSNR rasterization/comparison is unavailable",
    )

    args = parser.parse_args()

    reference_ppt = args.reference
    generated_ppt = args.generated
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    print("Running mandatory PSNR comparison...")
    psnr_report = None
    try:
        psnr_report = compare_psnr(reference_ppt, generated_ppt, output_dir)
        if psnr_report:
            print(f"PSNR complete: {psnr_report['visual_score']:.1f}%")
    except Exception as exc:
        print(f"PSNR comparison failed: {exc}")

    structural_report = None
    if args.mode in ["structural", "auto"]:
        print("Running structural comparison...")
        try:
            structural_report = compare_structural(reference_ppt, generated_ppt)
            print(f"Structural complete: {structural_report['visual_score']:.1f}%")
        except Exception as exc:
            print(f"Structural comparison failed: {exc}")

    if args.mode == "psnr":
        report = psnr_report
    elif structural_report and psnr_report:
        report = merge_structural_and_psnr(structural_report, psnr_report)
    else:
        report = structural_report or psnr_report

    if report is None:
        print("All comparison modes failed")
        return

    # Stable aliases for downstream regression loops.
    report["score"] = float(report.get("visual_score", 0) or 0)
    report["issue_count"] = len(report.get("issues", []))
    require_no_issues = str(args.require_no_issues or "on").strip().lower() == "on"
    require_psnr = str(args.require_psnr or "off").strip().lower() == "on"
    failed_checks = []
    if report["score"] < float(args.pass_score):
        failed_checks.append(
            {
                "check": "score_threshold",
                "expected_min": float(args.pass_score),
                "actual": float(report["score"]),
            }
        )
    if require_no_issues and report["issue_count"] > 0:
        failed_checks.append(
            {
                "check": "issues_must_be_zero",
                "expected": 0,
                "actual": int(report["issue_count"]),
            }
        )
    if require_psnr and psnr_report is None:
        failed_checks.append(
            {
                "check": "psnr_required",
                "expected": "psnr_report_available",
                "actual": "missing",
            }
        )
    report["verdict"] = "passed" if len(failed_checks) == 0 else "failed"
    report["failed_checks"] = failed_checks

    report_path = output_dir / "visual_comparison_report.json"
    if args.output:
        output_path = Path(args.output)
        if output_path.suffix.lower() == ".json":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            report_path = output_path
        else:
            output_path.mkdir(parents=True, exist_ok=True)
            report_path = output_path / "visual_comparison_report.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nComparison complete")
    print(f"Mode: {report.get('mode', 'unknown')}")
    print(f"Visual score: {report['visual_score']:.1f}%")
    print(f"Issue count: {len(report.get('issues', []))}")
    print(f"Verdict: {report['verdict']}")
    print(f"Report saved: {report_path}")

    if "structure_score" in report:
        print("\nDetailed dimensions:")
        print(f"  structure: {report['structure_score']:.1f}%")
        print(f"  content: {report['content_score']:.1f}%")
        print(f"  visual_style: {report['visual_style_score']:.1f}%")
        print(f"  geometry: {report['geometry_score']:.1f}%")
        print(f"  metadata: {report['metadata_score']:.1f}%")
    if "psnr_visual_score" in report:
        print(f"  psnr: {report['psnr_visual_score']:.1f}%")
        print(f"  psnr_raw: {report.get('psnr_raw_similarity', 0):.1f}%")
        print(f"  page_penalty: {report.get('page_count_penalty', 0):.1f}")

    if report["verdict"] != "passed":
        print("Comparison failed under strict gate")
        sys.exit(2)


if __name__ == "__main__":
    main()
