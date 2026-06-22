# Voice Agent Demo

多 persona 语音交互演示，基于 [pipecat](https://github.com/pipecat-ai/pipecat) 构建。

> 📋 详细规划见 [`PROJECT_PLAN.md`](./PROJECT_PLAN.md)。
> 当前状态：**M0 — 单 persona 中文对话验证**

## 当前可跑的内容

只有一个 persona「豆包」，用来验证三件事：
1. cix AIhub 网关 + deepseek-v4-pro 通否
2. Deepgram 中文 STT 准确度
3. Cartesia 默认声音的中文 TTS 效果

## 运行步骤（Windows PowerShell）

```powershell
# 1. 装依赖
uv sync

# 2. 确认 .env 已填好（已有，从 API_key.txt 自动生成）
Get-Content .env

# 3. 启动机器人（webrtc 模式）
#    Windows 强制 UTF-8 编码，否则 pipecat 启动横幅里的 emoji 会让 Python 崩溃
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
uv run python server\bot.py -t webrtc

# 4. 浏览器访问
#    http://localhost:7860
#    点击页面上的连接按钮，授权麦克风后开始对话
```

## 验收清单（M0）

- [ ] 服务器启动无报错
- [ ] 浏览器能连上 WebRTC
- [ ] 客户端连接后豆包**用中文**主动开场介绍自己
- [ ] 用户对豆包说一句中文 → 1 秒内 STT 出文本（看后端日志）
- [ ] 豆包流式 TTS 回复（无明显卡顿）
- [ ] 中文发音可懂程度评估（≥70% 字能听明白即接受，否则切 MiniMax）

## 已知遗留 / 下一步

- M1：从 `personas.yaml` 加载 4 个 persona + PersonaRouter
- M2：全局摘要
- M3：Voice UI Kit 接入
- M4：演示打磨

## 常见问题

**问：浏览器报麦克风权限错？**
答：Windows 端要确保 chrome 已授权麦克风权限；`localhost` 默认会被当作安全上下文，不需要 https。

**问：日志里有 `Cartesia voice doesn't support zh` 警告？**
答：占位 voice 是英语的，Cartesia 仍会勉强吐字但发音不准。M0 验收阶段就是要看这一点 —— 太差就换 voice 或换 provider。

**问：deepseek-v4-pro 报 unauthorized？**
答：检查 `.env` 里 `LLM_API_KEY` / `LLM_BASE_URL` 是否正确。

## 实时看后端日志

bot.py 通过 loguru 同时把日志写到 `logs/bot.log`（UTF-8，按 10MB 滚动）。在另一个 PowerShell 终端：

```powershell
cd D:\Programs\voice-agent-demo
Get-Content logs\bot.log -Wait -Tail 50
```

或者直接用 VS Code 打开 `logs/bot.log`，VS Code 会自动监听新增内容。



#### 启动命令
cd D:\Programs\voice-agent-demo
uv run python server\bot.py -t webrtc