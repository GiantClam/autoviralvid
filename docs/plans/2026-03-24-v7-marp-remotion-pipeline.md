# V7 Marp-Remotion Pipeline Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 让现有 v7 管线严格对齐附件方案：双 Agent 结构化输出、强校验 schema、Marp+Remotion 实时渲染、不走截图主轨、动作与 TTS 对齐。

**Architecture:** 以现有 `premium_generator_v7.py`、`v7_routes.py`、`marp_service_v7.py` 为主干，补充强约束 schema 和后处理修正层，避免大改。前端 Remotion 新增 `MarpPresentation` 组合并保持旧 `SlidePresentation` 兼容，通过渲染脚本自动选择组合。

**Tech Stack:** FastAPI, Pydantic v2, OpenRouter, Marp Core/CLI, Remotion, TypeScript

---

### Task 1: 建立 v7 强约束 Schema

**Files:**
- Create: `agent/src/schemas/ppt_v7.py`
- Modify: `agent/src/v7_routes.py`
- Test: `agent/tests/test_ppt_v7_schema.py`

**Step 1: Write the failing test**

```python
def test_slide_markdown_requires_mark_and_length_limit():
    ...
```

**Step 2: Run test to verify it fails**

Run: `cd agent && uv run pytest tests/test_ppt_v7_schema.py -v`
Expected: FAIL with missing schema/validator.

**Step 3: Write minimal implementation**

```python
class DialogueLine(BaseModel): ...
class SlideData(BaseModel): ...
class PresentationData(BaseModel): ...
```

**Step 4: Run test to verify it passes**

Run: `cd agent && uv run pytest tests/test_ppt_v7_schema.py -v`
Expected: PASS.

### Task 2: 重构 v7 生成链路并保证布局/内容约束

**Files:**
- Modify: `agent/src/premium_generator_v7.py`
- Test: `agent/tests/test_ppt_v7_generator.py`

**Step 1: Write the failing test**

```python
def test_enforce_non_adjacent_slide_type_and_ratio():
    ...
```

**Step 2: Run test to verify it fails**

Run: `cd agent && uv run pytest tests/test_ppt_v7_generator.py -v`
Expected: FAIL when planner output has duplicates or invalid ratio.

**Step 3: Write minimal implementation**

```python
def _plan_slide_types(...): ...
def _post_validate_and_fix(...): ...
```

**Step 4: Run test to verify it passes**

Run: `cd agent && uv run pytest tests/test_ppt_v7_generator.py -v`
Expected: PASS.

### Task 3: 升级动作与 TTS 对齐 + 导出链路校验

**Files:**
- Modify: `agent/src/v7_routes.py`
- Modify: `agent/src/marp_service_v7.py`
- Test: `agent/tests/test_ppt_v7_routes.py`

**Step 1: Write the failing test**

```python
def test_align_highlight_start_frame_with_keyword_timeline():
    ...
```

**Step 2: Run test to verify it fails**

Run: `cd agent && uv run pytest tests/test_ppt_v7_routes.py -v`
Expected: FAIL with old char-ratio alignment.

**Step 3: Write minimal implementation**

```python
def _estimate_word_timestamps(...): ...
def _align_action_start_frames(...): ...
```

**Step 4: Run test to verify it passes**

Run: `cd agent && uv run pytest tests/test_ppt_v7_routes.py -v`
Expected: PASS.

### Task 4: 新增 Remotion MarpPresentation 主轨并接入本地渲染脚本

**Files:**
- Create: `src/remotion/compositions/MarpPresentation.tsx`
- Modify: `src/remotion/components/MarpSlide.tsx`
- Modify: `src/remotion/index.tsx`
- Modify: `src/remotion/compositions/index.ts`
- Modify: `scripts/render-local.mjs`
- Test: `npm run test -- src/lib/render/remotion-mapper.test.ts`

**Step 1: Write the failing test**

```ts
it('selects MarpPresentation when markdown slides are provided', async () => {
  ...
});
```

**Step 2: Run test to verify it fails**

Run: `npm run test`
Expected: FAIL because composition selector is missing.

**Step 3: Write minimal implementation**

```tsx
export default function MarpPresentation(...) { ... }
```

**Step 4: Run test to verify it passes**

Run: `npm run test`
Expected: PASS.

