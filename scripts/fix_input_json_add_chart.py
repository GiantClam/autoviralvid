#!/usr/bin/env python3
import json
from pathlib import Path


def add_chart_kpi_blocks(slide, page_number):
    blocks = slide.get("blocks", [])
    has_chart = any(block.get("block_type") == "chart" for block in blocks)
    has_kpi = any(block.get("block_type") == "kpi" for block in blocks)

    if not (has_chart or has_kpi):
        kpi_block = {
            "block_type": "kpi",
            "type": "kpi",
            "card_id": f"card-kpi-{page_number}",
            "id": f"kpi-{page_number}",
            "content": "85%",
            "label": "完成率",
            "emphasis": ["primary"],
        }
        blocks.append(kpi_block)
        print(f"幻灯片 {page_number} 添加了KPI块")

    slide["blocks"] = blocks
    return slide


def main():
    input_path = Path("test_inputs/work-summary-minimax-format-fixed.json")
    output_path = Path("test_inputs/work-summary-minimax-format-fixed-v2.json")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slides = data.get("slides", [])
    for slide in slides:
        page_number = slide.get("page_number", 0)
        if page_number in [3, 4, 5]:
            slide = add_chart_kpi_blocks(slide, page_number)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修复后的文件已保存到: {output_path}")


if __name__ == "__main__":
    main()
