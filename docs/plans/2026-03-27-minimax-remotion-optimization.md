# MiniMax PPT + Remotion 一致性与局部重试优化 Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 在仅保留 MiniMax 生成器的前提下，实现“PPT 为主、视频一致、失败可定位并小范围重试”的稳定生产链路。

**Architecture:** 采用“生成-校验-分片重试-合并-渲染”五段式流水线。PPTX 为唯一事实源（source of truth），视频默认基于 PPT 栅格图层呈现，再叠加 Remotion 动效层。失败按 `deck/slide/block` 三级定位，严格禁止本地规则改写用户文案。

**Tech Stack:** FastAPI(Python), Node(PptxGenJS), Remotion, Supabase, R2

---

## 官方与社区最佳实践依据（用于本方案）

1. Remotion 官方建议优先在渲染前取数，避免并发渲染线程重复请求与闪烁；渲染并发在 Lambda 可达高倍并发，且多线程返回数据必须一致。
2. Remotion 官方说明 `delayRender()` 默认 30 秒超时，应使用 label、超时治理、失败即取消。
3. Google Cloud IAM 重试策略建议：仅对可重试错误使用“截断指数退避 + jitter”，并设置 deadline。
4. Azure Retry Pattern 强调：只对 transient fault 重试；终态错误快速失败；与 circuit breaker 组合。
5. Temporal 文档强调活动需幂等（idempotent），因为 Activity 存在至少一次执行语义。
6. MiniMax 官方 skills 仓库中的 `pptx-generator` 与 `pptx-plugin`均强调：有完整设计系统、模板编辑工作流、子任务化生成，不应被单一本地模板压平。
7. PptxGenJS 文档强调可使用 Slide Master 与亚洲字体支持，适合企业级一致样式输出。
8. PPTAgent/PPTEval（社区研究）提出应同时评估 Content / Design / Coherence 三维度，适合作为验收指标。

---

### Task 1: 定义“单一事实源 + 分片 ID”契约

**Files:**
- Create: `docs/specs/ppt-video-contract.md`
- Modify: `agent/src/schemas/ppt.py`
- Modify: `agent/src/schemas/ppt_v7.py`
- Test: `agent/tests/test_ppt_contract.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_ppt_contract.py

def test_export_request_has_retry_scope_fields():
    from src.schemas.ppt import ExportRequest
    req = ExportRequest(slides=[], title="t", author="a")
    assert hasattr(req, "retry_scope")
    assert hasattr(req, "retry_hint")
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_contract.py::test_export_request_has_retry_scope_fields -v`
Expected: FAIL with missing fields.

**Step 3: Write minimal implementation**
- 在 schema 中新增：`deck_id`、`slide_id`、`block_id`、`retry_scope(deck|slide|block)`、`retry_hint`、`idempotency_key`。
- 约束：`slide_id` 稳定且不可重排；`block_id` 对文本块稳定。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_contract.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add docs/specs/ppt-video-contract.md agent/src/schemas/ppt.py agent/src/schemas/ppt_v7.py agent/tests/test_ppt_contract.py
git commit -m "feat: define ppt-video contract with deck/slide/block ids"
```

### Task 2: 建立失败分类器（可重试/不可重试）

**Files:**
- Create: `agent/src/ppt_failure_classifier.py`
- Modify: `agent/src/minimax_exporter.py`
- Test: `agent/tests/test_ppt_failure_classifier.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_ppt_failure_classifier.py

def test_timeout_is_retryable():
    from src.ppt_failure_classifier import classify_failure
    c = classify_failure("subprocess.TimeoutExpired: timed out after 180 seconds")
    assert c.code == "timeout"
    assert c.retryable is True
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_failure_classifier.py::test_timeout_is_retryable -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 分类码：`timeout / rate_limit / upstream_5xx / schema_invalid / encoding_invalid / auth_invalid / unknown`。
- 为每类输出：`retryable`, `max_attempts`, `base_delay_ms`, `message_for_retry_prompt`。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_failure_classifier.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add agent/src/ppt_failure_classifier.py agent/src/minimax_exporter.py agent/tests/test_ppt_failure_classifier.py
git commit -m "feat: add structured failure classifier for minimax export"
```

### Task 3: 实现“携带失败原因”的定向重试器

**Files:**
- Create: `agent/src/ppt_retry_orchestrator.py`
- Modify: `agent/src/ppt_service.py`
- Test: `agent/tests/test_ppt_retry_orchestrator.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_ppt_retry_orchestrator.py

def test_non_retryable_fails_fast():
    from src.ppt_retry_orchestrator import should_retry
    assert should_retry(code="auth_invalid", attempt=1) is False
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_retry_orchestrator.py::test_non_retryable_fails_fast -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 实现截断指数退避 + jitter：`min(2^n + rand, max_backoff)`。
- 仅对 `timeout/429/5xx/schema_invalid/encoding_invalid` 重试。
- 每次重试附加 `retry_hint` 到 MiniMax 请求。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_retry_orchestrator.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add agent/src/ppt_retry_orchestrator.py agent/src/ppt_service.py agent/tests/test_ppt_retry_orchestrator.py
git commit -m "feat: add reason-aware retry orchestrator for ppt generation"
```

### Task 4: 支持 Slide/Block 局部重试与局部覆盖

**Files:**
- Modify: `scripts/generate-pptx-minimax.mjs`
- Modify: `agent/src/minimax_exporter.py`
- Create: `agent/src/ppt_patch_merge.py`
- Test: `agent/tests/test_ppt_patch_merge.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_ppt_patch_merge.py

def test_only_failed_slide_is_replaced():
    from src.ppt_patch_merge import merge_slides
    base = [{"slide_id": "s1", "title": "A"}, {"slide_id": "s2", "title": "B"}]
    patch = [{"slide_id": "s2", "title": "B2"}]
    out = merge_slides(base, patch)
    assert out[0]["title"] == "A"
    assert out[1]["title"] == "B2"
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_patch_merge.py::test_only_failed_slide_is_replaced -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- Node 侧支持参数：`--retry-scope --target-slide-ids --target-block-ids --retry-hint`。
- Python 侧合并策略：按稳定 ID 覆盖，不改顺序，不改其他页。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_patch_merge.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/generate-pptx-minimax.mjs agent/src/minimax_exporter.py agent/src/ppt_patch_merge.py agent/tests/test_ppt_patch_merge.py
git commit -m "feat: support slide/block scoped retry and deterministic merge"
```

### Task 5: 强化编码与内容完整性校验（防乱码/空页）

**Files:**
- Modify: `agent/src/ppt_service.py`
- Create: `agent/src/ppt_quality_gate.py`
- Test: `agent/tests/test_ppt_quality_gate.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_ppt_quality_gate.py

def test_detect_blank_or_garbled_slide():
    from src.ppt_quality_gate import validate_slide
    result = validate_slide({"title": "???", "elements": []})
    assert result.ok is False
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_quality_gate.py::test_detect_blank_or_garbled_slide -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 规则：标题/正文最小信息量、乱码占比、空白页、异常占位符（如 `???`）。
- 不通过时触发 block 或 slide 重试；超限后失败并回传原因。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_quality_gate.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add agent/src/ppt_service.py agent/src/ppt_quality_gate.py agent/tests/test_ppt_quality_gate.py
git commit -m "feat: add quality gate for garbled text blank slides and placeholders"
```

### Task 6: 锁定“PPT 为主”的视频一致性渲染

**Files:**
- Modify: `agent/src/ppt_service.py`
- Modify: `src/remotion/compositions/ImageSlideshow.tsx`
- Modify: `src/remotion/compositions/SlidePresentation.tsx`
- Test: `src/lib/generation/__tests__/ppt-video-consistency.test.ts`

**Step 1: Write the failing test**
```ts
// src/lib/generation/__tests__/ppt-video-consistency.test.ts
it('uses ppt raster slides as base layer when available', () => {
  const mode = chooseVideoMode({slide_image_urls: ['a.png'], render_spec: {slides: []}});
  expect(mode).toBe('ppt_image_slideshow');
});
```

**Step 2: Run test to verify it fails**
Run: `pnpm vitest src/lib/generation/__tests__/ppt-video-consistency.test.ts`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 优先使用 `slide_image_urls` 作为视频底图，保证文字/版式与 PPT 一致。
- 动效仅做“叠加层”（高亮、淡入、指示线），禁止改变底图内容。

**Step 4: Run test to verify it passes**
Run: `pnpm vitest src/lib/generation/__tests__/ppt-video-consistency.test.ts`
Expected: PASS.

**Step 5: Commit**
```bash
git add agent/src/ppt_service.py src/remotion/compositions/ImageSlideshow.tsx src/remotion/compositions/SlidePresentation.tsx src/lib/generation/__tests__/ppt-video-consistency.test.ts
git commit -m "feat: enforce ppt-first video rendering with overlay-only effects"
```

### Task 7: 持久化重试与诊断（Supabase）

**Files:**
- Create: `docs/sql/2026-03-27-ppt_retry_diagnostics.sql`
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/src/api_routes.py`
- Test: `agent/tests/test_ppt_retry_persistence.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_ppt_retry_persistence.py

def test_persist_failure_code_and_scope():
    row = {"failure_code": "timeout", "retry_scope": "slide"}
    assert row["failure_code"] == "timeout"
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_retry_persistence.py -v`
Expected: FAIL until persistence wiring done.

**Step 3: Write minimal implementation**
- 新增字段：`failure_code`, `failure_detail`, `retry_scope`, `retry_target_ids`, `attempt`, `idempotency_key`, `render_spec_version`。
- API 返回统一错误结构，前端可展示“失败页与失败文案”。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_ppt_retry_persistence.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add docs/sql/2026-03-27-ppt_retry_diagnostics.sql agent/src/ppt_service.py agent/src/api_routes.py agent/tests/test_ppt_retry_persistence.py
git commit -m "feat: persist ppt retry diagnostics and expose structured failure details"
```

### Task 8: 引入“模板生态不被压平”保护开关

**Files:**
- Modify: `scripts/generate-pptx-minimax.mjs`
- Modify: `agent/src/minimax_exporter.py`
- Test: `agent/tests/test_template_preservation.py`

**Step 1: Write the failing test**
```python
# agent/tests/test_template_preservation.py

def test_no_local_style_override_when_original_mode_enabled():
    from src.minimax_exporter import build_payload
    p = build_payload(slides=[], title='t', author='a', original_style=True)
    assert p['disable_local_style_rewrite'] is True
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_template_preservation.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
- 新增 `original_style=true` 时：禁用本地“强制 TOC/Summary 注入、风格重配、文案重写”。
- 仅在明确失败并命中重试策略时执行最小局部修复。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_template_preservation.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/generate-pptx-minimax.mjs agent/src/minimax_exporter.py agent/tests/test_template_preservation.py
git commit -m "feat: preserve minimax original template mode without local flattening"
```

### Task 9: 端到端验收（真实环境，不走 mock）

**Files:**
- Modify: `scripts/run_ui_ppt_v7_real_e2e.py`
- Modify: `scripts/run_ppt_dual_skill_fullflow.py`
- Create: `scripts/assert_ppt_video_consistency.py`
- Test: `test_reports/ppt_video_consistency/*.json`

**Step 1: Write the failing test harness**
```bash
python scripts/assert_ppt_video_consistency.py --ppt <pptx> --video <mp4> --expect-threshold 0.98
```

**Step 2: Run harness to verify it fails on known bad sample**
Run: `python scripts/assert_ppt_video_consistency.py --ppt bad.pptx --video bad.mp4 --expect-threshold 0.98`
Expected: FAIL with mismatch frames.

**Step 3: Write minimal implementation**
- 对每页首帧/中帧抽样 OCR + 结构相似度校验。
- 输出 `slide_match_score`，低于阈值触发告警。

**Step 4: Run real E2E and verify pass**
Run:
```bash
python scripts/run_ui_ppt_v7_real_e2e.py
python scripts/assert_ppt_video_consistency.py --ppt <new.pptx> --video <new.mp4> --expect-threshold 0.98
```
Expected: PASS, no mock path.

**Step 5: Commit**
```bash
git add scripts/run_ui_ppt_v7_real_e2e.py scripts/run_ppt_dual_skill_fullflow.py scripts/assert_ppt_video_consistency.py test_reports/ppt_video_consistency
git commit -m "test: add real e2e consistency validation for ppt-video pipeline"
```

### Task 10: 灰度上线与回滚预案

**Files:**
- Create: `docs/runbooks/ppt-pipeline-rollout.md`
- Modify: `agent/.env.example`
- Modify: `agent/src/configs/settings.py`

**Step 1: Write rollout checklist test**
- 定义可观测门槛：成功率、平均时长、重试次数、风格一致性评分。

**Step 2: Dry run checklist**
Run: 按 runbook 进行 staging 验证。
Expected: 所有阈值达标。

**Step 3: Write minimal implementation**
- 增加开关：`PPT_RETRY_ENABLED`, `PPT_PARTIAL_RETRY_ENABLED`, `PPT_VIDEO_BASE_MODE=ppt_image_slideshow`。
- 支持 10%/50%/100% 灰度。

**Step 4: Verify rollback path**
Run: 切换开关回退至旧逻辑并验证可用。
Expected: 回滚 5 分钟内可恢复。

**Step 5: Commit**
```bash
git add docs/runbooks/ppt-pipeline-rollout.md agent/.env.example agent/src/configs/settings.py
git commit -m "chore: add rollout and rollback controls for ppt pipeline"
```

---

## 验收标准（Definition of Done）

1. 真实环境 E2E（非 mock）成功率 >= 95%。
2. PPT 与视频一致性评分 >= 0.98（逐页）。
3. 失败重试平均范围 <= 1.5 页（不整份重跑）。
4. `timeout/429/5xx` 重试后恢复率 >= 80%。
5. 乱码/空白/声明污染问题在质量门禁中 100% 拦截。
6. original style 模式下，不再出现本地模板压平。

## 监控指标

- `ppt_export_success_rate`
- `ppt_export_latency_p50/p95`
- `ppt_retry_attempts_avg`
- `ppt_retry_scope_distribution(deck/slide/block)`
- `ppt_video_consistency_score`
- `ppt_template_preservation_score`

## 风险与缓解

1. 上游 API 抖动导致重试风暴。
缓解：限并发 + 指数退避 + 熔断。
2. 局部合并引入顺序错乱。
缓解：稳定 ID + 不可变顺序校验。
3. 动效层影响一致性评分。
缓解：动效仅叠加，不改底图。
