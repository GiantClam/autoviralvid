"""
Pytest 配置：确保 agent/ 在 sys.path 中，
使得 from src.xxx import ... 可以正常工作。
"""

import os
import sys

# 将 agent/ 目录加入 sys.path
agent_dir = os.path.join(os.path.dirname(__file__), "..")
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)
