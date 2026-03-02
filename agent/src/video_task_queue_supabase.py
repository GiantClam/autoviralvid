"""
基于 Supabase 数据库的视频任务队列实现

优势：
1. 持久化：任务不会因为服务重启而丢失
2. 多实例支持：可以在多个 Railway 实例间共享队列
3. 可靠性：数据库事务保证数据一致性
4. 免费版通常足够：Supabase 免费版提供 500MB 数据库存储，对于任务队列足够

成本分析：
- Supabase 免费版：500MB 数据库存储，通常足够小到中等规模使用
- 如果已有 Supabase 账号，无需额外付费
- 如果任务量很大，可以考虑 Railway 的 PostgreSQL（按使用量付费）

使用方式：
1. 在 Supabase 中创建 video_tasks 表
2. 配置 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY
3. 替换当前的内存队列管理器
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
from supabase import create_client, Client
import json
import httpx

logger = logging.getLogger("agent_skills")


class SupabaseVideoTaskQueue:
    """
    基于 Supabase 数据库的视频任务队列

    功能：
    1. 将任务持久化到数据库
    2. 支持多实例并发处理
    3. 自动重试失败的任务（队列满的情况）
    4. 任务状态跟踪
    5. Skills metrics 更新
    """

    # Global RunningHub concurrency limit (across all templates/workflows)
    RUNNINGHUB_MAX_CONCURRENT = int(os.getenv("RUNNINGHUB_MAX_CONCURRENT", "2"))

    def __init__(self, retry_interval: Optional[float] = None, max_concurrent: Optional[int] = None):
        """
        初始化队列

        Args:
            retry_interval: 重试间隔（秒），默认从配置读取
            max_concurrent: 最大并发数，默认从配置读取
        """
        # Load from config if not provided
        try:
            from configs.settings import get_config
            config = get_config()
            self.retry_interval = retry_interval or config.video_queue.poll_interval_seconds
            self.max_concurrent = max_concurrent or config.video_queue.max_concurrent_tasks
            self.RUNNINGHUB_MAX_CONCURRENT = config.video_queue.runninghub_max_concurrent
            self._max_queue_retries = config.video_queue.max_queue_full_retries
            self._max_general_retries = config.video_queue.max_general_retries
        except ImportError:
            # Fallback to defaults if config module not available
            self.retry_interval = retry_interval or 20.0
            self.max_concurrent = max_concurrent or 1
            self._max_queue_retries = 10
            self._max_general_retries = 3
        
        # 初始化 Supabase 客户端
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            raise RuntimeError("需要配置 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY")
        
        # 先初始化 logger，因为后面可能会用到
        self.logger = logging.getLogger("agent_skills")
        
        # 创建 Supabase 客户端
        # 注意：Supabase Python 客户端可能不支持在 options 中传递 httpx.Client
        # 直接使用默认配置（Supabase 客户端内部会使用自己的 httpx 配置）
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # 后台任务
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 确保表存在
        self._ensure_table()
    
    def _ensure_table(self):
        """确保 video_tasks 表存在并包含必要的列"""
        try:
            # 尝试查询表，如果不存在会报错
            self.supabase.table("autoviralvid_video_tasks").select("id").limit(1).execute()
            self.logger.info("[SupabaseVideoTaskQueue] Table 'video_tasks' exists")
        except Exception as e:
            self.logger.warning(
                f"[SupabaseVideoTaskQueue] Table 'video_tasks' may not exist. "
                f"Please create it with the SQL in the docstring. Error: {e}"
            )

        # Ensure exec_params column exists (for queue-based submission)
        try:
            self.supabase.rpc("exec_sql", {
                "query": (
                    "ALTER TABLE autoviralvid_video_tasks "
                    "ADD COLUMN IF NOT EXISTS exec_params JSONB DEFAULT '{}'::jsonb"
                )
            }).execute()
            self.logger.info("[SupabaseVideoTaskQueue] exec_params column ensured")
        except Exception:
            # RPC may not exist; that's fine — column may already exist
            # or user needs to run the migration manually
            self.logger.debug(
                "[SupabaseVideoTaskQueue] Could not auto-add exec_params column. "
                "Run migration manually if needed: "
                "ALTER TABLE autoviralvid_video_tasks ADD COLUMN IF NOT EXISTS "
                "exec_params JSONB DEFAULT '{}'::jsonb"
            )
    
    async def add_task(
        self,
        run_id: str,
        clip_idx: int,
        prompt: str,
        ref_img: Optional[str] = None,
        duration: int = 10,
        retry_count: int = 0,
        skill_id: Optional[str] = None,
        skill_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        添加任务到队列

        Args:
            run_id: 运行 ID
            clip_idx: 镜头序号
            prompt: 提示词
            ref_img: 参考图片
            duration: 视频时长
            retry_count: 重试次数
            skill_id: 技能 ID (Skills system)
            skill_name: 技能名称 (Skills system)

        Returns:
            任务信息字典
        """
        task_data = {
            "run_id": run_id,
            "clip_idx": clip_idx,
            "prompt": prompt,
            "ref_img": ref_img or "",
            "duration": duration,
            "status": "pending",
            "retry_count": retry_count,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        # Add skill info if available
        if skill_id:
            task_data["skill_id"] = skill_id
        if skill_name:
            task_data["skill_name"] = skill_name
        
        try:
            result = self.supabase.table("autoviralvid_video_tasks").insert(task_data).execute()
            task_id = result.data[0].get("id") if result.data else None
            
            self.logger.info(
                f"[SupabaseVideoTaskQueue] Task added: run_id={run_id}, clip_idx={clip_idx}, task_id={task_id}"
            )
            
            # 启动 worker（如果还没启动）
            # 注意：worker 需要在应用启动时启动，而不是在这里
            # 这里只是确保 worker 在运行
            if not self._running:
                try:
                    # 尝试获取当前事件循环
                    loop = asyncio.get_running_loop()
                    self._running = True
                    self._worker_task = asyncio.create_task(self._worker_loop())
                    self.logger.info("[SupabaseVideoTaskQueue] Worker task created in add_task")
                except RuntimeError:
                    # 没有运行中的事件循环，worker 无法启动
                    # 这通常意味着需要在应用启动时启动 worker
                    self.logger.warning(
                        "[SupabaseVideoTaskQueue] No running event loop, worker cannot start. "
                        "Please start worker in application startup."
                    )
            
            return {
                "id": task_id,
                "run_id": run_id,
                "clip_idx": clip_idx,
                "status": "pending"
            }
        except Exception as e:
            self.logger.error(f"[SupabaseVideoTaskQueue] Failed to add task: {e}", exc_info=True)
            raise
    
    def _get_submitted_count(self) -> int:
        """Count tasks currently running on RunningHub (status='submitted')."""
        try:
            res = (
                self.supabase.table("autoviralvid_video_tasks")
                .select("id")
                .eq("status", "submitted")
                .execute()
            )
            return len(res.data) if res.data else 0
        except Exception as exc:
            self.logger.warning(f"[SupabaseVideoTaskQueue] Failed to count submitted: {exc}")
            return 0

    async def _worker_loop(self):
        """后台 worker 循环 — 全局 RunningHub 并发控制

        Enforces ``RUNNINGHUB_MAX_CONCURRENT`` (default 2) across ALL
        video templates / workflows.

        Flow per cycle
        ──────────────
        1. Fetch tasks with status in (queued, pending, submitted).
        2. **Always** poll ``submitted`` tasks (just check RunningHub status).
        3. After polling, re-count active submitted tasks.
        4. Fill available slots with ``queued`` / ``pending`` tasks (FIFO).
           ``queued`` tasks use the Skills adapter (exec_params stored in DB).
           ``pending`` tasks use the legacy video_provider path.
        """
        self.logger.info(
            f"[Worker] Started (global max_concurrent={self.RUNNINGHUB_MAX_CONCURRENT})"
        )

        consecutive_errors = 0
        max_consecutive_errors = 5

        while self._running:
            try:
                await asyncio.sleep(self.retry_interval)

                try:
                    # ── Fetch active tasks ──
                    result = None
                    for retry in range(3):
                        try:
                            result = self.supabase.table("autoviralvid_video_tasks")\
                                .select("*")\
                                .in_("status", ["queued", "pending", "submitted"])\
                                .order("created_at", desc=False)\
                                .limit(50)\
                                .execute()
                            consecutive_errors = 0
                            break
                        except (httpx.ConnectError, httpx.TimeoutException,
                                httpx.NetworkError, httpx.PoolTimeout) as e:
                            if retry < 2:
                                wait_time = (retry + 1) * 2
                                self.logger.warning(
                                    f"[Worker] Network error (attempt {retry+1}/3): {e}, "
                                    f"retrying in {wait_time}s..."
                                )
                                await asyncio.sleep(wait_time)
                            else:
                                raise

                    if result is None:
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            await asyncio.sleep(self.retry_interval * 2)
                            consecutive_errors = 0
                        continue

                    tasks = result.data if result.data else []
                    if not tasks:
                        continue

                    # ── Separate by status ──
                    submitted_tasks = [t for t in tasks if t.get("status") == "submitted"]
                    queued_tasks   = [t for t in tasks if t.get("status") == "queued"]
                    pending_tasks  = [t for t in tasks if t.get("status") == "pending"]

                    self.logger.info(
                        f"[Worker] Tasks: queued={len(queued_tasks)}, "
                        f"pending={len(pending_tasks)}, submitted={len(submitted_tasks)}, "
                        f"limit={self.RUNNINGHUB_MAX_CONCURRENT}"
                    )

                    # ── 0. Clean up stuck tasks (submitted > 30 min) ──
                    if submitted_tasks:
                        now = datetime.utcnow()
                        stuck_timeout = timedelta(minutes=30)
                        for task in submitted_tasks:
                            updated_at = task.get("updated_at") or task.get("created_at")
                            if updated_at:
                                try:
                                    ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
                                    if now - ts > stuck_timeout:
                                        retry_status = "queued" if task.get("exec_params") else "pending"
                                        self.supabase.table("autoviralvid_video_tasks").update({
                                            "status": retry_status,
                                            "provider_task_id": None,
                                            "error": "Auto-reset: task stuck for >30 min",
                                            "updated_at": now.isoformat(),
                                        }).eq("id", task["id"]).execute()
                                        self.logger.warning(
                                            f"[Worker] Stuck task {task['id']} reset to {retry_status} "
                                            f"(submitted at {updated_at})"
                                        )
                                except (ValueError, TypeError):
                                    pass

                    # ── 1. Poll submitted tasks (no concurrency cost) ──
                    if submitted_tasks:
                        await asyncio.gather(*[
                            self._poll_submitted_task(task)
                            for task in submitted_tasks
                        ], return_exceptions=True)

                    # Re-count after polling
                    submitted_count = self._get_submitted_count()
                    available_slots = max(0, self.RUNNINGHUB_MAX_CONCURRENT - submitted_count)

                    # ── 2. Submit queued/pending tasks into available slots ──
                    # queued (Skills-based) first, then pending (legacy)
                    submit_queue = queued_tasks + pending_tasks
                    if submit_queue and available_slots > 0:
                        to_submit = submit_queue[:available_slots]
                        self.logger.info(
                            f"[Worker] Submitting {len(to_submit)} tasks "
                            f"({available_slots} slots free)"
                        )
                        for task in to_submit:
                            try:
                                await self._submit_task(task)
                            except Exception as exc:
                                self.logger.error(
                                    f"[Worker] Failed to submit task {task.get('id')}: {exc}",
                                    exc_info=True,
                                )
                    elif submit_queue:
                        self.logger.info(
                            f"[Worker] {len(submit_queue)} tasks waiting, "
                            f"all {self.RUNNINGHUB_MAX_CONCURRENT} slots occupied"
                        )

                except Exception as e:
                    consecutive_errors += 1
                    etype = type(e).__name__
                    if isinstance(e, (httpx.ConnectError, httpx.TimeoutException,
                                      httpx.NetworkError, httpx.PoolTimeout)):
                        self.logger.warning(f"[Worker] Network error: {etype}: {e}")
                    else:
                        self.logger.error(f"[Worker] Error: {etype}: {e}", exc_info=True)
                    if consecutive_errors >= max_consecutive_errors:
                        await asyncio.sleep(self.retry_interval * 2)
                        consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                self.logger.error(
                    f"[Worker] Loop error: {type(e).__name__}: {e}", exc_info=True,
                )
                if consecutive_errors >= max_consecutive_errors:
                    await asyncio.sleep(self.retry_interval * 2)
                    consecutive_errors = 0
                else:
                    await asyncio.sleep(self.retry_interval)

    # ─── Task submission (queued / pending → submitted) ─────────────────

    async def _submit_task(self, task: Dict[str, Any]):
        """Submit a queued or pending task to RunningHub.

        - **queued** tasks carry ``exec_params`` JSON and ``skill_name``;
          they are submitted via the Skills adapter.
        - **pending** tasks (legacy) are submitted via ``video_provider.generate()``.
        """
        task_id = task.get("id")
        run_id = task.get("run_id")
        clip_idx = task.get("clip_idx")
        status = task.get("status")
        retry_count = task.get("retry_count", 0)

        try:
            if status == "queued":
                await self._submit_queued_task(task)
            else:
                await self._submit_pending_task(task)

            # Update project status from queued → processing (if still queued)
            try:
                self.supabase.table("autoviralvid_jobs")\
                    .update({"status": "processing", "updated_at": datetime.utcnow().isoformat()})\
                    .eq("run_id", run_id)\
                    .eq("status", "queued")\
                    .execute()
                self.supabase.table("autoviralvid_crew_sessions")\
                    .update({"status": "processing", "updated_at": datetime.utcnow().isoformat()})\
                    .eq("run_id", run_id)\
                    .eq("status", "queued")\
                    .execute()
            except Exception:
                pass  # non-critical

        except Exception as e:
            error_str = str(e)
            is_queue_full = "TASK_QUEUE_MAXED" in error_str or "421" in error_str

            if is_queue_full:
                # RunningHub 平台队列满 — 放回 queued，下个周期重试
                retry_count += 1
                new_status = "queued" if status == "queued" else "pending"
                if retry_count < self._max_queue_retries:
                    self.supabase.table("autoviralvid_video_tasks").update({
                        "status": new_status,
                        "retry_count": retry_count,
                        "error": f"RunningHub queue full (retry {retry_count})",
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", task_id).execute()
                    self.logger.warning(
                        f"[Worker] Task {task_id} RunningHub queue full, "
                        f"re-queued ({retry_count}/{self._max_queue_retries})"
                    )
                else:
                    self.supabase.table("autoviralvid_video_tasks").update({
                        "status": "failed",
                        "error": f"Max queue-full retries exceeded: {error_str}",
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", task_id).execute()
            else:
                # Generic error — retry a few times
                retry_count += 1
                new_status = "queued" if status == "queued" else "pending"
                if retry_count <= self._max_general_retries:
                    self.supabase.table("autoviralvid_video_tasks").update({
                        "status": new_status,
                        "retry_count": retry_count,
                        "error": f"Retry {retry_count}/{self._max_general_retries}: {error_str}",
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", task_id).execute()
                    self.logger.warning(
                        f"[Worker] Task {task_id} error, will retry "
                        f"({retry_count}/{self._max_general_retries}): {error_str}"
                    )
                else:
                    self.supabase.table("autoviralvid_video_tasks").update({
                        "status": "failed",
                        "error": f"Max retries exceeded: {error_str}",
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", task_id).execute()
                    self.logger.error(f"[Worker] Task {task_id} permanently failed: {error_str}")

    async def _submit_queued_task(self, task: Dict[str, Any]):
        """Submit a *queued* task via the Skills adapter.

        The task record must carry ``skill_name`` and ``exec_params`` (JSON).
        """
        task_id = task["id"]
        run_id = task.get("run_id")
        clip_idx = task.get("clip_idx", 0)
        skill_name = task.get("skill_name")

        # Parse exec_params
        raw_params = task.get("exec_params")
        if isinstance(raw_params, str):
            exec_params = json.loads(raw_params)
        elif isinstance(raw_params, dict):
            exec_params = raw_params
        else:
            exec_params = {}

        if not skill_name:
            raise RuntimeError(f"Task {task_id} has no skill_name — cannot submit")

        # Resolve skill + adapter
        from src.skills import get_skills_registry, SkillExecutionRequest

        registry = await get_skills_registry()
        skill = registry.get_skill(skill_name)
        if not skill:
            raise RuntimeError(f"Skill '{skill_name}' not found in registry")

        adapter = registry.create_adapter(skill)
        if not adapter:
            raise RuntimeError(f"Could not create adapter for skill '{skill_name}'")

        request = SkillExecutionRequest(
            skill_id=skill.id or skill_name,
            run_id=run_id,
            params=exec_params,
            clip_idx=clip_idx,
        )

        self.logger.info(
            f"[Worker] Submitting queued task {task_id}: "
            f"skill={skill_name}, clip={clip_idx}, run={run_id}"
        )

        exec_result = await adapter.execute(request)

        # Update DB
        new_status = "submitted" if exec_result.status in ("submitted", "pending") else exec_result.status
        self.supabase.table("autoviralvid_video_tasks").update({
            "status": new_status,
            "provider_task_id": exec_result.task_id,
            "error": exec_result.error,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", task_id).execute()

        self.logger.info(
            f"[Worker] Task {task_id} → {new_status} "
            f"(provider_task_id={exec_result.task_id})"
        )

    async def _submit_pending_task(self, task: Dict[str, Any]):
        """Submit a *pending* (legacy) task via video_provider.generate()."""
        task_id = task["id"]
        run_id = task.get("run_id")
        clip_idx = task.get("clip_idx")
        prompt = task.get("prompt", "")
        ref_img = task.get("ref_img") or ""
        duration = task.get("duration", 10)

        # Mark as processing
        self.supabase.table("autoviralvid_video_tasks").update({
            "status": "processing",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", task_id).execute()

        from src.providers import get_video_provider
        video_provider = get_video_provider()

        result = await video_provider.generate(
            prompt=prompt,
            image_url=ref_img if ref_img else None,
            duration=duration,
            async_mode=True,
        )

        if isinstance(result, dict) and result.get("pending"):
            provider_task_id = result.get("task_id")
            self.supabase.table("autoviralvid_video_tasks").update({
                "status": "submitted",
                "provider_task_id": provider_task_id,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", task_id).execute()
            self.logger.info(f"[Worker] Task {task_id} submitted: {provider_task_id}")
        else:
            # Synchronous result
            video_url = result.get("video_url") if isinstance(result, dict) else str(result)
            if video_url:
                try:
                    from r2 import upload_url_to_r2
                except ImportError:
                    upload_url_to_r2 = None
                cdn_url = video_url
                if upload_url_to_r2:
                    cdn_url = await upload_url_to_r2(video_url, f"{run_id}_clip{clip_idx}.mp4")
                self.supabase.table("autoviralvid_video_tasks").update({
                    "status": "succeeded",
                    "video_url": cdn_url,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", task_id).execute()
                self.logger.info(f"[Worker] Task {task_id} completed: {cdn_url}")
                asyncio.create_task(self.check_and_trigger_stitch(run_id))

    # ─── Poll submitted tasks ──────────────────────────────────────────

    async def _poll_submitted_task(self, task: Dict[str, Any]):
        """Poll a submitted task's RunningHub status."""
        task_id = task.get("id")
        provider_task_id = task.get("provider_task_id")
        run_id = task.get("run_id")
        clip_idx = task.get("clip_idx")
        retry_count = task.get("retry_count", 0)

        if not provider_task_id:
            self.logger.warning(
                f"[Worker] Task {task_id} submitted but no provider_task_id, marking failed"
            )
            self.supabase.table("autoviralvid_video_tasks").update({
                "status": "failed",
                "error": "No provider_task_id",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", task_id).execute()
            return

        await self._poll_runninghub_task(
            task_id, provider_task_id, run_id, clip_idx, retry_count, task
        )
    
    async def _poll_runninghub_task(self, task_id: str, provider_task_id: str, run_id: str, clip_idx: int, retry_count: int = 0, task: Optional[Dict[str, Any]] = None):
        """
        Poll provider task status. Supports MultiGenerator fallback routing.
        
        The provider_task_id may be encoded as "index:actual_id" by MultiGenerator,
        which allows routing to the correct provider (RunningHub, Liblib, TokenEngine).
        """
        try:
            # Use MultiGenerator via get_video_provider for proper provider routing
            from src.providers import get_video_provider
            provider = get_video_provider()
            
            self.logger.info(
                f"[SupabaseVideoTaskQueue] Polling provider task: "
                f"task_id={task_id}, provider_task_id={provider_task_id}, run_id={run_id}, clip_idx={clip_idx}"
            )
            
            # MultiGenerator.get_status handles "index:actual_id" decoding internally
            result = await provider.get_status(provider_task_id)
            
            # Handle both dict and string status returns
            if isinstance(result, dict):
                status = result.get("status", "")
                video_url = result.get("video_url") or result.get("url")
            else:
                status = str(result)
                video_url = None
            
            status_upper = status.upper() if status else ""
            self.logger.info(
                f"[SupabaseVideoTaskQueue] Provider task {provider_task_id} status: {status} (normalized: {status_upper})"
            )
            
            # 检查多种成功状态值
            if status_upper in {"SUCCESS", "SUCCEEDED", "FINISHED", "DONE", "COMPLETED"}:
                # Use video_url from result if available, otherwise try to get outputs
                if not video_url and isinstance(result, dict):
                    # Try to extract from nested output arrays
                    outputs = result.get("outputs") or result.get("data") or []
                    for item in (outputs if isinstance(outputs, list) else [outputs]):
                        if isinstance(item, dict):
                            url = (
                                item.get("fileUrl") 
                                or item.get("url") 
                                or item.get("video_url")
                                or item.get("ossUrl") 
                                or item.get("downloadUrl")
                            )
                            if url and isinstance(url, str) and ("mp4" in url.lower() or url.endswith(".mp4")):
                                video_url = url
                                break
                
                if video_url:
                    # 上传到 R2（若不可用则使用原始 URL）
                    try:
                        from r2 import upload_url_to_r2
                    except ImportError:
                        try:
                            from r2 import upload_url_to_r2
                        except ImportError:
                            upload_url_to_r2 = None
                    cdn_url = video_url
                    if upload_url_to_r2:
                        cdn_url = await upload_url_to_r2(video_url, f"{run_id}_task{clip_idx}.mp4")
                    else:
                        self.logger.warning("[SupabaseVideoTaskQueue] R2 upload not available, using original URL")
                    
                    # 更新数据库
                    self.supabase.table("autoviralvid_video_tasks")\
                        .update({
                            "status": "succeeded",
                            "video_url": cdn_url,
                            "updated_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", task_id)\
                        .execute()
                    
                    self.logger.info(
                        f"[SupabaseVideoTaskQueue] Task {task_id} completed: {cdn_url}"
                    )

                    # Update skill metrics if skill was used
                    if task:
                        await self._update_skill_metrics_on_success(task_id, task)

                    # 检查是否所有任务完成，如果完成则触发拼接回调
                    try:
                        # 立即检查并触发拼接（不阻塞，使用 create_task）
                        asyncio.create_task(
                            self.check_and_trigger_stitch(run_id)
                        )
                        self.logger.info(
                            f"[SupabaseVideoTaskQueue] Triggered stitch check for run_id={run_id}"
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"[SupabaseVideoTaskQueue] Failed to trigger stitch callback: {e}",
                            exc_info=True
                        )
                else:
                    self.logger.warning(
                        f"[SupabaseVideoTaskQueue] Task {task_id} succeeded but no video URL found"
                    )
            elif status_upper in {"FAILED", "ERROR", "FAILURE"}:
                # 任务失败：自动重试逻辑
                max_retries = 3
                if retry_count < max_retries:
                    new_retry = retry_count + 1
                    self.logger.warning(
                        f"[Worker] Provider task {provider_task_id} failed, "
                        f"retrying ({new_retry}/{max_retries})..."
                    )
                    # If task has exec_params (Skills-based), re-queue as "queued";
                    # otherwise fall back to "pending" (legacy path).
                    has_exec_params = bool(task and task.get("exec_params"))
                    retry_status = "queued" if has_exec_params else "pending"
                    
                    self.supabase.table("autoviralvid_video_tasks")\
                        .update({
                            "status": retry_status,
                            "provider_task_id": None,   # 清除旧的 task id，强制重新提交
                            "retry_count": new_retry,
                            "error": f"Previous attempt failed: {status}",
                            "updated_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", task_id)\
                        .execute()
                else:
                    # 超过最大重试次数，标记失败
                    self.supabase.table("autoviralvid_video_tasks")\
                        .update({
                            "status": "failed",
                            "error": f"RunningHub task failed after {max_retries} attempts: {status}",
                            "updated_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", task_id)\
                        .execute()
                    
                    self.logger.error(
                        f"[Worker] Task {task_id} permanently failed: {status}"
                    )
            # 如果状态是 PENDING, RUNNING, QUEUED，不做任何操作，等待下次轮询
        except Exception as e:
            self.logger.warning(
                f"[SupabaseVideoTaskQueue] Error polling provider task {provider_task_id}: {e}"
            )
            # 不更新状态，等待下次轮询
    
    async def get_pending_tasks(self, run_id: str) -> List[Dict[str, Any]]:
        """获取指定 run_id 的待处理任务（包括 queued, pending, processing, submitted）"""
        try:
            result = self.supabase.table("autoviralvid_video_tasks")\
                .select("*")\
                .eq("run_id", run_id)\
                .in_("status", ["queued", "pending", "processing", "submitted"])\
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            self.logger.error(f"[SupabaseVideoTaskQueue] Failed to get pending tasks: {e}", exc_info=True)
            return []
    
    async def get_completed_tasks(self, run_id: str) -> List[Dict[str, Any]]:
        """获取指定 run_id 的已完成任务"""
        try:
            result = self.supabase.table("autoviralvid_video_tasks")\
                .select("*")\
                .eq("run_id", run_id)\
                .eq("status", "succeeded")\
                .execute()
            
            return result.data if result.data else []
        except Exception as e:
            self.logger.error(f"[SupabaseVideoTaskQueue] Failed to get completed tasks: {e}", exc_info=True)
            return []
    
    async def poll_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        轮询任务状态（用于检查 submitted 状态的任务是否完成）
        
        Args:
            task_id: Supabase 任务 ID 或 RunningHub task_id
            
        Returns:
            任务信息，如果完成则包含 video_url
        """
        try:
            # 先尝试用 Supabase task_id 查询
            result = self.supabase.table("autoviralvid_video_tasks")\
                .select("*")\
                .eq("id", task_id)\
                .single()\
                .execute()
            
            task = result.data if result.data else None
            
            if not task:
                # 尝试用 provider_task_id 查询
                result = self.supabase.table("autoviralvid_video_tasks")\
                    .select("*")\
                    .eq("provider_task_id", task_id)\
                    .single()\
                    .execute()
                
                task = result.data if result.data else None
            
            if not task:
                return None
            
            # 如果状态是 submitted，轮询 RunningHub 状态
            if task.get("status") == "submitted":
                provider_task_id = task.get("provider_task_id")
                if provider_task_id:
                    from src.runninghub_client import RunningHubClient
                    client = RunningHubClient()
                    
                    status = await client.get_status(provider_task_id)
                    
                    if status == "SUCCESS":
                        # 获取视频 URL
                        outputs = await client.get_outputs(provider_task_id)
                        for item in outputs:
                            url = (
                                item.get("fileUrl") 
                                or item.get("url") 
                                or item.get("ossUrl") 
                                or item.get("downloadUrl")
                                or (item.get("value") if isinstance(item.get("value"), str) else None)
                            )
                            if url and isinstance(url, str) and ("mp4" in url.lower() or url.lower().endswith(".mp4")):
                                # 上传到 R2
                                try:
                                    from src.r2 import upload_url_to_r2
                                except ImportError:
                                    try:
                                        from src.r2 import upload_url_to_r2
                                    except ImportError:
                                        upload_url_to_r2 = None
                                cdn_url = url
                                if upload_url_to_r2:
                                    cdn_url = await upload_url_to_r2(url, f"{task.get('run_id')}_clip{task.get('clip_idx')}.mp4")
                                else:
                                    self.logger.warning("[SupabaseVideoTaskQueue] R2 upload not available, using original URL")
                                
                                # 更新数据库
                                self.supabase.table("autoviralvid_video_tasks")\
                                    .update({
                                        "status": "succeeded",
                                        "video_url": cdn_url,
                                        "updated_at": datetime.utcnow().isoformat()
                                    })\
                                    .eq("id", task.get("id"))\
                                    .execute()
                                
                                task["status"] = "succeeded"
                                task["video_url"] = cdn_url
                                return task
                    
                    elif status in {"FAILED", "ERROR"}:
                        # 任务失败
                        self.supabase.table("autoviralvid_video_tasks")\
                            .update({
                                "status": "failed",
                                "error": f"RunningHub task failed: {status}",
                                "updated_at": datetime.utcnow().isoformat()
                            })\
                            .eq("id", task.get("id"))\
                            .execute()
                        
                        task["status"] = "failed"
                        return task
            
            return task
        except Exception as e:
            self.logger.error(f"[SupabaseVideoTaskQueue] Error in poll_task_status: {e}")
            return None
        
    async def _update_skill_metrics_on_success(self, task_id: str, task: Dict[str, Any]):
        """Update skill metrics when a task completes successfully."""
        try:
            # Get skill info from task
            skill_name = task.get("skill_name")
            if not skill_name:
                return

            # Get task timing info
            created_at = task.get("created_at")
            if created_at:
                try:
                    if isinstance(created_at, str):
                        from datetime import datetime as dt
                        start_time = dt.fromisoformat(created_at.replace("Z", "+00:00"))
                    else:
                        start_time = created_at
                    duration_ms = int((datetime.utcnow() - start_time.replace(tzinfo=None)).total_seconds() * 1000)
                except Exception:
                    duration_ms = None
            else:
                duration_ms = None

            # Try to update skill metrics via SkillsRegistry
            try:
                from src.skills import get_skills_registry
                registry = await get_skills_registry()
                skill = registry.get_skill(skill_name)

                if skill:
                    # Update metrics incrementally
                    metrics = skill.metrics
                    metrics.total_executions += 1
                    metrics.success_count += 1

                    # Update reliability score (rolling average)
                    metrics.reliability_score = metrics.success_count / metrics.total_executions

                    # Update average latency (exponential moving average)
                    if duration_ms:
                        alpha = 0.2  # Smoothing factor
                        metrics.avg_latency_ms = int(
                            alpha * duration_ms + (1 - alpha) * metrics.avg_latency_ms
                        )

                    # Persist to database
                    await registry.update_skill_metrics(
                        skill_name=skill_name,
                        reliability_score=metrics.reliability_score,
                        avg_latency_ms=metrics.avg_latency_ms,
                    )

                    self.logger.debug(
                        f"[SupabaseVideoTaskQueue] Updated metrics for skill {skill_name}: "
                        f"reliability={metrics.reliability_score:.2f}, latency={metrics.avg_latency_ms}ms"
                    )

            except ImportError:
                self.logger.debug("[SupabaseVideoTaskQueue] Skills module not available for metrics update")
            except Exception as e:
                self.logger.warning(f"[SupabaseVideoTaskQueue] Failed to update skill metrics: {e}")

        except Exception as e:
            self.logger.warning(f"[SupabaseVideoTaskQueue] Error in _update_skill_metrics_on_success: {e}")

    async def _update_skill_metrics_on_failure(self, task_id: str, task: Dict[str, Any]):
        """Update skill metrics when a task fails."""
        try:
            skill_name = task.get("skill_name")
            if not skill_name:
                return

            try:
                from src.skills import get_skills_registry
                registry = await get_skills_registry()
                skill = registry.get_skill(skill_name)

                if skill:
                    metrics = skill.metrics
                    metrics.total_executions += 1
                    # success_count stays the same

                    # Update reliability score
                    metrics.reliability_score = metrics.success_count / metrics.total_executions

                    # Persist to database
                    await registry.update_skill_metrics(
                        skill_name=skill_name,
                        reliability_score=metrics.reliability_score,
                    )

                    self.logger.debug(
                        f"[SupabaseVideoTaskQueue] Updated failure metrics for skill {skill_name}: "
                        f"reliability={metrics.reliability_score:.2f}"
                    )

            except ImportError:
                pass
            except Exception as e:
                self.logger.warning(f"[SupabaseVideoTaskQueue] Failed to update skill failure metrics: {e}")

        except Exception as e:
            self.logger.warning(f"[SupabaseVideoTaskQueue] Error in _update_skill_metrics_on_failure: {e}")

    async def check_and_trigger_stitch(self, run_id: str):
        """检查所有任务是否完成，如果是数字人多段则自动拼接，否则更新 session 状态"""
        try:
            # 1. 获取所有任务（需要 status, video_url, clip_idx）
            res = self.supabase.table("autoviralvid_video_tasks").select(
                "status, video_url, clip_idx, skill_name"
            ).eq("run_id", run_id).execute()
            tasks = res.data if res and res.data else []

            if not tasks:
                return

            # 2. 检查是否全部成功
            all_succeeded = all(t.get("status") == "succeeded" for t in tasks)

            if not all_succeeded:
                return

            self.logger.info(
                f"[SupabaseVideoTaskQueue] All {len(tasks)} tasks for run {run_id} completed."
            )

            # 3. 判断是否是数字人多段流程 — 需要自动拼接
            is_digital_human_multi = False
            try:
                job_res = self.supabase.table("autoviralvid_jobs").select(
                    "storyboards"
                ).eq("run_id", run_id).limit(1).execute()
                if job_res.data:
                    import json
                    sb_raw = job_res.data[0].get("storyboards")
                    sb_data = json.loads(sb_raw) if isinstance(sb_raw, str) and sb_raw else (
                        sb_raw if isinstance(sb_raw, dict) else {}
                    )
                    meta = sb_data.get("_meta", {}) if isinstance(sb_data, dict) else {}
                    pipeline_name = meta.get("pipeline_name", "")
                    if pipeline_name == "digital_human" and len(tasks) > 1:
                        is_digital_human_multi = True
            except Exception as e:
                self.logger.warning(
                    f"[SupabaseVideoTaskQueue] Failed to check pipeline type for {run_id}: {e}"
                )

            if is_digital_human_multi:
                # ── 数字人多段：自动拼接 ──
                self.logger.info(
                    f"[SupabaseVideoTaskQueue] Digital human multi-segment detected "
                    f"({len(tasks)} segments). Starting auto-stitch for {run_id}..."
                )

                # 更新状态为 stitching
                self.supabase.table("autoviralvid_crew_sessions").update({
                    "status": "stitching",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("run_id", run_id).execute()

                try:
                    # 按 clip_idx 排序，提取视频 URL
                    sorted_tasks = sorted(tasks, key=lambda t: t.get("clip_idx", 0))
                    video_urls = [t["video_url"] for t in sorted_tasks if t.get("video_url")]

                    if not video_urls:
                        raise RuntimeError("所有任务已完成但无视频 URL")

                    from src.video_stitcher import stitch_video_segments

                    output_key = f"{run_id}_dh_final.mp4"
                    final_url = await stitch_video_segments(
                        video_urls, run_id, output_key
                    )

                    self.logger.info(
                        f"[SupabaseVideoTaskQueue] Auto-stitch completed for {run_id}: {final_url}"
                    )

                    # 将最终视频 URL 写入 jobs 表
                    self.supabase.table("autoviralvid_jobs").update({
                        "video_url": final_url,
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("run_id", run_id).execute()

                    # 更新 session 状态为 completed
                    self.supabase.table("autoviralvid_crew_sessions").update({
                        "status": "completed",
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("run_id", run_id).execute()

                except Exception as stitch_err:
                    self.logger.error(
                        f"[SupabaseVideoTaskQueue] Auto-stitch failed for {run_id}: {stitch_err}",
                        exc_info=True,
                    )
                    # 拼接失败，回退到 ready_to_stitch 让前端/用户可以手动重试
                    self.supabase.table("autoviralvid_crew_sessions").update({
                        "status": "ready_to_stitch",
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("run_id", run_id).execute()
            else:
                # ── 非数字人多段（单段或普通视频）：只更新状态 ──
                self.supabase.table("autoviralvid_crew_sessions").update({
                    "status": "ready_to_stitch",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("run_id", run_id).execute()

        except Exception as e:
            self.logger.error(f"[SupabaseVideoTaskQueue] Error in check_and_trigger_stitch: {e}")

    def stop(self):
        """停止 worker"""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            try:
                self._worker_task.cancel()
            except Exception:
                # 忽略取消任务时的异常
                pass


# 单例
_supabase_queue: Optional[SupabaseVideoTaskQueue] = None


def get_supabase_queue() -> Optional[SupabaseVideoTaskQueue]:
    """获取 Supabase 队列实例（单例）"""
    global _supabase_queue
    
    if _supabase_queue is None:
        try:
            _supabase_queue = SupabaseVideoTaskQueue(
                retry_interval=20.0,
                max_concurrent=1
            )
            # 尝试启动 worker（如果有运行中的事件循环）
            try:
                loop = asyncio.get_running_loop()
                if not _supabase_queue._running:
                    _supabase_queue._running = True
                    _supabase_queue._worker_task = asyncio.create_task(_supabase_queue._worker_loop())
                    logger.info("[get_supabase_queue] Worker started")
            except RuntimeError:
                # 没有运行中的事件循环，worker 将在应用启动时启动
                logger.debug("[get_supabase_queue] No running event loop, worker will start on app startup")
        except Exception as e:
            logger.warning(f"[get_supabase_queue] Failed to initialize: {e}")
            return None
    
    return _supabase_queue


def start_supabase_queue_worker():
    """在应用启动时启动 Supabase 队列 worker"""
    global _supabase_queue
    
    if _supabase_queue is None:
        queue = get_supabase_queue()
        if queue is None:
            return
    
    if _supabase_queue and not _supabase_queue._running:
        try:
            loop = asyncio.get_running_loop()
            _supabase_queue._running = True
            _supabase_queue._worker_task = asyncio.create_task(_supabase_queue._worker_loop())
            logger.info("[start_supabase_queue_worker] Worker started on application startup")
        except RuntimeError:
            logger.warning("[start_supabase_queue_worker] No running event loop, cannot start worker")


"""
数据库表结构（需要在 Supabase 中创建）：

CREATE TABLE IF NOT EXISTS autoviralvid_video_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id TEXT NOT NULL,
  clip_idx INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  ref_img TEXT,
  duration INTEGER DEFAULT 10,
  status TEXT DEFAULT 'queued',  -- queued, pending, processing, submitted, succeeded, failed
  provider_task_id TEXT,  -- RunningHub task_id
  video_url TEXT,
  error TEXT,
  retry_count INTEGER DEFAULT 0,
  skill_name TEXT,
  skill_id UUID,
  exec_params JSONB DEFAULT '{}'::jsonb,  -- 完整执行参数 (Skills adapter 需要)
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 添加 exec_params 列 (已有表需要执行):
-- ALTER TABLE autoviralvid_video_tasks ADD COLUMN IF NOT EXISTS exec_params JSONB DEFAULT '{}'::jsonb;

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_video_tasks_run_id ON autoviralvid_video_tasks(run_id);
CREATE INDEX IF NOT EXISTS idx_video_tasks_status ON autoviralvid_video_tasks(status);
CREATE INDEX IF NOT EXISTS idx_video_tasks_created_at ON autoviralvid_video_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_video_tasks_provider_task_id ON autoviralvid_video_tasks(provider_task_id);
"""

