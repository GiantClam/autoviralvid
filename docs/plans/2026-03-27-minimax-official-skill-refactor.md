# MiniMax Official Skill Replacement (PPT Only) Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 先把 PPT 生成质量做对，用 MiniMax 官方 `pptx-plugin` 与 `pptx-generator` 作为核心替换当前本地风格生成逻辑，确保内容正确、版式稳定、风格不被压平。

**Architecture:** 采用分层替换（Strangler）而不是全量重写。Node 侧承接官方 skill 能力（编排+生成），Python 服务层保留失败分类、定向重试、质量门禁、诊断落库。当前阶段不改视频链路，视频能力进入 Phase 2。

**Tech Stack:** FastAPI, Node.js, PptxGenJS, Supabase, R2

---

## Decision

1. 不重写整套系统。
2. 不做“直接生替换后立即切流”。
3. 最优路径是“官方能力替换 + 适配层 + 灰度切流”，并且本阶段只做 PPT。

原因（针对你当前问题“效果不行”）：
- 当前问题核心在 PPT 生成内核和样式治理，不在视频渲染。
- 官方 `pptx-plugin` 是插件工作流形态，需要适配到现有后端调用契约，不能直接无缝替换。
- 你现有服务层的重试/门禁/诊断是生产能力，应该保留并与官方生成内核组合。

---

### Task 1: Vendor 官方能力并锁定版本

**Files:**
- Create: `vendor/minimax-skills/`
- Create: `scripts/vendor/sync_minimax_skills.sh`
- Modify: `README.md`
- Test: `scripts/tests/test_minimax_vendor_sync.sh`

**Step 1: Write the failing test**
```bash
# scripts/tests/test_minimax_vendor_sync.sh
test -f vendor/minimax-skills/plugins/pptx-plugin/README.md
test -f vendor/minimax-skills/skills/pptx-generator/SKILL.md
```

**Step 2: Run test to verify it fails**
Run: `bash scripts/tests/test_minimax_vendor_sync.sh`
Expected: FAIL (vendor 目录缺失)

**Step 3: Write minimal implementation**
- 添加同步脚本，只拉取：
  - `plugins/pptx-plugin`
  - `skills/pptx-generator`
- 固定 upstream commit SHA，禁止漂移。

**Step 4: Run test to verify it passes**
Run: `bash scripts/tests/test_minimax_vendor_sync.sh`
Expected: PASS

**Step 5: Commit**
```bash
git add vendor/minimax-skills scripts/vendor/sync_minimax_skills.sh scripts/tests/test_minimax_vendor_sync.sh README.md
git commit -m "chore: vendor minimax official pptx skills with pinned commit"
```

### Task 2: 建立官方 skill 兼容适配层（输入/输出契约）

**Files:**
- Create: `scripts/minimax/official_skill_adapter.mjs`
- Create: `scripts/minimax/official_skill_contract.mjs`
- Modify: `scripts/generate-pptx-minimax.mjs`
- Test: `scripts/tests/official-skill-adapter.harness.test.mjs`

**Step 1: Write the failing test**
```javascript
import { toOfficialInput, fromOfficialOutput } from "../minimax/official_skill_adapter.mjs";
const inData = { slides: [{ title: "灵创智能", elements: [] }], title: "灵创智能" };
const official = toOfficialInput(inData);
if (!official?.slides?.length) throw new Error("toOfficialInput failed");
const outData = fromOfficialOutput({ slides: [{ slide_id: "s1", title: "灵创智能" }] });
if (!outData?.slides?.length) throw new Error("fromOfficialOutput failed");
```

**Step 2: Run test to verify it fails**
Run: `node scripts/tests/official-skill-adapter.harness.test.mjs`
Expected: FAIL

**Step 3: Write minimal implementation**
- 输入适配到官方结构：
  - 5 page types（cover/toc/section-divider/content/summary）
  - `theme` 键固定为 `primary/secondary/accent/light/bg`
  - 色值统一 6-char hex（无 `#`）
- 输出适配回当前服务层：
  - 保留 `deck_id/slide_id/block_id/retry_scope`
  - 保留 `generator_meta` 和错误上下文

**Step 4: Run test to verify it passes**
Run: `node scripts/tests/official-skill-adapter.harness.test.mjs`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/minimax/official_skill_adapter.mjs scripts/minimax/official_skill_contract.mjs scripts/generate-pptx-minimax.mjs scripts/tests/official-skill-adapter.harness.test.mjs
git commit -m "feat: add official minimax skill input output adapter"
```

### Task 3: 将生成模式切到官方编排优先，并保留回滚

**Files:**
- Create: `scripts/minimax/official_orchestrator.mjs`
- Modify: `scripts/generate-pptx-minimax.mjs`
- Modify: `agent/src/minimax_exporter.py`
- Test: `agent/tests/test_exporter_official_mode.py`

**Step 1: Write the failing test**
```python
def test_exporter_default_mode_is_official():
    from src.minimax_exporter import build_payload
    payload = build_payload(slides=[], title="t", author="a")
    assert payload.get("generator_mode") == "official"
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_exporter_official_mode.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 新增 `generator_mode=official|legacy`。
- 默认 `official`，保留 `legacy` 回滚开关。
- 官方模式失败时仅在明确配置下回退 `legacy`（默认不回退）。

**Step 4: Run test to verify it passes**
Run: `cd agent; pytest tests/test_exporter_official_mode.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/minimax/official_orchestrator.mjs scripts/generate-pptx-minimax.mjs agent/src/minimax_exporter.py agent/tests/test_exporter_official_mode.py
git commit -m "feat: switch ppt generation to official orchestrator mode"
```

### Task 4: 取消本地风格压平，强制内容保真

**Files:**
- Modify: `scripts/generate-pptx-minimax.mjs`
- Modify: `agent/src/minimax_exporter.py`
- Modify: `agent/src/schemas/ppt.py`
- Test: `agent/tests/test_template_preservation.py`
- Test: `scripts/tests/minimax-style-heuristics.harness.test.mjs`

**Step 1: Write the failing test**
```python
def test_original_style_disables_local_rewrite():
    from src.minimax_exporter import build_payload
    payload = build_payload(slides=[{"title": "灵创智能"}], title="灵创智能", author="a", original_style=True)
    assert payload["disable_local_style_rewrite"] is True
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_template_preservation.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- `original_style=true` 时禁止：
  - 本地强制 TOC/Summary 注入
  - 本地风格重配覆盖
  - 文案重写或摘要替换
- `strict_structure` 已废弃（2026-03-27），改为自动结构编排 + 版式多样性 gate。

**Step 4: Run test to verify it passes**
Run:
```bash
cd agent; pytest tests/test_template_preservation.py -v
cd ..; npm run test:regex-harness
```
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/generate-pptx-minimax.mjs agent/src/minimax_exporter.py agent/src/schemas/ppt.py agent/tests/test_template_preservation.py scripts/tests/minimax-style-heuristics.harness.test.mjs
git commit -m "feat: preserve official style and content fidelity"
```

### Task 5: 定向重试只处理 transient 问题

**Files:**
- Modify: `agent/src/ppt_failure_classifier.py`
- Modify: `agent/src/ppt_retry_orchestrator.py`
- Modify: `agent/src/ppt_service.py`
- Test: `agent/tests/test_ppt_retry_orchestrator.py`
- Test: `agent/tests/test_ppt_export_retry_flow.py`

**Step 1: Write the failing test**
```python
def test_non_transient_error_fails_fast():
    from src.ppt_retry_orchestrator import should_retry
    assert should_retry("auth_invalid", 1, 3) is False
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_retry_orchestrator.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 仅对 `timeout/rate_limit/upstream_5xx/schema_invalid/encoding_invalid` 重试。
- 优先 `slide` 级重试，必要时下沉 `block`。
- 按稳定 ID 合并 patch，禁止整份重跑。

**Step 4: Run test to verify it passes**
Run:
```bash
cd agent; pytest tests/test_ppt_retry_orchestrator.py tests/test_ppt_export_retry_flow.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/ppt_failure_classifier.py agent/src/ppt_retry_orchestrator.py agent/src/ppt_service.py agent/tests/test_ppt_retry_orchestrator.py agent/tests/test_ppt_export_retry_flow.py
git commit -m "feat: keep scoped retry for transient ppt failures only"
```

### Task 6: 质量门禁前置，拦截“空白/乱码/占位符污染”

**Files:**
- Modify: `agent/src/ppt_quality_gate.py`
- Modify: `agent/src/ppt_service.py`
- Create: `scripts/tests/ppt_quality_gate_markitdown.harness.sh`
- Test: `agent/tests/test_ppt_quality_gate.py`

**Step 1: Write the failing test**
```python
def test_detect_blank_garbled_placeholder():
    from src.ppt_quality_gate import validate_slide
    result = validate_slide({"title": "???", "elements": [{"type": "text", "content": "lorem ipsum"}]})
    assert result.ok is False
```

**Step 2: Run test to verify it fails**
Run: `cd agent; pytest tests/test_ppt_quality_gate.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**
- 增强门禁规则：
  - 乱码比率检测
  - 空白页检测
  - 占位符污染检测（`xxxx|todo|tbd|lorem ipsum|placeholder`）
- 将失败原因写入 retry hint，指导局部重试。

**Step 4: Run test to verify it passes**
Run:
```bash
cd agent; pytest tests/test_ppt_quality_gate.py -v
bash ../scripts/tests/ppt_quality_gate_markitdown.harness.sh
```
Expected: PASS

**Step 5: Commit**
```bash
git add agent/src/ppt_quality_gate.py agent/src/ppt_service.py scripts/tests/ppt_quality_gate_markitdown.harness.sh agent/tests/test_ppt_quality_gate.py
git commit -m "feat: add strict ppt quality gate before final export"
```

### Task 7: 专项验收“灵创智能”内容与风格

**Files:**
- Create: `scripts/e2e_lingchuang_ppt_quality.py`
- Modify: `scripts/e2e_lingchuang_ppt.py`
- Create: `test_reports/ppt/lingchuang_quality_baseline.json`

**Step 1: Write the failing test harness**
```bash
python scripts/e2e_lingchuang_ppt_quality.py --require-keywords "灵创智能,AI营销,数字人" --min-slides 8
```

**Step 2: Run harness to verify it fails**
Run: `python scripts/e2e_lingchuang_ppt_quality.py --require-keywords "灵创智能,AI营销,数字人" --min-slides 8`
Expected: FAIL on current bad sample

**Step 3: Write minimal implementation**
- 校验输出 PPT：
  - 至少命中关键业务词
  - 不含占位符/乱码
  - 页面数、标题层级、目录页存在
- 输出质量报告 JSON，作为回归基线。

**Step 4: Run harness to verify it passes**
Run:
```bash
python scripts/e2e_lingchuang_ppt.py
python scripts/e2e_lingchuang_ppt_quality.py --require-keywords "灵创智能,AI营销,数字人" --min-slides 8
```
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/e2e_lingchuang_ppt_quality.py scripts/e2e_lingchuang_ppt.py test_reports/ppt/lingchuang_quality_baseline.json
git commit -m "test: add lingchuang ppt quality e2e baseline"
```

### Task 8: 灰度发布与回滚（仅 PPT）

**Files:**
- Modify: `agent/.env.example`
- Modify: `agent/src/configs/settings.py`
- Create: `docs/runbooks/ppt-official-rollout.md`

**Step 1: Write rollout checks**
- 目标指标：
  - `ppt_export_success_rate`
  - `ppt_quality_gate_pass_rate`
  - `ppt_retry_attempts_avg`
  - `ppt_placeholder_pollution_rate`

**Step 2: Dry run**
Run: staging 下 official/legacy A-B 对照 30 份样本
Expected: official 至少不低于 legacy

**Step 3: Write minimal implementation**
- 新增开关：
  - `PPT_GENERATOR_MODE=official|legacy`
  - `PPT_OFFICIAL_ROLLOUT_PERCENT=0..100`
  - `PPT_ENABLE_LEGACY_FALLBACK=true|false`

**Step 4: Verify rollback**
Run: 强制切回 `legacy` 并生成 1 份完整 PPT
Expected: 5 分钟内恢复

**Step 5: Commit**
```bash
git add agent/.env.example agent/src/configs/settings.py docs/runbooks/ppt-official-rollout.md
git commit -m "chore: add ppt-only rollout and rollback controls"
```

---

## Definition of Done (PPT Phase)

1. `official` 模式生成的 PPT 不再出现“内容不相关/空白/占位符污染”。
2. “灵创智能”样本可稳定命中核心关键词与业务结构。
3. 重试仅发生在 transient 错误，且以 `slide/block` 局部修复为主。
4. 质量门禁可拦截乱码、空白页、模板污染。
5. 具备灰度发布与快速回滚能力。

## Phase 2 (Deferred)

视频链路（Remotion、`render_spec` 动效策略、PPT-Video 一致性评分）暂不纳入本阶段，待 PPT 质量稳定后再单独立项。

## 关键外部依据

1. MiniMax 官方 `pptx-plugin`  
   https://github.com/MiniMax-AI/skills/tree/main/plugins/pptx-plugin
2. MiniMax 官方 `pptx-generator`  
   https://github.com/MiniMax-AI/skills/tree/main/skills/pptx-generator
3. PptxGenJS 官方文档（OOXML 兼容与 API 约束）  
   https://gitbrent.github.io/PptxGenJS/docs/introduction/
4. AWS Builders Library（transient 重试 + backoff + jitter）  
   https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
