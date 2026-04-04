#!/usr/bin/env python3
import json
from pathlib import Path


def fix_slide(blocks, slide_number):
    has_chart_or_kpi = any(
        block.get("block_type") in ("chart", "kpi") for block in blocks
    )
    if has_chart_or_kpi:
        print(f"幻灯片 {slide_number} 已有图表或KPI块，无需修复")
        return blocks

    kpi_block = {
        "block_type": "kpi",
        "type": "kpi",
        "card_id": f"card-kpi-{slide_number}",
        "id": f"kpi-{slide_number}",
        "content": "100%",
        "label": "完成率",
        "emphasis": ["primary"],
    }

    chart_block = {
        "block_type": "chart",
        "type": "chart",
        "card_id": f"card-chart-{slide_number}",
        "id": f"chart-{slide_number}",
        "chart_type": "bar",
        "data": {
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "datasets": [{"label": "销售额", "data": [100, 200, 150, 300]}],
        },
        "emphasis": ["primary"],
    }

    if slide_number == 3:
        blocks.append(kpi_block)
        print(f"幻灯片 {slide_number} 添加了KPI块")
    else:
        blocks.append(chart_block)
        print(f"幻灯片 {slide_number} 添加了图表块")

    return blocks


def main():
    input_path = Path("test_inputs/work-summary-minimax-format.json")
    output_path = Path("test_inputs/work-summary-minimax-format-fixed.json")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slides = data.get("slides", [])
    for i, slide in enumerate(slides):
        page_number = slide.get("page_number", i + 1)
        if page_number in (3, 4):
            blocks = slide.get("blocks", [])
            fixed_blocks = fix_slide(blocks, page_number)
            slide["blocks"] = fixed_blocks

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修复后的文件已保存到: {output_path}")
    print(f"总幻灯片数: {len(slides)}")


if __name__ == "__main__":
    main()
