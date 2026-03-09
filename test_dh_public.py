#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import time
import httpx

PHOTO_URL = "https://pub-1e13e40abdc946dcb20809a0dfa60b22.r2.dev/uploads/c5a53ed7_ComfyUI_00011_pcxyj_1764731727.png"
AUDIO_URL = "https://pub-1e13e40abdc946dcb20809a0dfa60b22.r2.dev/uploads/f71b159e_1766630274666746137-348477315510412.mp3"
DURATION = 240  # 4 minutes

print("=" * 60)
print("Digital Human Test - Using Public URLs")
print("=" * 60)

BASE = "http://localhost:8123/api/v1"


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        # Create project
        print("\n[1] Creating project...")
        resp = await client.post(
            f"{BASE}/projects",
            json={
                "template_id": "digital-human",
                "theme": "数字人直播带货测试 - 4分钟视频",
                "product_image_url": PHOTO_URL,
                "style": "现代简约",
                "duration": DURATION,
                "orientation": "竖屏",
                "audio_url": AUDIO_URL,
                "voice_mode": 0,
                "motion_prompt": "模特正在做产品展示，进行电商直播带货",
            },
        )

        if resp.status_code != 200:
            print(f"    ERROR: {resp.status_code} - {resp.text[:200]}")
            return

        project = resp.json()
        run_id = project.get("run_id")
        print(f"    OK: run_id = {run_id}")

        # Submit digital human
        print("\n[2] Submitting digital human task...")
        resp = await client.post(f"{BASE}/projects/{run_id}/digital-human")

        if resp.status_code != 200:
            print(f"    ERROR: {resp.status_code} - {resp.text[:200]}")
            return

        result = resp.json()
        print(f"    OK: status = {result.get('status')}")

        # Poll status
        print("\n[3] Polling status (max 20 minutes)...")
        print("    (4-minute video may take 5-15 minutes)\n")

        max_polls = 40  # 20 minutes
        for i in range(max_polls):
            await asyncio.sleep(30)

            resp = await client.get(f"{BASE}/projects/{run_id}/status")
            status = resp.json()

            total = status.get("tasks_total", 0)
            succeeded = status.get("tasks_summary", {}).get("succeeded", 0)
            pending = status.get("tasks_summary", {}).get("pending", 0)
            failed = status.get("tasks_summary", {}).get("failed", 0)

            minutes = (i + 1) * 30 // 60
            print(
                f"    [{minutes:02d} min] total={total}, succeeded={succeeded}, pending={pending}, failed={failed}"
            )

            if status.get("all_succeeded"):
                print(f"\n    SUCCESS! Video completed!")
                break

            if failed > 0 and pending == 0:
                print(f"\n    FAILED!")
                break

        print("\nDone!")


import asyncio

asyncio.run(main())
