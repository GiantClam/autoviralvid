@echo off
chcp 65001 >nul
echo ==========================================
echo 启动数字人视频生成测试环境
echo ==========================================
echo.

REM 检查Python依赖
pip show httpx >nul 2>&1
if errorlevel 1 (
    echo 安装依赖...
    pip install httpx asyncio -q
)

echo ==========================================
echo 测试脚本列表:
echo ==========================================
echo.
echo 1. API直接调用版本 (推荐)
echo    python test_digital_human_api.py
echo.
echo 2. Web界面自动化版本
echo    python test_digital_human_10min_v2.py
echo.
echo 3. 基础Web版本
echo    python test_digital_human_10min.py
echo.
echo ==========================================
echo 快速测试命令:
echo ==========================================
echo.
echo 请确保后端API服务器在 localhost:8123 运行后，执行:
echo.
echo   python test_digital_human_api.py
echo.
echo ==========================================
echo.
pause
