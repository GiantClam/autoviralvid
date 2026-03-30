---
iteration: 1
max_iterations: 10
completion_promise: "VERIFIED"
started_at: "2026-03-30T00:00:00+08:00"
---

## PPT 视觉回归测试循环

目标: 从参考 PPT 生成符合项目格式要求的 PPT，通过迭代修复，直到视觉分数达到 80 分以上。

### 参考 PPT
"C:\Users\liula\Downloads\ppt2\ppt2\1.pptx"

### 执行步骤

#### 步骤 2: 调用完整 PPT 生成功能
1. 调用 `python scripts/generate_ppt_from_desc.py --input "D:\github\with-langgraph-fastapi\test_inputs\work-summary-minimax-format.json" --output output/regression/generated.pptx --render-output output/regression/generated.render.json --mode auto` 生成新 PPT
2. 该脚本会优先调用 API 触发完整主流程（LLM 内容生成、图片搜索、Quality Gate、Retry 循环）
3. 如果 API 不可用，会 fallback 到本地 Node.js 渲染
4. 确保生成成功

#### 步骤 3: 视觉对比
1. 读取 `"C:\Users\liula\Downloads\ppt2\ppt2\1.pptx"`（参考 PPT）
2. 读取 `output/regression/generated.pptx`（生成 PPT）
3. 对比两个 PPT 的：
   - 每页的布局结构
   - 文字内容和位置
   - 颜色和样式
   - 图片和图表
   - 整体一致性
4. 生成差异报告，记录不足之处
5. 保存到 `output/regression/issues.json`

#### 步骤 4: 终止条件检查
- 如果没有不足，输出 VERIFIED 并结束循环
- 如果有不足，继续步骤 5

#### 步骤 5: 检索最佳实践
1. 检索方案文档 `"D:\github\with-langgraph-fastapi\.sisyphus\plans\2026-03-29-ppt-master-inspired-optimization.md"` 中的相关内容
2. 搜索社区最佳实践（PPT 生成、视觉设计、布局优化）
3. 根据不足类型，生成最优修复方案
4. 保存到 `output/regression/fix_plan.json`

#### 步骤 6: 实施修复
1. 根据修复方案，修改代码
2. 确保编译通过
3. 运行测试用例通过
4. 保存修复记录到 `output/regression/fix_record.json`

#### 步骤 7: 回到步骤 2
重新执行步骤 2-6，直到没有不足为止

### 加载 Skills
- pptx-generator
- slide-making-skill
- ppt-orchestra-skill
- systematic-debugging

### 使用 Agents
- explore: 查找代码模式
- librarian: 检索文档和最佳实践
- oracle: 架构决策和问题分析

### 完成条件
当生成的 PPT 与参考 PPT 视觉分数 >= 80 且无不足时，输出 VERIFIED 结束循环。
