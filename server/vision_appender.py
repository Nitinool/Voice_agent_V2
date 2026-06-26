"""VisionContextAppender —— 在 LLM 运行前把摄像头帧加进 context.

问题：标准 cascade pipeline 里，UserImageRawFrame(append_to_context=True) 从
transport 推下游，要流到 LLMAssistantAggregator（在 LLM 之后）才被加进 context。
导致当轮 LLM 看不到图，下一轮才看到（旧图）。

解法：本 processor 插在 user_aggregator 和 llm 之间，拦截 UserImageRawFrame，
立即调 context.add_image_frame_message 把图加进 context。这样当轮 LLM 运行时
context 里已有图。

触发：bot.py 用 user_aggregator 的 on_user_turn_started 事件推 UserImageRequestFrame
upstream，transport 抓一帧摄像头视频转成 UserImageRawFrame 推回下游，流到这里。
"""

from __future__ import annotations

from loguru import logger

from pipecat.frames.frames import Frame, UserImageRawFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class VisionContextAppender(FrameProcessor):
    """拦截 UserImageRawFrame，在 LLM 运行前把图加进 context."""

    def __init__(self, context: LLMContext):
        super().__init__()
        self._context = context

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserImageRawFrame) and frame.append_to_context:
            try:
                # 先清掉 context 里之前的摄像头图消息（content 是 list 且含 image_url 的
                # user 消息）。每轮只保留最新一张，避免 image 堆积撑爆 context + 旧图干扰。
                self._remove_old_camera_images()
                await self._context.add_image_frame_message(
                    format=frame.format,
                    size=frame.size,
                    image=frame.image,
                    text=frame.text,
                )
                logger.debug(
                    f"VisionContextAppender: appended camera frame to context "
                    f"(size={frame.size})"
                )
            except Exception as e:
                logger.warning(f"VisionContextAppender: failed to append image: {e}")
            # 不再往下游推 —— 避免 assistant_aggregator 重复加图
            return

        await self.push_frame(frame, direction)

    def _remove_old_camera_images(self) -> None:
        """从 context 移除旧的摄像头图消息（content 是 list 含 image_url 的 user 消息）."""
        msgs = self._context.messages
        kept = []
        removed = 0
        for m in msgs:
            if (
                isinstance(m, dict)
                and m.get("role") == "user"
                and isinstance(m.get("content"), list)
                and any(
                    isinstance(p, dict) and p.get("type") == "image_url"
                    for p in m["content"]
                )
            ):
                removed += 1
                continue
            kept.append(m)
        if removed:
            self._context.set_messages(kept)
            logger.debug(f"VisionContextAppender: removed {removed} old camera image(s)")
