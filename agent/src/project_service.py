"""
ProjectService — encapsulates the full project lifecycle for a
form-driven video generation workflow, replacing the LangGraph
chat-driven flow with direct async function calls.

Usage:
    svc = ProjectService()
    project = await svc.create_project("product-ad", {...})
    storyboard = await svc.generate_storyboard(project["run_id"])
    storyboard = await svc.generate_images(project["run_id"])
    tasks = await svc.submit_videos(project["run_id"])
    status = await svc.get_status(project["run_id"])
    result = await svc.render_final(project["run_id"])
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from supabase import create_client, Client

from src.agent_skills import plan_storyboard_impl
from src.creative_agent import (
    TEMPLATE_CONFIG,
    NARRATIVE_STRUCTURES,
    get_narrative_for_template,
    get_pipeline_hint_for_template,
    STYLE_OPTIONS,
    VIDEO_TYPES,
)
from src.r2 import upload_url_to_r2

logger = logging.getLogger("project_service")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _is_uuid(val: Any) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _normalise_orientation(raw: Optional[str]) -> str:
    """Convert user-facing orientation label to internal enum."""
    if not raw or not isinstance(raw, str):
        return "landscape"
    lower = raw.lower()
    if "竖" in raw or "vertical" in lower or "portrait" in lower:
        return "portrait"
    return "landscape"


# ---------------------------------------------------------------------------
# ProjectService
# ---------------------------------------------------------------------------

class ProjectService:
    """Stateless service — every public method receives a ``run_id`` and
    performs the corresponding lifecycle step against Supabase."""

    def __init__(self, supabase_client: Optional[Client] = None):
        if supabase_client is not None:
            self._sb = supabase_client
        else:
            sb_url = os.getenv("SUPABASE_URL")
            sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
            if not sb_url or not sb_key:
                raise RuntimeError(
                    "Missing Supabase credentials. "
                    "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars."
                )
            self._sb = create_client(sb_url, sb_key)

    # ── helpers ──────────────────────────────────────────────────────────

    def _load_project(self, run_id: str) -> Dict[str, Any]:
        """Load a single project row from autoviralvid_jobs.

        Merges the ``_meta`` block stored inside ``storyboards`` JSONB back
        into the top-level dict so downstream code can use ``project["theme"]``
        etc. transparently — regardless of whether the columns exist in the DB.
        """
        res = (
            self._sb.table("autoviralvid_jobs")
            .select("*")
            .eq("run_id", run_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise LookupError(f"Project not found: run_id={run_id}")
        row = res.data[0]

        # Inflate _meta from storyboards JSONB
        storyboards_raw = row.get("storyboards")
        if storyboards_raw:
            sb_data = json.loads(storyboards_raw) if isinstance(storyboards_raw, str) else storyboards_raw
            if isinstance(sb_data, dict) and "_meta" in sb_data:
                for k, v in sb_data["_meta"].items():
                    if k not in row or row[k] is None:
                        row[k] = v
        return row

    # Columns that actually exist in the original autoviralvid_jobs table
    _DB_COLUMNS = frozenset({
        "run_id", "slogan", "cover_url", "video_url", "status",
        "share_slug", "user_id", "storyboards", "total_duration",
        "styles", "image_control", "created_at", "updated_at",
    })

    def _update_project(self, run_id: str, updates: Dict[str, Any]) -> None:
        """Update project row. Fields not in the original schema are merged
        into the ``storyboards`` JSONB ``_meta`` block."""
        updates["updated_at"] = _utcnow_iso()

        # Split into DB-safe columns vs meta
        db_updates: Dict[str, Any] = {}
        meta_updates: Dict[str, Any] = {}

        for k, v in updates.items():
            if k in self._DB_COLUMNS:
                db_updates[k] = v
            else:
                meta_updates[k] = v

        # If there are meta updates, merge them into storyboards._meta
        if meta_updates:
            project = self._load_project(run_id)
            sb_raw = project.get("storyboards")
            sb_data = json.loads(sb_raw) if isinstance(sb_raw, str) and sb_raw else (sb_raw if isinstance(sb_raw, dict) else {"_meta": {}, "scenes": []})
            if not isinstance(sb_data, dict):
                sb_data = {"_meta": {}, "scenes": []}
            meta = sb_data.setdefault("_meta", {})
            meta.update(meta_updates)
            db_updates["storyboards"] = json.dumps(sb_data, ensure_ascii=False)

        if db_updates:
            self._sb.table("autoviralvid_jobs").update(db_updates).eq("run_id", run_id).execute()

    async def _resolve_pipeline(
        self,
        pipeline_hint: Optional[str],
        orientation: str = "landscape",
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Resolve pipeline → (pipeline_name, t2i_skill_name, i2v_skill_name).

        Priority:
        1. ``pipeline_hint`` from template config
        2. Automatic selection via SkillSelector scoring
        """
        # Priority 1: template hint
        if pipeline_hint:
            try:
                from src.skills.registry import get_skills_registry

                registry = await get_skills_registry()
                hinted = registry.get_pipeline(pipeline_hint)
                if hinted and hinted.is_enabled:
                    logger.info(
                        f"[PIPELINE] Using hint: {hinted.name} "
                        f"(t2i={hinted.t2i_skill_name}, i2v={hinted.i2v_skill_name})"
                    )
                    return hinted.name, hinted.t2i_skill_name, hinted.i2v_skill_name
                logger.info(f"[PIPELINE] Hint '{pipeline_hint}' unavailable, falling back")
            except Exception as exc:
                logger.warning(f"[PIPELINE] Hint resolution error: {exc}")

        # Priority 2: auto-select
        try:
            from src.skills import get_skill_selector

            selector = await get_skill_selector()
            pipelines = await selector.select_pipeline_with_fallback(
                requirements={
                    "duration": 10,
                    "requires_image": True,
                    "orientation": orientation,
                },
                max_fallbacks=3,
            )
            if pipelines:
                p = pipelines[0]
                logger.info(
                    f"[PIPELINE] Auto-resolved: {p.name} "
                    f"(t2i={p.t2i_skill_name}, i2v={p.i2v_skill_name})"
                )
                return p.name, p.t2i_skill_name, p.i2v_skill_name
        except Exception as exc:
            logger.warning(f"[PIPELINE] Auto-resolution error: {exc}")

        return None, None, None

    # ── 1. create_project ────────────────────────────────────────────────

    async def create_project(
        self,
        template_id: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new project row in ``autoviralvid_jobs``.

        Returns the inserted project dict (including ``run_id``).
        """
        try:
            run_id = _new_id()

            tpl_cfg = TEMPLATE_CONFIG.get(template_id, TEMPLATE_CONFIG.get("empty", {}))
            narrative_key = tpl_cfg.get("narrative", "product_showcase")
            pipeline_hint = tpl_cfg.get("pipeline_hint")
            video_type = params.get("video_type") or tpl_cfg.get("video_type", "自定义视频")

            narrative_structure = NARRATIVE_STRUCTURES.get(
                narrative_key, NARRATIVE_STRUCTURES.get("product_showcase")
            )

            now = _utcnow_iso()

            # Build extended metadata — stored inside `storyboards` JSONB
            # because the original DB schema only has a few TEXT columns.
            # The `storyboards` field will hold a JSON object with both
            # storyboard data (scenes) and project metadata (_meta).
            meta: Dict[str, Any] = {
                "template_id": template_id,
                "theme": params.get("theme", ""),
                "style": params.get("style", ""),
                "duration": params.get("duration", 30),
                "orientation": params.get("orientation", "横屏"),
                "product_image_url": params.get("product_image_url", ""),
                "video_type": video_type,
                "pipeline_hint": pipeline_hint,
                "narrative_key": narrative_key,
                "narrative_structure": narrative_structure,
            }

            # Digital human specific params
            if params.get("audio_url"):
                meta["audio_url"] = params["audio_url"]
            if params.get("voice_mode") is not None:
                meta["voice_mode"] = params["voice_mode"]
            if params.get("voice_text"):
                meta["voice_text"] = params["voice_text"]
            if params.get("motion_prompt"):
                meta["motion_prompt"] = params["motion_prompt"]

            # DB row — only use columns that exist in the original schema
            db_row = {
                "run_id": run_id,
                "slogan": params.get("theme", "")[:200],
                "status": "created",
                "total_duration": int(params.get("duration", 30)),
                "styles": params.get("style", ""),
                "image_control": params.get("product_image_url", ""),
                "storyboards": json.dumps({"_meta": meta, "scenes": []}, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            }

            self._sb.table("autoviralvid_jobs").insert(db_row).execute()
            logger.info(f"[create_project] Created project run_id={run_id}, template={template_id}")

            # Return full project info (superset of DB row for API response)
            project = {**db_row, **meta, "run_id": run_id}
            return project
        except LookupError:
            raise
        except Exception as exc:
            logger.exception(f"[create_project] Failed: {exc}")
            return {"error": str(exc)}

    # ── 2. generate_storyboard ───────────────────────────────────────────

    async def generate_storyboard(self, run_id: str) -> Dict[str, Any]:
        """Generate a storyboard for an existing project and persist it."""
        try:
            project = self._load_project(run_id)

            theme = project.get("theme", "")
            style = project.get("style", "")
            duration = float(project.get("duration", 30))
            num_clips = max(int(duration / 10), 3)

            # Build collected_info from project row
            collected_info: Dict[str, Any] = {
                "theme": theme,
                "style": style,
                "duration": duration,
                "video_type": project.get("video_type", ""),
                "orientation": project.get("orientation", "横屏"),
                "product_image": project.get("product_image_url", ""),
                "template_id": project.get("template_id"),
                "pipeline_hint": project.get("pipeline_hint"),
            }

            # Resolve narrative structure
            narrative_key = project.get("narrative_key", "product_showcase")
            narrative_structure = NARRATIVE_STRUCTURES.get(
                narrative_key, NARRATIVE_STRUCTURES.get("product_showcase")
            )

            logger.info(
                f"[generate_storyboard] run_id={run_id}, theme={theme}, "
                f"narrative={narrative_key}, clips={num_clips}"
            )

            styles_list = [style] if isinstance(style, str) and style else []

            storyboard_json = await plan_storyboard_impl(
                goal=theme,
                styles=styles_list,
                total_duration=duration,
                num_clips=num_clips,
                run_id=run_id,
                collected_info=collected_info,
                narrative_structure=narrative_structure,
            )

            storyboard = json.loads(storyboard_json)

            # Persist storyboard — preserve _meta block from original storyboards
            sb_raw = project.get("storyboards")
            sb_existing = json.loads(sb_raw) if isinstance(sb_raw, str) and sb_raw else (sb_raw if isinstance(sb_raw, dict) else {})
            meta_block = sb_existing.get("_meta", {}) if isinstance(sb_existing, dict) else {}
            storyboard["_meta"] = meta_block

            self._sb.table("autoviralvid_jobs").update({
                "storyboards": json.dumps(storyboard, ensure_ascii=False),
                "status": "storyboard_ready",
                "updated_at": _utcnow_iso(),
            }).eq("run_id", run_id).execute()

            logger.info(
                f"[generate_storyboard] Saved storyboard with "
                f"{len(storyboard.get('scenes', []))} scenes"
            )
            return storyboard
        except LookupError:
            raise
        except Exception as exc:
            logger.exception(f"[generate_storyboard] Failed: {exc}")
            return {"error": str(exc)}

    # ── 3. generate_images ───────────────────────────────────────────────

    async def generate_images(self, run_id: str) -> Dict[str, Any]:
        """Generate images for every scene in the storyboard."""
        try:
            project = self._load_project(run_id)

            storyboard_raw = project.get("storyboards")
            if not storyboard_raw:
                return {"error": "No storyboard found. Call generate_storyboard first."}
            storyboard = json.loads(storyboard_raw) if isinstance(storyboard_raw, str) else storyboard_raw
            scenes = storyboard.get("scenes", [])

            product_image_url = project.get("product_image_url", "")
            pipeline_hint = project.get("pipeline_hint")
            orientation = _normalise_orientation(project.get("orientation"))

            # Resolve pipeline
            pipeline_name, t2i_skill, i2v_skill = await self._resolve_pipeline(
                pipeline_hint, orientation
            )
            logger.info(
                f"[generate_images] run_id={run_id}, pipeline={pipeline_name}, "
                f"scenes={len(scenes)}"
            )

            # ── PATH A: qwen_product batch T2I ──
            if pipeline_name == "qwen_product":
                collected_info = {
                    "topic": project.get("theme", "产品展示"),
                    "style": project.get("style", ""),
                }
                batch_prompt = (
                    f"这是一部{collected_info['topic']}广告宣传片，参考图片，"
                    f"帮我生成{max(len(scenes), 6)}张产品广告宣传片分镜头，"
                    f"不同运镜和角度，不同的视角和景别。"
                )
                if collected_info["style"]:
                    batch_prompt += f" 风格: {collected_info['style']}"

                from src.langgraph_workflow import _qwen_product_batch_t2i

                image_urls, descriptions = await _qwen_product_batch_t2i(
                    product_image_url=product_image_url,
                    prompt=batch_prompt,
                )

                if not image_urls:
                    return {"error": "Batch T2I returned no images."}

                # Rebuild scenes from batch output
                new_scenes = []
                for idx, img_url in enumerate(image_urls):
                    desc = descriptions[idx] if idx < len(descriptions) else f"产品展示场景 {idx + 1}"
                    new_scenes.append({
                        "scene_idx": idx + 1,
                        "narration": desc,
                        "keyframes": {"in": img_url},
                        "visual_status": "success",
                    })
                storyboard["scenes"] = new_scenes
                storyboard["_batch_descriptions"] = descriptions

            # ── PATH B: per-scene provider (sora2 / legacy) ──
            else:
                from src.providers import get_image_provider

                ip = get_image_provider()
                for i, scene in enumerate(scenes):
                    if scene.get("keyframes", {}).get("in"):
                        continue  # already has an image
                    desc = scene.get("narration") or scene.get("desc", "")
                    try:
                        result = await ip.generate_scene(
                            image_url=product_image_url, text=desc
                        )
                        img_url = result.get("image_url") if isinstance(result, dict) else result
                        if img_url:
                            scene.setdefault("keyframes", {})["in"] = img_url
                            scene["visual_status"] = "success"
                        else:
                            scene["visual_status"] = "failed"
                            scene["visual_error"] = "No image URL returned"
                    except Exception as exc:
                        scene["visual_status"] = "failed"
                        scene["visual_error"] = str(exc)
                        logger.warning(f"[generate_images] Scene {i + 1} failed: {exc}")

            # Save pipeline + updated storyboard — preserve _meta
            meta_block = storyboard.get("_meta", {}) if isinstance(storyboard, dict) else {}
            meta_block.update({
                "pipeline_name": pipeline_name,
                "t2i_skill": t2i_skill,
                "i2v_skill": i2v_skill,
            })
            storyboard["_meta"] = meta_block

            self._sb.table("autoviralvid_jobs").update({
                "storyboards": json.dumps(storyboard, ensure_ascii=False),
                "status": "images_ready",
                "updated_at": _utcnow_iso(),
            }).eq("run_id", run_id).execute()

            logger.info(
                f"[generate_images] Done. "
                f"{sum(1 for s in storyboard.get('scenes', []) if s.get('visual_status') == 'success')} "
                f"succeeded out of {len(storyboard.get('scenes', []))} scenes"
            )
            return storyboard
        except LookupError:
            raise
        except Exception as exc:
            logger.exception(f"[generate_images] Failed: {exc}")
            return {"error": str(exc)}

    # ── 4. submit_videos ─────────────────────────────────────────────────

    async def submit_videos(self, run_id: str) -> List[Dict[str, Any]]:
        """Submit video generation tasks for every scene / frame pair."""
        try:
            project = self._load_project(run_id)

            storyboard_raw = project.get("storyboards")
            if not storyboard_raw:
                return [{"error": "No storyboard found."}]
            storyboard = json.loads(storyboard_raw) if isinstance(storyboard_raw, str) else storyboard_raw
            scenes = storyboard.get("scenes", [])

            pipeline_name = project.get("pipeline_name") or project.get("pipeline_hint")
            i2v_skill = project.get("i2v_skill")
            orientation = _normalise_orientation(project.get("orientation"))

            # If pipeline info wasn't stored yet, resolve now
            if not pipeline_name:
                pipeline_name, _, i2v_skill = await self._resolve_pipeline(
                    project.get("pipeline_hint"), orientation
                )

            logger.info(
                f"[submit_videos] run_id={run_id}, pipeline={pipeline_name}, "
                f"scenes={len(scenes)}"
            )

            # ── Build task list ──
            video_tasks: List[Dict[str, Any]] = []

            if pipeline_name == "qwen_product" and len(scenes) >= 2:
                # N-1 first/last frame pairs
                descriptions = storyboard.get("_batch_descriptions", [])
                for i in range(len(scenes) - 1):
                    first_url = scenes[i].get("keyframes", {}).get("in", "")
                    last_url = scenes[i + 1].get("keyframes", {}).get("in", "")
                    desc = descriptions[i] if i < len(descriptions) else scenes[i].get("narration", f"场景 {i + 1}")
                    video_tasks.append({
                        "idx": i + 1,
                        "prompt": desc,
                        "first_frame_url": first_url,
                        "last_frame_url": last_url,
                        "duration": 5,
                        "run_id": run_id,
                        "pipeline": "qwen_product",
                        "orientation": orientation,
                    })
            else:
                # 1 task per scene (sora2 / legacy)
                for i, scene in enumerate(scenes):
                    img_url = scene.get("keyframes", {}).get("in", "")
                    video_tasks.append({
                        "idx": i + 1,
                        "prompt": scene.get("narration") or scene.get("desc", ""),
                        "image_url": img_url,
                        "duration": scene.get("duration", 10),
                        "run_id": run_id,
                        "pipeline": pipeline_name or "legacy",
                        "orientation": orientation,
                    })

            # ── Resolve skills ──
            selected_skills: List[str] = []
            i2v_skill_name: Optional[str] = None
            i2v_skill_id: Optional[str] = None
            try:
                from src.skills import get_skill_selector, get_skills_registry

                selector = await get_skill_selector()
                pipelines = await selector.select_pipeline_with_fallback(
                    requirements={
                        "duration": 10,
                        "requires_image": True,
                        "orientation": orientation,
                    },
                    max_fallbacks=3,
                )
                if pipelines:
                    selected_skills = [
                        p.i2v_skill_name for p in pipelines if p.i2v_skill_name
                    ]
                    if selected_skills:
                        i2v_skill_name = selected_skills[0]
                registry = await get_skills_registry()
                if i2v_skill_name and registry:
                    _skill = registry.get_skill(i2v_skill_name)
                    if _skill:
                        i2v_skill_id = _skill.id
            except Exception as exc:
                logger.warning(f"[submit_videos] Skills module unavailable: {exc}")

            # ── Enqueue all tasks (Worker will submit to RunningHub) ──
            results: List[Dict[str, Any]] = []

            logger.info(
                f"[submit_videos] Enqueuing {len(video_tasks)} tasks "
                f"(Worker will submit with max_concurrent limit)"
            )

            for task in video_tasks:
                idx = task.get("idx", 0)
                exec_params: Dict[str, Any] = {
                    "prompt": task.get("prompt", ""),
                    "image_url": task.get("image_url", ""),
                    "first_frame_url": task.get("first_frame_url", ""),
                    "last_frame_url": task.get("last_frame_url", ""),
                    "duration": task.get("duration", 10),
                    "pipeline": task.get("pipeline", pipeline_name or "legacy"),
                    "orientation": orientation,
                    "selected_skills": selected_skills,
                }

                task_record = {
                    "run_id": run_id,
                    "clip_idx": idx,
                    "prompt": task.get("prompt", ""),
                    "ref_img": task.get("image_url") or task.get("first_frame_url", ""),
                    "duration": task.get("duration", 10),
                    "status": "queued",
                    "skill_name": i2v_skill_name,
                    "skill_id": i2v_skill_id,
                    "exec_params": json.dumps(exec_params),
                    "created_at": _utcnow_iso(),
                    "updated_at": _utcnow_iso(),
                }
                self._sb.table("autoviralvid_video_tasks").insert(task_record).execute()

                results.append({
                    "task_idx": idx,
                    "status": "queued",
                    "skill_name": i2v_skill_name,
                })

                logger.info(
                    f"[submit_videos] Enqueued task idx={idx}: "
                    f"pipeline={exec_params['pipeline']}"
                )

            self._update_project(run_id, {"status": "queued"})

            logger.info(
                f"[submit_videos] All {len(results)} tasks enqueued. "
                f"Worker will auto-submit respecting concurrency limit."
            )
            return results
        except LookupError:
            raise
        except Exception as exc:
            logger.exception(f"[submit_videos] Failed: {exc}")
            return [{"error": str(exc)}]

    # ── 4b. submit_digital_human ─────────────────────────────────────────

    async def submit_digital_human(self, run_id: str) -> List[Dict[str, Any]]:
        """Submit digital human video generation task(s).

        Digital human flow skips storyboard/image generation — the user directly
        provides a person image and audio. For short audio (<= 45s), a single
        task is created. For long audio (up to 30 min), the audio is
        automatically split into segments at silence points, with each segment
        submitted as an independent RunningHub task. All segments are later
        stitched into a single final video.
        """
        try:
            project = self._load_project(run_id)

            # _load_project inflates _meta from storyboards JSONB
            person_image_url = project.get("product_image_url") or project.get("image_control", "")
            if not person_image_url:
                return [{"error": "数字人形象图片为必填项 (product_image_url)"}]

            audio_url = project.get("audio_url", "")
            if not audio_url:
                return [{"error": "数字人音频文件为必填项 (audio_url)"}]

            voice_mode = int(project.get("voice_mode", 0))
            voice_text = project.get("voice_text", "")
            motion_prompt = project.get("motion_prompt", "模特正在做产品展示，进行电商直播带货")

            # If voice clone mode (1), voice_text is required
            if voice_mode == 1 and not voice_text:
                return [{"error": "声音克隆模式需要提供合成文本 (voice_text)"}]

            pipeline_name = "digital_human"
            i2v_skill = "runninghub_digital_human_i2v"

            logger.info(
                f"[submit_digital_human] run_id={run_id}, "
                f"voice_mode={voice_mode}, motion='{motion_prompt[:40]}...'"
            )

            # ── Determine whether to split audio ──
            from src.audio_splitter import (
                get_audio_duration,
                split_audio,
                MAX_SINGLE_SEGMENT_SECONDS,
                SegmentInfo,
            )

            audio_duration = await get_audio_duration(audio_url)
            logger.info(
                f"[submit_digital_human] Audio duration: {audio_duration:.1f}s "
                f"(max single segment: {MAX_SINGLE_SEGMENT_SECONDS}s)"
            )

            if audio_duration <= MAX_SINGLE_SEGMENT_SECONDS:
                # Short audio → single segment, no splitting needed
                segments = [
                    SegmentInfo(
                        index=0,
                        url=audio_url,
                        start_ms=0,
                        end_ms=int(audio_duration * 1000),
                        duration_s=audio_duration,
                    )
                ]
            else:
                # Long audio → split at silence points
                logger.info(
                    f"[submit_digital_human] Long audio detected ({audio_duration:.1f}s), "
                    f"splitting into segments..."
                )
                segments = await split_audio(
                    url=audio_url,
                    run_id=run_id,
                    max_segment_seconds=MAX_SINGLE_SEGMENT_SECONDS,
                )
                logger.info(
                    f"[submit_digital_human] Audio split into {len(segments)} segments"
                )

            # ── Validate skill exists ──
            from src.skills import get_skills_registry

            registry = await get_skills_registry()
            skill = registry.get_skill(i2v_skill)
            if not skill:
                return [{"error": f"Skill '{i2v_skill}' not found in registry"}]

            # ── Enqueue all segments (Worker will submit to RunningHub) ──
            results: List[Dict[str, Any]] = []

            logger.info(
                f"[submit_digital_human] Enqueuing {len(segments)} segments "
                f"(Worker will submit with max_concurrent limit)"
            )

            for seg in segments:
                exec_params: Dict[str, Any] = {
                    "prompt": motion_prompt,
                    "image_url": person_image_url,
                    "audio_url": seg.url,
                    "voice_mode": voice_mode,
                    "duration": int(seg.duration_s),
                }
                if voice_mode == 1 and voice_text:
                    exec_params["voice_text"] = voice_text

                task_record = {
                    "run_id": run_id,
                    "clip_idx": seg.index,
                    "prompt": motion_prompt,
                    "ref_img": person_image_url,
                    "duration": exec_params["duration"],
                    "status": "queued",
                    "skill_name": i2v_skill,
                    "skill_id": skill.id if skill.id else None,
                    "exec_params": json.dumps(exec_params),
                    "created_at": _utcnow_iso(),
                    "updated_at": _utcnow_iso(),
                }
                self._sb.table("autoviralvid_video_tasks").insert(task_record).execute()

                results.append({
                    "task_idx": seg.index,
                    "status": "queued",
                    "skill_name": i2v_skill,
                })

                logger.info(
                    f"[submit_digital_human] Enqueued segment {seg.index}/{len(segments)-1}: "
                    f"duration={seg.duration_s:.1f}s, audio={seg.url[:60]}..."
                )

            # ── Update session tracking ──
            try:
                self._sb.table("autoviralvid_crew_sessions").upsert({
                    "run_id": run_id,
                    "expected_clips": len(segments),
                    "status": "queued",
                    "updated_at": _utcnow_iso(),
                }).execute()
            except Exception as exc:
                logger.warning(f"[submit_digital_human] Failed to upsert crew_sessions: {exc}")

            self._update_project(run_id, {
                "status": "queued",
                "pipeline_name": pipeline_name,
            })

            logger.info(
                f"[submit_digital_human] All {len(results)} segments enqueued. "
                f"Worker will auto-submit respecting concurrency limit."
            )
            return results
        except LookupError:
            raise
        except Exception as exc:
            logger.exception(f"[submit_digital_human] Failed: {exc}")
            # Update status to failed so the frontend knows
            try:
                self._update_project(run_id, {"status": "videos_failed"})
            except Exception:
                pass
            return [{"error": str(exc)}]

    # ── 5. get_status ────────────────────────────────────────────────────

    async def get_status(self, run_id: str) -> Dict[str, Any]:
        """Return aggregated status of all video tasks for a project."""
        try:
            res = (
                self._sb.table("autoviralvid_video_tasks")
                .select("*")
                .eq("run_id", run_id)
                .execute()
            )
            db_tasks = res.data or []

            total = len(db_tasks)
            succeeded = sum(1 for t in db_tasks if t.get("status") == "succeeded")
            failed = sum(1 for t in db_tasks if t.get("status") == "failed")
            pending = sum(
                1 for t in db_tasks
                if t.get("status") in ("queued", "pending", "processing", "submitted")
            )
            all_done = total > 0 and pending == 0

            return {
                "run_id": run_id,
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "pending": pending,
                "all_done": all_done,
                "tasks": sorted(db_tasks, key=lambda t: t.get("clip_idx", 0)),
            }
        except Exception as exc:
            logger.exception(f"[get_status] Failed: {exc}")
            return {"error": str(exc), "run_id": run_id}

    # ── 6. render_final ──────────────────────────────────────────────────

    async def render_final(self, run_id: str) -> Dict[str, Any]:
        """Stitch all completed video clips into one final video."""
        try:
            from src.video_stitcher import stitch_videos_for_run

            logger.info(f"[render_final] Starting stitch for run_id={run_id}")
            final_url = await stitch_videos_for_run(run_id)

            if not final_url:
                return {"error": "Stitching produced no output URL."}

            self._update_project(run_id, {
                "final_video_url": final_url,
                "status": "completed",
            })

            logger.info(f"[render_final] Final video: {final_url}")
            return {"run_id": run_id, "final_video_url": final_url}
        except Exception as exc:
            logger.exception(f"[render_final] Failed: {exc}")
            return {"error": str(exc), "run_id": run_id}

    # ── 7. create_batch ──────────────────────────────────────────────────

    async def create_batch(
        self,
        template_id: str,
        product_images: List[str],
        params: Dict[str, Any],
    ) -> List[str]:
        """Create a batch of projects, one per product image.

        Returns a list of ``run_id`` strings.
        """
        run_ids: List[str] = []
        for img_url in product_images:
            per_params = {**params, "product_image_url": img_url}
            project = await self.create_project(template_id, per_params)
            rid = project.get("run_id")
            if rid:
                run_ids.append(rid)
            else:
                logger.warning(
                    f"[create_batch] Skipped image (create_project error): "
                    f"{img_url[:80]}"
                )
        logger.info(
            f"[create_batch] Created {len(run_ids)} projects for template={template_id}"
        )
        return run_ids
