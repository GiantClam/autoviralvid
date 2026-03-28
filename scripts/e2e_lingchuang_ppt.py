"""
LingChuang PPT-only E2E script.

Flow:
1. Build fixed outline (no video stage).
2. Generate slide content via `/api/v1/ppt/content`.
3. Export PPT via `scripts/generate-pptx-minimax.mjs`.
4. Save outputs for quality harness consumption.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


RENDERER_BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUTPUT_DIR = Path("test_outputs/lingchuang_ppt")
SLIDES_PER_BATCH = 3
CURL_BIN = shutil.which("curl.exe") or shutil.which("curl") or "curl"

OUTLINE_SLIDES = [
    {
        "id": "lc-cover",
        "order": 1,
        "title": "封面｜灵创智能企业介绍",
        "description": "封面页，突出品牌定位与核心价值主张。",
        "key_points": ["灵创智能", "AI营销", "数字人增长引擎"],
    },
    {
        "id": "lc-intro",
        "order": 2,
        "title": "公司概况与战略定位",
        "description": "说明公司定位、核心能力、增长方向与客户价值。",
        "key_points": [
            "服务品牌客户超120家，覆盖消费、制造、教育三大行业",
            "自主研发AI内容与投放系统，支持多渠道一体化运营",
            "形成“策略-素材-投放-复盘”全链路营销闭环",
        ],
    },
    {
        "id": "lc-tech",
        "order": 3,
        "title": "技术体系与能力栈",
        "description": "介绍模型能力、数据中台与自动化内容生产链路。",
        "key_points": [
            "大模型驱动创意生成，单日可产出300+条投放素材",
            "数据中台接入12类行为指标，实现人群分层与实时优化",
            "自动化A/B实验体系让素材迭代周期缩短至24小时",
        ],
    },
    {
        "id": "lc-products",
        "order": 4,
        "title": "产品矩阵与应用场景",
        "description": "展示核心产品形态以及典型业务场景。",
        "key_points": [
            "数字人直播：支持7x24小时多平台讲解与互动",
            "智能投放：自动分配预算并根据ROI实时调优",
            "创意工厂：脚本、口播、短视频素材自动化生成",
        ],
    },
    {
        "id": "lc-value",
        "order": 5,
        "title": "业务价值与ROI提升",
        "description": "量化展示效率、成本与转化层面的直接收益。",
        "key_points": [
            "内容生产成本平均下降42%，人工编辑时间减少60%",
            "投放点击率平均提升28%，线索转化率提升19%",
            "运营流程标准化后，跨团队协作效率提升35%",
        ],
    },
    {
        "id": "lc-cases",
        "order": 6,
        "title": "行业案例与落地成效",
        "description": "展示不同行业客户的典型成果与可复用方法。",
        "key_points": [
            "消费品牌：双11期间GMV同比增长31%，退货率下降8%",
            "制造企业：线索获客成本下降26%，销售跟进时效提升40%",
            "教育服务：私域咨询转化率提升22%，留资率提升18%",
        ],
    },
    {
        "id": "lc-market",
        "order": 7,
        "title": "市场机会与增长空间",
        "description": "分析行业增量、预算迁移趋势与结构性机会。",
        "key_points": [
            "AI营销预算连续3年增长，年复合增速预计超35%",
            "企业从“流量采购”转向“内容+投放一体化”模式",
            "数字人商业化进入规模期，渗透率持续上升",
        ],
    },
    {
        "id": "lc-plan",
        "order": 8,
        "title": "实施路线图（Roadmap）",
        "description": "分阶段推进，从诊断试点到规模化复制。",
        "key_points": [
            "第1阶段（2周）：业务诊断与数据基线建立",
            "第2阶段（4周）：小范围试点并验证投放模型",
            "第3阶段（8周）：跨业务线复制与组织协同落地",
        ],
    },
    {
        "id": "lc-roadmap",
        "order": 9,
        "title": "未来规划与生态合作",
        "description": "规划产品升级方向和生态伙伴协同机制。",
        "key_points": [
            "产品升级：引入多模态创意理解与自动脚本评估",
            "生态合作：联合渠道、SaaS与媒体平台共建方案",
            "国际化布局：优先拓展东南亚与中东市场",
        ],
    },
    {
        "id": "lc-summary",
        "order": 10,
        "title": "总结与合作建议",
        "description": "回顾核心优势，给出可执行的合作方案。",
        "key_points": [
            "灵创智能已形成可复制的AI营销增长方法论",
            "建议先以单业务线试点，4周内完成效果验证",
            "通过季度共创机制持续提升投放效率与增长质量",
        ],
    },
]


def call_api(method: str, path: str, body: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if body is None:
        cmd = [CURL_BIN, "-s", "-X", method, f"{RENDERER_BASE}{path}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(body, f, ensure_ascii=False)
            payload_path = f.name
        try:
            cmd = [
                CURL_BIN,
                "-s",
                "-X",
                method,
                f"{RENDERER_BASE}{path}",
                "-H",
                "Content-Type: application/json",
                "-d",
                f"@{payload_path}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
        finally:
            Path(payload_path).unlink(missing_ok=True)

    raw = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        return {
            "success": False,
            "error": f"curl_failed(code={result.returncode}): {(stderr or raw)[:500]}",
        }
    if not raw and stderr:
        raw = stderr
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "error": (raw or stderr)[:500]}


def build_outline_payload() -> Dict[str, Any]:
    return {
        "id": "lingchuang-2026-ppt-only",
        "title": "灵创智能：AI营销与数字人增长引擎",
        "theme": "professional",
        "style": "professional",
        "slides": OUTLINE_SLIDES,
        "total_duration": 8 * len(OUTLINE_SLIDES),
    }


def generate_slides(outline: Dict[str, Any]) -> List[Dict[str, Any]]:
    total = len(OUTLINE_SLIDES)
    generated: List[Dict[str, Any]] = []
    for start in range(0, total, SLIDES_PER_BATCH):
        end = min(start + SLIDES_PER_BATCH, total)
        batch = OUTLINE_SLIDES[start:end]
        req = {"outline": {**outline, "slides": batch}, "language": "zh-CN"}
        resp = call_api("POST", "/api/v1/ppt/content", req)
        if resp.get("success") and isinstance(resp.get("data"), list):
            generated.extend(resp["data"])
        else:
            raise RuntimeError(
                f"Content API degraded/fallback detected for batch {start}-{end}: "
                f"{json.dumps(resp, ensure_ascii=False)[:600]}"
            )
    return generated


def export_ppt(slides: List[Dict[str, Any]], title: str, output_dir: Path) -> Dict[str, Any]:
    export_req = {
        "slides": slides,
        "title": title,
        "author": "灵创智能",
        "generator_mode": "official",
        "original_style": True,
        "disable_local_style_rewrite": True,
        "visual_priority": True,
        "visual_preset": "tech_cinematic",
        "visual_density": "balanced",
        "constraint_hardness": "minimal",
    }
    req_path = output_dir / "export_req.json"
    render_path = output_dir / "lingchuang_ppt.render.json"
    pptx_path = output_dir / "lingchuang_ppt.pptx"
    req_path.write_text(json.dumps(export_req, ensure_ascii=False, indent=2), encoding="utf-8")

    node = shutil.which("node") or "node"
    cmd = [
        node,
        "scripts/generate-pptx-minimax.mjs",
        "--input",
        str(req_path),
        "--output",
        str(pptx_path),
        "--render-output",
        str(render_path),
        "--generator-mode",
        "official",
        "--visual-priority",
        "--visual-preset",
        "tech_cinematic",
        "--visual-density",
        "balanced",
        "--constraint-hardness",
        "minimal",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"PPT export failed: {(result.stderr or result.stdout)[:600]}")

    meta: Dict[str, Any] = {}
    for line in reversed((result.stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            meta = parsed
            break
    return {
        "pptx_path": str(pptx_path),
        "render_path": str(render_path),
        "meta": meta,
    }


def evaluate_render_metrics(render_path: Path, output_dir: Path) -> Dict[str, Any]:
    node = shutil.which("node") or "node"
    report_path = output_dir / "render_metrics.json"
    cmd = [
        node,
        "scripts/tests/validate-render-metrics.mjs",
        str(render_path),
        "--report-path",
        str(report_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    report: Dict[str, Any] = {
        "ok": result.returncode == 0,
        "report_path": str(report_path),
        "stdout": (result.stdout or "").strip()[:2000],
        "stderr": (result.stderr or "").strip()[:2000],
    }
    if report_path.exists():
        try:
            report["report"] = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            report["report"] = {}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument(
        "--skip-render-metrics",
        action="store_true",
        help="Skip validate-render-metrics after export.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outline = build_outline_payload()
    slides = generate_slides(outline)
    (output_dir / "outline.json").write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "slides.json").write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")

    export_info = export_ppt(slides, outline["title"], output_dir)
    metrics = (
        {"ok": True, "skipped": True}
        if args.skip_render_metrics
        else evaluate_render_metrics(Path(export_info["render_path"]), output_dir)
    )
    summary = {
        "success": bool(metrics.get("ok", True)),
        "slide_count": len(slides),
        "output_dir": str(output_dir),
        "pptx_path": export_info["pptx_path"],
        "render_path": export_info["render_path"],
        "generator_meta": export_info["meta"],
        "render_metrics": metrics,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
