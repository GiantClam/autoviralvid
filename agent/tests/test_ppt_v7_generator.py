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


class MarkdownPlannerClient:
    async def chat_completions(self, model, messages, temperature, max_tokens, response_format=None):
        system = messages[0]["content"]
        if "顶尖商业演示架构师" in system:
            return """
这是一个 4 页的商业 PPT 大纲。

## 第1页：封面
**标题：** AI 投资的发展阶段与未来趋势
**副标题：** 智能投顾与财富管理生态演进

---

## 第2页：目录
- 产业阶段演进
- 核心驱动因素
- 风险与约束

---

## 第3页：阶段演进
**核心结论：** AI 投资已从规则引擎走向数据+模型协同
1. 2018-2020：规则策略主导，投顾自动化仍偏弱
2. 2021-2023：大模型进入研究链路，效率提升 3 倍
3. 2024-至今：投研、风控、投顾开始闭环集成

---

## 第4页：总结
**核心结论：** 下一阶段竞争核心是数据资产、模型治理与人机协同
- 数据闭环决定策略质量
- 模型治理决定可持续合规
"""

        return json.dumps(
            {
                "slide_type": "grid_2",
                "markdown": "# AI投资演进\n\n- 研究效率提升 <mark>3倍</mark>\n- 数据资产成为壁垒",
                "script": [{"role": "host", "text": "AI 投资已经从单点工具进入系统化协同阶段。"}],
                "bg_image_keyword": "ai investment strategy dashboard",
                "actions": [{"type": "highlight", "keyword": "3倍", "startFrame": 24}],
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


@pytest.mark.asyncio
async def test_generate_v7_recovers_when_planner_returns_markdown_outline():
    data = await generate_v7(
        requirement="AI 投资的发展阶段与未来趋势",
        num_slides=4,
        language="zh-CN",
        ai_call=MarkdownPlannerClient(),
    )

    slides = data["slides"]
    assert len(slides) == 4
    assert slides[0]["slide_type"] == "cover"
    assert slides[1]["slide_type"] == "toc"
    assert slides[-1]["slide_type"] == "summary"
    assert all("<mark>" in slide["markdown"] for slide in slides)
    assert any("3倍" in slide["markdown"] or "3 倍" in slide["markdown"] for slide in slides)
