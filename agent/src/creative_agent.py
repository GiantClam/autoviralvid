from typing import Dict, Any, List, Optional, Union
from langchain_core.tools import tool
import json
import logging

logger = logging.getLogger("creative_agent")

# 视频类型选项（按分类组织）
VIDEO_TYPES = [
    # 电商带货
    "产品宣传视频",
    "产品演示视频",
    "美妆种草视频",
    "服饰穿搭视频",
    "美食展示视频",
    "3C数码评测视频",
    "家居好物视频",
    # 品牌营销
    "品牌故事视频",
    "活动推广视频",
    "广告片",
    # 内容创作
    "知识科普视频",
    "搞笑段子视频",
    "旅行Vlog",
    "社交媒体短视频",
    "教程视频",
    # 其他
    "其他",
]

# 视频时长选项（秒）
DURATION_OPTIONS = [10, 20, 30, 60, 90, 120]

# 视频方向选项（横/竖）
ORIENTATION_OPTIONS = [
    "横屏",
    "竖屏",
]

# 视频风格选项（扩展行业风格）
STYLE_OPTIONS = [
    # 通用风格
    "现代简约",
    "科技感",
    "温馨生活",
    "时尚潮流",
    "商务专业",
    "创意艺术",
    "自然清新",
    "复古怀旧",
    "动感活力",
    "优雅高端",
    # 行业风格
    "ins风清新",
    "日系治愈",
    "赛博朋克",
    "国潮国风",
    "奢华质感",
    "田园自然",
    "街头潮酷",
    "梦幻童话",
]

# 一致性元素选项
CONSISTENCY_ELEMENTS = [
    "品牌Logo",
    "产品外观",
    "人物形象",
    "色彩方案",
    "字体样式",
    "包装设计",
    "用户界面",
    "场景背景",
]

# ── 叙事结构模板 ──
# 映射：模板/视频类型 → 叙事结构名称 → 分镜节奏提示
NARRATIVE_STRUCTURES = {
    "product_showcase": {
        "name": "产品展示型",
        "beats": "问题引入 → 产品登场 → 功能亮点演示 → 效果对比 → 行动号召",
        "scene_guidance": (
            "第一幕：用户痛点或使用场景引入，建立共鸣；"
            "中间幕：产品多角度展示+核心卖点演示，节奏由慢到快；"
            "最后一幕：效果对比或用户好评，以行动号召收尾。"
        ),
    },
    "brand_story": {
        "name": "品牌故事型",
        "beats": "情感铺垫 → 品牌理念 → 产品自然融入 → 情感升华",
        "scene_guidance": (
            "第一幕：用情感化场景开场，营造氛围，不急于展示产品；"
            "中间幕：品牌理念或价值观传达，产品作为故事元素自然出现；"
            "最后一幕：情感升华，品牌slogan或态度表达。"
        ),
    },
    "beauty_review": {
        "name": "种草推荐型",
        "beats": "开箱展示 → 质地/细节特写 → 上脸/使用过程 → 前后对比 → 真实感受",
        "scene_guidance": (
            "第一幕：产品开箱或外包装展示，营造期待感；"
            "中间幕：产品质地、颜色、细节的特写镜头，使用过程的近景拍摄；"
            "最后一幕：使用前后对比，真实使用感受和推荐理由。"
        ),
    },
    "food_showcase": {
        "name": "美食展示型",
        "beats": "原料/食材展示 → 制作/烹饪过程 → 成品特写 → 品尝反应 → 推荐总结",
        "scene_guidance": (
            "第一幕：新鲜食材或原料的诱人特写；"
            "中间幕：制作过程的慢镜头和特写，烹饪细节和手法展示；"
            "最后一幕：成品的多角度展示、品尝时的满足表情。"
        ),
    },
    "tech_review": {
        "name": "数码评测型",
        "beats": "外观展示 → 功能测试 → 使用场景演示 → 优缺点总结 → 购买建议",
        "scene_guidance": (
            "第一幕：产品外观360度展示，做工细节特写；"
            "中间幕：核心功能实测画面，参数对比图表，实际使用场景；"
            "最后一幕：优缺点客观总结，购买建议。"
        ),
    },
    "lifestyle": {
        "name": "生活方式型",
        "beats": "场景引入 → 体验展示 → 细节分享 → 氛围营造 → 感受总结",
        "scene_guidance": (
            "第一幕：生活场景的自然引入，环境氛围铺设；"
            "中间幕：使用体验的记录，与日常生活的融合；"
            "最后一幕：生活感悟或场景回顾，自然收尾。"
        ),
    },
    "knowledge_edu": {
        "name": "知识科普型",
        "beats": "问题抛出 → 知识讲解 → 案例演示 → 要点回顾",
        "scene_guidance": (
            "第一幕：用一个引人好奇的问题或现象开场；"
            "中间幕：知识点图文配合讲解，案例或实验演示；"
            "最后一幕：要点总结回顾，引导互动（点赞/收藏）。"
        ),
    },
    "funny_skit": {
        "name": "搞笑反转型",
        "beats": "日常场景 → 铺垫积累 → 意外反转 → 点题收尾",
        "scene_guidance": (
            "第一幕：看似普通的日常场景，建立观众预期；"
            "中间幕：逐步铺垫，用节奏和细节暗示'有事要发生'；"
            "最后一幕：出人意料的反转，反差越大效果越好，快速收尾。"
        ),
    },
    "travel_vlog": {
        "name": "旅行记录型",
        "beats": "目的地引入 → 途中风景 → 人文体验 → 美食/特色 → 感悟收尾",
        "scene_guidance": (
            "第一幕：目的地标志性景观或交通工具出发画面；"
            "中间幕：沿途风景的空镜+人物互动，当地特色体验；"
            "最后一幕：旅途感悟或回忆蒙太奇。"
        ),
    },
    "tutorial": {
        "name": "教程步骤型",
        "beats": "目标引入 → 前置准备 → 分步操作演示 → 要点回顾 → 行动号召",
        "scene_guidance": (
            "第一幕：明确教程目标，展示最终效果或解决的问题，吸引观众继续看；"
            "中间幕：每个步骤一个场景，包含步骤编号、操作画面、关键标注文字；"
            "最后一幕：要点回顾总结，引导观众实践或关注。"
        ),
    },
}

# 模板ID → 叙事结构 + 推荐Pipeline的映射
TEMPLATE_CONFIG = {
    "product-ad": {
        "narrative": "product_showcase",
        "pipeline_hint": "qwen_product",
        "video_type": "产品宣传视频",
    },
    "beauty-review": {
        "narrative": "beauty_review",
        "pipeline_hint": "qwen_product",
        "video_type": "美妆种草视频",
    },
    "fashion-style": {
        "narrative": "product_showcase",
        "pipeline_hint": "qwen_product",
        "video_type": "服饰穿搭视频",
    },
    "food-showcase": {
        "narrative": "food_showcase",
        "pipeline_hint": "qwen_product",
        "video_type": "美食展示视频",
    },
    "tech-unbox": {
        "narrative": "tech_review",
        "pipeline_hint": "qwen_product",
        "video_type": "3C数码评测视频",
    },
    "home-living": {
        "narrative": "lifestyle",
        "pipeline_hint": "qwen_product",
        "video_type": "家居好物视频",
    },
    "brand-story": {
        "narrative": "brand_story",
        "pipeline_hint": "sora2",
        "video_type": "品牌故事视频",
    },
    "knowledge-edu": {
        "narrative": "knowledge_edu",
        "pipeline_hint": "sora2",
        "video_type": "知识科普视频",
    },
    "funny-skit": {
        "narrative": "funny_skit",
        "pipeline_hint": "sora2",
        "video_type": "搞笑段子视频",
    },
    "travel-vlog": {
        "narrative": "travel_vlog",
        "pipeline_hint": "sora2",
        "video_type": "旅行Vlog",
    },
    "tutorial": {
        "narrative": "tutorial",
        "pipeline_hint": "tutorial",
        "video_type": "教程视频",
    },
    "tutorial-soft": {
        "narrative": "tutorial",
        "pipeline_hint": "tutorial",
        "video_type": "教程视频",
    },
    "tutorial-know": {
        "narrative": "tutorial",
        "pipeline_hint": "tutorial",
        "video_type": "教程视频",
    },
    "tutorial-prod": {
        "narrative": "tutorial",
        "pipeline_hint": "tutorial",
        "video_type": "教程视频",
    },
    "digital-human": {
        "narrative": "product_showcase",
        "pipeline_hint": "digital_human",
        "video_type": "数字人口播视频",
    },
    "empty": {
        "narrative": "product_showcase",
        "pipeline_hint": None,
        "video_type": "自定义视频",
    },
}


def get_narrative_for_template(template_id: str) -> dict:
    """根据模板ID获取叙事结构配置"""
    config = TEMPLATE_CONFIG.get(template_id, TEMPLATE_CONFIG["empty"])
    narrative_key = config["narrative"]
    return NARRATIVE_STRUCTURES.get(
        narrative_key, NARRATIVE_STRUCTURES["product_showcase"]
    )


def get_pipeline_hint_for_template(template_id: str) -> str | None:
    """根据模板ID获取推荐的pipeline名称"""
    config = TEMPLATE_CONFIG.get(template_id, TEMPLATE_CONFIG["empty"])
    return config.get("pipeline_hint")


@tool
def extract_project_info(
    theme: Optional[str] = None,
    style: Optional[str] = None,
    duration: Optional[int] = None,
    orientation: Optional[str] = None,
    video_type: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    product_image: Optional[str] = None,
) -> str:
    """
    Extract and save project metadata from the conversation.
    Call this whenever the user provides specific details like theme, style, duration, etc.
    """
    update = {}
    if theme:
        update["theme"] = theme
    if style:
        update["style"] = style
    if duration:
        update["duration"] = duration
    if orientation:
        update["orientation"] = orientation
    if video_type:
        update["video_type"] = video_type
    if keywords:
        update["keywords"] = keywords
    if product_image:
        update["product_image"] = product_image

    return json.dumps(
        {"status": "success", "updated_metadata": update}, ensure_ascii=False
    )


@tool
def submit_production_plan() -> str:
    """
    Call this tool when you have gathered enough information (at least Theme and Product Image)
    and are ready to proceed to the storyboard planning phase.
    """
    return json.dumps({"status": "ready_to_plan"}, ensure_ascii=False)
