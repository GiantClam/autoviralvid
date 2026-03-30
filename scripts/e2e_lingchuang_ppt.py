"""
LingChuang PPT full-flow E2E script.

Flow:
1. Simulate user input via `/api/v1/ppt/outline` using a long requirement text.
2. Generate slide content via `/api/v1/ppt/content`.
3. Export PPT via `/api/v1/ppt/export` (main Python orchestration path).
4. Download PPTX and persist artifacts for quality harness consumption.
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
CURL_BIN = shutil.which("curl.exe") or shutil.which("curl") or "curl"

DEFAULT_REQUIREMENT = """灵创智能：引领数控加工新未来 —— 企业介绍PPT大纲
封面页
主标题： 灵创智能企业推介

副标题： 精准智造，赋能工业新未来

视觉元素： 公司Logo、极具科技感的高端数控机床实景图或3D渲染图。

演讲人/日期

第一部分：走进灵创智能（企业概况）
幻灯片 1：企业简介

公司定位：致力于高端智能数控机床的研发、生产与销售。

发展历程：成立年份、关键里程碑、所获荣誉（如高新技术企业、专精特新等）。

幻灯片 2：核心研发与生产实力

工厂规模与产能。

研发团队背景及核心专利（强调“智能”与“灵创”属性，如自研数控系统或高精度主轴技术）。

第二部分：匠心智造（企业产品与解决方案）
幻灯片 3：核心产品矩阵

高精度数控车床/铣床： 介绍加工精度、稳定性及适用基础零部件加工的优势。

高端五轴联动加工中心： 突出复杂曲面加工能力（适用于航空航天、医疗器械等高精尖领域）。

数控专用机床与复合机床： 车铣复合等高效加工设备。

幻灯片 4：产品核心技术优势

“精”： 微米级加工精度，高刚性床身设计。

“智”： 搭载智能化数控系统，支持物联网（IoT）接入，实现设备状态监控与故障预警。

“效”： 高效的排屑、冷却系统及自动化上下料接口。

幻灯片 5：行业应用案例（解决方案）

展示产品在新能源汽车（如压铸件加工）、3C电子、航空航天、模具制造等具体行业的成功应用。

第三部分：蓝海启航（市场规模与发展前景）
幻灯片 6：宏观市场机遇（广阔的市场规模）

全球与国内市场盘点： 引用最新行业数据（如：千亿级甚至万亿级的机床市场规模），说明数控机床作为“工业母机”的刚性需求。

国产替代浪潮： 分析当前高端数控机床国产化率的提升空间，强调国内品牌的巨大机遇。

幻灯片 7：驱动增长的核心动能

下游产业升级： 新能源汽车轻量化、5G通讯、自动化生产线对高端机床的爆发式需求。

政策红利： 国家对“智能制造”、“工业4.0”及设备更新换代的政策支持。

灵创智能的市场占位： 公司在特定细分市场的占有率及未来增长预测。

第四部分：携手共赢（多元化合作模式）
幻灯片 8：灵活的商业合作模式

区域代理与经销经销： 诚招各地代理商，提供完善的渠道保护、利润空间及市场支持。

大客户直采/集采： 针对大型制造企业提供批量采购优惠及驻厂售后保障。

设备融资租赁： 联合金融机构推出租赁模式，降低客户初期资金门槛，助力中小企业轻松升级设备。

幻灯片 9：深度技术与生态合作

OEM/ODM代工与定制研发： 根据客户特定工艺需求，提供非标机床或柔性生产线的定制开发。

产学研联合与“交钥匙”工程： 为客户提供从设备选型、工艺规划、夹具设计到打样生产的全套解决方案。

第五部分：未来展望与联系我们
幻灯片 10：企业愿景

短期与长期战略目标。

承诺：做最懂客户的数控机床合作伙伴，持续为中国智造贡献力量。

封底页：联系方式

公司地址、官方网址、联系人电话、微信公众号/销售微信二维码。

结语： 感谢聆听，期待合作！"""


def call_api(
    method: str,
    path: str,
    body: Dict[str, Any] | None = None,
    *,
    timeout_sec: int = 600,
) -> Dict[str, Any]:
    def _decode(raw: bytes | str | None) -> str:
        if raw is None:
            return ""
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace").strip()
        return str(raw).strip()

    if body is None:
        cmd = [CURL_BIN, "-s", "-X", method, f"{RENDERER_BASE}{path}"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            timeout=max(5, int(timeout_sec)),
            check=False,
        )
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
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=max(5, int(timeout_sec)),
                check=False,
            )
        finally:
            Path(payload_path).unlink(missing_ok=True)

    raw = _decode(result.stdout)
    stderr = _decode(result.stderr)
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


def expect_success(resp: Dict[str, Any], stage: str) -> Dict[str, Any]:
    if resp.get("success") and isinstance(resp.get("data"), dict):
        return resp["data"]
    raise RuntimeError(f"{stage} failed: {json.dumps(resp, ensure_ascii=False)[:1000]}")


def build_outline_request(requirement: str, num_slides: int) -> Dict[str, Any]:
    return {
        "requirement": requirement,
        "language": "zh-CN",
        "num_slides": num_slides,
        "style": "professional",
        "purpose": "企业介绍/商务合作路演",
    }


def build_export_request(
    slides: List[Dict[str, Any]],
    title: str,
    *,
    route_mode: str = "refine",
    quality_profile: str = "high_density_consulting",
) -> Dict[str, Any]:
    return {
        "slides": slides,
        "title": title,
        "author": "灵创智能",
        "generator_mode": "official",
        "route_mode": str(route_mode or "refine"),
        "quality_profile": str(quality_profile or "high_density_consulting"),
        "original_style": False,
        "disable_local_style_rewrite": False,
        "visual_priority": True,
        "visual_preset": "tech_cinematic",
        "visual_density": "balanced",
        "constraint_hardness": "balanced",
        "svg_mode": "on",
        "template_family": "auto",
    }


def download_file(url: str, output_path: Path) -> bool:
    if not url:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [CURL_BIN, "-L", "-s", "-o", str(output_path), url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def write_render_surrogate(
    output_dir: Path,
    *,
    outline_data: Dict[str, Any],
    slides: List[Dict[str, Any]],
    export_data: Dict[str, Any],
) -> Path:
    render_path = output_dir / "lingchuang_ppt.render.json"
    render_payload = {
        "mode": export_data.get("video_mode") or "mainflow_export",
        "generator_mode": export_data.get("generator_mode") or "official",
        "route_mode": export_data.get("route_mode") or "refine",
        "quality_profile": export_data.get("quality_profile") or "high_density_consulting",
        "quality_score": export_data.get("quality_score"),
        "visual_qa": export_data.get("visual_qa"),
        "official_input": {
            "title": str(outline_data.get("title") or "灵创智能企业推介"),
            "author": "灵创智能",
            "slides": slides,
        },
        "slides": export_data.get("video_slides") if isinstance(export_data.get("video_slides"), list) else [],
    }
    render_path.write_text(json.dumps(render_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return render_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--requirement-file", default="")
    parser.add_argument("--num-slides", type=int, default=12)
    parser.add_argument("--route-mode", default="refine")
    parser.add_argument("--quality-profile", default="high_density_consulting")
    parser.add_argument("--export-timeout", type=int, default=1800)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    requirement_text = (
        Path(args.requirement_file).read_text(encoding="utf-8")
        if args.requirement_file
        else DEFAULT_REQUIREMENT
    )

    outline_req = build_outline_request(requirement_text, max(3, min(50, int(args.num_slides))))
    (output_dir / "requirement.txt").write_text(requirement_text, encoding="utf-8")
    (output_dir / "outline_req.json").write_text(
        json.dumps(outline_req, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    outline_resp = call_api("POST", "/api/v1/ppt/outline", outline_req)
    outline_data = expect_success(outline_resp, "outline")
    (output_dir / "outline.json").write_text(
        json.dumps(outline_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    content_req = {"outline": outline_data, "language": "zh-CN"}
    (output_dir / "content_req.json").write_text(
        json.dumps(content_req, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    content_resp = call_api("POST", "/api/v1/ppt/content", content_req)
    if not (content_resp.get("success") and isinstance(content_resp.get("data"), list)):
        raise RuntimeError(f"content failed: {json.dumps(content_resp, ensure_ascii=False)[:1000]}")
    slides: List[Dict[str, Any]] = [item for item in content_resp["data"] if isinstance(item, dict)]
    (output_dir / "slides.json").write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")

    export_req = build_export_request(
        slides,
        str(outline_data.get("title") or "灵创智能企业推介"),
        route_mode=args.route_mode,
        quality_profile=args.quality_profile,
    )
    (output_dir / "export_req.json").write_text(
        json.dumps(export_req, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    export_resp = call_api(
        "POST",
        "/api/v1/ppt/export",
        export_req,
        timeout_sec=max(30, int(args.export_timeout)),
    )
    export_data = expect_success(export_resp, "export")
    (output_dir / "export_result.json").write_text(
        json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    pptx_url = str(export_data.get("url") or "").strip()
    pptx_path = output_dir / "lingchuang_ppt.pptx"
    downloaded = download_file(pptx_url, pptx_path)

    render_path = write_render_surrogate(
        output_dir,
        outline_data=outline_data,
        slides=slides,
        export_data=export_data,
    )

    quality_obj = export_data.get("quality_score") if isinstance(export_data.get("quality_score"), dict) else {}
    quality_passed = bool(quality_obj.get("passed"))
    alerts = export_data.get("alerts") if isinstance(export_data.get("alerts"), list) else []
    blocking_alerts = [
        item
        for item in alerts
        if isinstance(item, dict) and str(item.get("severity") or "").strip().lower() in {"high", "critical"}
    ]

    summary = {
        "success": downloaded and bool(slides) and quality_passed and (len(blocking_alerts) == 0),
        "output_dir": str(output_dir),
        "renderer_base": RENDERER_BASE,
        "slide_count": len(slides),
        "outline_title": outline_data.get("title"),
        "pptx_url": pptx_url,
        "pptx_path": str(pptx_path) if downloaded else "",
        "render_path": str(render_path),
        "route_mode": export_data.get("route_mode"),
        "quality_profile": export_data.get("quality_profile"),
        "quality_score": export_data.get("quality_score"),
        "quality_passed": quality_passed,
        "visual_qa": export_data.get("visual_qa"),
        "alerts": alerts,
        "blocking_alerts": blocking_alerts,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
