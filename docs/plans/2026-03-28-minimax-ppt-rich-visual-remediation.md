# MiniMax PPT Rich Visual Remediation Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** Make generated PPT content pages consistently visual-first (image/chart/kpi-driven), not text-dense, while preserving official-mode compatibility and retry semantics.

**Architecture:** Keep the existing Python->Node pipeline, but fix semantic drift at boundaries: preserve semantic page subtype, normalize a single canonical content model (`blocks` as source of truth), and map it losslessly for official adapter compatibility. Rebalance template routing away from architecture-only defaults, then add quality gates and regression tests to prevent text-only regressions.

**Tech Stack:** Python (FastAPI, pytest), Node.js (SVG-to-PPTX, node --test harness), existing MiniMax renderer modules in `scripts/minimax/*`.

**Related skills:** @writing-plans @pptx

---

### Task 1: Lock In Failing Tests for Current Regressions

**Files:**
- Modify: `scripts/tests/official-skill-adapter.harness.test.mjs`
- Modify: `scripts/tests/render-contract.harness.test.mjs`
- Create: `scripts/tests/generate-pptx-minimax.harness.test.mjs`

**Step 1: Add failing adapter test for blocks->official blocks mapping**

```javascript
test("toOfficialInput maps blocks when elements are missing", () => {
  const input = {
    slides: [
      {
        slide_id: "s1",
        slide_type: "content",
        blocks: [{ block_type: "chart", card_id: "c1", content: "Trend", data: { labels: ["A"], datasets: [{ data: [1] }] } }],
      },
    ],
  };
  const out = toOfficialInput(input);
  assert.equal(out.slides[0].blocks.length > 0, true);
});
```

**Step 2: Add failing renderer test for blocks-only slides preserving data subtype**

```javascript
test("build subtype from blocks chart when elements absent", () => {
  const slide = { title: "Growth", blocks: [{ block_type: "chart", content: "trend", data: { labels: ["2024"], datasets: [{ data: [10] }] } }] };
  assert.equal(inferSubtype(slide), "data");
});
```

**Step 3: Add failing render-output test for non-empty visual metadata in official mode**

```javascript
test("official render output should not emit empty block lists for content slides", async () => {
  // run generator fixture and assert official_input content slide blocks length > 0
});
```

**Step 4: Run JS harness tests to confirm failures**

Run: `node --test scripts/tests/official-skill-adapter.harness.test.mjs scripts/tests/render-contract.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs`  
Expected: FAIL in new cases, PASS in existing unrelated tests.

**Step 5: Commit**

```bash
git add scripts/tests/official-skill-adapter.harness.test.mjs scripts/tests/render-contract.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs
git commit -m "test: capture ppt semantic drift and official adapter regressions"
```

---

### Task 2: Fix Canonical Semantic Model Across Python->Node Boundary

**Files:**
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/tests/test_ppt_contract.py`
- Modify: `agent/tests/test_ppt_pipeline.py`

**Step 1: Write failing Python test that middle slides keep semantic subtype**

```python
def test_render_payload_middle_slide_uses_semantic_slide_type():
    # arrange plan with layout_grid split_2 and semantic "data"
    # assert payload slide_type == "data" and layout_grid == "split_2"
```

**Step 2: Run focused Python test**

Run: `cd agent && uv run pytest tests/test_ppt_contract.py::test_render_payload_middle_slide_uses_semantic_slide_type -v`  
Expected: FAIL with current `slide_type` mapped to layout names.

**Step 3: Update `_presentation_plan_to_render_payload` to preserve semantic `slide_type`**

```python
normalized_slide_type = raw_slide_type if raw_slide_type else "content"
# keep layout_grid separate for layout diversity
```

**Step 4: Update plan-generation path to emit semantic slide types (`data/comparison/timeline/content`)**

```python
SlidePlan(
    slide_type=semantic_type,
    layout_grid=note.layout_hint,
    ...
)
```

**Step 5: Re-run focused Python tests**

Run: `cd agent && uv run pytest tests/test_ppt_contract.py tests/test_ppt_pipeline.py -k "slide_type or layout_grid" -v`  
Expected: PASS.

**Step 6: Commit**

```bash
git add agent/src/ppt_service.py agent/tests/test_ppt_contract.py agent/tests/test_ppt_pipeline.py
git commit -m "fix: preserve semantic slide type and separate layout grid"
```

---

### Task 3: Make `blocks` the Source of Truth in JS Heuristics and Rendering

**Files:**
- Modify: `scripts/generate-pptx-minimax.mjs`
- Modify: `scripts/minimax-style-heuristics.mjs`
- Modify: `scripts/minimax/official_skill_adapter.mjs`

**Step 1: Add helper to derive virtual elements from blocks**

```javascript
function blocksToElements(slide) {
  const blocks = Array.isArray(slide?.blocks) ? slide.blocks : [];
  return blocks.map((b) => ({ type: b.block_type || "text", content: typeof b.content === "string" ? b.content : "", chart_data: b?.data }));
}
```

**Step 2: Refactor `collectBullets`, `extractChartSeries`, subtype inference to read blocks first**

```javascript
const blockLines = collectBlockText(slide.blocks);
const elements = Array.isArray(slide.elements) ? slide.elements : blocksToElements(slide);
```

**Step 3: Update `toOfficialInput` to map blocks (not only text elements)**

```javascript
const sourceBlocks = Array.isArray(slide?.blocks) ? slide.blocks : extractTextBlocks(slide, slideId);
```

**Step 4: Update `fromOfficialOutput` to preserve structured fields when available**

```javascript
type: normalizeKey(block?.type || "text"),
content: block?.content ?? "",
data: block?.data ?? null
```

**Step 5: Run JS harness tests**

Run: `npm run test:official-skill-adapter && node --test scripts/tests/render-contract.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs`  
Expected: PASS.

**Step 6: Commit**

```bash
git add scripts/generate-pptx-minimax.mjs scripts/minimax-style-heuristics.mjs scripts/minimax/official_skill_adapter.mjs
git commit -m "fix: use blocks as canonical source for subtype, bullets, and official adapter"
```

---

### Task 4: Rebalance Template Routing to Avoid Architecture Overuse

**Files:**
- Modify: `scripts/minimax/templates/template-catalog.json`
- Modify: `scripts/minimax/templates/template-registry.mjs`
- Modify: `scripts/tests/template-renderers.harness.test.mjs`

**Step 1: Add failing test ensuring orchestration topic does not force all slides to architecture template**

```javascript
test("template routing should distribute families across mixed content deck", () => {
  // assert not all content slides resolve to architecture_dark_panel
});
```

**Step 2: Update routing strategy from first-hit keyword to scored selection**

```javascript
// score by keyword hit + semantic subtype + layout suitability
// require minimum score threshold for architecture_dark_panel
```

**Step 3: Adjust `template-catalog` defaults and keyword rules**

```json
{
  "layout_defaults": {
    "split_2": "split_media_dark",
    "asymmetric_2": "split_media_dark"
  }
}
```

**Step 4: Run template harness tests**

Run: `node --test scripts/tests/template-renderers.harness.test.mjs scripts/tests/minimax-style-heuristics.harness.test.mjs`  
Expected: PASS with diversified template selection.

**Step 5: Commit**

```bash
git add scripts/minimax/templates/template-catalog.json scripts/minimax/templates/template-registry.mjs scripts/tests/template-renderers.harness.test.mjs
git commit -m "fix: diversify template routing and reduce architecture over-selection"
```

---

### Task 5: Reduce Text Density and Stabilize Card Placement

**Files:**
- Modify: `agent/src/ppt_service.py`
- Modify: `scripts/minimax/templates/template-renderers.mjs`
- Modify: `scripts/minimax/bento-grid.mjs`
- Modify: `scripts/tests/card-renderers.harness.test.mjs`

**Step 1: Add failing test for max text budget per content slide**

```python
def test_content_slide_text_budget_enforced():
    # assert body/list max chars and bullet count caps
```

**Step 2: Add concise summarization/truncation before `"; ".join(...)`**

```python
def _compact_points(points: list[str], max_points: int = 3, max_chars: int = 72) -> list[str]:
    ...
```

**Step 3: Standardize card IDs by layout semantic slots (`left/right/c1/c2/...`)**

```python
# assign card_id from layout slot map instead of card-1/card-2
```

**Step 4: Harden text splitting logic and remove mojibake delimiters**

```javascript
.split(/[;；。！？!?，,\n]+/)
```

**Step 5: Make `getCardById` strict in debug mode (warn when fallback by index)**

```javascript
if (!byId) console.warn(...)
```

**Step 6: Run mixed Python+JS tests**

Run: `cd agent && uv run pytest tests/test_ppt_pipeline.py -k "text_budget or card_id" -v`  
Run: `node --test scripts/tests/card-renderers.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs`  
Expected: PASS.

**Step 7: Commit**

```bash
git add agent/src/ppt_service.py scripts/minimax/templates/template-renderers.mjs scripts/minimax/bento-grid.mjs scripts/tests/card-renderers.harness.test.mjs
git commit -m "fix: enforce text budget and canonical card-slot mapping"
```

---

### Task 6: Add End-to-End Quality Gates and Rollout Verification

**Files:**
- Modify: `agent/tests/test_exporter_official_mode.py`
- Modify: `agent/tests/test_ppt_e2e.py`
- Modify: `docs/runbooks/` (new runbook section)

**Step 1: Add E2E assertion for visual-anchor coverage**

```python
assert visual_anchor_ratio >= 0.8
assert text_only_content_slides == 0
```

**Step 2: Add assertion that `official_input` content slides have non-empty blocks**

```python
assert all(len(s["blocks"]) > 0 for s in official_input_slides if s["page_type"] == "content")
```

**Step 3: Add assertion for template diversity threshold**

```python
assert len(set(content_templates)) >= 2
```

**Step 4: Run full target test suite**

Run: `cd agent && uv run pytest tests/test_exporter_official_mode.py tests/test_ppt_e2e.py tests/test_ppt_quality_gate.py -v`  
Run: `npm run test:official-skill-adapter && node --test scripts/tests/*.harness.test.mjs`  
Expected: PASS.

**Step 5: Document rollout checklist**

```markdown
- Verify stage-4 has chart/image/kpi blocks
- Verify stage-5 official_input blocks are non-empty
- Verify generated ppt has chart/image-focused content pages
```

**Step 6: Commit**

```bash
git add agent/tests/test_exporter_official_mode.py agent/tests/test_ppt_e2e.py docs/runbooks
git commit -m "test: add e2e quality gates for visual-first ppt outputs"
```

---

### Task 7: Final Verification With Real Fixture Decks

**Files:**
- Use fixture: `agent/renders/tmp/ppt_pipeline/d1ef781b8ac5/stage-4-render-payload.json`
- Use fixture: `agent/renders/tmp/ppt_pipeline/a6cfe06be5bf/stage-4-render-payload.json`

**Step 1: Generate PPT for both fixtures**

Run:  
`node scripts/generate-pptx-minimax.mjs --input agent/renders/tmp/ppt_pipeline/d1ef781b8ac5/stage-4-render-payload.json --output test_outputs/d1ef-fixed.pptx --render-output test_outputs/d1ef-fixed.render.json`  
`node scripts/generate-pptx-minimax.mjs --input agent/renders/tmp/ppt_pipeline/a6cfe06be5bf/stage-4-render-payload.json --output test_outputs/a6cf-fixed.pptx --render-output test_outputs/a6cf-fixed.render.json`  
Expected: `success=true` both runs.

**Step 2: Validate render JSON metrics**

Run: `node scripts/tests/validate-render-metrics.mjs test_outputs/d1ef-fixed.render.json test_outputs/a6cf-fixed.render.json`  
Expected:
- content slides with visual blocks >= 80%
- `official_input.content.blocks` non-empty
- template family diversity >= 2

**Step 3: Spot-check extracted text quality**

Run: `python -m markitdown test_outputs/d1ef-fixed.pptx > test_outputs/d1ef-fixed.md`  
Expected: no oversized repeated bullet chains and no mojibake tokens.

**Step 4: Commit final integration batch**

```bash
git add .
git commit -m "feat: restore rich visual ppt generation in official-mode pipeline"
```

