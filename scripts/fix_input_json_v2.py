#!/usr/bin/env python3
import json
from pathlib import Path


def main():
    input_path = Path("test_inputs/work-summary-minimax-format.json")
    output_path = Path("test_inputs/work-summary-minimax-format-fixed.json")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slides = data.get("slides", [])
    for i, slide in enumerate(slides):
        page_number = slide.get("page_number", i + 1)
        if page_number == 3:
            slide["contract_profile"] = "cover_meta_required"
            blocks = slide.get("blocks", [])
            has_subtitle = any(
                block.get("block_type") == "subtitle" for block in blocks
            )
            if not has_subtitle:
                subtitle_block = {
                    "block_type": "subtitle",
                    "type": "subtitle",
                    "card_id": "card-subtitle-3",
                    "id": "subtitle-3",
                    "content": "PART ONE",
                }
                blocks.append(subtitle_block)
                slide["blocks"] = blocks
                print(f"幻灯片 {page_number} 添加了subtitle块")
        elif page_number == 4:
            slide["contract_profile"] = "chart_or_kpi_required"
            blocks = slide.get("blocks", [])
            has_kpi = any(block.get("block_type") == "kpi" for block in blocks)
            if not has_kpi:
                kpi_block = {
                    "block_type": "kpi",
                    "type": "kpi",
                    "card_id": "card-kpi-4",
                    "id": "kpi-4",
                    "content": "85%",
                    "label": "项目完成度",
                    "emphasis": ["primary"],
                }
                blocks.append(kpi_block)
                slide["blocks"] = blocks
                print(f"幻灯片 {page_number} 添加了KPI块")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修复后的文件已保存到: {output_path}")
    print(f"总幻灯片数: {len(slides)}")


if __name__ == "__main__":
    main()
