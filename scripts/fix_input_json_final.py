#!/usr/bin/env python3
import json
from pathlib import Path


def ensure_min_text_blocks(slide, min_text_blocks):
    blocks = slide.get("blocks", [])
    page_number = slide.get("page_number", 0)

    # 计算当前文本块数量（排除title块和视觉块）
    visual_types = {"image", "chart", "kpi", "workflow", "diagram"}
    text_block_count = 0
    for block in blocks:
        block_type = block.get("block_type", "").lower()
        if block_type == "title":
            continue
        if block_type in visual_types:
            continue
        text_block_count += 1

    # 添加足够的文本块以满足min_text_blocks要求
    while text_block_count < min_text_blocks:
        body_block = {
            "block_type": "body",
            "type": "body",
            "card_id": f"card-body-{page_number}-{text_block_count}",
            "id": f"body-{page_number}-{text_block_count}",
            "content": f"内容{page_number}-{text_block_count}",
            "emphasis": ["primary"],
        }
        blocks.append(body_block)
        text_block_count += 1
        print(f"幻灯片 {page_number} 添加了body块")

    slide["blocks"] = blocks
    return slide


def main():
    input_path = Path("test_inputs/work-summary-minimax-format.json")
    output_path = Path("test_inputs/work-summary-minimax-format-fixed.json")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slides = data.get("slides", [])
    for slide in slides:
        # 根据合同配置文件设置min_text_blocks
        contract_profile = slide.get("contract_profile", "default")
        if contract_profile == "cover_meta_required":
            min_text_blocks = 1
        else:
            min_text_blocks = 2

        slide = ensure_min_text_blocks(slide, min_text_blocks)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"修复后的文件已保存到: {output_path}")
    print(f"总幻灯片数: {len(slides)}")


if __name__ == "__main__":
    main()
