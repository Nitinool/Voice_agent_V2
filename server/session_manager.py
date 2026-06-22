"""M1 多 persona 会话管理（in-place 模式）.

设计：4 个 persona 共享一个 LLMContext 对象（pipeline 里只有一份），切换时只
替换它内部的 messages 列表，**不换对象** —— 这样 user/assistant aggregator
持有的引用始终有效。

每个 persona 的对话历史单独存在 `_saved_messages[name]`，互不串台。
"""

from __future__ import annotations

from dataclasses import dataclass
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


class SessionManager:
    def __init__(self, config_path: Path, llm_context: LLMContext):
        self._context: LLMContext = llm_context
        self._configs: dict[str, PersonaConfig] = {}
        # 出厂默认值（personas.yaml 加载时快照），供前端 "reset" 用，运行时不可变
        self._defaults: dict[str, PersonaConfig] = {}
        self._saved_messages: dict[str, list[dict[str, Any]]] = {}
        self._active: str = ""
        self._default: str = ""
        self._load_config(config_path)

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
            # 保留出厂默认快照，供前端 "reset to defaults" 用
            self._defaults[name] = PersonaConfig(**cfg.__dict__)
        self._default = data.get("default_persona", next(iter(self._configs)))
        if self._default not in self._configs:
            raise ValueError(f"default_persona '{self._default}' not found")
        self._active = self._default
        self._context.set_messages(self._initial_messages_for(self._default))
        logger.info(
            f"SessionManager loaded {len(self._configs)} personas, default = {self.active.display_name}"
        )

    def _initial_messages_for(self, name: str) -> list[dict[str, Any]]:
        return [{"role": "system", "content": self._configs[name].system_prompt}]

    @property
    def active_name(self) -> str:
        return self._active

    @property
    def active(self) -> PersonaConfig:
        return self._configs[self._active]

    def all_names(self) -> list[str]:
        """所有 persona 的 name（按 yaml 里的顺序）—— 给 P2 AgentStatusManager 用."""
        return list(self._configs.keys())

    def detect_wake_name(self, text: str) -> str | None:
        """扫描文本，命中任一别名返回 persona name；多个命中取最长别名（更具体）。"""
        candidates: list[tuple[str, str]] = []
        for name, cfg in self._configs.items():
            for alias in cfg.aliases:
                if alias in text:
                    candidates.append((alias, name))
        if not candidates:
            return None
        candidates.sort(key=lambda x: -len(x[0]))
        return candidates[0][1]

    def switch_to(self, name: str) -> PersonaConfig | None:
        """切换 active persona。没切换（同名或无效）返回 None，否则返回新配置。"""
        if name == self._active or name not in self._configs:
            return None
        # 1. 快照当前 messages 到旧 active
        self._saved_messages[self._active] = list(self._context.messages)
        # 2. 加载新 active 的 messages（历史 or 全新初始化）
        new_msgs = (
            self._saved_messages[name]
            if name in self._saved_messages
            else self._initial_messages_for(name)
        )
        # 3. 写回 LLMContext —— set_messages，不换对象
        self._context.set_messages(new_msgs)
        old_name = self._active
        self._active = name
        logger.info(
            f"Persona switched: {self._configs[old_name].display_name} → "
            f"{self._configs[name].display_name}"
        )
        return self._configs[name]

    def reset(self) -> None:
        self._saved_messages.clear()
        self._active = self._default
        self._context.set_messages(self._initial_messages_for(self._default))
        logger.info(f"SessionManager reset, active = {self.active.display_name}")

    # ----- 前端设置面板支持 -----
    # 可由前端 RTVI update_config 修改的字段（白名单），其它字段忽略
    _MUTABLE_FIELDS: tuple[str, ...] = (
        "display_name",
        "system_prompt",
        "tts_voice_id",
    )

    def get(self, name: str) -> PersonaConfig | None:
        return self._configs.get(name)

    def defaults(self) -> dict[str, PersonaConfig]:
        """返回出厂默认值的浅拷贝快照（前端 reset 用）."""
        return {k: PersonaConfig(**v.__dict__) for k, v in self._defaults.items()}

    def current(self) -> dict[str, PersonaConfig]:
        """返回当前生效配置（含 override）的快照."""
        return {k: PersonaConfig(**v.__dict__) for k, v in self._configs.items()}

    def apply_overrides(self, updates: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        """应用前端发来的 diff（不写回 yaml）.

        返回每个 persona 实际生效的字段名列表，供调用方记日志.
        下次切到该 persona 时（switch_to）新值生效；已缓存的 saved_messages
        会重置（system_prompt 可能变了，要让新 prompt 进 LLM context）.
        """
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
                # system_prompt 改了 → 该 persona 缓存的 messages 失效，丢弃，
                # 下次切回时重新用新 prompt 初始化
                self._saved_messages.pop(pid, None)
        return applied
