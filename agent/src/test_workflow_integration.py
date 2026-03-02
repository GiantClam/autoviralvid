"""
集成测试: 验证 qwen_product pipeline 在 LangGraph workflow 中的完整数据流。

测试路径:
  1. _qwen_product_batch_t2i() → 批量生成分镜图片
  2. task_prepper 逻辑 → 将 N 张图片配对为 N-1 个首尾帧任务
  3. RunningHubAdapter.execute() → 通过 Skill 系统提交 I2V 任务
  4. RunningHubAdapter.get_status() → 轮询任务状态直到完成

不依赖 copilotkit / LangGraph 运行时。
"""

import asyncio
import json
import logging
import os
import sys
import time

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.runninghub_client import RunningHubClient
from src.skills.registry import SkillsRegistry
from src.skills.models import SkillExecutionRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("integration_test")

# ─── Config ───
T2I_WORKFLOW_ID = os.getenv("RUNNINGHUB_QWEN_STORYBOARD_WORKFLOW_ID", "2021433434782044162")
I2V_WORKFLOW_ID = os.getenv("RUNNINGHUB_QWEN_FL_WORKFLOW_ID", "2019403401959837698")
PRODUCT_IMAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_product.png")
POLL_INTERVAL = 5
I2V_TIMEOUT = 1200  # 20 min per task
MAX_CONCURRENT = 2
MAX_I2V_PAIRS = 0  # 0 = 不限制，N 张图生成 N-1 段视频


async def phase1_batch_t2i(client: RunningHubClient) -> tuple:
    """Phase 1: 批量 T2I (与 _qwen_product_batch_t2i 相同逻辑)"""
    import httpx

    logger.info("=" * 60)
    logger.info("Phase 1: 批量 T2I 分镜图片生成")
    logger.info("=" * 60)

    # Upload product image
    if os.path.isfile(PRODUCT_IMAGE):
        with open(PRODUCT_IMAGE, "rb") as f:
            content = f.read()
        image_ref = await client.upload_bytes(content, "test_product.png", file_type="input")
        logger.info(f"  产品图上传: {image_ref}")
    else:
        raise RuntimeError(f"测试产品图不存在: {PRODUCT_IMAGE}")

    prompt = "这是一部化妆品广告宣传片，参考图片，帮我生成6张美女化妆品广告宣传片，从坐姿到站起身，不同运镜和角度，不同的视角和景别"

    node_info = [
        {"nodeId": "74", "fieldName": "image", "fieldValue": image_ref},
        {"nodeId": "103", "fieldName": "text", "fieldValue": prompt},
    ]

    # Retry on TASK_QUEUE_MAXED
    for attempt in range(30):
        try:
            task_id = await client.create_task(T2I_WORKFLOW_ID, node_info)
            logger.info(f"  T2I 任务已提交: {task_id}")
            break
        except Exception as e:
            if "TASK_QUEUE_MAXED" in str(e):
                wait = 30
                logger.warning(f"  队列已满，等待 {wait}s 后重试 (attempt {attempt+1}/30)...")
                await asyncio.sleep(wait)
            else:
                raise
    else:
        raise RuntimeError("T2I 提交失败：队列持续满载")

    # Poll
    for i in range(120):
        status = await client.get_status(task_id)
        if i % 12 == 0:
            logger.info(f"  T2I 状态: {status}, elapsed={i * POLL_INTERVAL}s")
        if status == "SUCCESS":
            outputs = await client.get_outputs(task_id)
            break
        elif status in ("FAILED", "ERROR"):
            raise RuntimeError(f"T2I 失败: {task_id}")
        await asyncio.sleep(POLL_INTERVAL)
    else:
        raise RuntimeError(f"T2I 超时: {task_id}")

    # Parse
    image_urls = []
    desc_text = None
    for item in outputs:
        url = None
        for field in ("fileUrl", "url", "ossUrl", "value"):
            val = item.get(field)
            if val and isinstance(val, str) and val.startswith("http"):
                url = val.strip()
                break
        if not url:
            continue
        url_path = url.split("?")[0].lower()
        ft = (item.get("fileType") or "").lower()
        if ft in ("png", "jpg", "jpeg", "webp") or any(url_path.endswith(e) for e in (".png", ".jpg", ".jpeg", ".webp")):
            image_urls.append(url)
        elif ft in ("txt", "json") or any(url_path.endswith(e) for e in (".txt", ".json")):
            try:
                async with httpx.AsyncClient(timeout=30) as hc:
                    r = await hc.get(url)
                    if r.status_code == 200:
                        desc_text = r.text
            except Exception:
                pass

    # Parse descriptions
    descriptions = []
    if desc_text:
        parts = desc_text.split("Next Scene:")
        for p in parts:
            p = p.strip()
            if p:
                descriptions.append(p)
    while len(descriptions) < len(image_urls):
        descriptions.append(f"产品展示场景 {len(descriptions)+1}")

    logger.info(f"  T2I 结果: {len(image_urls)} 张图片, {len(descriptions)} 段描述")
    for i, url in enumerate(image_urls):
        logger.info(f"    图片 {i+1}: {url[:80]}...")
    return image_urls, descriptions


def phase2_task_prep(image_urls: list, descriptions: list) -> list:
    """Phase 2: 模拟 task_prepper_node 的首尾帧配对逻辑"""
    logger.info("=" * 60)
    logger.info("Phase 2: 首尾帧配对 (task_prepper_node 逻辑)")
    logger.info("=" * 60)

    pairs = []
    limit = min(len(image_urls) - 1, MAX_I2V_PAIRS) if MAX_I2V_PAIRS > 0 else len(image_urls) - 1
    for i in range(limit):
        desc = descriptions[i] if i < len(descriptions) else f"产品展示场景 {i+1}"
        pair = {
            "idx": i + 1,
            "task_idx": i + 1,
            "prompt": desc,
            "first_frame_url": image_urls[i],
            "last_frame_url": image_urls[i + 1],
            "duration": 5,
            "pipeline": "qwen_product",
        }
        pairs.append(pair)
        logger.info(f"  Pair {i+1}: first={image_urls[i][:60]}... → last={image_urls[i+1][:60]}...")

    logger.info(f"  共 {len(pairs)} 对首尾帧任务")
    return pairs


async def phase3_executor_via_adapter(video_tasks: list) -> list:
    """
    Phase 3: 通过 SkillsRegistry + RunningHubAdapter 提交 I2V 任务。
    模拟 executor_node 中的 Skills 路径。
    """
    logger.info("=" * 60)
    logger.info("Phase 3: 通过 RunningHubAdapter 提交 I2V 任务")
    logger.info("=" * 60)

    # Load registry
    registry = SkillsRegistry()
    await registry.initialize()

    skill = registry.get_skill("runninghub_qwen_fl_i2v")
    if not skill:
        raise RuntimeError("runninghub_qwen_fl_i2v skill 未找到！请检查 skills.yaml")
    logger.info(f"  Skill: {skill.name} (workflow_id={skill.workflow_id})")

    adapter = registry.create_adapter(skill)
    if not adapter:
        raise RuntimeError("无法创建 RunningHubAdapter")

    # Submit tasks with delay
    task_ids = []
    for task in video_tasks:
        params = {
            "prompt": task["prompt"],
            "first_frame_url": task["first_frame_url"],
            "last_frame_url": task["last_frame_url"],
            "duration": task.get("duration", 5),
        }
        request = SkillExecutionRequest(
            skill_id=skill.id or "test",
            run_id="integration_test",
            params=params,
            clip_idx=task["idx"],
        )
        logger.info(f"  提交 Pair {task['idx']}: prompt='{task['prompt'][:50]}...'")

        # Retry on queue full (each I2V task ~5-10 min, so need long retry window)
        submitted = False
        for attempt in range(60):  # 60 * 30s = 30 min max wait
            result = await adapter.execute(request)

            if result.status in ("submitted", "pending") and result.task_id:
                logger.info(f"    ✓ 提交成功: task_id={result.task_id}")
                task_ids.append({"pair_idx": task["idx"], "task_id": result.task_id})
                submitted = True
                break
            elif result.error and "TASK_QUEUE_MAXED" in result.error:
                wait = 30
                if attempt % 4 == 0:
                    logger.warning(f"    队列满，等待 {wait}s 后重试 (attempt {attempt+1}/60)...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"    Pair {task['idx']} 提交失败: {result.error}")
                task_ids.append({"pair_idx": task["idx"], "task_id": None, "error": result.error})
                break

        if not submitted and not any(t["pair_idx"] == task["idx"] for t in task_ids):
            task_ids.append({"pair_idx": task["idx"], "task_id": None, "error": "Max retries exceeded"})

        # Delay between submissions
        await asyncio.sleep(3)

    return task_ids


async def phase4_poll_results(task_ids: list) -> list:
    """Phase 4: 轮询所有 I2V 任务直到完成"""
    logger.info("=" * 60)
    logger.info("Phase 4: 轮询 I2V 任务状态")
    logger.info("=" * 60)

    # Load adapter for status checks
    registry = SkillsRegistry()
    await registry.initialize()
    skill = registry.get_skill("runninghub_qwen_fl_i2v")
    adapter = registry.create_adapter(skill)

    pending = {t["task_id"]: t["pair_idx"] for t in task_ids if t.get("task_id")}
    results = {}
    start = time.time()

    while pending and (time.time() - start) < I2V_TIMEOUT:
        for task_id, pair_idx in list(pending.items()):
            try:
                status_result = await adapter.get_status(task_id)
                elapsed = int(time.time() - start)

                if status_result.status == "succeeded":
                    results[pair_idx] = status_result.output_url
                    logger.info(f"  ✓ Pair {pair_idx} 完成: {status_result.output_url}")
                    del pending[task_id]
                elif status_result.status == "failed":
                    results[pair_idx] = None
                    logger.error(f"  ✗ Pair {pair_idx} 失败: {status_result.error}")
                    del pending[task_id]
                else:
                    if elapsed % 60 < POLL_INTERVAL:
                        logger.info(f"  Pair {pair_idx} (task={task_id[:12]}...): {status_result.status}, elapsed={elapsed}s")
            except Exception as e:
                logger.warning(f"  Pair {pair_idx} 轮询异常: {e}")

        if pending:
            await asyncio.sleep(POLL_INTERVAL)

    if pending:
        logger.warning(f"  超时！仍有 {len(pending)} 个任务未完成")
        for task_id, pair_idx in pending.items():
            results[pair_idx] = None

    return results


async def main():
    logger.info("=" * 70)
    logger.info(" Qwen Product Pipeline 集成测试")
    logger.info(" 测试 image_gen_node → task_prepper_node → executor_node 数据流")
    logger.info("=" * 70)

    api_key = os.getenv("RUNNINGHUB_API_KEY")
    if not api_key:
        logger.error("RUNNINGHUB_API_KEY 未设置！")
        return

    client = RunningHubClient(api_key)

    # Phase 1: Batch T2I
    image_urls, descriptions = await phase1_batch_t2i(client)
    if len(image_urls) < 2:
        logger.error("T2I 返回图片不足 2 张，无法配对")
        return

    # Phase 2: Task prep (first/last frame pairing)
    video_tasks = phase2_task_prep(image_urls, descriptions)

    # Phase 3: Submit via adapter
    task_ids = await phase3_executor_via_adapter(video_tasks)

    # Phase 4: Poll until done
    results = await phase4_poll_results(task_ids)

    await client.aclose()

    # Summary
    logger.info("=" * 70)
    logger.info(" 测试结果汇总")
    logger.info("=" * 70)
    success = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info(f"  总计: {total} 个视频任务")
    logger.info(f"  成功: {success}")
    logger.info(f"  失败: {total - success}")
    for idx in sorted(results.keys()):
        url = results[idx]
        status = "✓" if url else "✗"
        logger.info(f"  Pair {idx}: {status} {url or 'FAILED'}")

    if success == total:
        logger.info("\n  ✓ 集成测试通过！所有视频素材生成成功。")
    elif success > 0:
        logger.info(f"\n  ⚠ 部分成功: {success}/{total}")
    else:
        logger.error(f"\n  ✗ 集成测试失败: 所有 {total} 个任务都失败了")


if __name__ == "__main__":
    asyncio.run(main())
