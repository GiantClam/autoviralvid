#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试API - 使用开发模式token
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import asyncio
import httpx

BASE = "http://localhost:8123/api/v1"


async def test_api():
    print("测试API访问...")

    # 使用dev用户（开发模式）
    dev_token = "dev-user"

    async with httpx.AsyncClient(timeout=60) as client:
        # 测试获取项目列表
        print("\n1. 获取项目列表...")
        resp = await client.get(
            f"{BASE}/projects", headers={"Authorization": f"Bearer {dev_token}"}
        )
        print(f"   状态: {resp.status_code}")
        print(f"   响应: {resp.text[:200]}")

        # 测试创建项目
        print("\n2. 创建项目...")
        resp = await client.post(
            f"{BASE}/projects",
            headers={"Authorization": f"Bearer {dev_token}"},
            json={"template_id": "product-ad", "theme": "测试项目", "duration": 10},
        )
        print(f"   状态: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"   项目ID: {data.get('run_id')}")
            return data.get("run_id")
        else:
            print(f"   错误: {resp.text[:200]}")


asyncio.run(test_api())
