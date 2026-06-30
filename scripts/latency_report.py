"""scripts/latency_report.py — 从 bot.log 解析交互延迟，按状态分组统计.

用法：
    uv run python scripts/latency_report.py [bot.log 路径]

解析 pipecat metrics 日志，提取：
  - STT/LLM/TTS 各自 TTFB + processing time
  - LLM prompt tokens（context 大小指标）
  - 端到端：Generating chat → Bot started speaking（LLM 启动到开口）
  - 按是否含 image / 是否有工具调用 分组对比

输出：终端表格 + 各分组平均值。
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# loguru 行格式：2026-06-29 11:49:44.425 | DEBUG | module:func:line - 消息
_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) \| (\w+)\s*\| ([^|]+?) - (.+)$"
)

# metrics
_TTFB_RE = re.compile(r"(OpenAILLMService|MimoTTSService|DeepgramSTTService)#\d+ TTFB: ([\d.]+)s")
_PROC_RE = re.compile(
    r"(OpenAILLMService|MimoTTSService|DeepgramSTTService)#\d+ processing time: ([\d.]+)s"
)
_USAGE_RE = re.compile(
    r"prompt tokens: (\d+), completion tokens: (\d+), reasoning tokens: (\d+)"
)
_GEN_RE = re.compile(r"OpenAILLMService#\d+: Generating chat from context")
_BOT_SPEAK_RE = re.compile(r"Bot started speaking")
_USER_STOP_RE = re.compile(r"User stopped speaking")


def _ts(s: str) -> float:
    """日志时间字符串 → epoch 秒."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f").timestamp()


@dataclass
class Turn:
    """一次 LLM 推理回合（从 Generating chat 到对应 metrics）."""
    gen_ts: float  # Generating chat 时间
    has_image: bool = False
    has_tool_call: bool = False
    llm_ttfb: float | None = None
    llm_proc: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    bot_speak_ts: float | None = None  # 之后最近一次 Bot started speaking


def parse(path: Path) -> list[Turn]:
    turns: list[Turn] = []
    cur: Turn | None = None
    pending_user_stop: float | None = None

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _LINE_RE.match(line)
            if not m:
                continue
            ts_str, _level, _src, msg = m.groups()
            try:
                ts = _ts(ts_str)
            except ValueError:
                continue

            # Generating chat → 新回合
            if _GEN_RE.search(msg):
                if cur:
                    turns.append(cur)
                cur = Turn(gen_ts=ts, has_image="'image_url'" in msg, has_tool_call="'tool_calls'" in msg)
                continue

            # 在 cur 回合里收集 metrics
            if cur is not None:
                t = _TTFB_RE.search(msg)
                if t:
                    svc, val = t.group(1), float(t.group(2))
                    if svc == "OpenAILLMService" and cur.llm_ttfb is None:
                        cur.llm_ttfb = val
                    continue
                p = _PROC_RE.search(msg)
                if p:
                    svc, val = p.group(1), float(p.group(2))
                    if svc == "OpenAILLMService" and cur.llm_proc is None:
                        cur.llm_proc = val
                    continue
                u = _USAGE_RE.search(msg)
                if u and cur.prompt_tokens is None:
                    cur.prompt_tokens = int(u.group(1))
                    cur.completion_tokens = int(u.group(2))
                    cur.reasoning_tokens = int(u.group(3))
                    continue

            # Bot started speaking → 归给最近的 cur（且未记 speak_ts）
            if _BOT_SPEAK_RE.search(msg) and cur is not None and cur.bot_speak_ts is None:
                cur.bot_speak_ts = ts
                turns.append(cur)
                cur = None
                continue

    if cur:
        turns.append(cur)
    return turns


def _avg(xs: list[float | None]) -> str:
    vals = [x for x in xs if x is not None]
    if not vals:
        return "—"
    return f"{sum(vals) / len(vals):.2f}s"


def _avg_int(xs: list[int | None]) -> str:
    vals = [x for x in xs if x is not None]
    if not vals:
        return "—"
    return f"{sum(vals) / len(vals):.0f}"


def report(turns: list[Turn]) -> None:
    if not turns:
        print("没有解析到任何 LLM 回合")
        return

    print(f"\n=== 共 {len(turns)} 个 LLM 回合 ===\n")

    # 明细表
    print(f"{'#':>3} {'image':>6} {'tool':>5} {'tokens':>7} {'LLM_TTFB':>9} {'LLM_proc':>9} {'→开口':>8}")
    print("-" * 55)
    for i, t in enumerate(turns, 1):
        e2e = (t.bot_speak_ts - t.gen_ts) if t.bot_speak_ts else None
        print(
            f"{i:>3} {'Y' if t.has_image else 'N':>6} {'Y' if t.has_tool_call else 'N':>5} "
            f"{t.prompt_tokens or 0:>7} {_f(t.llm_ttfb):>9} {_f(t.llm_proc):>9} {_f(e2e):>8}"
        )

    # 分组统计
    def group(label: str, pred):
        sub = [t for t in turns if pred(t)]
        if not sub:
            return
        print(f"\n--- {label}（{len(sub)} 回合）---")
        print(f"  LLM TTFB 平均: {_avg([t.llm_ttfb for t in sub])}")
        print(f"  LLM 处理时间 平均: {_avg([t.llm_proc for t in sub])}")
        print(f"  prompt tokens 平均: {_avg_int([t.prompt_tokens for t in sub])}")
        e2e = [t.bot_speak_ts - t.gen_ts for t in sub if t.bot_speak_ts]
        print(f"  Generating→开口 平均: {_avg(e2e)}")

    print("\n=== 分组对比 ===")
    group("含 image", lambda t: t.has_image)
    group("无 image", lambda t: not t.has_image)
    group("含 tool_call", lambda t: t.has_tool_call)
    group("无 tool_call", lambda t: not t.has_tool_call)
    group("全部", lambda t: True)


def _f(v: float | None) -> str:
    return f"{v:.2f}s" if v is not None else "—"


if __name__ == "__main__":
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs/bot.log")
    if not log_path.exists():
        print(f"日志不存在: {log_path}")
        sys.exit(1)
    turns = parse(log_path)
    report(turns)
