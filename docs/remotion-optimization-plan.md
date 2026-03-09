# Remotion-Oriented Video Editor Optimization Plan

## 1. Objective
Upgrade the current video editor from a timeline-only exporter into a render-ready system compatible with a Remotion pipeline, while reusing existing UI/state and avoiding a risky rewrite.

## 2. Current Baseline
- UI/editor interaction already works and should be kept:
  - `src/components/VideoEditor/Timeline.tsx`
  - `src/components/VideoEditor/PropertyEditor.tsx`
  - `src/contexts/EditorContext.tsx`
- Native preview is manually time-synced (non-declarative):
  - `src/components/VideoEditor/Player.tsx`
- Export only downloads raw timeline JSON:
  - `src/components/VideoEditor/EditorPanel.tsx`
- Backend generation/stitching exists and is independent:
  - `agent/src/langgraph_workflow.py`
  - `agent/src/video_stitcher.py`

## 3. Target Architecture
1. Keep existing editor UI and item model.
2. Introduce a render-domain schema independent from UI state shape.
3. Add deterministic mapper: `VideoProject -> RemotionCompositionPayload`.
4. Add render job request contract and API endpoint.
5. Keep current player as fallback preview path until full Remotion runtime is deployed.

## 4. Implemented in This Iteration

### 4.1 Render Domain Layer
- Added typed render schema and helpers:
  - `src/lib/render/types.ts`
  - `src/lib/render/remotion-mapper.ts`
  - `src/lib/render/index.ts`
- Core utilities:
  - `secondsToFrames()`
  - `toRemotionComposition()`
  - `buildRenderJobRequest()`
  - `summarizeRenderJob()`

### 4.2 Project Model Extensions
- Extended `VideoProject` with render-relevant metadata:
  - `fps?: number`
  - `backgroundColor?: string`
- Updated defaults:
  - `src/lib/types.ts`
  - `src/constants.ts`
  - `src/contexts/EditorContext.tsx`

### 4.3 Editor Export + Render Submit Flow
- Upgraded editor controls:
  - `Export Timeline` (legacy compatibility)
  - `Export Render Payload` (new remotion-ready payload)
  - `Submit Render Job` (server API call)
- Added render summary strip (fps, duration frames, layer count, audio count).
- Implemented in:
  - `src/components/VideoEditor/EditorPanel.tsx`

### 4.4 Render API Contract
- Added render job endpoint:
  - `src/app/api/render/jobs/route.ts`
- Behavior:
  - Accepts either:
    - full `RenderJobRequest` (already mapped composition), or
    - raw `VideoProject` (server maps to composition).
  - If `REMOTION_RENDERER_URL` is configured: forward to `${REMOTION_RENDERER_URL}/render/jobs`.
  - If not configured: accept in `dry_run` mode and return summary + synthetic job id.

## 5. Rollout Plan (Next Steps)
1. Add Remotion runtime packages and server renderer worker.
2. Implement actual composition component in renderer service.
3. Replace current player with `@remotion/player` behind feature flag.
4. Support transition presets and caption animations in mapper.
5. Link render-job status polling in UI.

## 6. FFmpeg Renderer Service (Implemented)
- Renderer endpoints are now available in `agent/main.py`:
  - `GET /render/health`
  - `POST /render/jobs`
  - `GET /render/jobs`
  - `GET /render/jobs/{job_id}`
- Runtime behavior:
  - Receives composition payload (render layers/audio tracks)
  - Builds ffmpeg `filter_complex` graph for timeline composition
  - Renders to local output directory (default: `agent/renders`)
  - Attempts upload to R2 if configured; otherwise keeps local file path
  - Tracks job state in-memory (`queued` / `running` / `completed` / `failed`)
- To connect frontend submit flow:
  - Set `REMOTION_RENDERER_URL` to your agent backend URL (example: `http://localhost:8123`)
  - Next route `/api/render/jobs` forwards requests to `${REMOTION_RENDERER_URL}/render/jobs`

## 7. Environment Variables
- `REMOTION_RENDERER_URL` (optional in this iteration):
  - Example: `https://render.example.com`
  - If absent, `/api/render/jobs` runs in dry-run mode.
- `RENDER_OUTPUT_DIR` (optional):
  - Local output directory for ffmpeg renders.
- `RENDER_FFMPEG_PRESET` / `RENDER_FFMPEG_CRF` (optional):
  - ffmpeg quality/speed controls.

## 8. Compatibility and Risk
- Existing editing behavior remains unchanged.
- Existing backend generation workflow remains unchanged.
- New flow is additive and backward-compatible.
- Main risk left for next iteration: actual render runtime deployment.
