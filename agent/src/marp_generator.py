"""
Marp 生成器 v3 — 双步生成 + 高级设计 Prompt

Step 1: 内容架构师 Agent — 深度扩充 (案例+数据+比喻)
Step 2: 视觉排版师 Agent — 版式映射 (Marp Markdown + Script)
"""

from __future__ import annotations
import asyncio, json, logging, os, re
from typing import Any, Dict, List, Optional

from src.schemas.ppt_marp import SlideData, DialogueLine, PresentationMarp

logger = logging.getLogger("marp_generator")
MODEL = os.getenv("CONTENT_LLM_MODEL", "openai/gpt-4o-mini")


# ════════════════════════════════════════════════════════════════════
# Step 1: 内容扩充 Prompt (麦肯锡咨询顾问)
# ════════════════════════════════════════════════════════════════════

EXPANSION_PROMPT = """你是一个资深麦肯锡咨询顾问和商业文案专家。用户给你一个 PPT 主题和要点，你需要深度扩充每个观点。

对于每个核心观点，必须补充：
1. 具体数据 (数字、百分比、金额)
2. 实际案例 (真实场景、客户故事)
3. 生动比喻 (让普通人也能理解)

输出 JSON 格式:
{
    "slides": [
        {
            "title": "页面标题",
            "key_message": "这页最想传达的一句话 (30字以内, 用于屏幕显示)",
            "key_data": "最震撼的一个数据 (用于重点标注)",
            "expanded_content": "200-400字的深度解读 (用于讲解剧本)",
            "visual_hint": "建议的视觉表现方式: lead封面/要点列表/数据高亮/表格对比/引用金句",
            "bg_mood": "背景氛围: dark深沉/light明亮/gradient渐变"
        }
    ]
}"""


# ════════════════════════════════════════════════════════════════════
# Step 2: 视觉排版 Prompt (苹果发布会文案专家)
# ════════════════════════════════════════════════════════════════════

VISUAL_PROMPT = """你是一个顶级的幻灯片视觉设计师和苹果发布会文案专家。根据扩充后的内容，输出带强烈设计感的 Marp Markdown 和讲解剧本。

## 严格设计规范

### 1. 屏幕极简
屏幕上的 Markdown 文字不超过 30 个字。扩充解释、案例、数据全部放入 script 字段。

### 2. 重点标注
用 `<mark>` 包裹核心数据或金句:
- `今年营收增长了 <mark>500%</mark>`
- `<mark>0.005mm</mark> 微米级精度`

### 3. 高级布局 (必须交替使用)

**封面页**:
```html
<!-- _class: lead -->

# <!-- fit --> 灵创智能

**精准智造，赋能工业新未来**
```

**数据高亮页**:
```html
<!-- _class: lead -->

<div class="big-number"><mark>1000亿</mark></div>

全球数控机床市场规模 (美元)
```

**双栏卡片页**:
```html
# 核心产品

<div class="grid-2">
<div class="card">

### 高精度数控车床
加工精度 **0.005mm**
适用于基础零部件

</div>
<div class="card accent">

### 五轴联动加工中心
复杂曲面加工
适用于 **航空航天**

</div>
</div>
```

**表格对比页**:
```html
# 传统 vs 智能

| 对比项 | 传统加工 | 灵创智能 |
|--------|----------|----------|
| 精度 | 0.05mm | **0.005mm** |
| 效率 | 100件/天 | **150件/天** |
| 故障率 | 5% | **<1%** |
```

**金句引用页**:
```html
<!-- _class: lead -->

> 做最懂客户的数控机床合作伙伴

**持续为中国智造贡献力量**
```

**反色沉浸页**:
```html
<!-- _class: invert -->

# 千亿级市场

国产高端化率不足 <mark>10%</mark>

**巨大替代空间**
```

### 4. 讲解剧本
- 2-4 句话，每句 20-50 字
- 口语化，像跟朋友聊天
- 包含具体数据和案例
- 关键处配置 action: "draw_circle" 或 "spotlight"
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    si, ei = text.find("{"), text.rfind("}")
    if si != -1 and ei > si:
        try:
            return json.loads(text[si : ei + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Cannot parse: {text[:300]}")


# ════════════════════════════════════════════════════════════════════
# 双步生成
# ════════════════════════════════════════════════════════════════════


async def _step1_expand(
    requirement: str, slides_meta: List[Dict], client
) -> List[Dict]:
    """Step 1: 内容扩充"""
    meta_text = json.dumps(slides_meta, ensure_ascii=False, indent=2)
    prompt = f"""请深度扩充以下 PPT 内容:

【用户需求】
{requirement}

【大纲结构】
{meta_text}

每页补充: 具体数据、实际案例、生动比喻、核心金句。

返回 JSON: {{"slides": [{{"title": "...", "key_message": "...", "key_data": "...", "expanded_content": "...", "visual_hint": "lead/要点/数据高亮/表格对比/引用金句", "bg_mood": "dark/light"}}]}}"""

    raw = await client.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": EXPANSION_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    data = _extract_json(raw)
    return data.get("slides", slides_meta)


async def _step2_visualize(
    idx: int, expanded: Dict, total: int, client, prev_ending: str
) -> SlideData:
    """Step 2: 版式映射"""
    visual_hint = expanded.get("visual_hint", "要点列表")
    bg_mood = expanded.get("bg_mood", "light")

    layout_hints = {
        "lead": "使用 <!-- _class: lead --> 全屏居中",
        "数据高亮": "使用 <div class='big-number'> 大数字 + <mark> 标注",
        "表格对比": "使用 Markdown 表格 | 对比表",
        "引用金句": "使用 > 引用块 + <!-- _class: lead -->",
        "要点列表": "使用 <div class='grid-2'><div class='card'> 卡片布局",
    }
    layout_hint = layout_hints.get(visual_hint, "要点列表")

    ctx = f"上一页结尾: {prev_ending}\n用过渡句衔接。" if prev_ending else ""

    prompt = f"""请为第 {idx + 1}/{total} 页设计 Marp Markdown:

【页面标题】{expanded.get("title", "")}
【核心金句】{expanded.get("key_message", "")}
【关键数据】{expanded.get("key_data", "")}
【扩充内容】{expanded.get("expanded_content", "")[:500]}
【视觉提示】{layout_hint}
【背景氛围】{bg_mood}
{ctx}

返回 JSON:
{{
    "markdown": "Marp Markdown 代码 (含 Marp 指令、<mark> 标注、grid/card 布局)",
    "script": [
        {{"role": "host", "text": "20-50字口语化讲解", "target_id": "", "action": "none"}},
        {{"role": "host", "text": "强调核心数据", "target_id": "highlight-1", "action": "draw_circle"}}
    ]
}}"""

    raw = await client.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": VISUAL_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=2048,
    )
    data = _extract_json(raw)

    md = data.get("markdown", "")
    if not md or len(md) < 20:
        title = expanded.get("title", "未命名")
        msg = expanded.get("key_message", "")
        kd = expanded.get("key_data", "")
        md = f"# {title}\n\n<mark>{kd}</mark>\n\n{msg}"

    script = [
        DialogueLine(**s)
        for s in data.get(
            "script",
            [{"role": "host", "text": expanded.get("expanded_content", "")[:100]}],
        )
    ]

    return SlideData(order=idx, markdown=md, script=script)


async def generate_marp(
    req_data: dict, language: str = "zh-CN", ai_call=None
) -> PresentationMarp:
    """双步生成: 内容扩充 → 版式映射"""
    from src.openrouter_client import OpenRouterClient

    client = ai_call or OpenRouterClient()
    requirement = req_data.get("requirement", "")
    slides_meta = req_data.get("slides", [])

    # Step 1: 内容扩充 (整体一次)
    logger.info("[marp_gen] Step 1: Content expansion...")
    expanded = await _step1_expand(requirement, slides_meta, client)
    if len(expanded) < len(slides_meta):
        expanded = slides_meta  # 降级

    # Step 2: 版式映射 (并行)
    logger.info(f"[marp_gen] Step 2: Visual mapping {len(expanded)} slides...")
    num = len(expanded)
    sem = asyncio.Semaphore(3)
    all_endings: List[str] = [""] * num

    async def _run(idx: int, ex: dict) -> tuple[int, SlideData]:
        async with sem:
            prev = all_endings[idx - 1] if idx > 0 else ""
            result = await _step2_visualize(idx, ex, num, client, prev)
            all_endings[idx] = result.script[-1].text if result.script else ""
            return idx, result

    tasks = [_run(i, e) for i, e in enumerate(expanded)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    slides = [None] * num
    failures: List[str] = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Slide failed: {r}")
            failures.append(str(r))
            continue
        idx, data = r
        slides[idx] = data

    missing_indexes = [idx for idx, slide in enumerate(slides) if slide is None]
    if failures or missing_indexes:
        detail_parts = []
        if failures:
            detail_parts.append("; ".join(failures[:3]))
        if missing_indexes:
            detail_parts.append(f"missing_indexes={missing_indexes[:10]}")
        detail = " | ".join(detail_parts)[:800]
        raise RuntimeError(
            f"Marp content generation degraded: {len(failures)} failed, {len(missing_indexes)} missing. "
            f"Fallback is disabled. detail={detail}"
        )

    return PresentationMarp(
        title=req_data.get("title", ""),
        theme=req_data.get("theme", "default"),
        slides=[slide for slide in slides if slide is not None],
    )
