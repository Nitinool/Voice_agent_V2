"""会话管理（会话与 persona 解耦版）.

核心模型：
- **会话**是独立实体，每个会话有唯一 session_id、自己的 messages 历史、自己的
  active_persona。一个会话内可以 handoff 切换发言 persona，但历史不丢。
- **persona** 只是会话内的"当前发言身份"，切换 persona 不换历史，只换 system_prompt
  头 + TTS voice。
- pipeline 共享一个 LLMContext 对象，切换会话时 set_messages 整体替换（不换对象），
  这样 user/assistant aggregator 持有的引用始终有效。

message 格式（存储，带 persona 标记）：
    {"role": "user", "content": "...", "persona": "doubao"}
    {"role": "assistant", "content": "...", "persona": "doubao"}
灌进 LLMContext 前剥掉 persona 字段（OpenAI API 不要未知字段）。

持久化：
    data/sessions/index.json   会话列表元数据
    data/sessions/<sid>.json   单会话完整数据（含 messages）
文件损坏一律当空，不崩。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from pipecat.processors.aggregators.llm_context import LLMContext


@dataclass
class PersonaConfig:
    name: str
    display_name: str
    aliases: list[str]
    color: str
    avatar: str
    tts_voice_id: str
    system_prompt: str


@dataclass
class SessionMeta:
    """会话元数据（index.json 里每条）。"""
    session_id: str
    title: str
    active_persona: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "active_persona": self.active_persona,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SessionMeta":
        return cls(
            session_id=str(d.get("session_id", "")),
            title=str(d.get("title", "新会话")),
            active_persona=str(d.get("active_persona", "")),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
        )


# message 里发给 LLM 时要剥掉的非标准字段
_NON_LLM_FIELDS = ("persona", "_identity_hint")


def _strip_for_llm(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """剥掉 message 里的非 LLM 字段（如 persona），返回可发给 LLM 的干净 messages."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        out.append({k: v for k, v in m.items() if k not in _NON_LLM_FIELDS})
    return out


class SessionManager:
    def __init__(
        self,
        config_path: Path,
        llm_context: LLMContext,
        data_dir: Path | None = None,
        skill_contents: str = "",
    ):
        self._context: LLMContext = llm_context
        self._skill_contents: str = skill_contents
        self._configs: dict[str, PersonaConfig] = {}
        # 出厂默认值（personas.yaml 加载时快照），供前端 "reset" 用，运行时不可变
        self._defaults: dict[str, PersonaConfig] = {}
        self._default_persona: str = ""
        # 会话：session_id -> messages（带 persona 字段，内存缓存）
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        # 会话元数据列表（按 updated_at 降序，最新的在前）
        self._session_metas: list[SessionMeta] = []
        # 当前 active 会话
        self._active_session_id: str = ""
        # 当前 active persona（会话内的发言身份）
        self._active_persona: str = ""

        self._sessions_dir: Path = data_dir or (config_path.parent.parent / "data" / "sessions")
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._sessions_dir / "index.json"

        self._load_config(config_path)
        self._load_sessions_index()
        # 启动时激活最新会话（或新建一个空会话）
        self._activate_initial_session()

    # ===================== 配置加载 =====================

    def _load_config(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for name, raw in data["personas"].items():
            cfg = PersonaConfig(
                name=name,
                display_name=raw["display_name"],
                aliases=raw["aliases"],
                color=raw["color"],
                avatar=raw["avatar"],
                tts_voice_id=raw["tts_voice_id"],
                system_prompt=raw["system_prompt"].strip(),
            )
            self._configs[name] = cfg
            self._defaults[name] = PersonaConfig(**cfg.__dict__)
        self._default_persona = data.get("default_persona", next(iter(self._configs)))
        if self._default_persona not in self._configs:
            raise ValueError(f"default_persona '{self._default_persona}' not found")
        self._default_persona = data.get("default_persona", next(iter(self._configs)))
        if self._default_persona not in self._configs:
            raise ValueError(f"default_persona '{self._default_persona}' not found")
        logger.info(
            f"SessionManager loaded {len(self._configs)} personas, "
            f"default = {self._configs[self._default_persona].display_name}"
        )

    def _runtime_prompt(self, persona: str, with_hint: bool = False) -> str:
        """构造运行时 system prompt：原始 prompt + skill 内容 +（可选）身份提示.

        skill 内容（tool 使用说明）拼到原始 prompt 末尾，所有 persona 共享。
        with_hint=True 时再追加身份提示（persona 切换时用，覆盖旧历史身份影响）。
        """
        display = self._configs[persona].display_name
        content = self._configs[persona].system_prompt + self._skill_contents
        if with_hint:
            content += (
                f"\n\n注意：从现在起你是{display}。之前的对话可能由其他助手产生，"
                f"请忽略它们的身份和口吻，始终以{display}的身份和风格回答。"
            )
        return content

    def _initial_messages_for(self, persona: str) -> list[dict[str, Any]]:
        """某 persona 的初始化 messages（带 persona 字段的 system 头）."""
        return [
            {
                "role": "system",
                "content": self._runtime_prompt(persona),
                "persona": persona,
            }
        ]

    # ===================== 会话索引持久化 =====================

    def _load_sessions_index(self) -> None:
        """从 index.json 读会话元数据列表."""
        if not self._index_path.exists():
            self._session_metas = []
            return
        try:
            with open(self._index_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._session_metas = [SessionMeta.from_dict(d) for d in data if isinstance(d, dict)]
            else:
                self._session_metas = []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load sessions index: {e}, starting empty")
            self._session_metas = []
        # 按 updated_at 降序
        self._session_metas.sort(key=lambda m: m.updated_at, reverse=True)

    def _persist_index(self) -> None:
        """落盘会话索引."""
        try:
            tmp = self._index_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([m.to_dict() for m in self._session_metas], f, ensure_ascii=False, indent=2)
            tmp.replace(self._index_path)
        except OSError as e:
            logger.warning(f"Failed to persist sessions index: {e}")

    def _session_path(self, sid: str) -> Path:
        return self._sessions_dir / f"{sid}.json"

    def _load_session_messages(self, sid: str) -> list[dict[str, Any]] | None:
        """从磁盘读某会话的 messages。文件不存在/损坏返回 None."""
        path = self._session_path(sid)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            msgs = data.get("messages") if isinstance(data, dict) else None
            if not isinstance(msgs, list):
                logger.warning(f"Session file {sid} malformed, ignoring")
                return None
            return msgs
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load session {sid}: {e}, treating as empty")
            return None

    def _persist_session(self, sid: str, messages: list[dict[str, Any]], meta: SessionMeta) -> None:
        """落盘单会话（messages + meta）."""
        path = self._session_path(sid)
        try:
            tmp = path.with_suffix(".json.tmp")
            payload = {
                "session_id": sid,
                "title": meta.title,
                "active_persona": meta.active_persona,
                "created_at": meta.created_at,
                "updated_at": meta.updated_at,
                "messages": messages,
            }
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as e:
            logger.warning(f"Failed to persist session {sid}: {e}")

    def _delete_session_disk(self, sid: str) -> None:
        try:
            self._session_path(sid).unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"Failed to delete session file {sid}: {e}")

    # ===================== 会话生命周期 =====================

    def _activate_initial_session(self) -> None:
        """启动时激活最新会话；没有任何会话则新建一个."""
        if self._session_metas:
            sid = self._session_metas[0].session_id
            self._activate_session(sid)
        else:
            self.new_session()

    def _activate_session(self, sid: str) -> bool:
        """激活指定会话：加载 messages 到 context，设 active persona.
        会话不存在返回 False."""
        meta = next((m for m in self._session_metas if m.session_id == sid), None)
        if meta is None:
            return False
        # 先持久化当前会话（如果有改动）
        self._persist_active_if_any()
        # 加载目标会话 messages（内存有就用内存，否则磁盘）
        msgs = self._sessions.get(sid)
        if msgs is None:
            disk = self._load_session_messages(sid)
            if disk is not None:
                msgs = self._validated_messages(disk, meta.active_persona)
            else:
                msgs = self._initial_messages_for(meta.active_persona)
            self._sessions[sid] = msgs
        else:
            msgs = self._validated_messages(msgs, meta.active_persona)
            self._sessions[sid] = msgs
        # 灌进 LLMContext（剥掉 persona 字段）
        self._context.set_messages(_strip_for_llm(msgs))
        self._active_session_id = sid
        self._active_persona = meta.active_persona
        logger.info(f"Activated session {sid} ({meta.title}), persona={meta.active_persona}")
        return True

    def _validated_messages(
        self, msgs: list[dict[str, Any]], persona: str
    ) -> list[dict[str, Any]]:
        """校验 messages 第一条 system 是否匹配该 persona 当前运行时 prompt
        （原始 prompt + skill 内容）。不匹配（prompt 被 override/yaml 改过）→ 重建.
        接受 switch_to 追加身份提示后缀的版本（以运行时 prompt 开头）."""
        if not msgs:
            return self._initial_messages_for(persona)
        first = msgs[0]
        expected = self._runtime_prompt(persona)
        if isinstance(first, dict) and first.get("role") == "system":
            content = first.get("content", "")
            # 完全匹配，或以运行时 prompt 开头（switch_to 追加了身份提示后缀）
            if content == expected or (
                isinstance(content, str) and content.startswith(expected)
            ):
                return msgs
        logger.info(
            f"Session system prompt stale for {persona}, rebuilding system head "
            f"(keeping {len(msgs) - 1} msgs)"
        )
        new_msgs = list(msgs)
        new_msgs[0] = {"role": "system", "content": expected, "persona": persona}
        return new_msgs

    def new_session(self, persona: str | None = None) -> SessionMeta:
        """新建空会话并激活。persona 默认用 default_persona."""
        pid = persona or self._default_persona
        if pid not in self._configs:
            pid = self._default_persona
        # 先持久化当前会话
        self._persist_active_if_any()
        sid = uuid.uuid4().hex[:12]
        now = _now_iso()
        meta = SessionMeta(
            session_id=sid,
            title="新会话",
            active_persona=pid,
            created_at=now,
            updated_at=now,
        )
        msgs = self._initial_messages_for(pid)
        self._sessions[sid] = msgs
        self._session_metas.insert(0, meta)
        self._persist_session(sid, msgs, meta)
        self._persist_index()
        # 激活
        self._context.set_messages(_strip_for_llm(msgs))
        self._active_session_id = sid
        self._active_persona = pid
        logger.info(f"Created new session {sid}, persona={pid}")
        return meta

    def switch_session(self, sid: str) -> SessionMeta | None:
        """切换到指定会话。不存在返回 None."""
        if sid == self._active_session_id:
            return self.active_session_meta
        if not self._activate_session(sid):
            return None
        return self.active_session_meta

    def delete_session(self, sid: str) -> bool:
        """删除会话。删的是当前 active 会话则自动切到最新剩余会话（或新建）."""
        meta = next((m for m in self._session_metas if m.session_id == sid), None)
        if meta is None:
            return False
        self._session_metas = [m for m in self._session_metas if m.session_id != sid]
        self._sessions.pop(sid, None)
        self._delete_session_disk(sid)
        self._persist_index()
        logger.info(f"Deleted session {sid}")
        # 删的是当前 active → 切到最新剩余会话，没有就新建
        if sid == self._active_session_id:
            if self._session_metas:
                self._activate_session(self._session_metas[0].session_id)
            else:
                self.new_session()
        return True

    def list_sessions(self) -> list[dict[str, Any]]:
        """返回会话列表（按 updated_at 降序），供前端展示."""
        return [m.to_dict() for m in self._session_metas]

    # ===================== 持久化当前会话 =====================

    def _persist_active_if_any(self) -> None:
        """把当前 active 会话的 messages 落盘（如果有的话）."""
        if not self._active_session_id:
            return
        meta = self.active_session_meta
        if meta is None:
            return
        # 从 context 同步最新 messages（aggregator 实时往 context 加消息，但带不带 persona？
        # aggregator 加的是纯 role/content，我们要补上当前 active_persona）
        self._sync_context_to_session()
        msgs = self._sessions.get(self._active_session_id, [])
        meta.updated_at = _now_iso()
        # 更新标题（如果还是"新会话"且有 user 消息了）
        meta.title = self._derive_title(msgs, meta.title)
        self._persist_session(self._active_session_id, msgs, meta)
        # 重新排序 index
        self._session_metas.sort(key=lambda m: m.updated_at, reverse=True)
        self._persist_index()

    def _sync_context_to_session(self) -> None:
        """把 LLMContext 里的最新 messages 同步回当前会话的内存缓存，并补 persona 字段.

        aggregator 往 context 加消息时只放 role/content，不带 persona。我们同步时
        给每条没有 persona 的消息补上"它产生时的 active persona"。
        简化：user/assistant 消息没 persona 的，统一标当前 active_persona。
        （handoff 期间产生的消息，persona 已在 handoff_to 里手动标好，不会被覆盖。）
        """
        if not self._active_session_id:
            return
        ctx_msgs = list(self._context.messages)
        sess_msgs = self._sessions.get(self._active_session_id, [])
        # 用 context 的消息覆盖会话缓存，但保留会话里已有的 persona 字段
        merged: list[dict[str, Any]] = []
        for i, m in enumerate(ctx_msgs):
            if not isinstance(m, dict):
                merged.append(m)
                continue
            existing = sess_msgs[i] if i < len(sess_msgs) and isinstance(sess_msgs[i], dict) else {}
            persona = existing.get("persona") or m.get("persona") or self._active_persona
            merged.append({**m, "persona": persona})
        self._sessions[self._active_session_id] = merged

    def _derive_title(self, msgs: list[dict[str, Any]], current: str) -> str:
        """会话标题：如果还是"新会话"且有 user 消息，用首条 user 消息前 20 字.
        跳过 list content（vision image 消息）和开场 greeting prompt."""
        if current and current != "新会话":
            return current
        for m in msgs:
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            content = m.get("content", "")
            # 跳过 list content（vision image 消息），只取字符串
            if not isinstance(content, str):
                continue
            content = content.strip()
            # 跳过开场 greeting prompt、转交标记消息
            if not content:
                continue
            if content.startswith("你好，请用一句简短的话"):
                continue
            if content.startswith("[转交自"):
                continue
            return content[:20]
        return current or "新会话"

    def rename_session(self, sid: str, title: str) -> SessionMeta | None:
        """修改会话标题。会话不存在返回 None."""
        meta = next((m for m in self._session_metas if m.session_id == sid), None)
        if meta is None:
            return None
        title = (title or "").strip() or "新会话"
        meta.title = title[:50]
        meta.updated_at = _now_iso()
        # 重新排序 + 落盘
        self._session_metas.sort(key=lambda m: m.updated_at, reverse=True)
        self._persist_index()
        # 同步到会话文件
        msgs = self._sessions.get(sid)
        if msgs is not None:
            self._persist_session(sid, msgs, meta)
        logger.info(f"Renamed session {sid} -> {meta.title}")
        return meta

    def persist_active(self) -> None:
        """断开连接时调用：持久化当前会话."""
        self._persist_active_if_any()

    # ===================== persona 切换（会话内）=====================

    def switch_to(self, persona: str) -> PersonaConfig | None:
        """会话内切换发言 persona：只换 system 头 + active_persona，**不丢历史**.

        与旧版区别：旧版 persona=会话，切换换整个 messages；现在会话独立，
        切 persona 只把 messages[0] 的 system 换成新 persona 的 prompt。
        """
        if persona == self._active_persona or persona not in self._configs:
            return None
        # 同步当前 context 到会话缓存
        self._sync_context_to_session()
        # 换当前会话 messages 的 system 头。
        # 会话内切 persona 不丢历史，但旧 persona 的对话（如豆包自我介绍）会带偏新 persona
        # 身份。解法：system 头除了新 persona 的 prompt，追加一句身份强调，覆盖历史影响。
        sid = self._active_session_id
        msgs = self._sessions.get(sid, [])
        # 换 system 头：新 persona 的运行时 prompt（含 skill + 身份提示）
        new_system = {
            "role": "system",
            "content": self._runtime_prompt(persona, with_hint=True),
            "persona": persona,
        }
        if msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system":
            msgs[0] = new_system
        else:
            msgs.insert(0, new_system)
        self._sessions[sid] = msgs
        # 灌进 context
        self._context.set_messages(_strip_for_llm(msgs))
        old = self._active_persona
        self._active_persona = persona
        # 更新会话元数据的 active_persona
        meta = self.active_session_meta
        if meta:
            meta.active_persona = persona
            meta.updated_at = _now_iso()
        logger.info(
            f"Persona switched in session: {self._configs[old].display_name} → "
            f"{self._configs[persona].display_name}"
        )
        return self._configs[persona]

    # ===================== 查询 =====================

    @property
    def active_name(self) -> str:
        """当前 active persona name（兼容旧接口）."""
        return self._active_persona

    @property
    def active(self) -> PersonaConfig:
        return self._configs[self._active_persona]

    @property
    def context(self) -> LLMContext:
        return self._context

    @property
    def active_session_id(self) -> str:
        return self._active_session_id

    @property
    def active_session_meta(self) -> SessionMeta | None:
        return next((m for m in self._session_metas if m.session_id == self._active_session_id), None)

    def all_names(self) -> list[str]:
        return list(self._configs.keys())

    def detect_wake_name(self, text: str) -> str | None:
        """扫描文本，命中任一别名返回 persona name；多个命中取最长别名。"""
        candidates: list[tuple[str, str]] = []
        for name, cfg in self._configs.items():
            for alias in cfg.aliases:
                if alias in text:
                    candidates.append((alias, name))
        if not candidates:
            return None
        candidates.sort(key=lambda x: -len(x[0]))
        return candidates[0][1]

    # ===================== 前端设置面板支持 =====================

    _MUTABLE_FIELDS: tuple[str, ...] = (
        "display_name",
        "system_prompt",
        "tts_voice_id",
    )

    def get(self, name: str) -> PersonaConfig | None:
        return self._configs.get(name)

    def defaults(self) -> dict[str, PersonaConfig]:
        return {k: PersonaConfig(**v.__dict__) for k, v in self._defaults.items()}

    def current(self) -> dict[str, PersonaConfig]:
        return {k: PersonaConfig(**v.__dict__) for k, v in self._configs.items()}

    def apply_overrides(self, updates: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        """应用前端 persona 配置 diff。system_prompt 改了 → 重建该 persona 的 system 头."""
        applied: dict[str, list[str]] = {}
        for pid, fields in updates.items():
            cfg = self._configs.get(pid)
            if cfg is None:
                continue
            changed: list[str] = []
            for key, val in fields.items():
                if key not in self._MUTABLE_FIELDS:
                    continue
                if getattr(cfg, key) == val:
                    continue
                setattr(cfg, key, val)
                changed.append(key)
            if changed:
                applied[pid] = changed
                # system_prompt 改了 → 当前会话如果 active_persona 是它，重建 system 头
                if "system_prompt" in changed and self._active_persona == pid:
                    self._rebuild_active_system_head()
        return applied

    def _rebuild_active_system_head(self) -> None:
        """当前 active 会话的 system 头用最新运行时 prompt 重建（含 skill）."""
        sid = self._active_session_id
        msgs = self._sessions.get(sid, [])
        pid = self._active_persona
        new_system = {"role": "system", "content": self._runtime_prompt(pid), "persona": pid}
        if msgs and isinstance(msgs[0], dict) and msgs[0].get("role") == "system":
            msgs[0] = new_system
        else:
            msgs.insert(0, new_system)
        self._sessions[sid] = msgs
        self._context.set_messages(_strip_for_llm(msgs))

    def reset(self) -> None:
        """重置：删所有会话文件 + index，新建一个空会话."""
        for meta in list(self._session_metas):
            self._delete_session_disk(meta.session_id)
        self._session_metas = []
        self._sessions = {}
        try:
            self._index_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.new_session()
        logger.info("SessionManager reset, created fresh session")


def _now_iso() -> str:
    """当前时间 ISO 字符串（秒级精度）."""
    from datetime import datetime

    return datetime.now().replace(microsecond=0).isoformat()
