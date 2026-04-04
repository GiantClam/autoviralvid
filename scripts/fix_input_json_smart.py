#!/usr/bin/env python3
import json
from pathlib import Path


def add_required_blocks(slide, contract_profile):
    blocks = slide.get("blocks", [])
    page_number = slide.get("page_number", 0)

    has_chart = any(block.get("block_type") == "chart" for block in blocks)
    has_kpi = any(block.get("block_type") == "kpi" for block in blocks)

    if contract_profile == "chart_or_kpi_required" and not (has_chart or has_kpi):
        kpi_block = {
            "block_type": "kpi",
            "type": "kpi",
            "card_id": f"card-kpi-{page_number}",
            "id": f"kpi-{page_number}",
            "content": "85%",
            "label": "指标",
            "emphasis": ["primary"],
        }
        blocks.append(kpi_block)
        print(f"幻灯片 {page_number} 添加了KPI块")

    elif contract_profile == "default" and not (has_chart or has_kpi):
        kpi_block = {
            "block_type": "kpi",
            "type": "kpi",
            "card_id": f"card-kpi-{page_number}",
            "id": f"kpi-{page_number}",
            "content": "90%",
            "label": "完成率",
            "emphasis": ["primary"],
        }
        blocks.append(kpi_block)
        print(f"幻灯片 {page_number} 添加了KPI块")

    if contract_profile == "cover_meta_required":
        has_subtitle = any(block.get("block_type") == "subtitle" for block in blocks)
        if not has_subtitle:
            subtitle_block = {
                "block_type": "subtitle",
                "type": "subtitle",
                "card_id": f"card-subtitle-{page_number}",
                "id": f"subtitle-{page_number}",
                "content": "子标题",
            }
            blocks.append(subtitle_block)
            print(f"幻灯片 {page_number} 添加了subtitle块")

    for block in blocks:
        if "emphasis" not in block:
            block["emphasis"] = ["primary"]

    slide["blocks"] = blocks
    return slide


def main():
    input_path = Path("test_inputs/work-summary-minimax-format.json")
    output_path = Path("test_inputs/work-summary-minimax-format-fixed.json")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slides = data.get("slides", [])
    for slide in slides:
        contract_profile = slide.get("contract_profile", "default")
        slide = add_required_blocks(slide, contract_profile)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修复后的文件已保存到: {output_path}")
    print(f"总幻灯片数: {len(slides)}")


if __name__ == "__main__":
    main()
