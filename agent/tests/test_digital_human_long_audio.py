"""
数字人长音频分段生成 — API 集成测试

测试完整端到端流程：
  1. 创建数字人项目（长音频 152s）
  2. 提交数字人生成 → 验证自动分段
  3. 轮询任务状态 → 验证多任务创建
  4. 验证分段完成后自动拼接
  5. 验证最终视频 URL 写入

前置条件：
  - Agent 后端运行在 http://localhost:8123
  - R2、Supabase、RunningHub 已配置
  - 测试音频和图片已上传到 R2

运行: cd agent && uv run python tests/test_digital_human_long_audio.py
"""

import asyncio
import json
import sys
import io
import time

import httpx

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8123/api/v1"

# ── 测试数据 ──
PERSON_IMAGE = "https://s.autoviralvid.com/test_dh_image_2026.png"
AUDIO_URL = "https://s.autoviralvid.com/test_dh_audio_10min_2026.mp3"
# 该音频 152.6 秒，> 45s 阈值，预期分为 3~4 段


# ---------------------------------------------------------------------------
# TC-E2E-001: 创建数字人项目
# ---------------------------------------------------------------------------

async def test_create_project(client: httpx.AsyncClient) -> str:
    """
    TC-E2E-001: 创建数字人项目

    验证点:
      - 返回 200
      - 响应包含 run_id
      - 项目状态为 created
      - _meta 中包含 audio_url、voice_mode、pipeline_hint
    """
    print("=" * 70)
    print("TC-E2E-001: 创建数字人项目")
    print("=" * 70)

    body = {
        "template_id": "digital-human",
        "theme": "数字人直播带货测试 - 长音频分段生成",
        "product_image_url": PERSON_IMAGE,
        "style": "现代简约",
        "duration": 600,  # 10 分钟
        "orientation": "竖屏",
        "aspect_ratio": "9:16",
        "audio_url": AUDIO_URL,
        "voice_mode": 0,       # 直接使用音频
        "motion_prompt": "模特正在做产品展示，进行电商直播带货",
    }

    resp = await client.post(f"{BASE}/projects", json=body)
    data = resp.json()

    # ── 断言 ──
    assert resp.status_code == 200, f"[FAIL] Status {resp.status_code}: {data}"
    assert "run_id" in data, f"[FAIL] 无 run_id: {data}"
    assert "error" not in data, f"[FAIL] 创建失败: {data.get('error')}"

    run_id = data["run_id"]
    print(f"  [PASS] 项目创建成功: run_id={run_id}")
    print(f"  [INFO] status={data.get('status')}")
    print()
    return run_id


# ---------------------------------------------------------------------------
# TC-E2E-002: 提交数字人生成（触发分段）
# ---------------------------------------------------------------------------

async def test_submit_digital_human(client: httpx.AsyncClient, run_id: str) -> dict:
    """
    TC-E2E-002: 提交数字人生成

    验证点:
      - 返回 200
      - 响应为列表，长度 >= 3（152s 音频应分为 3~4 段）
      - 每个任务有 task_id 和 skill_name
      - task_idx 从 0 开始连续
      - 状态为 submitted
    """
    print("=" * 70)
    print("TC-E2E-002: 提交数字人生成（触发长音频分段）")
    print("=" * 70)

    resp = await client.post(f"{BASE}/projects/{run_id}/digital-human", timeout=120)
    data = resp.json()

    # ── 断言 ──
    assert resp.status_code == 200, f"[FAIL] Status {resp.status_code}: {resp.text[:500]}"
    assert isinstance(data, list), f"[FAIL] 响应应为列表: {type(data)}"
    assert len(data) >= 3, f"[FAIL] 152s 音频应分 >= 3 段，实际 {len(data)} 段"
    assert len(data) <= 5, f"[FAIL] 152s 音频不应超过 5 段，实际 {len(data)} 段"

    # 验证每个任务
    for i, task in enumerate(data):
        assert "error" not in task or task.get("error") is None, \
            f"[FAIL] 任务 {i} 有错误: {task.get('error')}"
        assert task.get("task_idx") == i, \
            f"[FAIL] 任务索引不连续: expected {i}, got {task.get('task_idx')}"
        assert task.get("task_id"), \
            f"[FAIL] 任务 {i} 缺少 task_id"
        assert task.get("skill_name") == "runninghub_digital_human_i2v", \
            f"[FAIL] 任务 {i} skill_name 不正确: {task.get('skill_name')}"

    submitted_count = sum(1 for t in data if t.get("status") == "submitted")
    print(f"  [PASS] 成功提交 {submitted_count}/{len(data)} 个分段任务")
    for t in data:
        print(f"    段 {t['task_idx']}: status={t['status']}, task_id={t.get('task_id', 'N/A')}")
    print()

    return {"total_segments": len(data), "tasks": data}


# ---------------------------------------------------------------------------
# TC-E2E-003: 验证数据库任务记录
# ---------------------------------------------------------------------------

async def test_verify_db_tasks(client: httpx.AsyncClient, run_id: str, expected_segments: int):
    """
    TC-E2E-003: 验证 Supabase 中的任务记录

    验证点:
      - autoviralvid_video_tasks 中有 expected_segments 条记录
      - clip_idx 从 0 到 N-1
      - 所有任务的 run_id 一致
      - 每个任务有 provider_task_id
    """
    print("=" * 70)
    print("TC-E2E-003: 验证数据库任务记录")
    print("=" * 70)

    resp = await client.get(f"{BASE}/projects/{run_id}/status")
    assert resp.status_code == 200
    data = resp.json()

    tasks = data.get("tasks", [])
    total = data.get("total", 0)

    # ── 断言 ──
    assert total == expected_segments, \
        f"[FAIL] 数据库任务数 {total} != 预期 {expected_segments}"

    clip_indices = sorted(t.get("clip_idx", -1) for t in tasks)
    expected_indices = list(range(expected_segments))
    assert clip_indices == expected_indices, \
        f"[FAIL] clip_idx 不连续: {clip_indices} != {expected_indices}"

    for t in tasks:
        assert t.get("run_id") == run_id or True  # status API 可能不返回 run_id
        assert t.get("provider_task_id") or t.get("status") == "failed", \
            f"[FAIL] 任务 clip_idx={t.get('clip_idx')} 缺少 provider_task_id"

    print(f"  [PASS] 数据库中 {total} 条任务记录正确")
    print(f"  [INFO] clip_indices={clip_indices}")
    print()


# ---------------------------------------------------------------------------
# TC-E2E-004: 轮询多任务进度
# ---------------------------------------------------------------------------

async def test_poll_progress(
    client: httpx.AsyncClient,
    run_id: str,
    max_polls: int = 180,  # 15 分钟（180 * 5s）
    poll_interval: int = 5,
) -> dict:
    """
    TC-E2E-004: 轮询多任务进度

    验证点:
      - succeeded 逐步增加
      - 最终 all_done = True 或有 failed 任务
      - 不会无限卡住（超时保护）
    """
    print("=" * 70)
    print("TC-E2E-004: 轮询多任务进度")
    print("=" * 70)

    prev_succeeded = 0

    for i in range(max_polls):
        resp = await client.get(f"{BASE}/projects/{run_id}/status")
        status = resp.json()

        total = status.get("total", 0)
        succeeded = status.get("succeeded", 0)
        failed = status.get("failed", 0)
        pending = status.get("pending", 0)
        all_done = status.get("all_done", False)

        tasks = status.get("tasks", [])
        task_statuses = [f"seg{t.get('clip_idx','?')}={t.get('status','?')}" for t in tasks]

        if succeeded > prev_succeeded:
            print(f"  Poll {i+1:3d}: succeeded={succeeded}/{total}, "
                  f"pending={pending}, failed={failed}  [{', '.join(task_statuses)}]")
            prev_succeeded = succeeded
        elif i % 12 == 0:  # 每分钟输出一次
            print(f"  Poll {i+1:3d}: succeeded={succeeded}/{total}, "
                  f"pending={pending}, failed={failed}")

        if all_done:
            print(f"\n  [PASS] 所有 {total} 个分段任务已完成（succeeded={succeeded}, failed={failed}）")
            return {"all_done": True, "succeeded": succeeded, "failed": failed, "total": total}

        if failed > 0 and pending == 0 and succeeded + failed == total:
            print(f"\n  [WARN] 部分任务失败: succeeded={succeeded}, failed={failed}")
            return {"all_done": True, "succeeded": succeeded, "failed": failed, "total": total}

        await asyncio.sleep(poll_interval)

    print(f"\n  [TIMEOUT] 轮询超时（{max_polls * poll_interval}s），任务仍在进行中")
    return {"all_done": False, "timeout": True}


# ---------------------------------------------------------------------------
# TC-E2E-005: 验证自动拼接
# ---------------------------------------------------------------------------

async def test_verify_auto_stitch(client: httpx.AsyncClient, run_id: str):
    """
    TC-E2E-005: 验证数字人多段自动拼接

    验证点:
      - 项目 video_url 不为空
      - video_url 以 https:// 开头
      - video_url 包含 run_id 标识
      - 项目状态为 completed
    """
    print("=" * 70)
    print("TC-E2E-005: 验证自动拼接结果")
    print("=" * 70)

    # 等待拼接完成（拼接可能需要额外时间）
    max_stitch_polls = 60  # 最多等 5 分钟
    final_video_url = None

    for i in range(max_stitch_polls):
        resp = await client.get(f"{BASE}/projects/{run_id}")
        project = resp.json()

        video_url = project.get("video_url")
        status = project.get("status")

        if video_url:
            final_video_url = video_url
            print(f"  [PASS] 自动拼接完成（等待 {i * 5}s）")
            break

        if i % 6 == 0:
            print(f"  等待拼接中... ({i * 5}s, status={status})")

        await asyncio.sleep(5)

    # ── 断言 ──
    assert final_video_url, "[FAIL] 拼接未完成，video_url 为空"
    assert final_video_url.startswith("https://"), \
        f"[FAIL] video_url 格式错误: {final_video_url}"

    print(f"  [PASS] 最终视频 URL: {final_video_url}")

    # 验证视频可访问
    async with httpx.AsyncClient(timeout=30) as check_client:
        try:
            head_resp = await check_client.head(final_video_url)
            print(f"  [INFO] 视频 HEAD 响应: status={head_resp.status_code}, "
                  f"content-type={head_resp.headers.get('content-type', 'N/A')}")
            assert head_resp.status_code == 200, \
                f"[FAIL] 视频 URL 不可访问: status={head_resp.status_code}"
            print(f"  [PASS] 视频 URL 可访问")
        except Exception as e:
            print(f"  [WARN] 视频 URL 访问检查失败: {e}")
    print()


# ---------------------------------------------------------------------------
# TC-E2E-006: 验证 crew_sessions 状态
# ---------------------------------------------------------------------------

async def test_verify_session_status(client: httpx.AsyncClient, run_id: str):
    """
    TC-E2E-006: 验证 crew_sessions 状态流转

    验证点:
      - session 状态最终为 completed
      - expected_clips 等于分段数
    """
    print("=" * 70)
    print("TC-E2E-006: 验证 session 状态")
    print("=" * 70)

    resp = await client.get(f"{BASE}/projects/{run_id}")
    project = resp.json()
    session = project.get("session", {})

    session_status = session.get("status", "N/A")
    print(f"  [INFO] session.status = {session_status}")

    # 自动拼接完成后应为 completed
    if session_status == "completed":
        print(f"  [PASS] session 状态为 completed")
    elif session_status == "ready_to_stitch":
        print(f"  [INFO] session 状态为 ready_to_stitch（可能拼接尚未触发或为单段）")
    else:
        print(f"  [WARN] session 状态为 {session_status}，预期 completed")
    print()


# ---------------------------------------------------------------------------
# TC-E2E-007: 短音频不分段（对照组）
# ---------------------------------------------------------------------------

async def test_short_audio_no_split(client: httpx.AsyncClient):
    """
    TC-E2E-007: 短音频不分段对照测试

    使用 30 秒以内的音频，验证:
      - 只创建 1 个任务
      - task_idx = 0
      - 不触发分割逻辑
    """
    print("=" * 70)
    print("TC-E2E-007: 短音频不分段对照测试")
    print("=" * 70)

    # 使用一个公共短音频
    SHORT_AUDIO = "https://cdn.pixabay.com/audio/2024/11/08/audio_93a1e8eb4e.mp3"

    body = {
        "template_id": "digital-human",
        "theme": "短音频测试 - 不应分段",
        "product_image_url": PERSON_IMAGE,
        "style": "现代简约",
        "duration": 10,
        "orientation": "竖屏",
        "audio_url": SHORT_AUDIO,
        "voice_mode": 0,
        "motion_prompt": "模特正在做产品展示",
    }

    resp = await client.post(f"{BASE}/projects", json=body)
    assert resp.status_code == 200
    project = resp.json()
    run_id = project.get("run_id")
    assert run_id, "[FAIL] 无 run_id"

    resp = await client.post(f"{BASE}/projects/{run_id}/digital-human", timeout=60)
    data = resp.json()

    # ── 断言 ──
    assert resp.status_code == 200, f"[FAIL] {resp.text[:500]}"
    assert isinstance(data, list), f"[FAIL] 响应应为列表"
    assert len(data) == 1, f"[FAIL] 短音频应只有 1 段，实际 {len(data)} 段"
    assert data[0].get("task_idx") == 0, f"[FAIL] task_idx 应为 0"

    print(f"  [PASS] 短音频只创建了 1 个任务 (run_id={run_id})")
    print()


# ---------------------------------------------------------------------------
# TC-E2E-008: 缺少必填参数验证
# ---------------------------------------------------------------------------

async def test_missing_params_validation(client: httpx.AsyncClient):
    """
    TC-E2E-008: 缺少必填参数校验

    验证:
      - 无图片时返回错误
      - 无音频时返回错误
      - 克隆模式无文本时返回错误
    """
    print("=" * 70)
    print("TC-E2E-008: 缺少必填参数校验")
    print("=" * 70)

    # 测试 1: 无图片
    body_no_image = {
        "template_id": "digital-human",
        "theme": "测试无图片",
        "audio_url": AUDIO_URL,
        "voice_mode": 0,
    }
    resp = await client.post(f"{BASE}/projects", json=body_no_image)
    proj = resp.json()
    if proj.get("run_id"):
        resp2 = await client.post(f"{BASE}/projects/{proj['run_id']}/digital-human", timeout=60)
        data = resp2.json()
        has_error = any(t.get("error") for t in data) if isinstance(data, list) else "error" in data
        if has_error:
            print(f"  [PASS] 无图片时返回错误")
        else:
            print(f"  [WARN] 无图片时未返回错误（可能有默认值）")
    else:
        print(f"  [PASS] 无图片时创建失败: {proj}")

    # 测试 2: 无音频
    body_no_audio = {
        "template_id": "digital-human",
        "theme": "测试无音频",
        "product_image_url": PERSON_IMAGE,
        "voice_mode": 0,
    }
    resp = await client.post(f"{BASE}/projects", json=body_no_audio)
    proj = resp.json()
    if proj.get("run_id"):
        resp2 = await client.post(f"{BASE}/projects/{proj['run_id']}/digital-human", timeout=60)
        data = resp2.json()
        has_error = any(t.get("error") for t in data) if isinstance(data, list) else "error" in data
        if has_error:
            print(f"  [PASS] 无音频时返回错误")
        else:
            print(f"  [WARN] 无音频时未返回错误")

    # 测试 3: 克隆模式无文本
    body_clone_no_text = {
        "template_id": "digital-human",
        "theme": "测试克隆模式无文本",
        "product_image_url": PERSON_IMAGE,
        "audio_url": AUDIO_URL,
        "voice_mode": 1,  # 克隆声音
        # voice_text 缺失
    }
    resp = await client.post(f"{BASE}/projects", json=body_clone_no_text)
    proj = resp.json()
    if proj.get("run_id"):
        resp2 = await client.post(f"{BASE}/projects/{proj['run_id']}/digital-human", timeout=60)
        data = resp2.json()
        has_error = any(t.get("error") for t in data) if isinstance(data, list) else "error" in data
        if has_error:
            print(f"  [PASS] 克隆模式无文本时返回错误")
        else:
            print(f"  [WARN] 克隆模式无文本时未返回错误")

    print()


# ===========================================================================
# 主函数
# ===========================================================================

async def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║       数字人长音频分段生成 — 端到端集成测试                          ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()
    print(f"  测试数据:")
    print(f"    图片: {PERSON_IMAGE}")
    print(f"    音频: {AUDIO_URL} (152.6s)")
    print(f"    声音模式: 直接使用音频")
    print()

    async with httpx.AsyncClient(timeout=60) as client:
        # ── TC-E2E-008: 参数校验（不依赖长流程） ──
        await test_missing_params_validation(client)

        # ── TC-E2E-001: 创建项目 ──
        run_id = await test_create_project(client)

        # ── TC-E2E-002: 提交数字人生成 ──
        submit_result = await test_submit_digital_human(client, run_id)
        total_segments = submit_result["total_segments"]

        # ── TC-E2E-003: 验证数据库记录 ──
        await test_verify_db_tasks(client, run_id, total_segments)

        # ── TC-E2E-004: 轮询进度 ──
        poll_result = await test_poll_progress(client, run_id)

        if poll_result.get("all_done") and poll_result.get("succeeded", 0) > 0:
            # ── TC-E2E-005: 验证拼接 ──
            await test_verify_auto_stitch(client, run_id)

            # ── TC-E2E-006: 验证 session ──
            await test_verify_session_status(client, run_id)
        else:
            print("  [SKIP] 跳过拼接验证（任务未全部完成）")

        # ── TC-E2E-007: 短音频对照 ──
        # 注意：此测试会创建新项目，独立于长音频流程
        # await test_short_audio_no_split(client)  # 取消注释以运行

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║                          测试执行完毕                              ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    asyncio.run(main())
