# PPT Master Phased Refactor Implementation Plan

> Use this plan to execute the work task-by-task with tight verification after each step.

**Goal:** 鍦ㄧ幇鏈?MiniMax PPT 鐢熸垚閾捐矾涓紩鍏?ppt-master 椋庢牸鐨?`design_spec + 鍙岃建娓叉煋 + 鍒嗙骇闄嶇骇`锛屽苟淇濊瘉姣忛樁娈靛彲娴嬭瘯銆佸彲鍥炲綊銆?
**Architecture:** 淇濇寔 Python 缂栨帓 + Node 娓叉煋涓诲共涓嶅彉锛屽湪 Python 渚ф柊澧?`design_spec` 涓?`render_path` 鍐崇瓥锛屽湪 Node 渚ф柊澧?`SVG -> PptxGenJS(Custom Geometry)` 娓叉煋鍣紝骞跺湪閲嶈瘯缂栨帓灞傝ˉ榻愯法璺緞闄嶇骇銆傛瘡涓樁娈甸兘浠ユ祴璇曞厛琛岋紝鍏堣ˉ澶辫触娴嬭瘯锛屽啀瀹炵幇鏈€灏忔敼鍔ㄤ娇鍏堕€氳繃銆?
**Tech Stack:** Python(FastAPI/pytest), Node.js(PptxGenJS/node:test), template-catalog contract

---

### Task 1: Phase 1 - Unified `design_spec` + `render_path` Contract

**Files:**
- Create: `agent/src/ppt_master_design_spec.py`
- Modify: `agent/src/ppt_service.py`
- Modify: `agent/src/minimax_exporter.py`
- Modify: `scripts/minimax/render-contract.mjs`
- Test: `agent/tests/test_exporter_official_mode.py`
- Test: `agent/tests/test_ppt_contract.py`

**Step 1: Write the failing tests**

```python
def test_build_payload_contains_design_spec_contract():
    payload = build_payload(...)
    assert "design_spec" in payload
    assert payload["design_spec"]["visual"]["style_recipe"] in {"sharp", "soft", "rounded", "pill"}

def test_visual_orchestration_assigns_render_path_by_slide_semantics():
    out = _apply_visual_orchestration(payload)
    assert out["slides"][0]["render_path"] == "pptxgenjs"
    assert any(s["render_path"] == "svg" for s in out["slides"] if s["slide_type"] == "content")
```

**Step 2: Run tests to verify failure**

Run: `cd agent && uv run pytest tests/test_exporter_official_mode.py tests/test_ppt_contract.py -k "design_spec or render_path" -q`
Expected: FAIL with missing `design_spec` / `render_path`.

**Step 3: Write minimal implementation**

- 鏂板 `build_design_spec(...)` 涓?`choose_render_path(...)`锛屽皢鑹插僵/瀛椾綋/闂磋窛/瑙嗚閰嶇疆缁撴瀯鍖栥€?- `_apply_visual_orchestration()` 鍐欏叆 deck 绾?`design_spec`锛屽苟缁欐瘡椤垫墦 `render_path`銆?- `build_payload()` 閫忎紶 `design_spec` 涓庢瘡椤?`render_path`銆?- `normalizeRenderInput()` 淇濈暀骞惰鑼冨寲 `design_spec` 涓?`render_path`銆?
**Step 4: Run tests to verify pass**

Run: `cd agent && uv run pytest tests/test_exporter_official_mode.py tests/test_ppt_contract.py -k "design_spec or render_path" -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add agent/src/ppt_master_design_spec.py agent/src/ppt_service.py agent/src/minimax_exporter.py scripts/minimax/render-contract.mjs agent/tests/test_exporter_official_mode.py agent/tests/test_ppt_contract.py
git commit -m "feat(ppt): add design_spec and render_path contract for ppt-master style routing"
```

---

### Task 2: Phase 2 - SVG to PptxGenJS Custom Geometry Renderer

**Files:**
- Create: `scripts/minimax/svg-slide-renderer.mjs`
- Modify: `scripts/generate-pptx-minimax.mjs`
- Test: `scripts/tests/svg-slide-renderer.harness.test.mjs`
- Test: `scripts/tests/generate-pptx-minimax.harness.test.mjs`

**Step 1: Write the failing tests**

```javascript
test("svg renderer maps path to CUSTOM_GEOMETRY points", () => {
  const metrics = renderSvgSlideToPptx(...);
  assert.equal(metrics.customGeometryCount > 0, true);
});

test("generator uses svg renderer when render_path=svg", () => {
  // run generator fixture
  // assert render_output includes slide.render_path=svg and svg_render_mode='custgeom'
});
```

**Step 2: Run tests to verify failure**

Run: `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs`
Expected: FAIL with missing module or assertions.

**Step 3: Write minimal implementation**

- 瀹炵幇 SVG 瀛愰泦瑙ｆ瀽锛歚rect/circle/ellipse/line/text/path`銆?- `path` 杞崲涓?`pptx.shapes.CUSTOM_GEOMETRY + points`锛堟渶灏忔敮鎸?`M/L/C/Q/Z`锛夈€?- 鐢熸垚鍣ㄥ湪 `render_path=svg` 鏃朵紭鍏堣皟鐢ㄦ柊娓叉煋鍣紱澶辫触鏃堕€€鍥炴棫鐨?SVG image overlay銆?- 灏嗘瘡椤垫覆鏌撳厓鏁版嵁鍐欏叆 `render_output`锛堜緥濡?`svg_render_mode`锛夈€?
**Step 4: Run tests to verify pass**

Run: `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/minimax/svg-slide-renderer.mjs scripts/generate-pptx-minimax.mjs scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs
git commit -m "feat(ppt): add svg to custom-geometry renderer and wire dual-track execution"
```

---

### Task 3: Phase 3 - Retry Downgrade Loop (pptxgenjs -> svg -> png)

**Files:**
- Modify: `agent/src/ppt_retry_orchestrator.py`
- Modify: `agent/src/ppt_service.py`
- Test: `agent/tests/test_ppt_retry_orchestrator.py`
- Test: `agent/tests/test_ppt_export_retry_flow.py`

**Step 1: Write the failing tests**

```python
def test_retry_orchestrator_degrades_render_path_after_render_failures():
    # attempt 1/2 fail -> slide render_path switches to svg
    # svg fail after threshold -> mark png fallback
```

**Step 2: Run tests to verify failure**

Run: `cd agent && uv run pytest tests/test_ppt_retry_orchestrator.py tests/test_ppt_export_retry_flow.py -k "degrade or render_path" -q`
Expected: FAIL due to missing downgrade behavior.

**Step 3: Write minimal implementation**

- 鍦?orchestrator 涓柊澧?`compute_render_path_downgrade(...)`銆?- 鍦?`ppt_service` 閲嶈瘯鍒嗘敮閲屾牴鎹け璐ョ爜鏇存柊鐩爣 slide 鐨?`render_path` / `svg_fallback_png`銆?- 璁板綍璇婃柇瀛楁锛屼究浜庡悗缁娴嬨€?
**Step 4: Run tests to verify pass**

Run: `cd agent && uv run pytest tests/test_ppt_retry_orchestrator.py tests/test_ppt_export_retry_flow.py -k "degrade or render_path" -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add agent/src/ppt_retry_orchestrator.py agent/src/ppt_service.py agent/tests/test_ppt_retry_orchestrator.py agent/tests/test_ppt_export_retry_flow.py
git commit -m "feat(ppt): add staged render-path downgrade for retry loop"
```

---

### Task 4: Phase 4 - End-to-End Validation & Acceptance Snapshot

**Files:**
- Modify: `docs/plans/2026-03-29-ppt-master-phased-refactor.md`
- Optional: `docs/runbooks/*`锛堜粎褰撳彂鐜板繀瑕佽繍缁磋鏄庣己鍙ｏ級

**Step 1: Run full targeted suites**

Run:
- `cd agent && uv run pytest tests/test_exporter_official_mode.py tests/test_ppt_contract.py tests/test_ppt_planning.py tests/test_ppt_retry_orchestrator.py tests/test_ppt_export_retry_flow.py -q`
- `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs`

Expected: PASS with no regression in modified areas.

**Step 2: Smoke export**

Run: `node scripts/generate-pptx-minimax.mjs --input <fixture.json> --output <tmp.pptx> --render-output <tmp.render.json>`
Expected: 鎴愬姛浜у嚭 `pptx` 涓?`render_output` 甯?`design_spec/render_path/svg_render_mode`銆?
**Step 3: Capture acceptance notes**

- 璁板綍姣忛樁娈垫祴璇曠粨鏋溿€佸け璐ヤ慨澶嶇偣銆佸凡鐭ラ檺鍒讹紙渚嬪 SVG path 楂樼骇鍛戒护瑕嗙洊鑼冨洿锛夈€?
**Step 4: Commit**

```bash
git add docs/plans/2026-03-29-ppt-master-phased-refactor.md
git commit -m "docs(ppt): record phased implementation and verification results"
```

---

### Task 5: Phase 5 - SVG Advanced Path (`A/S/T`) Geometry Support

**Files:**
- Modify: `scripts/minimax/svg-slide-renderer.mjs`
- Test: `scripts/tests/svg-slide-renderer.harness.test.mjs`

**Step 1: Write the failing tests**

```javascript
test("svg arc path command A is approximated into cubic geometry points", () => {
  const points = svgPathToCustomGeometryPoints("M 100 100 A 50 50 0 0 1 200 100 Z", ...);
  assert.equal(points.some((p) => p?.curve?.type === "cubic"), true);
});

test("svg smooth cubic command S is converted into cubic geometry points", () => {
  const points = svgPathToCustomGeometryPoints("M ... C ... S ... Z", ...);
  assert.equal(points.filter((p) => p?.curve?.type === "cubic").length >= 2, true);
});

test("svg smooth quadratic command T is converted into quadratic geometry points", () => {
  const points = svgPathToCustomGeometryPoints("M ... Q ... T ... Z", ...);
  assert.equal(points.filter((p) => p?.curve?.type === "quadratic").length >= 2, true);
});
```

**Step 2: Run tests to verify failure**

Run: `node --test scripts/tests/svg-slide-renderer.harness.test.mjs`
Expected: FAIL because `A/S/T` were not mapped to curve geometry.

**Step 3: Write minimal implementation**

- 鎵╁睍 path tokenizer 鏀寔 `A/S/T`锛堝苟琛ラ綈 `H/V`锛夈€?- 瀹炵幇 SVG Arc endpoint-parameterization 鍒?cubic Bezier 娈佃繎浼艰浆鎹€?- 瀹炵幇骞虫粦鏇茬嚎 `S/T` 鐨勬帶鍒剁偣鍙嶅皠閫昏緫骞跺啓鍏?`points`銆?
**Step 4: Run tests to verify pass**

Run:
- `node --test scripts/tests/svg-slide-renderer.harness.test.mjs`
- `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs`

Expected: PASS.

---

### Execution Log (2026-03-29)

- `Phase 1` status: completed
- `Phase 1` verification:
  - `cd agent && uv run pytest tests/test_exporter_official_mode.py tests/test_ppt_contract.py -k "design_spec or render_path" -q`
  - result: `2 passed`

- `Phase 2` status: completed
- `Phase 2` verification:
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs`
  - result: `3 passed`
  - regression check: `node --test scripts/tests/generate-pptx-minimax.harness.test.mjs` -> `1 passed`

- `Phase 3` status: completed
- `Phase 3` implementation:
  - 鏂板 `compute_render_path_downgrade(...)`锛屾寜 `pptxgenjs -> svg -> png_fallback` 鍒嗙骇闄嶇骇
  - 鍦?`ppt_service` 閲嶈瘯鍒嗘敮鎸夊け璐ョ爜瀵圭洰鏍?slide 鏇存柊 `render_path/svg_fallback_png`
  - 灏嗛檷绾ц涓哄啓鍏?`diagnostics`锛坄render_path_downgrade`锛?- `Phase 3` verification:
  - `cd agent && uv run pytest tests/test_ppt_retry_orchestrator.py tests/test_ppt_export_retry_flow.py -k "degrade or render_path" -q`
  - result: `4 passed`

- `Phase 4` status: completed
- `Phase 4` verification:
  - `cd agent && uv run pytest tests/test_exporter_official_mode.py tests/test_ppt_contract.py tests/test_ppt_planning.py tests/test_ppt_retry_orchestrator.py tests/test_ppt_export_retry_flow.py -q`
  - result: `56 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs`
  - result: `4 passed`
  - smoke:
    - `node scripts/generate-pptx-minimax.mjs --input <tmp.json> --output <tmp.pptx> --render-output <tmp.render.json>`
    - output check: `output_exists=true`, `render_path=svg`, `svg_render_mode=custgeom`, `has_design_spec=true`

- `Phase 5` status: completed
- `Phase 5` implementation:
  - `svg-slide-renderer` 鏂板 `A/a` 寮х嚎鍛戒护鍒?cubic Bezier 杩戜技杞崲
  - 鏂板 `S/s` 涓?`T/t` 骞虫粦鏇茬嚎鎺у埗鐐瑰弽灏勯€昏緫
  - tokenizer 鎵╁睍鑷?`M/L/H/V/C/S/Q/T/A/Z` 瀛愰泦
- `Phase 5` verification:
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs` -> `5 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs` -> `7 passed`

- known limitations:
  - 褰撳墠 `svg path` 宸叉敮鎸?`M/L/H/V/C/S/Q/T/A/Z`锛屼絾浠嶆槸宸ョ▼杩戜技瀹炵幇锛涙瀬绔姬绾垮弬鏁板満鏅渶缁х画鍋氳瑙夊洖褰掓娊妫€銆?
- `Phase 6` status: completed
- `Phase 6` scope: local template renderer extension for bento-family templates and render metadata disambiguation
- `Phase 6` implementation:
  - Added local renderer coverage for `bento_2x2_dark` and `bento_mosaic_dark` in `scripts/minimax/templates/template-renderers.mjs`.
  - Added `renderBentoTemplate(...)` adapter to route bento-family templates into `renderBentoSlide(...)` with normalized layout and fallback card-slot assignment.
  - Added locked-template render metadata safeguard in `scripts/generate-pptx-minimax.mjs` so template-rendered slides are not misclassified as generic `grid_4` bento fallback in render output.
  - Extended harnesses in `scripts/tests/template-renderers.harness.test.mjs` and `scripts/tests/template-render-priority.harness.test.mjs`.
- `Phase 6` verification:
  - `node --test scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `2 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `9 passed`
- `Phase 7` status: completed
- `Phase 7` scope: catalog-driven preferred layout resolution for template rendering and render metadata
- `Phase 7` implementation:
  - Added `getTemplateSupportedLayouts(...)` and `getTemplatePreferredLayout(...)` in `scripts/minimax/templates/template-catalog.mjs`.
  - Added skill-profile-aware layout preference rules to decouple template layout selection from hardcoded renderer mappings.
  - Updated bento template renderer normalization to use catalog preferred layout (`scripts/minimax/templates/template-renderers.mjs`).
  - Updated content render metadata mapping to use catalog preferred layout (`scripts/generate-pptx-minimax.mjs`).
  - Added catalog harness tests (`scripts/tests/template-catalog.harness.test.mjs`) and tightened template priority assertions.
- `Phase 7` verification:
  - `node --test scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `4 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `11 passed`
- `Phase 8` status: completed
- `Phase 8` scope: catalog-to-renderer coverage guardrail (prevent silent template fallback drift)
- `Phase 8` implementation:
  - Added renderer inventory exports: `listTemplateContentRenderers()` and `listTemplateCoverRenderers()` in `scripts/minimax/templates/template-renderers.mjs`.
  - Added coverage harness `scripts/tests/template-renderer-coverage.harness.test.mjs`.
  - Coverage rules include:
    - every local renderer id must exist in catalog templates;
    - every content-capable template must have local content renderer coverage;
    - cover-capable templates must have cover renderer or explicit generic allowance (`hero_dark`).
- `Phase 8` verification:
  - `node --test scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `7 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `14 passed`
- `Phase 9` status: completed
- `Phase 9` scope: template capability-constrained renderer fallback (`supported_block_types` + `requires_image_asset`)
- `Phase 9` implementation:
  - Added `assessTemplateCapabilityForSlide(...)` to `scripts/minimax/templates/template-registry.mjs`.
  - Capability assessment marks template/content mismatch when constrained block types are unsupported (e.g. `chart`, `table`, `workflow`, `diagram`, `icon_text`, `svg`) or when image-required templates lack usable image assets.
  - Integrated assessment into `scripts/generate-pptx-minimax.mjs` content rendering path:
    - if incompatible, skip local template renderer and fallback to generic content branch;
    - emit per-slide internal skip flags (`__template_renderer_skipped`, `__template_renderer_skip_reason`) to avoid template-layout misclassification in render metadata.
  - Added/extended tests:
    - `scripts/tests/template-registry.harness.test.mjs` (capability assessment unit tests)
    - `scripts/tests/template-render-priority.harness.test.mjs` (locked template with capability mismatch should fallback)
- `Phase 9` verification:
  - `node --test scripts/tests/template-registry.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `8 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `21 passed`
- `Phase 10` status: completed
- `Phase 10` scope: template capability guardrail expansion (`supported_slide_types` + `supported_layouts`)
- `Phase 10` implementation:
  - Extended `assessTemplateCapabilityForSlide(...)` in `scripts/minimax/templates/template-registry.mjs` to evaluate:
    - slide-type compatibility (`supported_slide_types`), with subtype alias normalization;
    - layout compatibility (`supported_layouts`).
  - Kept existing constrained block-type and image-asset checks and merged all checks into unified `compatible` decision.
  - Wired explicit slide-type/layout inputs from `addContentSlide(...)` in `scripts/generate-pptx-minimax.mjs`.
  - When incompatible, local template renderer is skipped and generic content branch is used (with existing skip markers to keep render metadata accurate).
  - Added tests:
    - `scripts/tests/template-registry.harness.test.mjs`: unsupported slide type/layout detection.
    - `scripts/tests/template-render-priority.harness.test.mjs`: locked template + unsupported layout must fallback.
- `Phase 10` verification:
  - `node --test scripts/tests/template-registry.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs` -> `10 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `23 passed`
- `Phase 11` status: completed
- `Phase 11` scope: render-output diagnostics for template capability fallback decisions
- `Phase 11` implementation:
  - Added per-slide `template_renderer` diagnostics into render identity output in `scripts/generate-pptx-minimax.mjs`.
  - Diagnostics include: `mode`, `skipped`, `reason`, `unsupported_block_types`, `unsupported_slide_type`, `unsupported_layout`, `missing_required_image_asset`.
  - Persisted capability assessment snapshot on source slides (`__template_capability`) and refined skip reason priority:
    - `missing_required_image_asset` > `unsupported_layout` > `unsupported_slide_type` > `unsupported_block_types`.
  - Extended `scripts/tests/template-render-priority.harness.test.mjs` to verify fallback diagnostics for block mismatch and layout mismatch cases.
- `Phase 11` verification:
  - `node --test scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `10 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `23 passed`
- `Phase 12` status: completed
- `Phase 12` scope: deck-level aggregation for template renderer fallback diagnostics
- `Phase 12` implementation:
  - Added `summarizeTemplateRendererDiagnostics(renderSlides)` in `scripts/generate-pptx-minimax.mjs`.
  - Added top-level `template_renderer_summary` into render output JSON and console metadata.
  - Summary fields include:
    - `evaluated_slides`, `skipped_slides`, `skipped_ratio`
    - `mode_counts` (`local_template` / `fallback_generic`)
    - `reason_counts` and `reason_ratios` for fallback reasons.
  - Extended `scripts/tests/template-render-priority.harness.test.mjs` to validate summary aggregation values.
- `Phase 12` verification:
  - `node --test scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `10 passed`
  - `node --test scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `23 passed`
- `Phase 13` status: completed
- `Phase 13` scope: Python observability integration for `template_renderer_summary` diagnostics and alerting
- `Phase 13` implementation:
  - Extended `agent/src/ppt_service.py::_build_export_alerts(...)` to accept template renderer deck summary and emit:
    - `template_renderer_fallback_ratio_high` (warn/high severity by skip ratio),
    - `template_renderer_fallback_reason_concentrated` (dominant fallback reason concentration).
  - Wired `render_spec.template_renderer_summary` into export success pipeline:
    - attached to `export_data["observability_report"]["template_renderer_summary"]`,
    - fed into alert builder,
    - appended to persisted observability `diagnostics` as `status=template_renderer_summary`.
  - Added regression test in `agent/tests/test_ppt_export_retry_flow.py`:
    - `test_template_renderer_summary_surfaces_in_observability_and_alerts`.
- `Phase 13` verification:
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "template_renderer_summary_surfaces_in_observability_and_alerts"` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py` -> `12 passed`
- `Phase 14` status: completed
- `Phase 14` scope: non-standard chart fallback path (`funnel/waterfall/sankey`) via SVG-to-custGeom conversion
- `Phase 14` implementation:
  - Added `scripts/minimax/svg-chart-converter.mjs`:
    - `isNonStandardChartType(...)`
    - `buildNonStandardChartSvg(...)`
    - `renderNonStandardChartInCard(...)` (delegates to `renderSvgSlideToPptx` for `path -> custGeom`).
  - Updated `scripts/minimax/card-renderers.mjs`:
    - `renderChartCard(...)` now routes non-standard chart types to SVG converter before standard `addChart`.
    - kept standard chart route unchanged for BAR/LINE/PIE/DOUGHNUT/AREA/RADAR/SCATTER/BAR3D.
  - Added tests: `scripts/tests/svg-chart-converter.harness.test.mjs`.
- `Phase 14` verification:
  - `node --test scripts/tests/svg-chart-converter.harness.test.mjs` -> `4 passed`
  - `node --test scripts/tests/svg-chart-converter.harness.test.mjs scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs` -> `10 passed`
  - `node scripts/tests/chart-factory.harness.test.mjs` -> `chart-factory harness passed`
- `Phase 15` status: completed
- `Phase 15` scope: textual QA layer (S12 Layer A) for placeholder/page-order/assertion-evidence coverage signals
- `Phase 15` implementation:
  - Added `audit_textual_slides(...)` in `agent/src/ppt_visual_qa.py`.
  - Text QA outputs include:
    - `placeholder_ratio`, `missing_title_count`, `missing_body_count`
    - `page_number_discontinuous`, `page_numbers`
    - `issue_codes`, per-slide issue rows, and `score`.
  - Wired text QA into export success path in `agent/src/ppt_service.py`:
    - `export_data["text_qa"]`
    - `export_data["observability_report"]["text_qa"]`
    - merged text QA `issue_codes` into observability issue set
    - persisted into diagnostics as `status=text_qa_summary`.
  - Extended alert builder with text QA signals:
    - `text_qa_placeholder_ratio_high`
    - `text_qa_missing_evidence_body_ratio_high`
    - `text_qa_page_number_discontinuous`.
  - Added tests:
    - `agent/tests/test_ppt_visual_qa.py::test_textual_qa_detects_placeholder_and_page_number_gap`
    - `agent/tests/test_ppt_export_retry_flow.py::test_text_qa_surfaces_in_observability_and_alerts`
- `Phase 15` verification:
  - `pytest -q agent/tests/test_ppt_visual_qa.py` -> `5 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "text_qa_surfaces_in_observability_and_alerts"` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py` -> `13 passed`
- `Phase 16` status: completed
- `Phase 16` scope: icon system upgrade for `icon_text` blocks (S3 react-icons path)
- `Phase 16` implementation:
  - Added `scripts/minimax/icon-factory.mjs`:
    - `resolveIconName(...)` with alias + keyword mapping
    - `renderIconSvgMarkup(...)`
    - `renderIconDataForPptx(...)` (`image/svg+xml;base64,...` payload for `addImage`).
  - Updated `scripts/minimax/card-renderers.mjs`:
    - `icon_text` renderer upgraded from plain text to icon+text layout.
    - when `addImage` unavailable, degrades gracefully to text-only output.
  - Added tests:
    - `scripts/tests/icon-factory.harness.test.mjs`
    - `scripts/tests/card-renderers-icon.harness.test.mjs`
  - Added dependency:
    - `react-icons` (via `npm install react-icons@^5.5.0`).
- `Phase 16` verification:
  - `node --test scripts/tests/icon-factory.harness.test.mjs scripts/tests/card-renderers-icon.harness.test.mjs` -> `5 passed`
  - `node --test scripts/tests/svg-chart-converter.harness.test.mjs scripts/tests/svg-slide-renderer.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs` -> `10 passed`
  - `node --test scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `10 passed`
- `Phase 17` status: completed
- `Phase 17` scope: SCQA content strategy layer (S6) with assertive-title contract propagation
- `Phase 17` implementation:
  - Added `SlideContentStrategy` inference in `agent/src/ppt_planning.py`:
    - introduced `SlideContentStrategy` dataclass and `build_slide_content_strategy(...)`,
    - inferred `page_role`, `density_hint`, `render_path` and selected `data_anchor`,
    - enforced assertive-title synthesis for generic headings (e.g., replacing plain "甯傚満鍒嗘瀽" style titles with evidence-anchored assertions).
  - Extended `agent/src/schemas/ppt_plan.py`:
    - added `SlideContentStrategy` schema model,
    - added optional `content_strategy` field to `SlidePlan`.
  - Integrated strategy generation into `agent/src/ppt_service.py::generate_presentation_plan(...)`:
    - title block now uses strategy `assertion`,
    - strategy evidence participates in body/list point composition,
    - each slide now carries typed `content_strategy` metadata.
  - Updated `agent/src/ppt_service.py::_presentation_plan_to_render_payload(...)`:
    - now propagates `content_strategy` into render payload slide contract.
  - Added tests:
    - `agent/tests/test_ppt_planning.py`:
      - `test_build_slide_content_strategy_enforces_assertive_title_for_generic_message`
      - `test_build_slide_content_strategy_routes_timeline_to_svg`
    - `agent/tests/test_ppt_research_flow.py`:
      - strengthened `test_research_outline_plan_flow_contract` with `content_strategy` assertions.
    - `agent/tests/test_ppt_contract.py`:
      - `test_render_payload_preserves_slide_content_strategy_contract`
- `Phase 17` verification:
  - `pytest -q agent/tests/test_ppt_planning.py -k "build_slide_content_strategy or enforce_layout_diversity or paginate_content_overflow"` -> `10 passed`
  - `pytest -q agent/tests/test_ppt_research_flow.py -k "research_outline_plan_flow_contract"` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_contract.py -k "content_strategy or render_payload_preserves_semantic_slide_type_and_layout_grid"` -> `2 passed`
  - `pytest -q agent/tests/test_ppt_planning.py agent/tests/test_ppt_research_flow.py agent/tests/test_ppt_contract.py` -> `40 passed`
- `Phase 18` status: completed
- `Phase 18` scope: textual QA coverage checks for SCQA strategy (`assertion/evidence` hit validation)
- `Phase 18` implementation:
  - Extended `agent/src/ppt_visual_qa.py::audit_textual_slides(...)`:
    - added strategy-aware coverage checks based on `slide.content_strategy`,
    - added per-slide fields: `assertion_covered`, `evidence_expected`, `evidence_hit_count`,
    - added deck metrics: `assertion_coverage_ratio`, `evidence_coverage_ratio`,
    - added issue codes: `assertion_not_covered`, `evidence_not_fully_covered`.
  - Extended `agent/src/ppt_service.py::_build_export_alerts(...)`:
    - added `text_qa_assertion_coverage_low` alert,
    - added `text_qa_evidence_coverage_low` alert.
  - Added/updated tests:
    - `agent/tests/test_ppt_visual_qa.py::test_textual_qa_detects_placeholder_and_page_number_gap` now validates assertion/evidence coverage metrics and issue codes.
    - `agent/tests/test_ppt_export_retry_flow.py::test_text_qa_surfaces_in_observability_and_alerts` now validates coverage alerts and observability issue propagation.
- `Phase 18` verification:
  - `pytest -q agent/tests/test_ppt_visual_qa.py` -> `5 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "text_qa_surfaces_in_observability_and_alerts"` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_planning.py agent/tests/test_ppt_research_flow.py agent/tests/test_ppt_contract.py agent/tests/test_ppt_visual_qa.py agent/tests/test_ppt_export_retry_flow.py` -> `58 passed`
- `Phase 19` status: completed
- `Phase 19` scope: S10 per-slide module orchestration foundation (`slide-XX module + manifest + compile entry + parallel per-slide render`)
- `Phase 19` implementation:
  - Added module orchestrator `scripts/minimax/slide-module-orchestrator.mjs`:
    - `buildSlideModuleRecords(...)`: creates typed per-slide records (`cover-page-generator` / `content-page-generator` / `section-divider-generator` / `summary-page-generator`).
    - `writeSlideModules(...)`: writes `slide-XX.js` modules plus `manifest.json`.
    - `loadSlideModules(...)` and `assemblePayloadFromModules(...)`: restore ordered payload from module files.
    - `compileSlideModules(...)`: compiles assembled deck by invoking existing `scripts/generate-pptx-minimax.mjs`.
    - `renderSlideModulesInParallel(...)`: runs per-slide render jobs with concurrency cap (default max 5), using `--retry-scope slide --target-slide-ids`.
  - Added CLI wrapper `scripts/orchestrate-pptx-modules.mjs`:
    - supports `modules generation`, optional `--render-each`, optional `--compile`.
  - Added tests:
    - `scripts/tests/slide-module-orchestrator.harness.test.mjs`
    - `scripts/tests/orchestrate-pptx-modules.harness.test.mjs`
- `Phase 19` verification:
  - `node --test scripts/tests/slide-module-orchestrator.harness.test.mjs` -> `3 passed`
  - `node --test scripts/tests/orchestrate-pptx-modules.harness.test.mjs scripts/tests/slide-module-orchestrator.harness.test.mjs` -> `4 passed`
  - regression:
    - `node --test scripts/tests/generate-pptx-minimax.harness.test.mjs scripts/tests/generate-pptx-minimax-svg-route.harness.test.mjs` -> `2 passed`
    - `node --test scripts/tests/template-render-priority.harness.test.mjs scripts/tests/template-registry.harness.test.mjs` -> `10 passed`
- `Phase 20` status: completed
- `Phase 20` scope: Python retry orchestration integrated with module entry (`single-slide retry -> parallel regenerate -> compile full deck`)
- `Phase 20` implementation:
  - Extended Node module orchestrator path:
    - `scripts/minimax/slide-module-orchestrator.mjs`:
      - `renderSlideModulesInParallel(...)` now supports `targetSlideIds` filtering.
      - `compileSlideModules(...)` now normalizes compile payload to full-deck scope (`retry_scope=deck`, cleared target ids), ensuring compile output is full deck instead of patch deck.
    - `scripts/orchestrate-pptx-modules.mjs`:
      - added CLI option `--target-slide-ids`.
  - Extended Python exporter `agent/src/minimax_exporter.py`:
    - added module-retry command routing for slide-scope retries:
      - when `retry_scope=slide` and `target_slide_ids` provided, exporter invokes `scripts/orchestrate-pptx-modules.mjs` (render-each + compile) instead of direct generator call.
    - added env controls:
      - `PPT_MODULE_RETRY_ENABLED` (default on)
      - `PPT_MODULE_RETRY_MAX_PARALLEL` (default 5, bounded).
    - added `is_full_deck` in export result contract.
    - improved cleanup for temporary module directories.
  - Updated Python retry loop `agent/src/ppt_service.py`:
    - if partial retry result already has `is_full_deck=true`, skip legacy extra `full_deck_finalize` export pass.
    - keep legacy finalize fallback when partial result is patch-like (`is_full_deck` absent/false).
  - Added tests:
    - `scripts/tests/slide-module-orchestrator.harness.test.mjs`:
      - new test: target slide filtering.
      - new test: compile input force-normalized to full deck.
    - `scripts/tests/orchestrate-pptx-modules.harness.test.mjs`:
      - new test: render-each with slide targeting + compile still produces full-deck render output.
    - `agent/tests/test_minimax_exporter_module_retry.py`:
      - verifies exporter routes to `orchestrate-pptx-modules.mjs` for slide retries.
    - `agent/tests/test_ppt_export_retry_flow.py`:
      - `test_partial_retry_full_deck_result_skips_finalize_call`.
- `Phase 20` verification:
  - `node --test scripts/tests/slide-module-orchestrator.harness.test.mjs scripts/tests/orchestrate-pptx-modules.harness.test.mjs` -> `6 passed`
  - `pytest -q agent/tests/test_minimax_exporter_module_retry.py` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "quality_gate_triggers_slide_retry_and_persists_diagnostics or partial_retry_full_deck_result_skips_finalize_call or schema_invalid_retries_failed_slide_only or retry_flow_downgrades_render_path_until_png_fallback"` -> `4 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py` -> `14 passed`
  - `pytest -q agent/tests/test_exporter_official_mode.py` -> `6 passed`
- `Phase 21` status: completed
- `Phase 21` scope: S11 template-edit dual-route MVP (`template_file_url -> template placeholder fill -> export`)
- `Phase 21` implementation:
  - Extended export request schema:
    - `agent/src/schemas/ppt.py`
      - added optional `template_file_url` with URL validation (`http://` / `https://`).
  - Added template placeholder fill engine:
    - `agent/src/pptx_engine.py`
      - added `fill_template_pptx(...)` to load uploaded template bytes and replace placeholders in slide text/table/notes.
      - supports deck/global placeholders (`{{deck_title}}`, `{{author}}`, `{{date}}`) and slide placeholders (`{{slide_1_title}}`, `{{body}}`, `{{bullet_1}}`...).
  - Added service-level route switch:
    - `agent/src/ppt_service.py`
      - added `_download_remote_file_bytes(...)` using existing SSRF-protected downloader from `document_parser`.
      - in `export_pptx(...)`, when `template_file_url` is provided:
        - bypasses MiniMax generator route,
        - applies template placeholder fill,
        - uploads final PPTX to R2,
        - returns export metadata (`skill=pptx_template_editor`, `generator_mode=template_edit`) with diagnostics/observability.
  - Added tests:
    - `agent/tests/test_pptx_engine_template_fill.py`:
      - validates placeholder replacement on a synthetic PPTX template.
    - `agent/tests/test_ppt_export_retry_flow.py`:
      - `test_template_file_url_uses_template_edit_route` verifies template route selection and MiniMax bypass.
    - `agent/tests/test_ppt_contract.py`:
      - validates `template_file_url` schema behavior.
- `Phase 21` verification:
  - `pytest -q agent/tests/test_pptx_engine_template_fill.py` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_contract.py -k "template_file_url or export_request_has_retry_scope_fields"` -> `2 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "template_file_url_uses_template_edit_route or partial_retry_full_deck_result_skips_finalize_call or quality_gate_triggers_slide_retry_and_persists_diagnostics"` -> `3 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py` -> `15 passed`
  - `pytest -q agent/tests/test_ppt_contract.py` -> `23 passed`
- `Phase 22` status: completed
- `Phase 22` scope: S10 deep merge completion (`render-each` single-slide result is merged back into slide modules before final compile)
- `Phase 22` implementation:
  - Updated `scripts/minimax/slide-module-orchestrator.mjs`:
    - added render-output parser + patch builder (`official_output` + per-slide render metadata merge).
    - `renderSlideModulesInParallel(...)` now applies merged patch into targeted `slide-XX.js` modules before compile stage.
    - fixed module reload cache path (`require + cache clear`) to ensure compile reads latest module writes.
    - added merge summary fields in render-each result:
      - `merged_slide_ids`
      - `merged_slide_count`
  - Added test coverage in `scripts/tests/slide-module-orchestrator.harness.test.mjs`:
    - verifies targeted render-output patch is written back into module slide data.
    - verifies subsequent `compileSlideModules(...)` input contains merged slide content (not stale seed payload).
- `Phase 22` verification:
  - `node --test scripts/tests/slide-module-orchestrator.harness.test.mjs` -> `5 passed`
  - `node --test scripts/tests/orchestrate-pptx-modules.harness.test.mjs` -> `2 passed`
  - `pytest -q agent/tests/test_minimax_exporter_module_retry.py` -> `1 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "partial_retry_full_deck_result_skips_finalize_call or quality_gate_triggers_slide_retry_and_persists_diagnostics or retry_flow_downgrades_render_path_until_png_fallback"` -> `3 passed`
- `Phase 23` status: completed
- `Phase 23` scope: S12 Layer A enhancement with markitdown-based post-export text extraction QA
- `Phase 23` implementation:
  - Added markitdown QA helpers in `agent/src/ppt_visual_qa.py`:
    - `extract_text_with_markitdown(...)`
    - `summarize_markitdown_text(...)`
    - `run_markitdown_text_qa(...)`
  - Integrated into `agent/src/ppt_service.py` export pipeline:
    - after PPTX generation, run markitdown text QA (env-gated, default on).
    - merge markitdown issue codes into existing `text_qa.issue_codes`.
    - persist markitdown summary under `text_qa.markitdown` / observability report.
  - Extended alerting logic in `_build_export_alerts(...)`:
    - `text_qa_markitdown_unavailable`
    - `text_qa_markitdown_placeholder_ratio_high`
    - `text_qa_markitdown_empty_output`
  - Added tests:
    - `agent/tests/test_ppt_visual_qa.py`
      - markitdown summary placeholder detection
      - extraction-failure propagation
    - `agent/tests/test_ppt_export_retry_flow.py::test_text_qa_surfaces_in_observability_and_alerts`
      - verifies markitdown summary propagation + alert + issue code merge.
- `Phase 23` verification:
  - `pytest -q agent/tests/test_ppt_visual_qa.py` -> `7 passed`
  - `pytest -q agent/tests/test_ppt_export_retry_flow.py -k "text_qa_surfaces_in_observability_and_alerts or template_renderer_summary_surfaces_in_observability_and_alerts or partial_retry_full_deck_result_skips_finalize_call"` -> `3 passed`
  - `python -m py_compile agent/src/ppt_visual_qa.py agent/src/ppt_service.py` -> `ok`
- `Phase 24` status: completed
- `Phase 24` scope: S13 real subagent executor (LangGraph) integration for module retry pre-render patching
- `Phase 24` implementation:
  - Added Python LangGraph executor `agent/src/ppt_subagent_executor.py`:
    - graph stages: `prepare -> apply_tools -> call_llm -> finalize`.
    - built-in tool hints:
      - `recommend_render_path`
      - `recommend_layout_grid`
    - output contract aligned to Node executor protocol:
      - `slide_patch`
      - `load_skills`
      - `notes`
      - `skipped/reason`.
  - Added dependency:
    - `agent/pyproject.toml`: `langgraph>=1.1.3`.
  - Bridged Node default external executor to Python module:
    - `scripts/minimax/slide-module-orchestrator.mjs`:
      - when no custom `PPT_SUBAGENT_EXECUTOR_BIN/ARGS` provided, default to
        `uv run --project agent python -m src.ppt_subagent_executor`.
  - Added tests:
    - `agent/tests/test_ppt_subagent_executor.py`:
      - verifies patch + skills merge when model callback returns structured output.
      - verifies safe skip when no model credentials configured.
    - `agent/tests/test_minimax_exporter_module_retry.py`:
      - verifies Python exporter appends `--subagent-exec` under worker-role default behavior.
    - `scripts/tests/orchestrate-pptx-modules.harness.test.mjs`:
      - verifies CLI path executes external subagent process and records `subagent_runs.applied=true`.
- `Phase 24` verification:
  - `cd agent && uv run pytest tests/test_ppt_subagent_executor.py tests/test_minimax_exporter_module_retry.py tests/test_ppt_export_retry_flow.py -q` -> `19 passed`
  - `node --test scripts/tests/slide-module-orchestrator.harness.test.mjs scripts/tests/orchestrate-pptx-modules.harness.test.mjs` -> `9 passed`
  - smoke:
    - `cd agent && echo '{"slide_id":"s1","slide_type":"content","render_path":"pptxgenjs","load_skills":["slide-making-skill"],"prompt":"refine","slide_data":{"title":"x"}}' | uv run python -m src.ppt_subagent_executor`
    - expected: JSON output with `ok=true` and `skipped=true` when no LLM key configured.
- `Phase 25` status: completed
- `Phase 25` scope: deployment/runtime enablement docs for module retry + subagent executor
- `Phase 25` implementation:
  - Updated `agent/RAILWAY.md`:
    - documented `PPT_MODULE_RETRY_ENABLED` / `PPT_MODULE_RETRY_MAX_PARALLEL`.
    - documented subagent executor switch (later removed; worker role now defaults to always-on).
    - documented default Python executor fallback and optional custom executor override.
    - documented `PPT_SUBAGENT_MODEL` + OpenRouter/OpenAI credential options.
- `Phase 25` verification:
  - docs review + command replay verification on local environment.
- `Phase 26` status: completed
- `Phase 26` scope: S13 runtime skill execution wiring + S11 template image/cleanup hardening + S2 chart coverage to target + module retry e2e compile-back validation
- `Phase 26` implementation:
  - S13 runtime execution (LangGraph node-level skill runtime):
    - `agent/src/ppt_subagent_executor.py`
      - added `run_skill_runtime` graph node and state fields `skill_runtime_patch` / `skill_runtime_trace`.
      - added built-in runtime handlers for `slide-making-skill`, `design-style-skill`, `color-font-skill`, `pptx`.
      - added env switch `PPT_SUBAGENT_ENABLE_SKILL_RUNTIME` and output contract field `skill_runtime`.
      - finalized slide patch merge precedence: `skill_runtime_patch < tool_patch < llm_patch`.
    - `agent/tests/test_ppt_subagent_executor.py`
      - added assertions for runtime trace presence and merged patch behavior.
  - S11 template-edit route hardening:
    - `agent/src/pptx_engine.py`
      - added image placeholder extraction/replacement path for `{{image}}` / `{{image_url}}` and `slide_{n}_image*` keys.
      - added template image placeholder detection and automatic route fallback to python-pptx fill path when image replacement is needed.
      - added XML media reference scan + orphan media cleanup accounting (`cleaned_resource_count`).
      - added `image_replacement_count` output metric for template fill diagnostics.
    - `agent/tests/test_pptx_engine_template_fill.py`
      - added tests for image placeholder replacement and orphan media cleanup.
  - S2 chart coverage lift:
    - `scripts/minimax/chart-factory.mjs`
      - normalized chart alias resolution and expanded non-standard chart family to 7 types (`funnel`, `waterfall`, `sankey`, `treemap`, `heatmap`, `gauge`, `pyramid`).
    - `scripts/minimax/svg-chart-converter.mjs`
      - added concrete SVG builders for `treemap`, `heatmap`, `gauge`, `pyramid`.
    - tests updated in:
      - `scripts/tests/chart-factory.harness.test.mjs`
      - `scripts/tests/svg-chart-converter.harness.test.mjs`
  - S10 module retry e2e regression:
    - `scripts/tests/orchestrate-pptx-modules.harness.test.mjs`
      - added end-to-end test: single-slide retry patch merge into modules, then compile returns full deck with patched target slide.
- `Phase 26` verification:
  - `uv run --project agent pytest agent/tests/test_ppt_subagent_executor.py agent/tests/test_pptx_engine_template_fill.py agent/tests/test_minimax_exporter_module_retry.py agent/tests/test_ppt_export_retry_flow.py -k "partial_retry_full_deck_result_skips_finalize_call or quality_gate_triggers_slide_retry_and_persists_diagnostics or retry_flow_downgrades_render_path_until_png_fallback or template_file_url_uses_template_edit_route or text_qa_surfaces_in_observability_and_alerts" -q`
  - result: `5 passed, 18 deselected`
  - `node --test scripts/tests/chart-factory.harness.test.mjs scripts/tests/svg-chart-converter.harness.test.mjs scripts/tests/slide-module-orchestrator.harness.test.mjs scripts/tests/orchestrate-pptx-modules.harness.test.mjs scripts/tests/icon-factory.harness.test.mjs scripts/tests/card-renderers-icon.harness.test.mjs`
  - result: `22 passed`
  - chart coverage check:
    - `node --input-type=module -e "import { SUPPORTED_CHART_TYPES, NON_STANDARD_CHART_TYPES } from './scripts/minimax/chart-factory.mjs'; ..."`
    - result: `realCoverage=15` (`supported=8`, `nonstandard=7`).
- `Phase 27` status: completed
- `Phase 27` scope: remaining-gap completion in requested order (`S9 -> S7 -> S5/S2`)
- `Phase 27` implementation:
  - `S9` density rhythm hard rules (planning + gate alignment):
    - `agent/src/ppt_template_catalog.py`
      - added normalized quality-profile knobs:
        - `density_max_consecutive_high`
        - `density_window_size`
        - `density_require_low_or_breathing_per_window`
    - `agent/src/ppt_service.py`
      - wired `_apply_visual_orchestration(...)` layout pipeline to run `enforce_density_rhythm(...)` using profile knobs.
    - `agent/src/ppt_quality_gate.py`
      - added density-level helpers and gate checks:
        - `layout_density_consecutive_high`
        - `layout_density_window_missing_breathing`
      - added score penalties for both new gate codes.
    - tests:
      - `agent/tests/test_ppt_quality_gate.py`
        - `test_layout_diversity_detects_density_consecutive_high_run`
        - `test_layout_diversity_detects_density_window_missing_breathing`
      - `agent/tests/test_ppt_contract.py`
        - `test_visual_orchestration_enforces_density_rhythm_every_five_middle_pages`
      - adjusted compatibility fixture:
        - `agent/tests/test_ppt_export_retry_flow.py::test_layout_gate_uses_input_payload_when_render_spec_lacks_layout_metadata`
  - `S7` five-level image strategy completion tests:
    - `agent/tests/test_ppt_contract.py`
      - added level-3 stock branch test:
        - `test_hydrate_image_assets_uses_serper_stock_as_level_3`
      - added level-5 terminal placeholder branch test:
        - `test_hydrate_image_assets_falls_back_to_brand_placeholder_as_level_5`
    - keeps full ladder verified:
      - level-1 `user_url`
      - level-2 `ai_svg`
      - level-3 `stock/web`
      - level-4 `icon_bg`
      - level-5 `placeholder`
  - `S5/S2` target guardrails:
    - `scripts/tests/template-renderer-coverage.harness.test.mjs`
      - added `template coverage meets S5 target thresholds` (catalog templates >= 12, content renderers >= 12).
    - `scripts/tests/chart-factory.harness.test.mjs`
      - added explicit composition gates:
        - standard chart types >= 7
        - non-standard chart types >= 7
      - preserves total real chart coverage >= 15.
- `Phase 27` verification:
  - Python targeted:
    - `uv run --project agent pytest agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_contract.py agent/tests/test_ppt_export_retry_flow.py -k "density or hydrate_image_assets_uses_serper_stock_as_level_3 or falls_back_to_brand_placeholder_as_level_5 or enforces_density_rhythm_every_five_middle_pages or layout_gate_uses_input_payload_when_render_spec_lacks_layout_metadata" -q`
    - result: `12 passed, 64 deselected`
  - Python focused:
    - `uv run --project agent pytest agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_contract.py -k "density or hydrate_image_assets_uses_serper_stock_as_level_3 or falls_back_to_brand_placeholder_as_level_5 or enforces_density_rhythm_every_five_middle_pages" -q`
    - result: `11 passed, 50 deselected`
  - Node:
    - `node --test scripts/tests/template-renderer-coverage.harness.test.mjs scripts/tests/template-catalog.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/chart-factory.harness.test.mjs scripts/tests/svg-chart-converter.harness.test.mjs`
    - result: `15 passed`
  - Coverage snapshot:
    - template catalog total: `16`
    - content-capable templates: `14`
    - local content renderers: `14`
    - chart real coverage: `15` (`supported=8`, `nonstandard=7`)
- `Phase 28` status: completed
- `Phase 28` scope: S3 icon system enhancement by introducing ppt-master icon library into renderer chain
- `Phase 28` implementation:
  - vendored ppt-master icon assets:
    - added `scripts/minimax/vendor/ppt-master-icons/`
    - includes:
      - `640` SVG icons
      - `icons_index.json`
      - upstream `README.md`
      - local attribution: `ATTRIBUTION.md`
  - extended icon render chain:
    - `scripts/minimax/icon-factory.mjs`
      - added ppt-master index loading + lookup cache.
      - added ppt-master SVG read cache.
      - added resolution order:
        - explicit ppt-master icon name
        - explicit react-icons `Fi*`
        - ppt-master keyword/category alias
        - react-icons keyword alias
        - fallback icon
      - added raw SVG normalization for ppt-master icons:
        - XML/comment cleanup
        - `viewBox` unification (`0 0 16 16`)
        - fill/stroke recolor with theme primary
      - kept existing PNG rasterization fallback path unchanged.
  - tests:
    - `scripts/tests/icon-factory.harness.test.mjs`
      - updated keyword expectations to ppt-master resolution.
      - added explicit ppt-master icon resolution test (`rocket`).
      - added ppt-master SVG+PNG render payload test.
- `Phase 28` verification:
  - `node --test scripts/tests/icon-factory.harness.test.mjs scripts/tests/card-renderers-icon.harness.test.mjs`
  - result: `7 passed`
  - `node --test scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/chart-factory.harness.test.mjs scripts/tests/svg-chart-converter.harness.test.mjs`
  - result: `9 passed`
- `Phase 29` status: completed
- `Phase 29` scope: Chinese semantic icon mapping enhancement on top of S3 icon system
- `Phase 29` implementation:
  - `scripts/minimax/icon-factory.mjs`
    - added Chinese keyword contains-mapping table for high-frequency business/ppt terms.
    - added Chinese semantic fallback in `resolvePptMasterByKeyword(...)` after exact token lookup.
    - priority tuned so `鐩爣/鎸囨爣` semantics resolve before `璺緞/娴佺▼`.
  - tests:
    - `scripts/tests/icon-factory.harness.test.mjs`
      - added `icon factory resolves chinese semantic keywords to ppt-master icons`.
    - `scripts/tests/card-renderers-icon.harness.test.mjs`
      - added `card renderer infers icon from chinese title when icon is missing`.
- `Phase 29` verification:
  - `node --test scripts/tests/icon-factory.harness.test.mjs scripts/tests/card-renderers-icon.harness.test.mjs`
  - result: `9 passed`
  - `node --test scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/chart-factory.harness.test.mjs scripts/tests/svg-chart-converter.harness.test.mjs`
  - result: `9 passed`
- `Phase 30` status: completed
- `Phase 30` scope: close remaining high/medium gaps (`S13/S12/S14/S11/S3`)
- `Phase 30` implementation:
  - `S13` installed skill execution chain (LangGraph runtime node):
    - `agent/src/ppt_subagent_executor.py`
      - added external installed-skill executor adapter:
        - `PPT_INSTALLED_SKILL_EXECUTOR_ENABLED`
        - `PPT_INSTALLED_SKILL_EXECUTOR_BIN`
        - `PPT_INSTALLED_SKILL_EXECUTOR_ARGS`
        - `PPT_INSTALLED_SKILL_EXECUTOR_TIMEOUT_SEC`
      - `run_skill_runtime(...)` now executes external skill chain first, then builtin handlers as fallback for unresolved skills.
      - runtime trace now includes source attribution (`installed_skill_executor` / `builtin_fallback`).
    - `scripts/minimax/slide-module-orchestrator.mjs`
      - propagated `skill_runtime_enabled` + `skill_runtime_trace` into per-slide `subagent_runs` diagnostics.
    - tests:
      - `agent/tests/test_ppt_subagent_executor.py`
        - added `test_subagent_executor_uses_installed_skill_executor_chain`.
  - `S12` visual QA -> slide-level retry loop:
    - `agent/src/ppt_quality_gate.py`
      - upgraded `validate_visual_audit(...)` to infer slide-level targets from `visual_audit.slides` (`local_issues`/`multimodal_issues` + per-slide metrics).
      - visual gate issues now emit `retry_scope="slide"` + `retry_target_ids=[...]` whenever slide targets can be resolved.
    - `agent/src/ppt_service.py`
      - added `_collect_issue_retry_target_slides(...)`.
      - retry routing now prefers issue `retry_target_ids` and switches to single-slide retry for visual gate failures.
    - tests:
      - `agent/tests/test_ppt_quality_gate.py`
        - added `test_visual_audit_gate_returns_slide_level_retry_targets`.
  - `S14` expanded route matrix:
    - `agent/src/ppt_master_design_spec.py`
      - expanded `_COMPLEX_LAYOUTS`.
      - expanded `_COMPLEX_BLOCK_TYPES`.
      - added `_COMPLEX_CHART_TYPES` + subtype detection for chart blocks.
      - extended `choose_render_path(...)` semantic rules for complex slide types.
    - tests:
      - added `agent/tests/test_ppt_master_design_spec.py` for complex layout/block/chart/semantic routing.
  - `S11` markitdown-driven template replacement:
    - `agent/src/pptx_engine.py`
      - integrated markitdown extraction into `fill_template_pptx(...)` as replacement-input path (not probe-only).
      - added markdown section parser + merge strategy to enrich per-slide replacement map.
      - included markitdown flags in output metadata (`markitdown_enabled/ok/used/issue`).
    - `agent/src/ppt_service.py`
      - surfaced template markitdown usage metadata in `template_edit` response and diagnostics.
    - tests:
      - `agent/tests/test_pptx_engine_template_fill.py`
        - added `test_fill_template_uses_markitdown_structure_for_replacements`.
  - `S3` icon library scale to 4000+:
    - `scripts/minimax/icon-factory.mjs`
      - expanded React icon packs from `fi` only to multi-pack aggregation (`fi/fa6/md/ai/io5/bi/tb/ri/hi2`).
      - added `getIconLibraryStats()` for runtime observability.
      - preserved ppt-master icon precedence + png rasterization path.
    - tests:
      - `scripts/tests/icon-factory.harness.test.mjs`
        - added multi-pack explicit icon assertion (`MdOutlineSecurity`).
        - added 4000+ icon-scale assertion.
- `Phase 30` verification:
  - Python:
    - `uv run --project agent pytest agent/tests/test_ppt_subagent_executor.py agent/tests/test_ppt_quality_gate.py agent/tests/test_ppt_master_design_spec.py agent/tests/test_pptx_engine_template_fill.py -q`
    - result: `45 passed`
  - Node:
    - `node --test scripts/tests/icon-factory.harness.test.mjs scripts/tests/card-renderers-icon.harness.test.mjs scripts/tests/template-renderers.harness.test.mjs scripts/tests/template-render-priority.harness.test.mjs scripts/tests/chart-factory.harness.test.mjs scripts/tests/svg-chart-converter.harness.test.mjs`
    - result: `19 passed`
    - `node --test scripts/tests/orchestrate-pptx-modules.harness.test.mjs scripts/tests/slide-module-orchestrator.harness.test.mjs`
    - result: `10 passed`
- `Phase 31` status: completed
- `Phase 31` scope: deployment-role split hardening for `Vercel(web)` + `Railway(worker)`
- `Phase 31` implementation:
  - runtime role switch:
    - introduced `PPT_EXECUTION_ROLE` (`web|worker|auto`) strategy.
    - `auto` infers `web` on Vercel (`VERCEL*` env present), else `worker`.
  - exporter defaults by role:
    - `agent/src/minimax_exporter.py`
      - `_module_retry_enabled()` now defaults:
        - `worker`: enabled
        - `web`: disabled
      - explicit env (`PPT_MODULE_RETRY_ENABLED`) still overrides.
  - subagent external skill executor defaults by role:
    - `agent/src/ppt_subagent_executor.py`
      - `_installed_skill_exec_enabled()` now defaults:
        - `web`: disabled
        - `worker`: enabled only when executor bin+args are configured.
      - explicit env (`PPT_INSTALLED_SKILL_EXECUTOR_ENABLED`) still overrides.
  - deployment docs:
    - updated `README.md` Vercel/Railway env guidance.
    - updated `agent/RAILWAY.md` with role split env matrix.
    - added `docs/VERCEL_RAILWAY_SPLIT_DEPLOYMENT.md`.
  - tests:
    - `agent/tests/test_minimax_exporter_module_retry.py`
      - added vercel-default-off and explicit-override tests.
    - `agent/tests/test_ppt_subagent_executor.py`
      - added web-role default no-external-executor test.
- `Phase 31` verification:
  - `uv run --project agent pytest agent/tests/test_minimax_exporter_module_retry.py agent/tests/test_ppt_subagent_executor.py -q`
  - result: `8 passed`
  - `uv run --project agent pytest agent/tests/test_ppt_export_retry_flow.py -k "quality_gate_triggers_slide_retry_and_persists_diagnostics or partial_retry_full_deck_result_skips_finalize_call" -q`
  - result: `2 passed`
- `Phase 32` status: completed
- `Phase 32` scope: split deployment API hardening for V7 export submit/status workflow
- `Phase 32` implementation:
  - `agent/src/v7_routes.py`
    - extracted sync export body into reusable `_execute_export(...)`.
    - added async task lifecycle for local worker execution:
      - `POST /api/v1/v7/export/submit`
      - `GET /api/v1/v7/export/status/{task_id}`
    - added web->worker proxy path (no local heavy execution on web by default):
      - `PPT_EXPORT_WORKER_BASE_URL`
      - `PPT_EXPORT_WORKER_TOKEN` (optional)
      - `PPT_EXPORT_WORKER_TIMEOUT_SEC`
    - added sync-gate by role:
      - `PPT_EXPORT_SYNC_ENABLED` default `false` on `web`, `true` on `worker`.
      - sync endpoint `POST /api/v1/v7/export` now returns 503 on web-role default and points to submit/status API.
    - added explicit web local-async escape hatch:
      - `PPT_EXPORT_ALLOW_LOCAL_ASYNC_ON_WEB=true` (default off).
  - tests:
    - added `agent/tests/test_v7_export_submit_status.py`:
      - local background submit/status success path.
      - web-role sync export default deny behavior.
      - web-role worker-proxy submit behavior.
  - deployment docs:
    - updated `README.md` with split-mode V7 API calls + new envs.
    - updated `agent/RAILWAY.md` with submit/status workflow and env matrix.
    - updated `docs/VERCEL_RAILWAY_SPLIT_DEPLOYMENT.md` with worker-proxy env and endpoint guidance.
- `Phase 32` verification:
  - `uv run --project agent pytest agent/tests/test_v7_export_submit_status.py agent/tests/test_ppt_v7_routes.py agent/tests/test_v7_routes_presign.py -q`
  - result: `8 passed`
  - `uv run --project agent pytest agent/tests/test_ppt_v7_schema.py agent/tests/test_ppt_v7_generator.py agent/tests/test_ppt_v7_routes.py agent/tests/test_v7_routes_presign.py agent/tests/test_v7_export_submit_status.py -q`
  - result: `14 passed`
- `Phase 33` status: completed
- `Phase 33` scope: worker proxy hardening with request signing + persistent task status storage
- `Phase 33` implementation:
  - `agent/src/v7_routes.py`
    - added HMAC signature chain for `web -> worker` proxy:
      - `PPT_EXPORT_WORKER_SHARED_SECRET`
      - `PPT_EXPORT_WORKER_REQUIRE_SIGNATURE` (default true when shared secret exists)
      - `PPT_EXPORT_WORKER_SIGNATURE_TTL_SEC`
      - headers: `X-PPT-Worker-TS`, `X-PPT-Worker-Digest`, `X-PPT-Worker-Signature`
    - worker-side verification is enforced only on worker role for:
      - `POST /api/v1/v7/export/submit`
      - `GET /api/v1/v7/export/status/{task_id}`
    - added Supabase-backed task persistence for v7 export status:
      - table via `PPT_EXPORT_TASKS_TABLE` (default `autoviralvid_ppt_export_tasks`)
      - task create/update now upsert to DB
      - status read falls back to DB when in-memory cache misses
  - migrations:
    - added `agent/src/migrations/006_create_ppt_export_tasks.sql`
  - docs:
    - updated `README.md`, `agent/RAILWAY.md`, `docs/VERCEL_RAILWAY_SPLIT_DEPLOYMENT.md`
      with shared-secret signing env guidance.
  - tests:
    - `agent/tests/test_v7_export_submit_status.py`
      - added worker signature required/valid path test
      - added Supabase persistence fallback load test
- `Phase 33` verification:
  - `uv run --project agent pytest agent/tests/test_v7_export_submit_status.py -q`
  - result: `5 passed`
  - `uv run --project agent pytest agent/tests/test_ppt_v7_schema.py agent/tests/test_ppt_v7_generator.py agent/tests/test_ppt_v7_routes.py agent/tests/test_v7_routes_presign.py agent/tests/test_v7_export_submit_status.py -q`
  - result: `16 passed`
  - `uv run --project agent pytest agent/tests/test_minimax_exporter_module_retry.py agent/tests/test_ppt_subagent_executor.py -q`
  - result: `8 passed`
- `Phase 34` status: completed
- `Phase 34` scope: development fail-fast hardening (remove S13/S11 fallback paths)
- `Phase 34` implementation:
  - `S13` fallback removal and hard-fail:
    - `agent/src/ppt_subagent_executor.py`
      - removed builtin skill runtime fallback path from `run_skill_runtime(...)`.
      - when installed executor is disabled/not configured/error/unresolved skill coverage:
        - marks `runtime_error=True`
        - returns explicit reason (`installed_skill_executor_disabled` / `installed_skill_unresolved:...` / executor reason)
        - skips downstream LLM patch call.
      - finalize now sets `ok = false` when `runtime_error` is true.
    - `scripts/minimax/slide-module-orchestrator.mjs`
      - subagent result `ok=false` now throws immediately (`subagent_executor_rejected`), no silent continue.
    - `scripts/orchestrate-pptx-modules.mjs`
      - exits with non-zero code when result `success=false` to surface failure to Python caller.
  - `S11` fallback removal and strict markitdown-only replacement:
    - `agent/src/pptx_engine.py`
      - removed `_build_template_replacements` fallback usage.
      - template fill now requires markitdown extraction success and non-empty sections.
      - extraction disabled/failure/empty sections now raise explicit error.
      - removed old slide-text fallback helper path.
  - tests updated:
    - `agent/tests/test_ppt_subagent_executor.py` expectations aligned to fail-fast behavior.
    - `agent/tests/test_pptx_engine_template_fill.py` now mocks markitdown extraction in all template-fill tests.
- `Phase 34` verification:
  - `uv run --project agent pytest agent/tests/test_ppt_subagent_executor.py agent/tests/test_pptx_engine_template_fill.py -q`
  - result: `9 passed`
  - `node --test scripts/tests/slide-module-orchestrator.harness.test.mjs scripts/tests/orchestrate-pptx-modules.harness.test.mjs`
  - result: `10 passed`

