"""voice-agent-demo M1 — in-place 多 persona 切换（单连接）.

工作模式：
- 一条 WebRTC 连接，一个 bot 进程，一条 pipeline
- 用户说"小爱同学" → STT 转写 → PersonaRouter 命中 → SessionManager 把 LLMContext
  的 messages 换成小爱的历史 → 推 TTSUpdateSettingsFrame 切 voice → 推 RTVI 通知前端
- 每个 persona 独立对话历史（互不串台），共享一个 LLMContext 对象（只换 messages）
- TTS 用 MiMo TTS（小米 mimo-v2.5-tts），4 个中文预置音色对应 4 个 persona

启动：
    uv run python server\\bot.py -t webrtc
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import FunctionCallResultProperties, LLMRunFrame, UserImageRequestFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from agent_status import AgentStatusManager
from mimo_tts import MimoTTSService
from persona_router import PersonaRouter
from session_manager import SessionManager
from skills.loader import load_skills
from skills.registry import get_active_skill_contents
from tools.registry import get_all_schemas, register_all
from vision_appender import VisionContextAppender

load_dotenv(override=True)

# ============================================================================
# 日志：pipecat.runner.run.main() 内部 logger.remove()，文件 sink 在 bot() 入口加
# ============================================================================
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_FILE_SINK_ADDED = False
_PERSONAS_YAML = Path(__file__).resolve().parent / "personas.yaml"


def _ensure_file_log_sink() -> None:
    global _FILE_SINK_ADDED
    if _FILE_SINK_ADDED:
        return
    logger.add(
        _LOG_DIR / "bot.log",
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
        level="DEBUG",
    )
    _FILE_SINK_ADDED = True


# 开场提示词（user role —— deepseek-v4-pro 推理模型无 user 消息时 completion=0）
GREETING_PROMPTS: dict[str, str] = {
    "initial": "你好，请用一句简短的话向我打招呼并介绍你自己。",
    "welcome_back": (
        "我刚从别的助手那边切换回来找你。请用一句话简短欢迎我回来，"
        "如果你还记得我们刚才聊的内容，可以顺带提一句。"
    ),
    "none": "",
}


def _collect_provider_metadata() -> dict:
    """收集当前后端使用的 LLM / TTS / STT 元信息，供前端 Settings 面板只读展示.

    所有字段均不含 api_key（出于安全考虑），仅 url / model / language 这类
    标识信息. 前端 Settings → Provider 标签页消费这份数据.
    """
    from mimo_tts import DEFAULT_BASE_URL as MIMO_DEFAULT_BASE, MIMO_SAMPLE_RATE

    return {
        "llm": {
            "provider": "OpenAI-compatible",
            "model": os.environ.get("LLM_MODEL", ""),
            "base_url": os.environ.get("LLM_BASE_URL", ""),
        },
        "tts": {
            "provider": "MiMo v2.5",
            "base_url": os.environ.get("MIMO_BASE_URL", MIMO_DEFAULT_BASE),
            "sample_rate": MIMO_SAMPLE_RATE,
        },
        "stt": {
            "provider": "Deepgram",
            "model": "nova-3",
            "language": "zh-CN",
        },
    }


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    # 注册所有结构化工具（builtin/ 下各模块导入时自动 register 到全局 registry）
    register_all()
    # 加载所有 skill（SKILL.md 知识包，注入 system prompt 告诉 LLM 何时用 tool）
    load_skills()
    skill_contents = get_active_skill_contents()
    # SessionManager（先建空 context，让它填 default persona 的 system prompt）
    # skill 内容拼到每个 persona 的 system prompt 末尾（见 _runtime_prompt）
    context = LLMContext()
    sm = SessionManager(_PERSONAS_YAML, context, skill_contents=skill_contents)
    # 前端切会话 reload 时，URL ?session=sid → 连接后发 switch_session（见 SessionActivator）。
    # 这里不靠 requestData 传 session_id（链路不稳），启动时按默认最新会话激活即可，
    # SessionActivator 会在连接后纠正到目标会话。
    # P2: agent 状态管理器，初始时 default persona = online，其余 = idle
    asm = AgentStatusManager(
        agent_names=list(sm.all_names()),
        active_name=sm.active_name,
    )
    logger.info(f"Starting M1 in-place bot, default persona = {sm.active.display_name}")

    # STT
    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramSTTService.Settings(
            model="nova-3",
            language=Language.ZH_CN,
            interim_results=True,
        ),
    )

    # TTS（MiMo，初始 voice = default persona 的中文音色名）
    tts = MimoTTSService(
        api_key=os.environ["MIMO_API_KEY"],
        settings=MimoTTSService.Settings(voice=sm.active.tts_voice_id),
    )

    # LLM（不设 system_instruction，prompt 由 messages 第一项承载，避免重复警告）
    llm = OpenAILLMService(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        settings=OpenAILLMService.Settings(model=os.environ["LLM_MODEL"]),
    )

    # Aggregators（VAD 调严防误打断 —— 替代之前的 InputGate）
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.8,
                    min_volume=0.8,
                    start_secs=0.2,
                    stop_secs=0.2,
                )
            )
        ),
    )

    router = PersonaRouter(sm, asm)

    # vision：用户开始说话时，往上游推 UserImageRequestFrame，让 transport 抓一帧
    # 摄像头视频加进 LLM context（append_to_context=True）。这样 LLM 回答时能看画面。
    # 用 user_aggregator 的 on_user_turn_started 事件触发（VAD 在 aggregator 内部，
    # PersonaRouter 在它上游收不到 UserStartedSpeakingFrame）。
    # 参考 pipecat smallwebrtc transport 的 request_participant_image 机制。
    @user_aggregator.event_handler("on_user_turn_started")
    async def on_user_turn_started(aggregator, strategy):
        req = UserImageRequestFrame(
            user_id="",
            text="（用户当前的摄像头画面）",
            append_to_context=True,
            video_source="camera",
        )
        await aggregator.push_frame(req, FrameDirection.UPSTREAM)
        logger.debug("Vision: requested camera frame at user turn start")

    # handoff_to：persona 交接工具。闭包捕获 router/sm。
    # 时序设计（解决"转交话被记成 target 说的"问题）：
    #   LLM 输出 content + tool_call 是并发的，content 的 TTS 和 tool 执行会抢，
    #   工具切 voice 会抢在豆包 TTS 播放前 → 转交话用了 target 的 voice/身份。
    #   解法：不让当前 persona 说转交话（prompt 约束），工具直接切 + 触发 target，
    #   由 target 的 prompt 引导它先说一句承接（"豆包让我来回答…"）。
    # run_llm=False：当前 persona 不再生成工具后回合（否则会补一句）。
    async def handoff_to(params: FunctionCallParams, target: str, question: str) -> None:
        """把用户的问题转交给另一个更合适的助手回答。

        当用户的问题超出你当前助手的擅长领域时调用此工具。调用此工具时不要输出任何文字，
        直接调用即可，目标助手会主动开口承接并回答。

        Args:
            target: 目标助手名，必须是以下之一：doubao（豆包）、xiaoai（小爱同学）、siri（Siri）、deepseek（DeepSeek）。不能填自己。
            question: 要转交给目标助手的问题，原样转述用户的问题。
        """
        valid = {"doubao", "xiaoai", "siri", "deepseek"}
        if target not in valid:
            await params.result_callback(
                {"error": f"无效的目标助手「{target}」，可选：{','.join(sorted(valid))}"},
                properties=FunctionCallResultProperties(run_llm=False),
            )
            return
        if target == sm.active_name:
            await params.result_callback(
                {"handed_off": False, "reason": f"{target} 已经是当前助手"},
                properties=FunctionCallResultProperties(run_llm=False),
            )
            return
        # 记下转交来源（switch 后 active 就变成 target 了，先存）
        from_display = sm.active.display_name
        # 1. 会话内切到 target（换 system 头 + 切 TTS voice + 通知前端，不丢历史）
        cfg = await router.switch_to(target, triggered_by="handoff")
        if cfg is None:
            await params.result_callback(
                {"error": f"切换到 {target} 失败"},
                properties=FunctionCallResultProperties(run_llm=False),
            )
            return
        # 2. 把问题作为干净的 user 消息灌进 context（此时 system 头已是 target 的 prompt）
        #    [转交自XX] 前缀让 target 知道是转交来的，prompt 引导它先承接再答。
        #    persona 由 _sync_context_to_session 自动标成当前 active（=target），符合预期。
        sm.context.add_message(
            {"role": "user", "content": f"[转交自{from_display}] {question}"}
        )
        # 3. 触发 target 的 LLM 回答
        await params.llm.push_frame(LLMRunFrame())
        # 4. 当前（原）persona 不再说话
        await params.result_callback(
            {"handed_off": True, "to": target, "display_name": cfg.display_name},
            properties=FunctionCallResultProperties(run_llm=False),
        )

    # 注册所有 tool 到 context：registry 里的结构化 tool + handoff_to（闭包工具，暂留此处）
    context.set_tools([*get_all_schemas(), handoff_to])

    # vision：在 LLM 前拦截摄像头帧加进 context（标准 pipeline 里图要到 LLM 后才进 context，
    # 本 processor 让当轮 LLM 就能看到画面）
    vision_appender = VisionContextAppender(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            router,            # 唤醒名检测 + 切 persona
            user_aggregator,
            vision_appender,   # 摄像头帧 → context（LLM 前）
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    async def _broadcast_sessions_update(worker, sm):
        """把最新会话列表 + active 会话推给前端，前端刷新会话栏."""
        await worker.queue_frames(
            [
                RTVIServerMessageFrame(
                    data={
                        "type": "sessions_update",
                        "sessions": sm.list_sessions(),
                        "active_session_id": sm.active_session_id,
                        "active_persona": sm.active_name,
                    }
                )
            ]
        )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected, persona={sm.active.display_name}")
        # P2: 先推一次 agent 状态全量快照，让前端拿到初始状态
        await worker.queue_frames(
            [RTVIServerMessageFrame(data=asm.snapshot())]
        )
        # 推当前会话列表 + active 会话元数据，前端用来渲染会话栏
        await worker.queue_frames(
            [
                RTVIServerMessageFrame(
                    data={
                        "type": "sessions_update",
                        "sessions": sm.list_sessions(),
                        "active_session_id": sm.active_session_id,
                        "active_persona": sm.active_name,
                    }
                )
            ]
        )
        # 会话历史回放：从会话缓存取（带 persona 字段），排除 system/greeting prompt
        msgs = sm._sessions.get(sm.active_session_id, [])
        replay = []
        skipped_greeting = False
        for m in msgs:
            if not isinstance(m, dict):
                continue
            if m.get("role") not in ("user", "assistant"):
                continue
            content = m.get("content", "")
            # content 可能是 list（vision image 消息 / tool_calls 的 None）——提取文本部分，
            # 非 string 一律转成可显示文本或跳过
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = " ".join(text_parts).strip()
            if not isinstance(content, str) or not content:
                continue
            if (
                not skipped_greeting
                and m.get("role") == "user"
                and content in GREETING_PROMPTS.values()
            ):
                skipped_greeting = True
                continue
            replay.append({"role": m["role"], "content": content, "persona": m.get("persona", sm.active_name)})
        if replay:
            await worker.queue_frames(
                [RTVIServerMessageFrame(data={"type": "history_replay", "messages": replay})]
            )
            logger.info(f"Replayed {len(replay)} history messages")

        # 没有真实对话历史则开场打招呼；有历史则接着聊
        has_real_history = len(replay) > 0
        if not has_real_history:
            context.add_message(
                {"role": "user", "content": GREETING_PROMPTS["initial"]}
            )
            await worker.queue_frames([LLMRunFrame()])

    # P3.1 / P6 / 会话管理: 前端 client message 路由
    # set_persona       → 会话内切 persona（换 system 头 + voice，不丢历史）
    # get_config        → persona 配置 + provider 元信息
    # update_config     → persona 配置 override
    # list_sessions     → 会话列表
    # new_session       → 新建会话
    # switch_session    → 切换会话
    # delete_session    → 删除会话
    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        msg_type = getattr(message, "type", None)
        msg_data = message.data or {}

        if msg_type == "set_persona":
            target = msg_data.get("persona")
            if not target:
                return
            logger.info(f"Received set_persona client message: {target}")
            await router.switch_to(target, triggered_by="frontend click")
            return

        if msg_type == "get_config":
            payload = {
                "personas_default": {k: v.__dict__ for k, v in sm.defaults().items()},
                "personas_current": {k: v.__dict__ for k, v in sm.current().items()},
                "active_persona": sm.active_name,
                "default_persona": sm._default_persona,
                "provider": _collect_provider_metadata(),
            }
            await rtvi.send_server_response(message, payload)
            return

        if msg_type == "update_config":
            applied = sm.apply_overrides(msg_data.get("personas", {}))
            logger.info(f"Applied persona overrides: {applied}")
            await rtvi.send_server_response(message, {"ok": True, "applied": applied})
            return

        # ----- 会话管理 -----
        if msg_type == "list_sessions":
            await rtvi.send_server_response(
                message,
                {
                    "sessions": sm.list_sessions(),
                    "active_session_id": sm.active_session_id,
                    "active_persona": sm.active_name,
                },
            )
            return

        if msg_type == "new_session":
            persona = msg_data.get("persona")
            meta = sm.new_session(persona)
            logger.info(f"New session created: {meta.session_id}")
            # 切 voice + 通知前端
            await router.switch_to(meta.active_persona, triggered_by="new_session")
            await _broadcast_sessions_update(worker, sm)
            await rtvi.send_server_response(message, {"ok": True, "session": meta.to_dict()})
            return

        if msg_type == "switch_session":
            sid = msg_data.get("session_id")
            if not sid:
                await rtvi.send_server_response(message, {"ok": False, "error": "no session_id"})
                return
            meta = sm.switch_session(sid)
            if meta is None:
                await rtvi.send_server_response(message, {"ok": False, "error": "session not found"})
                return
            logger.info(f"Switched to session {sid}")
            # 切 voice + 通知前端
            await router.switch_to(meta.active_persona, triggered_by="switch_session")
            await _broadcast_sessions_update(worker, sm)
            await rtvi.send_server_response(message, {"ok": True, "session": meta.to_dict()})
            return

        if msg_type == "delete_session":
            sid = msg_data.get("session_id")
            if not sid:
                await rtvi.send_server_response(message, {"ok": False, "error": "no session_id"})
                return
            ok = sm.delete_session(sid)
            if not ok:
                await rtvi.send_server_response(message, {"ok": False, "error": "session not found"})
                return
            logger.info(f"Deleted session {sid}")
            # 删除可能触发 active 会话切换，同步 voice + 通知前端
            await router.switch_to(sm.active_name, triggered_by="delete_session")
            await _broadcast_sessions_update(worker, sm)
            await rtvi.send_server_response(message, {"ok": True})
            return

        if msg_type == "rename_session":
            sid = msg_data.get("session_id")
            title = msg_data.get("title")
            if not sid or title is None:
                await rtvi.send_server_response(message, {"ok": False, "error": "need session_id and title"})
                return
            meta = sm.rename_session(sid, str(title))
            if meta is None:
                await rtvi.send_server_response(message, {"ok": False, "error": "session not found"})
                return
            await _broadcast_sessions_update(worker, sm)
            await rtvi.send_server_response(message, {"ok": True, "session": meta.to_dict()})
            return

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        # 持久化当前会话，下次重连能恢复
        sm.persist_active()
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    _ensure_file_log_sink()
    if not isinstance(runner_args, SmallWebRTCRunnerArguments):
        logger.error(f"Unsupported runner args type: {type(runner_args)}")
        return
    transport: SmallWebRTCTransport = SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=True,  # 接收用户摄像头视频，供 vision LLM 看画面
        ),
    )
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
