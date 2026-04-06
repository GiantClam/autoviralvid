# 数字人视频生成测试

本项目提供多种测试脚本，用于测试生成长达10分钟的数字人视频。

## 测试文件说明

### 输入文件
- **照片**: `C:\Users\liula\Downloads\ComfyUI_00011_pcxyj_1764731727.png`
- **音频**: `C:\Users\liula\Downloads\1766630274666746137-348477315510412.mp3`
- **目标时长**: 600秒 (10分钟)
- **视频方向**: 竖屏 (9:16)

### 测试脚本

#### 1. API直接调用版本 (推荐) ⭐
**文件**: `test_digital_human_api.py`

最稳定可靠的测试方式，直接调用后端API，不需要浏览器自动化。

```bash
# 确保后端API服务器在 localhost:8123 运行
cd agent
python main.py

# 运行测试
python test_digital_human_api.py
```

**特点**:
- 自动启动本地文件服务器提供图片/音频文件
- 直接调用API创建项目和提交任务
- 自动轮询任务状态直到完成
- 支持最长30分钟的轮询等待
- 实时显示进度

#### 2. Web界面自动化版本
**文件**: `test_digital_human_10min_v2.py`

通过Playwright控制浏览器，模拟真实用户操作Web界面。

```bash
# 确保前后端都在运行
npm run dev  # 启动前端
python agent/main.py  # 启动后端

# 安装Playwright
pip install playwright
playwright install chromium

# 运行测试
python test_digital_human_10min_v2.py
```

**特点**:
- 完整模拟用户操作流程
- 自动截图记录每个步骤
- 可视化查看测试过程
- 每分钟自动保存进度截图

#### 3. 简单Web版本
**文件**: `test_digital_human_10min.py`

基础版本的Web自动化测试。

## 快速开始

### 方法一：使用API版本（推荐）

1. **启动后端服务器**:
```bash
cd D:\github\with-langgraph-fastapi\agent
python main.py
```

2. **运行测试脚本**:
```bash
cd D:\github\with-langgraph-fastapi
python test_digital_human_api.py
```

3. **等待完成**:
- 脚本会自动创建项目
- 提交数字人视频生成任务
- 轮询任务状态直到完成
- 10分钟视频预计需要15-30分钟生成

### 方法二：使用Web自动化版本

1. **启动前后端**:
```bash
# 终端1: 启动前端
cd D:\github\with-langgraph-fastapi
npm run dev

# 终端2: 启动后端
cd D:\github\with-langgraph-fastapi\agent
python main.py
```

2. **运行测试**:
```bash
python test_digital_human_10min_v2.py
```

3. **观察测试过程**:
- 浏览器会自动打开
- 自动选择"数字人口播"模板
- 填写表单并提交
- 自动截图记录进度

## 测试输出

测试完成后会生成以下文件：

### API版本
- 控制台输出完整的任务状态
- 视频URL（生成成功后显示）

### Web版本
- `test_01_homepage.png` - 首页截图
- `test_02_template_selected.png` - 模板选择后截图
- `test_form_filled.png` - 表单填写完成截图
- `test_03_submitted.png` - 提交后截图
- `test_progress_XXmin.png` - 每分钟进度截图
- `test_completed.png` / `test_failed.png` - 最终结果
- `test_final_result.png` - 完整页面截图

## 配置参数

### 视频参数
```python
{
    "template_id": "digital-human",
    "theme": "数字人直播带货演示 - 10分钟长视频测试",
    "duration": 600,  # 10分钟
    "orientation": "竖屏",
    "aspect_ratio": "9:16",
    "voice_mode": 0,  # 直接使用音频
    "motion_prompt": "专业主播进行产品介绍..."
}
```

### 等待时间配置
- 最大轮询次数: 360次 (默认)
- 轮询间隔: 10秒
- 总等待时间: 约60分钟

可根据需要修改脚本中的参数。

## 故障排除

### 问题1: 文件服务器启动失败
**解决方案**: 检查端口8765是否被占用，或修改脚本中的`FILE_SERVER_PORT`

### 问题2: API连接失败
**解决方案**: 
- 确认后端服务器运行在 `localhost:8123`
- 检查防火墙设置
- 查看后端日志确认服务正常

### 问题3: Web界面找不到元素
**解决方案**:
- 确认前端运行在 `localhost:3000`
- 检查页面是否完全加载（增加等待时间）
- 查看截图了解页面状态

### 问题4: 生成时间过长
**说明**: 10分钟视频生成需要较长时间，这是正常的。系统会自动分段处理长视频。

## 技术细节

### 系统架构
```
测试脚本 -> API/Web界面 -> LangGraph Agent -> MiniMax API
                ↓
        本地文件服务器 (localhost:8765)
```

### 工作流程
1. 启动本地文件服务器，提供图片/音频文件的HTTP访问
2. 创建数字人项目，配置600秒时长
3. 提交数字人视频生成任务
4. 轮询任务状态直到完成
5. 输出视频URL或错误信息

## 依赖安装

```bash
# API版本依赖（通常已安装）
pip install httpx asyncio

# Web版本额外依赖
pip install playwright
playwright install chromium
```

## 联系与支持

如遇到问题，请检查：
1. 前后端服务是否正常运行
2. 文件路径是否正确
3. 网络连接是否正常
4. 查看生成的截图了解详细状态
