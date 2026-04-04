#!/usr/bin/env python3
import json
from pathlib import Path


def create_simple_input():
    simple_data = {
        "title": "测试PPT",
        "author": "测试作者",
        "theme": {"palette": "business_authority", "style": "sharp"},
        "contract_profile": "default",
        "quality_profile": "default",
        "slides": [
            {
                "page_number": 1,
                "slide_id": "slide-001",
                "slide_type": "cover",
                "contract_profile": "cover_meta_required",
                "title": "封面",
                "blocks": [
                    {"block_type": "title", "type": "title", "content": "测试PPT"},
                    {"block_type": "subtitle", "type": "subtitle", "content": "子标题"},
                    {
                        "block_type": "kpi",
                        "type": "kpi",
                        "content": "100%",
                        "label": "完成率",
                        "emphasis": ["primary"],
                    },
                ],
            },
            {
                "page_number": 2,
                "slide_id": "slide-002",
                "slide_type": "content",
                "contract_profile": "default",
                "title": "内容页",
                "blocks": [
                    {"block_type": "title", "type": "title", "content": "内容页"},
                    {"block_type": "body", "type": "body", "content": "这是内容"},
                    {
                        "block_type": "chart",
                        "type": "chart",
                        "chart_type": "bar",
                        "data": {
                            "labels": ["A", "B"],
                            "datasets": [{"label": "数据", "data": [10, 20]}],
                        },
                        "emphasis": ["primary"],
                    },
                ],
            },
            {
                "page_number": 3,
                "slide_id": "slide-003",
                "slide_type": "content",
                "contract_profile": "chart_or_kpi_required",
                "title": "图表页",
                "blocks": [
                    {"block_type": "title", "type": "title", "content": "图表页"},
                    {"block_type": "list", "type": "list", "content": "要点1\\n要点2"},
                    {
                        "block_type": "kpi",
                        "type": "kpi",
                        "content": "80%",
                        "label": "进度",
                        "emphasis": ["primary"],
                    },
                ],
            },
        ],
    }

    output_path = Path("test_inputs/simple-test.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(simple_data, f, ensure_ascii=False, indent=2)

    print(f"简单输入文件已保存到: {output_path}")


if __name__ == "__main__":
    create_simple_input()
