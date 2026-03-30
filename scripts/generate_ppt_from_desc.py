#!/usr/bin/env python3
"""从描述 JSON 生成 PPT（调用完整主流程）。

用法:
    python scripts/generate_ppt_from_desc.py --input desc.json --output output.pptx
    python scripts/generate_ppt_from_desc.py --input desc.json --output output.pptx --api-url http://127.0.0.1:8124

支持两种模式:
    1. API 模式: 调用后端服务 (需要后端运行)
    2. 本地模式: 直接调用 Node.js 渲染脚本 (仅渲染部分)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def generate_via_api(
    desc: Dict[str, Any],
    api_url: str,
    output_path: str,
    render_output_path: Optional[str] = None,
) -> bool:
    payload = {
        "topic": desc.get("title", "Untitled"),
        "audience": desc.get("audience", "general"),
        "purpose": desc.get("purpose", "presentation"),
        "style_preference": desc.get("style_preference", "professional"),
        "total_pages": len(desc.get("slides", [])),
        "language": "zh-CN",
        "route_mode": "standard",
        "quality_profile": "auto",
        "with_export": True,
        "save_artifacts": True,
        "minimax_style_variant": desc.get("theme", {}).get("style", "auto"),
        "minimax_palette_key": desc.get("theme", {}).get("palette", "auto"),
        "constraints": desc.get("constraints", []),
        "required_facts": desc.get("required_facts", []),
    }

    try:
        resp = requests.post(
            f"{api_url}/api/v1/ppt/pipeline",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            print(f"API 错误: {data.get('error', '未知错误')}")
            return False

        result = data.get("data", {})
        export = result.get("export", {})
        pptx_url = export.get("pptx_url")

        if pptx_url:
            pptx_resp = requests.get(f"{api_url}{pptx_url}", timeout=30)
            pptx_resp.raise_for_status()
            Path(output_path).write_bytes(pptx_resp.content)
            print(f"PPT 已保存到: {output_path}")

            if render_output_path:
                artifacts = result.get("artifacts", {})
                Path(render_output_path).write_text(
                    json.dumps(
                        artifacts.get("render_payload", {}),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print(f"渲染输出已保存到: {render_output_path}")

            return True
        else:
            print("API 未返回 PPT URL")
            return False

    except requests.exceptions.ConnectionError:
        print(f"无法连接到 API: {api_url}")
        print("请确保后端服务正在运行 (pnpm dev:agent:render)")
        return False
    except Exception as e:
        print(f"API 调用失败: {e}")
        return False


def generate_via_local(
    desc: Dict[str, Any],
    output_path: str,
    render_output_path: Optional[str] = None,
) -> bool:
    scripts_dir = Path(__file__).parent
    generator_script = scripts_dir / "generate-pptx-minimax.mjs"

    if not generator_script.exists():
        print(f"找不到渲染脚本: {generator_script}")
        return False

    desc_path = Path(output_path).with_suffix(".desc.json")
    desc_path.write_text(
        json.dumps(desc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    cmd = [
        "node",
        str(generator_script),
        "--input",
        str(desc_path),
        "--output",
        output_path,
    ]

    if render_output_path:
        cmd.extend(["--render-output", render_output_path])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            print(f"PPT 已保存到: {output_path}")
            return True
        else:
            print(f"渲染失败: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("渲染超时")
        return False
    except Exception as e:
        print(f"渲染异常: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="从描述 JSON 生成 PPT")
    parser.add_argument("--input", "-i", required=True, help="描述 JSON 文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出 PPTX 文件路径")
    parser.add_argument("--render-output", "-r", help="渲染输出 JSON 路径")
    parser.add_argument("--api-url", default="http://127.0.0.1:8124", help="API 地址")
    parser.add_argument(
        "--mode", choices=["api", "local", "auto"], default="auto", help="生成模式"
    )

    args = parser.parse_args()

    desc = json.loads(Path(args.input).read_text(encoding="utf-8"))

    success = False

    if args.mode == "api":
        success = generate_via_api(desc, args.api_url, args.output, args.render_output)
    elif args.mode == "local":
        success = generate_via_local(desc, args.output, args.render_output)
    else:
        success = generate_via_api(desc, args.api_url, args.output, args.render_output)
        if not success:
            print("API 模式失败，尝试本地模式...")
            success = generate_via_local(desc, args.output, args.render_output)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
