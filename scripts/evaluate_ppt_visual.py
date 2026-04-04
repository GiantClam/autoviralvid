#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.append(str(Path("agent/src")))


def evaluate_ppt(pptx_path):
    from ppt_visual_qa import audit_rendered_slides
    from pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes
    import asyncio

    pptx_bytes = Path(pptx_path).read_bytes()
    png_bytes_list = rasterize_pptx_bytes_to_png_bytes(pptx_bytes)

    if not png_bytes_list:
        print("无法将PPT转换为PNG图像")
        return None

    result = asyncio.run(
        audit_rendered_slides(
            png_bytes_list=png_bytes_list,
            deck_title="生成的PPT",
            route_mode="standard",
            enable_multimodal=False,
        )
    )

    return result


def main():
    generated_ppt = "output/regression/generated.pptx"
    output_dir = Path("output/regression")
    output_dir.mkdir(exist_ok=True)

    print("正在评估生成PPT的视觉质量...")
    result = evaluate_ppt(generated_ppt)

    if result:
        report_path = output_dir / "visual_qa_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"视觉质量评估完成！")
        print(f"视觉评分: {result.get('score', 'N/A')}")
        print(f"问题数量: {len(result.get('issues', []))}")
        print(f"报告已保存到: {report_path}")
    else:
        print("视觉质量评估失败")


if __name__ == "__main__":
    main()
