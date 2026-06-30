"""latency_observer.py — 扩展官方 UserBotLatencyObserver，多收 processing + token 用量.

官方 observer 只收 TTFB + text aggregation，漏了两个关键指标：
  - ProcessingMetricsData（LLM processing time，含 reasoning 的隐性成本）
  - LLMUsageMetricsData（prompt/completion/reasoning tokens）

本 observer 继承官方，重写 _handle_metrics_frame 多收这两个，breakdown 里带上。
"""

from __future__ import annotations

from pipecat.metrics.metrics import LLMUsageMetricsData, ProcessingMetricsData
from pipecat.observers.user_bot_latency_observer import (
    LatencyBreakdown,
    TTFBBreakdownMetrics,
    UserBotLatencyObserver,
)
from pydantic import BaseModel, Field

from loguru import logger


class ProcessingBreakdownMetrics(BaseModel):
    """单个 service 的 processing time（生成完整回复耗时，含 reasoning）."""
    processor: str
    model: str | None = None
    start_time: float
    duration_secs: float


class UsageBreakdownMetrics(BaseModel):
    """LLM token 用量（reasoning_tokens 是隐性延迟成本）."""
    processor: str
    model: str | None = None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int | None = None


class ExtendedLatencyBreakdown(LatencyBreakdown):
    """扩展 breakdown：加 processing + usage."""
    processing: list[ProcessingBreakdownMetrics] = Field(default_factory=list)
    usage: list[UsageBreakdownMetrics] = Field(default_factory=list)

    def chronological_events(self) -> list[str]:
        """时间线（含 processing + usage）."""
        events: list[tuple] = []
        if self.user_turn_start_time is not None and self.user_turn_secs is not None:
            events.append((self.user_turn_start_time, f"User turn: {self.user_turn_secs:.3f}s"))
        for t in self.ttfb:
            events.append((t.start_time, f"{t.processor}: TTFB {t.duration_secs:.3f}s"))
        for p in self.processing:
            events.append((p.start_time, f"{p.processor}: processing {p.duration_secs:.3f}s"))
        for fc in self.function_calls:
            events.append((fc.start_time, f"工具 {fc.function_name}: {fc.duration_secs:.3f}s"))
        if self.text_aggregation:
            ta = self.text_aggregation
            events.append((ta.start_time, f"{ta.processor}: 文本聚合 {ta.duration_secs:.3f}s"))
        events.sort(key=lambda e: e[0])
        return [label for _, label in events]


class ExtendedLatencyObserver(UserBotLatencyObserver):
    """扩展官方 observer，多收 ProcessingMetricsData + LLMUsageMetricsData."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 额外累加器
        self._processing: list[ProcessingBreakdownMetrics] = []
        self._usage: list[UsageBreakdownMetrics] = []

    def _reset_accumulators(self):
        super()._reset_accumulators()
        self._processing = []
        self._usage = []

    def _handle_metrics_frame(self, frame):
        """重写：除了官方的 TTFB + text aggregation，多收 processing + usage."""
        # 先调官方逻辑收 TTFB + text aggregation
        super()._handle_metrics_frame(frame)

        # 判断是否在测量窗口内（跟官方一样）
        waiting_for_first_speech = (
            self._client_connected_time is not None and not self._first_bot_speech_measured
        )
        if self._user_stopped_time is None and not waiting_for_first_speech:
            return

        import time
        now = time.time()
        for metrics_data in frame.data:
            if isinstance(metrics_data, ProcessingMetricsData) and metrics_data.value > 0:
                self._processing.append(
                    ProcessingBreakdownMetrics(
                        processor=metrics_data.processor,
                        model=metrics_data.model,
                        start_time=now - metrics_data.value,
                        duration_secs=metrics_data.value,
                    )
                )
            elif isinstance(metrics_data, LLMUsageMetricsData):
                usage = metrics_data.value  # LLMTokenUsage 对象
                self._usage.append(
                    UsageBreakdownMetrics(
                        processor=metrics_data.processor,
                        model=metrics_data.model,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        reasoning_tokens=usage.reasoning_tokens,
                    )
                )

    async def _handle_bot_started_speaking(self):
        """重写：发出扩展版 breakdown（带 processing + usage）."""
        # 复用官方的触发判断逻辑，但发出 ExtendedLatencyBreakdown
        emit_breakdown = False

        if self._client_connected_time is not None and not self._first_bot_speech_measured:
            self._first_bot_speech_measured = True
            import time
            latency = time.time() - self._client_connected_time
            await self._call_event_handler("on_first_bot_speech_latency", latency)
            emit_breakdown = True

        if self._user_stopped_time is not None:
            import time
            latency = time.time() - self._user_stopped_time
            self._user_stopped_time = None
            await self._call_event_handler("on_latency_measured", latency)
            emit_breakdown = True

        if emit_breakdown:
            breakdown = ExtendedLatencyBreakdown(
                ttfb=list(self._ttfb),
                text_aggregation=self._text_aggregation,
                user_turn_start_time=self._user_turn_start_time,
                user_turn_secs=self._user_turn,
                function_calls=list(self._function_call_metrics),
                processing=list(self._processing),
                usage=list(self._usage),
            )
            await self._call_event_handler("on_latency_breakdown", breakdown)
            self._reset_accumulators()
