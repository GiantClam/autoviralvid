# Phase 1: 深耕电商 + Phase 2 架构扩展 执行计划

## 目标
1. 将电商产品视频场景做深做透（模板、叙事结构、风格）
2. 为后续数字人等新 pipeline 铺好扩展架构

---

## 任务清单

### T1: 扩展模板系统（前端 TemplateGallery）
**文件**: `src/components/TemplateGallery.tsx`

新增 8 个行业/场景模板：

| ID | 名称 | 描述 | 适用场景 |
|----|------|------|----------|
| beauty-review | 美妆种草 | 产品特写+使用效果，适合美妆护肤品推广 | 电商-美妆 |
| fashion-style | 服饰穿搭 | 多角度展示+搭配推荐，适合服装鞋包 | 电商-服饰 |
| food-showcase | 美食探店 | 美食特写+制作过程，适合餐饮食品 | 电商-食品 |
| tech-unbox | 3C数码开箱 | 开箱+功能演示+参数对比 | 电商-3C |
| home-living | 家居好物 | 场景化展示+使用体验 | 电商-家居 |
| knowledge-edu | 知识科普 | 问题驱动+图解讲解+案例演示 | 内容-教育 |
| funny-skit | 搞笑段子 | 日常反转+创意表达 | 内容-搞笑 |
| travel-vlog | 旅行Vlog | 风景+人文+叙事 | 内容-旅行 |

### T2: 扩展视频类型和风格选项（Agent gatherer）
**文件**: `agent/src/creative_agent.py`

- 扩展 VIDEO_TYPES：新增对应模板的视频类型
- 扩展 STYLE_OPTIONS：按行业增加风格
- 新增模板→视频类型→叙事结构的映射关系

### T3: 叙事结构模板系统（Planner 增强）
**文件**: `agent/src/agent_skills.py`

为 planner 增加多种叙事结构模板：

| 结构类型 | 适用场景 | 镜头节奏 |
|----------|---------|----------|
| product_showcase | 产品展示 | 问题引入→产品登场→功能演示→效果对比→行动号召 |
| brand_story | 品牌故事 | 情感铺垫→品牌理念→产品融入→情感升华 |
| beauty_review | 种草推荐 | 开箱展示→细节特写→上脸/使用→前后对比→真实感受 |
| food_showcase | 美食展示 | 原料展示→制作过程→成品特写→品尝反应→推荐总结 |
| knowledge_edu | 知识科普 | 问题抛出→知识讲解→案例演示→总结回顾 |
| funny_skit | 搞笑反转 | 日常场景→铺垫积累→意外反转→点题收尾 |
| tech_review | 数码评测 | 外观展示→功能测试→对比评测→优缺点→购买建议 |
| lifestyle | 生活方式 | 场景引入→体验展示→细节分享→氛围营造→感受总结 |

### T4: 前端模板→Agent 映射
**文件**: `src/app/page.tsx`, `src/components/AssistantChat.tsx`

- 扩展 `templateVideoTypes` 映射
- 模板选择时传递更多上下文（叙事结构、默认风格）到 Agent

### T5: Pipeline 注册便捷化 + 数字人预留
**文件**: `agent/src/configs/skills.yaml`, `agent/src/skills/registry.py`

- 在 skills.yaml 中增加 `digital_human` pipeline 占位
- 确保 SkillsRegistry 能自动发现新 pipeline
- 添加 pipeline 自描述能力（适用场景、所需输入）

### T6: 叙事结构与 Pipeline 智能匹配
**文件**: `agent/src/skills/selector.py` 或 `agent/src/langgraph_workflow.py`

- 根据视频类型自动选择最佳 pipeline
- 电商产品类 → qwen_product
- 通用/品牌故事 → sora2
- 数字人场景 → digital_human（预留）

---

## 执行顺序

```
T1 (模板UI) + T2 (Agent类型扩展) → 并行
    ↓
T3 (叙事结构) → 依赖 T2 的类型定义
    ↓
T4 (前端→Agent映射) → 依赖 T1 + T2
    ↓
T5 (Pipeline扩展) + T6 (智能匹配) → 并行
```

## 预计影响
- 模板从 2 个增加到 10 个
- 视频类型从 8 个增加到 15+ 个
- 分镜规划从通用广告结构扩展到 8 种叙事结构
- 为数字人 pipeline 预留完整接入点
