"""
Qwen Product Pipeline 端到端测试脚本

测试流程：
1. T2I: 调用 runninghub_qwen_storyboard_t2i 工作流，一次性批量生成分镜图+描述
2. 解析批量输出：提取多张图片 URL 和描述文件
3. I2V: 将相邻图片两两配对为首尾帧，调用 runninghub_qwen_fl_i2v 生成视频
4. 等待所有视频任务完成，输出最终视频 URL

用法：
    cd agent && python -m src.test_qwen_product_pipeline
"""

import os
import sys
import json
import asyncio
import logging
import httpx
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_qwen_product")

# ── 配置 ────────────────────────────────────────────────────
# T2I 工作流
T2I_WORKFLOW_ID = os.getenv("RUNNINGHUB_QWEN_STORYBOARD_WORKFLOW_ID", "2021433434782044162")
T2I_IMAGE_NODE_ID = "74"
T2I_PROMPT_NODE_ID = "103"

# I2V 工作流
I2V_WORKFLOW_ID = os.getenv("RUNNINGHUB_QWEN_FL_WORKFLOW_ID", "2019403401959837698")
I2V_FIRST_FRAME_NODE_ID = "48"
I2V_LAST_FRAME_NODE_ID = "49"
I2V_PROMPT_NODE_ID = "34"
I2V_WIDTH_NODE_ID = "30"
I2V_HEIGHT_NODE_ID = "29"
I2V_DURATION_NODE_ID = "56"

# 默认测试参数
DEFAULT_TEST_IMAGE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_product.png")  # 本地测试产品图
DEFAULT_T2I_PROMPT = (
    "这是一部化妆品广告宣传片，参考图片，帮我生成6张美女化妆品广告宣传片，"
    "从坐姿到站起身，不同运镜和角度，不同的视角和景别"
)

# 轮询参数
POLL_INTERVAL = 5  # 秒
T2I_TIMEOUT = 600  # 10分钟
I2V_TIMEOUT = 1200  # 20分钟 — I2V 首尾帧视频生成通常需要 10~15 分钟


# ── RunningHub 基础操作 ──────────────────────────────────────

async def upload_image(client: Any, url_or_path: str) -> str:
    """下载并上传图片到 RunningHub，返回内部路径。支持 HTTP URL 和本地文件路径"""
    import uuid
    
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        async with httpx.AsyncClient(timeout=60) as hc:
            resp = await hc.get(url_or_path)
            if resp.status_code != 200:
                raise RuntimeError(f"下载图片失败: HTTP {resp.status_code}")
            content = resp.content
            ext = url_or_path.split(".")[-1].split("?")[0].lower()
            if ext not in ("png", "jpg", "jpeg", "webp"):
                ext = "png"
    elif os.path.isfile(url_or_path):
        with open(url_or_path, "rb") as f:
            content = f.read()
        ext = url_or_path.rsplit(".", 1)[-1].lower() if "." in url_or_path else "png"
    else:
        raise RuntimeError(f"图片路径不存在且不是有效 URL: {url_or_path}")
    
    filename = f"test_{uuid.uuid4().hex[:8]}.{ext}"
    uploaded = await client.upload_bytes(content, filename)
    logger.info(f"图片上传成功: {uploaded}")
    return uploaded


async def poll_task(client: Any, task_id: str, timeout: int = 600) -> List[Dict[str, Any]]:
    """轮询任务直到完成，返回所有 outputs"""
    max_iters = timeout // POLL_INTERVAL
    for i in range(max_iters):
        # 使用 get_status_full 获取原始响应用于调试
        try:
            raw_resp = await client.get_status_full(task_id)
            status = (raw_resp.get("data") or "").upper()
        except Exception as e:
            logger.warning(f"  Task {task_id}: poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        elapsed = (i + 1) * POLL_INTERVAL
        if i % 12 == 0:  # 每60秒输出详细日志
            logger.info(f"  Task {task_id}: status={status}, elapsed={elapsed}s, raw_data={raw_resp.get('data')}")
        elif i % 6 == 0:  # 每30秒输出简要日志
            logger.info(f"  Task {task_id}: status={status}, elapsed={elapsed}s")

        if status == "SUCCESS":
            outputs = await client.get_outputs(task_id)
            logger.info(f"  Task {task_id}: SUCCESS after {elapsed}s, {len(outputs)} outputs")
            return outputs
        elif status in ("FAILED", "ERROR"):
            logger.error(f"  Task {task_id}: FAILED, raw_resp={raw_resp}")
            raise RuntimeError(f"任务失败: task_id={task_id}, status={status}")
        
        await asyncio.sleep(POLL_INTERVAL)
    
    # 超时后再检查一次 — 任务可能刚好完成
    try:
        final_status = await client.get_status(task_id)
        if final_status == "SUCCESS":
            outputs = await client.get_outputs(task_id)
            logger.info(f"  Task {task_id}: SUCCESS (final check), {len(outputs)} outputs")
            return outputs
    except Exception:
        pass
    
    raise RuntimeError(f"任务超时: task_id={task_id}, timeout={timeout}s (最后状态: {status})")


def parse_batch_t2i_outputs(outputs: List[Dict[str, Any]]) -> Tuple[List[str], Optional[str]]:
    """
    解析 T2I 批量输出：
    - 图片 URL 列表（.png/.jpg/.jpeg/.webp）
    - 描述文件内容（.txt/.json）
    
    Returns:
        (image_urls, description_text_url)
    """
    image_urls = []
    desc_url = None

    logger.info(f"  解析 {len(outputs)} 个输出项...")
    for idx, item in enumerate(outputs):
        # Dump raw output for debugging
        logger.info(f"    output[{idx}]: {json.dumps(item, ensure_ascii=False, default=str)[:300]}")

        # 提取 URL
        url = None
        for field in ("fileUrl", "url", "ossUrl", "downloadUrl", "value"):
            val = item.get(field)
            if val and isinstance(val, str) and val.strip().startswith("http"):
                url = val.strip()
                break
        
        if not url:
            continue
        
        # 去掉查询参数再判断扩展名
        url_path = url.split("?")[0].lower()
        file_type = (item.get("fileType") or "").lower()
        
        # 图片: 通过扩展名或 fileType 判断
        is_image = (
            any(url_path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp"))
            or file_type in ("png", "jpg", "jpeg", "webp", "image")
        )
        # 描述文件
        is_text = (
            any(url_path.endswith(ext) for ext in (".txt", ".json"))
            or file_type in ("txt", "json", "text")
        )
        
        if is_image:
            image_urls.append(url)
            logger.info(f"    → 图片: {url[:80]}...")
        elif is_text:
            desc_url = url
            logger.info(f"    → 描述文件: {url[:80]}...")
        else:
            # 未识别类型 — 如果 URL 像图片（包含常见图片路径模式），也收入
            logger.info(f"    → 未识别类型 (fileType='{file_type}'): {url[:80]}...")
            # 兜底：如果不是视频，都当图片收
            if not any(url_path.endswith(ext) for ext in (".mp4", ".mp3", ".wav", ".avi")):
                image_urls.append(url)
                logger.info(f"      (兜底归为图片)")
    
    return image_urls, desc_url


async def download_description(url: str) -> str:
    """下载描述文件内容"""
    async with httpx.AsyncClient(timeout=30) as hc:
        resp = await hc.get(url)
        if resp.status_code == 200:
            return resp.text
        raise RuntimeError(f"下载描述文件失败: HTTP {resp.status_code}")


def pair_images_as_first_last(image_urls: List[str]) -> List[Dict[str, str]]:
    """
    将相邻图片两两配对为首尾帧。
    
    [img1, img2, img3, img4] → [
        {first: img1, last: img2},
        {first: img2, last: img3},
        {first: img3, last: img4},
    ]
    """
    pairs = []
    for i in range(len(image_urls) - 1):
        pairs.append({
            "first_frame_url": image_urls[i],
            "last_frame_url": image_urls[i + 1],
            "pair_idx": i + 1,
        })
    return pairs


# ── 测试阶段 ──────────────────────────────────────────────

async def test_t2i_batch(
    client: Any,
    product_image_url: str,
    prompt: str,
) -> Tuple[List[str], Optional[str]]:
    """
    Phase 1: 测试 T2I 批量分镜出图
    
    Returns:
        (image_urls, description_text)
    """
    logger.info("=" * 60)
    logger.info("Phase 1: T2I 批量分镜出图")
    logger.info(f"  工作流: {T2I_WORKFLOW_ID}")
    logger.info(f"  产品图: {product_image_url}")
    logger.info(f"  提示词: {prompt[:80]}...")
    logger.info("=" * 60)

    # 上传产品图
    logger.info("上传产品参考图...")
    uploaded_image = await upload_image(client, product_image_url)

    # 构建 nodeInfoList
    node_info_list = [
        {"nodeId": T2I_IMAGE_NODE_ID, "fieldName": "image", "fieldValue": uploaded_image},
        {"nodeId": T2I_PROMPT_NODE_ID, "fieldName": "text", "fieldValue": prompt},
    ]
    logger.info(f"提交 T2I 任务: {json.dumps(node_info_list, ensure_ascii=False)[:200]}")

    # 提交任务
    task_id = await client.create_task(T2I_WORKFLOW_ID, node_info_list)
    logger.info(f"T2I 任务已提交: task_id={task_id}")

    # 轮询等待
    logger.info(f"等待 T2I 完成 (timeout={T2I_TIMEOUT}s)...")
    outputs = await poll_task(client, task_id, T2I_TIMEOUT)

    # 解析输出
    image_urls, desc_url = parse_batch_t2i_outputs(outputs)
    logger.info(f"T2I 输出: {len(image_urls)} 张图片")
    for i, url in enumerate(image_urls):
        logger.info(f"  图片 {i+1}: {url}")

    desc_text = None
    if desc_url:
        logger.info(f"下载描述文件: {desc_url}")
        desc_text = await download_description(desc_url)
        logger.info(f"描述内容 (前200字): {desc_text[:200]}")
    else:
        logger.warning("未找到描述文件")

    return image_urls, desc_text


async def submit_i2v_task(
    client: Any,
    first_frame_url: str,
    last_frame_url: str,
    prompt: str,
    pair_idx: int,
    width: int = 720,
    height: int = 1280,
    duration: int = 5,
) -> str:
    """
    提交 I2V 任务（仅上传图片+创建任务，不轮询）。
    
    Returns:
        task_id
    """
    logger.info(f"\n--- 提交 I2V Pair {pair_idx} ---")
    logger.info(f"  首帧: {first_frame_url[:60]}...")
    logger.info(f"  尾帧: {last_frame_url[:60]}...")
    logger.info(f"  提示词: {prompt[:60]}...")
    logger.info(f"  尺寸: {width}x{height}, 时长: {duration}s")

    # 上传首尾帧图片
    uploaded_first = await upload_image(client, first_frame_url)
    uploaded_last = await upload_image(client, last_frame_url)

    # 构建 nodeInfoList
    node_info_list = [
        {"nodeId": I2V_FIRST_FRAME_NODE_ID, "fieldName": "image", "fieldValue": uploaded_first},
        {"nodeId": I2V_LAST_FRAME_NODE_ID, "fieldName": "image", "fieldValue": uploaded_last},
        {"nodeId": I2V_PROMPT_NODE_ID, "fieldName": "text", "fieldValue": prompt},
        {"nodeId": I2V_WIDTH_NODE_ID, "fieldName": "width", "fieldValue": str(width)},
        {"nodeId": I2V_HEIGHT_NODE_ID, "fieldName": "height", "fieldValue": str(height)},
        {"nodeId": I2V_DURATION_NODE_ID, "fieldName": "num_frames", "fieldValue": str(duration)},
    ]
    
    # 提交任务
    task_id = await client.create_task(I2V_WORKFLOW_ID, node_info_list)
    logger.info(f"  I2V Pair {pair_idx} 已提交: task_id={task_id}")
    return task_id


def extract_video_url_from_outputs(outputs: List[Dict[str, Any]], pair_idx: int) -> str:
    """从 RunningHub outputs 中提取视频 URL"""
    logger.info(f"  I2V Pair {pair_idx}: {len(outputs)} outputs:")
    for oi, item in enumerate(outputs):
        logger.info(f"    output[{oi}]: {json.dumps(item, ensure_ascii=False, default=str)[:300]}")

    video_url = None
    all_urls = []
    for item in outputs:
        for field in ("fileUrl", "url", "ossUrl", "downloadUrl", "value"):
            val = item.get(field)
            if val and isinstance(val, str) and val.strip().startswith("http"):
                all_urls.append(val.strip())
                if ".mp4" in val.lower():
                    video_url = val.strip()
                break

    if not video_url and all_urls:
        video_url = all_urls[0]

    if not video_url:
        raise RuntimeError(f"Pair {pair_idx}: 未在 {len(outputs)} 个输出中找到视频 URL")

    logger.info(f"  I2V Pair {pair_idx} 完成: {video_url}")
    return video_url


RUNNINGHUB_MAX_CONCURRENT = 2  # RunningHub 并发任务上限


async def test_i2v_batch(
    client: Any,
    pairs: List[Dict[str, str]],
    descriptions: List[str],
    max_concurrent: int = RUNNINGHUB_MAX_CONCURRENT,
) -> List[str]:
    """
    Phase 2: 滑动窗口并发 I2V 首尾帧视频生成。
    
    RunningHub 并发限制为 2，所以：
    - 同时提交最多 max_concurrent 个任务
    - 当任一任务完成/失败后，立即提交下一个
    - 所有任务完成后返回结果
    
    Returns:
        [video_url, ...]  按 pair 顺序排列
    """
    logger.info("=" * 60)
    logger.info(f"Phase 2: I2V 首尾帧视频生成 ({len(pairs)} 对)")
    logger.info(f"  工作流: {I2V_WORKFLOW_ID}")
    logger.info(f"  并发窗口: {max_concurrent}")
    logger.info("=" * 60)

    # 结果数组，按 pair 索引存放
    results: List[Optional[str]] = [None] * len(pairs)

    # ── 1. 提交所有任务（受并发窗口限制） ──
    # 用一个 list 保存 {pair_idx, task_id} 的活跃任务
    pending_pairs = list(range(len(pairs)))  # 等待提交的 pair 索引
    active_tasks: Dict[str, int] = {}  # task_id → pair list index
    submitted_count = 0

    async def _submit_next():
        """提交下一个等待中的 pair，返回 True 表示成功提交"""
        nonlocal submitted_count
        if not pending_pairs:
            return False
        
        pi = pending_pairs.pop(0)
        pair = pairs[pi]
        idx = pair["pair_idx"]
        desc = descriptions[idx - 1] if idx - 1 < len(descriptions) else f"产品展示场景 {idx}"
        
        try:
            task_id = await submit_i2v_task(
                client=client,
                first_frame_url=pair["first_frame_url"],
                last_frame_url=pair["last_frame_url"],
                prompt=desc,
                pair_idx=idx,
            )
            active_tasks[task_id] = pi
            submitted_count += 1
            return True
        except Exception as e:
            import traceback as tb
            logger.error(f"  Pair {idx} 提交失败: {type(e).__name__}: {e}")
            logger.error(f"  {tb.format_exc()}")
            results[pi] = None
            return False

    # 填满并发窗口
    for _ in range(min(max_concurrent, len(pending_pairs))):
        await _submit_next()
        # 提交间隔 2s，避免瞬间打满
        if pending_pairs:
            await asyncio.sleep(2)

    # ── 2. 轮询所有活跃任务，完成一个就补提交一个 ──
    logger.info(f"\n开始轮询 {len(active_tasks)} 个活跃任务...")
    
    poll_round = 0
    while active_tasks:
        poll_round += 1
        await asyncio.sleep(POLL_INTERVAL)

        # 检查每个活跃任务的状态
        completed_tasks = []
        for task_id, pi in list(active_tasks.items()):
            pair = pairs[pi]
            idx = pair["pair_idx"]
            
            try:
                raw_resp = await client.get_status_full(task_id)
                status = (raw_resp.get("data") or "").upper()
            except Exception as e:
                logger.warning(f"  Pair {idx} (task={task_id}): poll error: {e}")
                continue

            if poll_round % 12 == 0:  # 每 60s 详细日志
                logger.info(f"  Pair {idx} (task={task_id}): status={status}, round={poll_round}")

            if status == "SUCCESS":
                try:
                    outputs = await client.get_outputs(task_id)
                    video_url = extract_video_url_from_outputs(outputs, idx)
                    results[pi] = video_url
                    logger.info(f"  ✓ Pair {idx} 完成: {video_url}")
                except Exception as e:
                    logger.error(f"  Pair {idx} 输出解析失败: {e}")
                    results[pi] = None
                completed_tasks.append(task_id)

            elif status in ("FAILED", "ERROR"):
                logger.error(f"  ✗ Pair {idx} (task={task_id}) 失败: {raw_resp}")
                results[pi] = None
                completed_tasks.append(task_id)

        # 移除已完成的任务
        for tid in completed_tasks:
            del active_tasks[tid]

        # 补提交新任务，填满并发窗口
        while len(active_tasks) < max_concurrent and pending_pairs:
            await _submit_next()
            await asyncio.sleep(2)

        # 状态摘要（每 30 轮 = 150s 输出一次）
        if poll_round % 30 == 0:
            done = sum(1 for r in results if r is not None)
            logger.info(
                f"  [进度] 活跃={len(active_tasks)}, 待提交={len(pending_pairs)}, "
                f"已完成={done}/{len(pairs)}"
            )

    return results


def parse_descriptions(desc_text: Optional[str], num_pairs: int) -> List[str]:
    """
    解析描述文件为每对首尾帧的提示词列表。
    
    描述文件可能是 JSON 数组 或 换行分隔的文本。
    如果解析失败，返回默认描述。
    """
    if not desc_text:
        return [f"产品展示场景 {i+1}" for i in range(num_pairs)]
    
    try:
        # 尝试 JSON 解析
        data = json.loads(desc_text)
        if isinstance(data, list):
            descs = [str(d) for d in data]
            # 如果描述数量与图片数量匹配，为每对生成描述
            # 每对使用 "当前场景描述 → 下一场景描述" 的过渡描述
            if len(descs) >= num_pairs:
                return descs[:num_pairs]
            return descs + [f"产品展示场景 {i+1}" for i in range(len(descs), num_pairs)]
        elif isinstance(data, dict) and "scenes" in data:
            scenes = data["scenes"]
            descs = [s.get("description", s.get("desc", f"场景 {i+1}")) for i, s in enumerate(scenes)]
            return descs[:num_pairs] if len(descs) >= num_pairs else descs + [f"产品展示场景 {i+1}" for i in range(len(descs), num_pairs)]
    except (json.JSONDecodeError, TypeError):
        pass
    
    # 尝试按行分割
    lines = [l.strip() for l in desc_text.strip().split("\n") if l.strip()]
    if lines:
        return lines[:num_pairs] if len(lines) >= num_pairs else lines + [f"产品展示场景 {i+1}" for i in range(len(lines), num_pairs)]
    
    return [f"产品展示场景 {i+1}" for i in range(num_pairs)]


# ── 主测试 ────────────────────────────────────────────────

async def run_full_pipeline_test(
    product_image_url: str = DEFAULT_TEST_IMAGE,
    prompt: str = DEFAULT_T2I_PROMPT,
    max_i2v_pairs: int = 3,
):
    """运行完整的 Qwen Product Pipeline 测试"""
    from src.runninghub_client import RunningHubClient
    
    api_key = os.getenv("RUNNINGHUB_API_KEY")
    if not api_key:
        logger.error("缺少 RUNNINGHUB_API_KEY 环境变量")
        return

    client = RunningHubClient(api_key)

    try:
        # ── Phase 1: T2I 批量分镜出图 ──
        image_urls, desc_text = await test_t2i_batch(client, product_image_url, prompt)

        if len(image_urls) < 2:
            logger.error(f"T2I 输出图片不足: 需要至少2张，实际 {len(image_urls)} 张")
            return

        # ── 配对首尾帧 ──
        pairs = pair_images_as_first_last(image_urls)
        logger.info(f"\n相邻图片配对: {len(pairs)} 对")
        for p in pairs:
            logger.info(f"  Pair {p['pair_idx']}: {p['first_frame_url'][:50]}... → {p['last_frame_url'][:50]}...")

        # 限制 I2V 测试对数
        if max_i2v_pairs > 0 and len(pairs) > max_i2v_pairs:
            logger.info(f"限制 I2V 测试: {max_i2v_pairs}/{len(pairs)} 对")
            pairs = pairs[:max_i2v_pairs]

        # 解析描述
        descriptions = parse_descriptions(desc_text, len(pairs))
        logger.info(f"分镜描述 ({len(descriptions)} 条):")
        for i, d in enumerate(descriptions):
            logger.info(f"  [{i+1}] {d[:80]}...")

        # ── Phase 2: I2V 首尾帧视频生成 ──
        video_urls = await test_i2v_batch(client, pairs, descriptions)

        # ── 结果汇总 ──
        logger.info("\n" + "=" * 60)
        logger.info("测试结果汇总")
        logger.info("=" * 60)
        logger.info(f"T2I 输出: {len(image_urls)} 张图片")
        logger.info(f"I2V 输入: {len(pairs)} 对首尾帧")
        
        success_count = sum(1 for v in video_urls if v)
        logger.info(f"I2V 成功: {success_count}/{len(pairs)}")
        
        for i, url in enumerate(video_urls):
            status = "✓" if url else "✗"
            logger.info(f"  {status} 视频 {i+1}: {url or 'FAILED'}")

        if success_count == len(pairs):
            logger.info("\n🎉 全部测试通过！Pipeline 端到端验证成功。")
        elif success_count > 0:
            logger.warning(f"\n⚠ 部分成功: {success_count}/{len(pairs)}")
        else:
            logger.error("\n❌ 所有 I2V 任务失败")

    finally:
        await client.aclose()


async def run_t2i_only_test(
    product_image_url: str = DEFAULT_TEST_IMAGE,
    prompt: str = DEFAULT_T2I_PROMPT,
):
    """仅测试 T2I 部分（用于快速验证分镜出图）"""
    from src.runninghub_client import RunningHubClient
    
    api_key = os.getenv("RUNNINGHUB_API_KEY")
    if not api_key:
        logger.error("缺少 RUNNINGHUB_API_KEY 环境变量")
        return

    client = RunningHubClient(api_key)

    try:
        image_urls, desc_text = await test_t2i_batch(client, product_image_url, prompt)
        
        logger.info("\n" + "=" * 60)
        logger.info("T2I 测试结果")
        logger.info("=" * 60)
        logger.info(f"图片数量: {len(image_urls)}")
        for i, url in enumerate(image_urls):
            logger.info(f"  [{i+1}] {url}")
        
        if desc_text:
            logger.info(f"\n描述文件内容:\n{desc_text[:500]}")
        
        if len(image_urls) >= 2:
            pairs = pair_images_as_first_last(image_urls)
            logger.info(f"\n可配对数量: {len(pairs)}")
            logger.info("✓ T2I 测试通过，可用于 I2V 配对")
        else:
            logger.warning("⚠ 图片不足2张，无法配对")
    finally:
        await client.aclose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Qwen Product Pipeline 测试")
    parser.add_argument("--mode", choices=["full", "t2i", "i2v"], default="full",
                        help="测试模式: full=完整流程, t2i=仅分镜出图, i2v=仅视频生成")
    parser.add_argument("--image", default=DEFAULT_TEST_IMAGE, help="产品参考图 URL")
    parser.add_argument("--prompt", default=DEFAULT_T2I_PROMPT, help="T2I 提示词")
    parser.add_argument("--max-pairs", type=int, default=0, help="最大 I2V 测试对数 (0=不限制)")

    args = parser.parse_args()

    if args.mode == "full":
        asyncio.run(run_full_pipeline_test(args.image, args.prompt, args.max_pairs))
    elif args.mode == "t2i":
        asyncio.run(run_t2i_only_test(args.image, args.prompt))
    else:
        logger.info("I2V 单独测试需要提供图片 URL，请使用 --mode full")
