# PPT-Video Contract (MiniMax + Remotion)

## Goal
Use PPTX as the single source of truth while allowing scoped retry (`deck/slide/block`) and deterministic merge.

## Identity Model
- `deck_id`: Stable deck identity for one logical presentation.
- `slide_id`: Stable identity for each slide across retries.
- `block_id`: Stable identity for each text/content block inside a slide.

## Retry Fields
- `retry_scope`: `deck | slide | block`
- `retry_hint`: Human-readable failure reason forwarded to retried generation.
- `target_slide_ids`: Target slides for scoped retry.
- `target_block_ids`: Target blocks for scoped retry.
- `idempotency_key`: Caller-provided key for idempotent retries.

## Merge Rules
- Merge key priority for slides: `slide_id` -> `id` -> `page_number`.
- Only patched slides/blocks are replaced.
- Original order of base slides is preserved.
- Non-target slides remain untouched.

## Video Consistency Rule
- If `slide_image_urls` is available, force `video_mode=ppt_image_slideshow`.
- Remotion effects must be overlay-only and must not alter base slide text/layout.

