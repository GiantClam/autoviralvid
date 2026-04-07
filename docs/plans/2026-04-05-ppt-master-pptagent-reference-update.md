# PPT 生成质量升级方案（基于 `ppt-master` / `PPTAgent` 代码复核）

> 本文档是在 `docs/plans/PPT生成质量问题根因分析与解决方案.md` 与 `docs/plans/2026-04-01-ppt-design-quality-optimization-v1.md` 的基础上，结合对 `https://github.com/hugohe3/ppt-master` 与 `https://github.com/icip-cas/PPTAgent` 实际代码/文档的复核后形成的补充更新版方案。

## 1. 目标

当前仓库已经完成了：
- 统一设计决策主干（`design_decision_v1`）
- 主流程接入（`run_ppt_pipeline` / `export_pptx`）
- 质量门、重试、模板路由、视觉 critic 的基础收敛

但在与参考样本 `1.pptx` 的对比中，仍存在明显差距：
- 标题序列已改善，但正文内容与课堂叙事结构仍偏离参考
- 字体体系、主题色体系、几何版式与 `ppt-master` 风格明显不同
- 课堂/训练场景仍会被通用模板的“语义补写”和图像倾向拖偏

本方案的目标不是“为单个主题硬编码”，而是：

1. 吸收 `ppt-master` 的 **严格串行 + SVG/模板高保真执行** 思路
2. 吸收 `PPTAgent` 的 **参考驱动 + 功能页骨架 + Content/Design/Coherence 评估** 思路
3. 在现有 `v1` 主干架构内，形成一套 **对课堂/训练类 deck 普适** 的 text/chart-first 生成方案

---

## 2. 参考项目代码结论

### 2.1 `ppt-master` 的核心做法

复核位置：
- `.omx/reference-repos/ppt-master/README.md`
- `.omx/reference-repos/ppt-master/docs/technical-design.md`
- `.omx/reference-repos/ppt-master/skills/ppt-master/SKILL.md`

结论：

1. **严格串行流水线**
   - `Source -> Template Option -> Strategist -> Executor -> Post-processing -> Export`
   - 不允许跨阶段偷跑，不允许在 Strategist 阶段提前生成 SVG。

2. **Design Spec 先于页面生成**
   - 通过 Eight Confirmations 先确定格式、页数、受众、颜色、字体、图像策略。
   - 页面执行阶段只消费已确认的全局设计规格。

3. **SVG-first，而不是自由 SVG-to-PPTX 拼装**
   - `ppt-master` 先产出 SVG 页面，再做后处理与 PPTX 导出。
   - 复杂页面依赖 SVG 保真，而不是在 PPTX 层临时自由几何拼装。

4. **逐页顺序生成，主代理持有完整上下文**
   - 明确禁止子代理分摊 SVG 页面生成。
   - 其目的是保证跨页风格一致性和叙事连续性。

5. **它解决的是“高保真执行”问题**
   - 不是靠更多启发式选模板，而是靠：
     - 先定设计规格
     - 再顺序生成页面
     - 再工程化导出

### 2.2 `PPTAgent` 的核心做法

复核位置：
- `.omx/reference-repos/PPTAgent/pptagent/README.md`
- `.omx/reference-repos/PPTAgent/pptagent/BESTPRACTICE.md`
- `.omx/reference-repos/PPTAgent/pptagent/agent.py`
- `.omx/reference-repos/PPTAgent/pptagent/ppteval.py`

结论：

1. **Analysis -> Generation 两阶段**
   - 先从参考演示文稿中学习结构/版式/功能页模式
   - 再基于 outline 逐页生成

2. **功能页骨架是刚性的**
   - Opening / Table of Contents / Section Header / Ending 四类功能页被显式约束
   - 功能页不是模型自由生成，而是规则化插入

3. **参考驱动，而不是无约束模板路由**
   - 质量高度依赖高质量 reference slide
   - 重点不是“自动发明新结构”，而是“在参考约束下迁移内容”

4. **内容/设计/逻辑三维评估**
   - `PPTEval` 不是只看是否导出成功
   - 它把质量拆为：Content、Design、Coherence

5. **它解决的是“风格迁移与结构约束”问题**
   - 不是复杂页面 SVG 保真优先，而是：
     - 参考页约束
     - 文本量控制
     - 功能页规则
     - 三维验收

---

## 3. 两个参考项目对当前系统的启示

### 3.1 `ppt-master` 给我们的启示

当前系统最应该吸收的不是“再做一个独立工具”，而是：

1. **Render 端不要再做语义决策**
   - 模板执行层只负责布局与视觉，不负责“补写一段更像演讲的文案”。

2. **复杂页与高保真页应走受控表达路径**
   - 不是在 SVG-to-PPTX 里任意拼 shape。
   - 更适合：
     - text/chart-first 模板主干
     - 必要时走 SVG/受控图表路径

3. **逐页顺序执行仍然有价值**
   - 当前系统虽然有统一决策源，但模板层仍存在局部 fallback 语义生成。
   - `ppt-master` 的串行 discipline 提醒我们：跨页一致性比单页“聪明修补”更重要。

### 3.2 `PPTAgent` 给我们的启示

当前系统最应该吸收的是：

1. **课堂/训练类 deck 需要固定骨架**
   - 不能只把 research key points 平铺成 8 张中间页。
   - 应有稳定教学骨架：
     - cover
     - toc
     - concept
     - roles
     - process
     - impact / institutional interface
     - case
     - trend / reflection
     - summary
     - thanks

2. **功能页和内容页要区别对待**
   - 当前系统在训练类 deck 上仍有过多“内容模板自由切换”。
   - `PPTAgent` 的功能页约束说明：目录页、结尾页、章节页应有单独合同。

3. **正文长度和元素数量应被显式控制**
   - 课堂页不适合塞入过多 card/图像占位。
   - 每页元素数量、文字密度、文本占比都应进入合同/评分。

4. **评估应显式分 Content / Design / Coherence**
   - 当前系统已有 `quality_gate + visual_qa + comparator`，但还缺“教育场景专属验收基线”。

---

## 4. 当前系统的剩余根因（基于真实生成与对比）

以主流程 prompt：

`请制作一份高中课堂展示课件，主题为“解码立法过程：理解其对国际关系的影响”`

对比参考 `1.pptx` 后，当前主要根因是：

### 根因 A：课堂故事线仍然偏“通用扩写”

表现：
- 中间页虽然不再严重重复，但仍更像“自动归纳出来的主题串”，而不是典型课堂课件的稳定教学主线。

根因：
- `build_instructional_topic_points()` 生成的中间页骨架此前偏通用
- `expand_semantic_support_points()` 仍会输出大量“提示型前缀句”

### 根因 B：模板层仍会轻度做“语义补写”

表现：
- 即使 `render_payload` 标题已正确，模板 fallback 仍可能把局部内容改造成“背景/机制/影响”式短句

根因：
- `scripts/minimax/templates/template-renderers.mjs` 中仍存在 `semanticFallbackBullets`、`semanticSequenceLabel`、图表 fallback label 这类语义生成逻辑

### 根因 C：训练类 deck 仍未真正切到 text/chart-first 主干

表现：
- 参考 `1.pptx` 基本是文本/结构驱动
- 当前系统仍倾向插入 image/media placeholder 或 image slot

根因：
- `training_deck` 虽已接入质量 profile，但模板 pack 仍混有不必要的 image/media 表达偏好

### 根因 D：视觉系统与参考风格系谱不同

表现：
- 字体体系：当前更偏 `Microsoft YaHei/Segoe UI`
- 主题色体系：更偏现代 template catalog，而不是参考 PPT 的课堂风格

根因：
- 当前模板 pack 的主题方案是“现代通用模板系统”，并非“课堂课件 reference 系谱”

---

## 5. 更新后的最优方案

### 原则 1：继续保留 `v1` 单主干架构

不另起一套新系统，不复制 `ppt-master` 或 `PPTAgent`。

仍然坚持：

`Input Normalize -> Design Decision -> Render -> Quality Evaluate -> Bounded Retry`

### 原则 2：引入“Deck Archetype Profile”层，但不新增独立智能层

新增一个轻量策略层：`deck_archetype_profile`

候选：
- `education_textbook`
- `consulting_argument`
- `marketing_visual`
- `technical_review`

作用：
- 只决定 **结构合同与模板族边界**
- 不直接生成文案

对于课堂/训练类：
- `deck_archetype_profile = education_textbook`

它将决定：
- 允许的 page roles
- 允许的 template family pack
- 是否允许 image-first
- 字体/色彩/密度上限
- 是否启用 reference-like story skeleton

### 原则 3：课堂 deck 必须走 `text/chart-first` 而不是 `image-first`

对 `education_textbook`：

1. 默认不要求 image anchor
2. 视觉锚点优先级：
   - chart
   - table
   - quote / callout
   - text highlight
   - image（仅当输入有真实图像证据）
3. layout solver 的 `add_visual_anchor` 不应默认补 image，而应优先补：
   - chart
   - kpi
   - quote / structure block

### 原则 4：Node 模板层停止语义生成，只做布局执行

这是最关键的一条。

当前模板层仍存在：
- `semanticFallbackBullets`
- `semanticSequenceLabel`
- 图表 label fallback 的语义拼接

这些逻辑应降级为：

1. **只允许格式化现有内容**
2. **不允许创造新的语义短句**
3. fallback 只能做：
   - 截断
   - 去重
   - 文本拆分
   - 排序
   - 视觉映射

不允许再做：
- `背景/机制/影响/结论` 这类自动补写
- `Core idea / Key point` 这类模板句拼接

### 原则 5：功能页骨架借鉴 `PPTAgent`

课堂/训练类 deck 固定中间骨架，不再完全由 research keypoints 自由铺开。

推荐骨架：

1. `课程导航`
2. `什么是 X`
3. `X 中的关键角色`
4. `X 的关键阶段`
5. `X 与 Y 的交汇`
6. `Y 中的制度接口`
7. `案例分析：X 的 Y 影响`
8. `未来趋势与思考`
9. `课堂总结`
10. `谢谢`

其中：
- 具体标题由 `subject/focus` 语义化填充
- 不是针对“立法过程”硬编码，而是对所有课堂主题普适

### 原则 6：参考相似度引入“教育专属验收”

在现有 comparator 基础上增加：

1. `functional_skeleton_similarity`
   - cover/toc/summary/thanks 顺序一致性

2. `text_first_ratio`
   - 非终页中 image/media 主导页占比上限

3. `instructional_storyline_similarity`
   - concept / role / process / impact / case / trend 的顺序匹配度

4. `template_pack_stability`
   - classroom deck 中 template family 应收敛到少数 text/chart-first family

---

## 6. 落地任务（在 `v1` 框架上的增量更新）

### Task A：新增 `deck_archetype_profile`

**Files**
- Modify: `agent/src/ppt_service.py`
- Modify: `scripts/minimax/templates/template-catalog.json`
- Test: `agent/tests/test_ppt_service_skill_path.py`

**目标**
- 在主流程中统一推导 `education_textbook / consulting_argument / marketing_visual / technical_review`
- 课堂场景固定走 `education_textbook`

### Task B：Node 模板层去语义生成

**Files**
- Modify: `scripts/minimax/templates/template-renderers.mjs`
- Test: `scripts/tests/generate-pptx-minimax.harness.test.mjs`

**目标**
- 删除/降级 `semanticFallbackBullets`、`semanticSequenceLabel`、语义 chart label fallback
- 模板层只做布局/截断/格式化，不生成新句子

### Task C：教育模板 pack 主干化

**Files**
- Modify: `scripts/minimax/templates/template-catalog.json`
- Modify: `agent/src/ppt_service.py`
- Test: `agent/tests/test_ppt_template_routing.py`

**目标**
- `training_deck` / `education_textbook` 只允许少数 text/chart-first family
- 默认禁用非必要 image-first family

### Task D：layout solver 的视觉锚点策略改为“文本/图表优先”

**Files**
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/src/ppt_layout_solver.py`
- Test: `agent/tests/test_ppt_underflow_ladder.py`

**目标**
- underflow 时优先补 chart/kpi/quote，不默认补 image

### Task E：教育专属验收指标

**Files**
- Modify: `agent/src/pptx_comparator.py`
- Modify: `scripts/compare_ppt_visual.py`
- Test: `agent/tests/test_run_reference_regression_phase.py`

**目标**
- 除 `overall_score` 外，新增：
  - `functional_skeleton_similarity`
  - `text_first_ratio`
  - `instructional_storyline_similarity`
  - `template_pack_stability`

---

## 7. 非目标

本轮不做：

1. 不复制 `ppt-master` 的整套工具链
2. 不把当前系统改造成 reference-only 模式
3. 不针对“立法过程”做专门 case-by-case hardcode
4. 不通过放松所有质量门来“换取成功率”

---

## 8. 当前建议

如果后续要继续提升与 `1.pptx` 的接近度，优先级建议是：

1. **Task B：Node 模板层去语义生成**
2. **Task C：教育模板 pack 主干化**
3. **Task D：layout solver 视觉锚点改为 text/chart-first**
4. **Task E：教育专属验收指标**

这四项完成后，当前系统才更有可能在不硬编码具体主题的前提下，系统性逼近 `ppt-master` 的课堂类输出质量。
