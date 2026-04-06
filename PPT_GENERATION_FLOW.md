# PPT生成整体流程说明

## 📋 流程概览

当前项目的PPT生成采用**多阶段Pipeline架构**，主要分为以下几个核心阶段：

```
用户请求 → 输入规范化 → 设计决策 → 内容规划 → 渲染生成 → 质量评估 → 重试修复 → 导出输出
```

---

## 🔄 详细流程

### 阶段1: 请求接收与输入规范化

**入口**: `POST /api/v1/ppt/pipeline`

**主要文件**: `agent/src/ppt_routes.py`, `agent/src/ppt_service.py`

**处理内容**:
```python
# 1. 接收用户请求
{
    "topic": "解码霍尔木兹海峡危机",
    "purpose": "课程讲义",
    "audience": "high-school-students",
    "total_pages": 13,
    "quality_profile": "high_density_consulting",
    "route_mode": "refine"
}

# 2. 输入规范化
- 补齐缺失字段（默认值）
- 验证参数合法性
- 解析quality_profile和route_mode
- 确定execution_profile（dev_strict/prod_safe）
```

**关键函数**:
- `export_pptx()` - 主入口函数
- `_normalize_execution_profile()` - 规范化执行配置

---

### 阶段2: 设计决策（Design Decision）

**主要文件**: `agent/src/ppt_design_decision.py`, `agent/src/ppt_master_skill_adapter.py`

**核心理念**: **单一决策源（Single Source of Truth）**

```python
# 设计决策包含：
design_decision_v1 = {
    "deck": {
        "style_variant": "soft",           # 风格变体
        "palette_key": "education_charts", # 配色方案
        "theme_recipe": "classroom_soft",  # 主题配方
        "template_family": "consulting_warm_light", # 模板家族
        "tone": "light",                   # 色调
        "quality_profile": "high_density_consulting"
    },
    "slides": [
        # 每页幻灯片的决策
    ],
    "decision_trace": [
        # 决策来源追踪
    ]
}
```

**决策流程**:
1. **检测内容类型**
   ```python
   # 教育内容检测（我们的修复）
   if should_force_ppt_master_hit(
       quality_profile="high_density_consulting",
       purpose="课程讲义",
       topic="解码霍尔木兹海峡危机"
   ):
       use_ppt_master = True  # 强制使用专业模板
   ```

2. **运行设计技能链**
   ```python
   # Layer1设计技能
   skills = [
       "ppt-orchestra-skill",  # 整体编排
       "color-font-skill",     # 配色字体
       "design-style-skill",   # 设计风格
       "ppt-master"            # 专业模板（教育内容）
   ]
   ```

3. **生成统一决策**
   - 风格选择（sharp/soft/rounded/pill）
   - 配色方案（18种预设）
   - 模板家族选择
   - 布局网格确定

**关键函数**:
- `build_design_decision_v1()` - 构建设计决策
- `should_force_ppt_master_hit()` - 判断是否使用ppt-master
- `_run_layer1_design_skill_chain()` - 运行设计技能链

---

### 阶段3: 内容规划（Content Planning）

**主要文件**: `agent/src/ppt_planning.py`, `agent/src/ppt_storyline_planning.py`

**处理内容**:

1. **Storyline规划**
   ```python
   # 教育类PPT的storyline（我们的修复）
   required_sections = [
       "cover",              # 封面
       "learning_objectives", # 学习目标
       "core_concepts",      # 核心概念
       "case_analysis",      # 案例分析
       "discussion",         # 讨论
       "summary",            # 总结
       "references"          # 参考文献
   ]
   ```

2. **布局推荐**
   ```python
   # 根据内容类型推荐布局
   - hero_1: 封面、总结页
   - split_2: 概念解释、对比
   - grid_3/grid_4: 多要素展示
   - timeline: 流程、历史
   - bento_5: 数据可视化
   ```

3. **内容分页**
   - 控制每页内容密度
   - 避免文本溢出
   - 确保视觉平衡

**关键函数**:
- `build_instructional_topic_points()` - 构建教学要点
- `ensure_education_storyline_completeness()` - 验证教育内容完整性
- `recommend_layout()` - 推荐布局
- `enforce_density_rhythm()` - 控制密度节奏

---

### 阶段4: 渲染生成（Render）

**主要文件**: `agent/src/minimax_exporter.py`, `agent/src/svg_to_pptx/`

**渲染路径**:

```
Python层准备 → Node.js渲染 → PPTX生成
```

**两种渲染模式**:

1. **PptxGenJS模式**（默认）
   ```javascript
   // 使用PptxGenJS库直接生成
   const pptx = new PptxGenJS();
   pptx.addSlide();
   pptx.writeFile("output.pptx");
   ```

2. **SVG模式**（复杂图表）
   ```javascript
   // 先生成SVG，再嵌入PPTX
   - 适用于timeline、workflow、diagram等
   - 更高的视觉保真度
   ```

**渲染决策**:
```python
# 根据内容选择渲染路径
def choose_render_path(slide):
    if slide.layout == "timeline":
        return "svg"
    if "workflow" in slide.blocks:
        return "svg"
    return "pptxgenjs"
```

**关键函数**:
- `export_to_minimax_format()` - 导出为MiniMax格式
- `apply_render_paths()` - 应用渲染路径决策
- `minimax_exporter.py` + `svg_to_pptx` - Python DrawingML渲染脚本

---

### 阶段5: 质量评估（Quality Gate）

**主要文件**: `agent/src/ppt_quality_gate.py`

**评估维度**:

```python
quality_score = {
    "score": 78.5,  # 综合分数
    "passed": True,  # 是否通过
    "threshold": 80.0,  # 阈值（我们提升到80）
    "dimensions": {
        "structure": 82.0,    # 结构完整性
        "layout": 78.0,       # 布局多样性
        "family": 85.0,       # 模板一致性
        "visual": 76.0,       # 视觉质量
        "consistency": 80.0   # 一致性
    },
    "issue_counts": {
        "layout_homogeneous": 2,
        "title_font_too_small": 1
    }
}
```

**检查项目**:

1. **设计约束检查**（我们强化的部分）
   ```python
   - 三色原则: 最多3种非中性色
   - 字号约束: 标题≥24pt, 正文≥18pt
   - 空白比例: ≥15%
   - 对齐检查: 0.1英寸网格
   ```

2. **布局多样性**
   - 避免相邻页面重复布局
   - 控制单一布局占比
   - 确保视觉节奏

3. **视觉专业度**
   ```python
   visual_professional_score = {
       "color_consistency_score": 8.5,
       "layout_order_score": 8.0,
       "hierarchy_clarity_score": 8.2,
       "visual_avg_score": 8.23,
       "accuracy_gate_passed": True
   }
   ```

**关键函数**:
- `validate_render_payload_design()` - 设计约束验证
- `score_quality_gate()` - 质量评分
- `score_visual_professional_metrics()` - 视觉专业度评分

---

### 阶段6: 重试修复（Retry & Repair）

**主要文件**: `agent/src/ppt_retry_orchestrator.py`, `agent/src/ppt_visual_critic.py`

**重试策略**:

```python
# 根据route_mode确定重试次数
retry_budget = {
    "fast": 1,      # 快速模式
    "standard": 2,  # 标准模式
    "refine": 3     # 精细模式
}
```

**修复动作**:

```python
# 有限动作梯（我们的架构改进）
allowed_actions = [
    "compress_text",              # 压缩文本
    "downgrade_layout_density",   # 降低布局密度
    "add_visual_anchor",          # 添加视觉锚点
    "switch_render_path_once"     # 切换渲染路径
]

# 禁止的动作（避免不稳定）
forbidden_actions = [
    "change_style_variant",       # 不改变风格
    "change_palette_key",         # 不改变配色
    "change_template_family"      # 不改变模板
]
```

**修复流程**:
1. 识别问题码（issue_codes）
2. 映射到修复动作
3. 应用修复
4. 重新渲染
5. 再次评估

**关键函数**:
- `classify_failure()` - 失败分类
- `recommend_retry_action()` - 推荐修复动作
- `apply_visual_critic_feedback()` - 应用视觉反馈

---

### 阶段7: 导出输出

**主要文件**: `agent/src/ppt_export_pipeline.py`

**输出内容**:

```python
result = {
    "success": True,
    "data": {
        "run_id": "abc123",
        "pptx_path": "/path/to/output.pptx",
        "quality_score": {...},
        "visual_professional_score": {...},
        "design_decision_v1": {...},
        "observability_report": {
            "total_slides": 13,
            "render_success_rate": 1.0,
            "retry_count": 1,
            "issue_codes": []
        }
    }
}
```

**可观测性**:
- 每个阶段的耗时
- 决策来源追踪
- 问题码统计
- 重试历史

---

## 🎯 关键改进点（我们的修复）

### 1. 质量门禁提升

```python
# 修复前
"default": {"quality_score_threshold": 72}
"high_density_consulting": {"quality_score_threshold": 78}

# 修复后
"default": {"quality_score_threshold": 75}
"high_density_consulting": {"quality_score_threshold": 80}
```

### 2. 教育内容自动检测

```python
def should_force_ppt_master_hit(quality_profile, purpose, topic):
    # 自动检测教育关键词
    education_keywords = ["教学", "课程", "课堂", "培训", "教育"]
    
    if any(keyword in purpose for keyword in education_keywords):
        return True  # 强制使用ppt-master
    
    if quality_profile == "high_density_consulting":
        return True
```

### 3. Storyline完整性验证

```python
def ensure_education_storyline_completeness(slides, purpose, topic):
    # 检查必需章节
    required = ["cover", "learning_objectives", "core_concepts", "summary"]
    missing = check_missing_sections(slides, required)
    return missing  # 返回缺失章节列表
```

### 4. 设计约束强化

```python
# 在渲染前执行约束检查
design_constraint_report = validate_render_payload_design(render_payload)

if execution_profile == "dev_strict" and not design_constraint_report["passed"]:
    raise ValueError("Design constraints failed")
```

---

## 📊 数据流示意

```
用户输入
  ↓
[输入规范化]
  ↓
[设计决策] ← ppt-master (教育内容)
  ↓
design_decision_v1 (单一决策源)
  ↓
[内容规划] ← storyline验证
  ↓
render_payload
  ↓
[设计约束检查] ← 三色/字号/空白
  ↓
[渲染生成] (PptxGenJS/SVG)
  ↓
generated.pptx
  ↓
[质量评估] ← 阈值80分
  ↓
quality_score < threshold?
  ↓ Yes
[重试修复] (最多3次)
  ↓
[导出输出]
  ↓
最终PPTX + 可观测性报告
```

---

## 🔧 核心组件

### 1. Pipeline编排
- **文件**: `agent/src/ppt_export_pipeline.py`
- **职责**: 协调各阶段执行

### 2. 设计决策
- **文件**: `agent/src/ppt_design_decision.py`
- **职责**: 统一视觉决策

### 3. 内容规划
- **文件**: `agent/src/ppt_planning.py`
- **职责**: 布局推荐、分页

### 4. 质量门禁
- **文件**: `agent/src/ppt_quality_gate.py`
- **职责**: 质量评分、约束检查

### 5. 重试编排
- **文件**: `agent/src/ppt_retry_orchestrator.py`
- **职责**: 失败修复、重试控制

### 6. 渲染引擎
- **文件**: `agent/src/minimax_exporter.py`
- **职责**: PPTX文件生成

---

## 📈 性能指标

### 典型耗时（13页PPT）

```
阶段                耗时
输入规范化          < 0.1s
设计决策            0.5-1s
内容规划            0.3-0.5s
渲染生成            3-5s
质量评估            0.5-1s
重试修复（如需）    3-5s × 重试次数
总计                5-15s（无重试）
                    10-30s（有重试）
```

### 质量指标

```
指标                目标值
Quality Score       ≥ 75 (default) / ≥ 80 (high_density)
Visual Avg          ≥ 7.5
Accuracy Gate       PASSED
Retry Count         ≤ 1.5 (平均)
Success Rate        ≥ 95%
```

---

## 🎓 最佳实践

### 1. 使用合适的quality_profile

```python
# 教育类内容
quality_profile = "high_density_consulting"  # 推荐

# 快速草稿
quality_profile = "lenient_draft"

# 标准商务
quality_profile = "default"
```

### 2. 选择合适的route_mode

```python
# 高质量要求
route_mode = "refine"  # 最多3次重试

# 标准质量
route_mode = "standard"  # 最多2次重试

# 快速生成
route_mode = "fast"  # 最多1次重试
```

### 3. 提供完整的输入

```python
request = {
    "topic": "明确的主题",
    "purpose": "课程讲义/工作汇报/融资路演",  # 明确目的
    "audience": "high-school-students",
    "total_pages": 13,  # 明确页数
    "quality_profile": "high_density_consulting"
}
```

---

## 📚 相关文档

- **架构设计**: `docs/plans/2026-04-01-ppt-design-quality-optimization-v1.md`
- **修复总结**: `docs/reports/2026-04-06-ppt-quality-fix-summary.md`
- **验证指南**: `VERIFICATION_GUIDE.md`
- **最终总结**: `FINAL_SUMMARY.md`

---

**文档生成时间**: 2026-04-06  
**当前版本**: v1.0 (质量提升版)
