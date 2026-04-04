# 2026-04-01 PPT Design Quality Refactor Progress

## 1) Current Status

- The main refactor plan in `docs/plans/2026-04-01-ppt-design-quality-optimization-v1.md` has been integrated into the primary pipeline flow (Task 1 to Task 5).
- Regression and unit tests for decision layer, render layer, retry ladder, export pipeline split, and quality gate are in place and passing.
- `phase5` (fidelity path) remains stable at high quality (`VERIFIED`, score `98.0`).

## 2) New Continuation Work (Zero Create Stability)

This continuation focused on removing `zero_create` instability in fallback/repair paths.

### 2.1 Changes in `scripts/run_reference_regression_once.py`

- Added schema-invalid parsing for render-contract failures:
  - `_extract_schema_invalid_contract_slide_indexes(...)`
- Added targeted contract self-heal for zero-create retries:
  - `_inject_chart_blocks_for_zero_create_contract_repair(...)`
  - injects minimal `chart` blocks only on affected slide indexes (from failure report)
- Added retry lock protection on Windows:
  - `_wait_for_path_unlock(...)`
  - avoids second-attempt failure caused by `EBUSY` on `generated.pptx`
- Integrated contract self-heal into two paths:
  - zero-create API -> local fallback retry
  - visual-critic repair retry
- Added diagnostics fields:
  - `zero_create_contract_repair_attempted`
  - `zero_create_contract_repair_used`
- Fixed dead branch in repair shortcut logic:
  - `restore_shortcuts` now runs only for non-zero-create mode.

### 2.2 Tests Updated

- `agent/tests/test_run_reference_regression_phase.py`
  - added tests for schema-invalid index extraction
  - added tests for targeted chart injection
  - added tests for file unlock wait helper

## 3) Validation Results

### 3.1 Unit/Script Tests

- `pytest agent/tests/test_run_reference_regression_phase.py -q` -> `32 passed`
- `pytest agent/tests/test_run_reference_regression_nightly.py -q` -> `6 passed`
- `python -m py_compile scripts/run_reference_regression_once.py scripts/generate_ppt_from_desc.py` -> pass

### 3.2 Real Regression Rounds

- `phase5` (fidelity): `VERIFIED`, score `98.0`, issue count `0` (baseline kept stable)
- `phase5z11` (zero_create): `NEEDS_IMPROVEMENT`, score `55.13`, issue count `30`
  - important improvement: repair-stage schema failure no longer hard-stops the run
  - diagnostics confirm self-heal path executed:
    - `zero_create_contract_repair_attempted=true`
    - `zero_create_contract_repair_used=true`

## 4) Practical Conclusion

- Mainline architecture refactor remains effective and stable.
- Zero-create is now more robust operationally (less brittle retries), but quality is still low and dominated by geometry/visual similarity.
- Next optimization should target **quality uplift** (not more orchestration complexity), especially:
  - geometry similarity and layout fidelity
  - media/image mismatch control
  - font/style overlap recovery in zero-create mode
