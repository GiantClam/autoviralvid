import json
import re

import pytest

from src.premium_generator_v7 import generate_v7


def _visible_text_len(markdown: str) -> int:
    text = re.sub(r"<[^>]+>", "", markdown or "")
    text = re.sub(r"[`*_>#-]", " ", text)
    text = re.sub(r"\s+", "", text)
    return len(text)


class FakeClient:
    async def chat_completions(self, model, messages, temperature, max_tokens, response_format=None):
        system = messages[0]["content"]
        user = messages[1]["content"]
        if "顶尖商业演示架构师" in system:
            # 故意给出不稳定的 type，验证后处理会修正
            return json.dumps(
                {
                    "title": "制造业增长方案",
                    "design_system": "tech_blue",
                    "slides": [
                        {"slide_index": 1, "slide_type": "cover", "key_message": "封面", "data_points": []},
                        {"slide_index": 2, "slide_type": "cover", "key_message": "目录", "data_points": []},
                        {"slide_index": 3, "slide_type": "grid_2", "key_message": "效率提升", "data_points": ["效率提升340%"]},
                    ],
                },
                ensure_ascii=False,
            )

        # mapper 输出故意不规范，验证 normalize 能兜底
        return json.dumps(
            {
                "slide_type": "grid_2",
                "markdown": "# 这一页内容很多很多很多很多很多很多很多很多",
                "script": [{"role": "host", "text": "这一页我们看关键结论"}],
                "bg_image_keyword": "",
                "actions": [],
            },
            ensure_ascii=False,
        )


@pytest.mark.asyncio
async def test_generate_v7_enforces_layout_and_schema():
    data = await generate_v7(
        requirement="制造业企业增长汇报",
        num_slides=8,
        language="zh-CN",
        ai_call=FakeClient(),
    )

    slides = data["slides"]
    assert len(slides) == 8
    assert slides[0]["slide_type"] == "cover"
    assert slides[1]["slide_type"] == "toc"
    assert slides[-1]["slide_type"] == "summary"

    for i in range(len(slides) - 1):
        assert slides[i]["slide_type"] != slides[i + 1]["slide_type"]

    for slide in slides:
        assert "<mark>" in slide["markdown"]
        assert _visible_text_len(slide["markdown"]) <= 40
        assert len(slide["script"]) >= 1
        assert len(slide["actions"]) >= 1

