"""Agent 状态管理（P2）.

维护 4 个 persona 的当前状态，提供给前端展示：
- online: 当前 active 的 agent
- idle:   在线但不是 active
- busy:   正在做异步任务（P5 才会真触发，P2 留接口）
- error:  调用失败（先不触发，留协议位）

状态变更走 RTVI serverMessage 通道：
    {
      "type": "agent_status",
      "agents": {"doubao": {"status": "online"}, "xiaoai": {"status": "idle"}, ...}
    }

每次都全量推送（少量数据，前端无脑替换 state，比增量稳）。
"""

from __future__ import annotations

from typing import Any, Literal

AgentStatus = Literal["online", "idle", "busy", "error"]


class AgentStatusManager:
    """单例风格 —— 一次连接一个 manager，跟 SessionManager 平级."""

    def __init__(self, agent_names: list[str], active_name: str):
        self._statuses: dict[str, AgentStatus] = {}
        for name in agent_names:
            self._statuses[name] = "online" if name == active_name else "idle"

    def mark_active(self, name: str) -> None:
        """切到新 active —— 老 active 转 idle，新 active 转 online。

        注意：busy/error 的 agent 不会被 mark_idle 覆盖（它仍在做事或仍出错）。
        只有 online ↔ idle 之间互转。
        """
        if name not in self._statuses:
            return
        for n, s in list(self._statuses.items()):
            if s == "online" and n != name:
                self._statuses[n] = "idle"
        # 如果新 active 当前是 busy/error，保留状态（active 但仍 busy 是合法的）
        if self._statuses[name] not in ("busy", "error"):
            self._statuses[name] = "online"

    def mark_busy(self, name: str) -> None:
        """P5 预留 —— agent 开始做异步任务."""
        if name in self._statuses:
            self._statuses[name] = "busy"

    def mark_idle(self, name: str) -> None:
        """P5 预留 —— agent 结束异步任务，回到 idle（除非 active）."""
        if name in self._statuses:
            self._statuses[name] = "idle"

    def mark_error(self, name: str) -> None:
        """留位."""
        if name in self._statuses:
            self._statuses[name] = "error"

    def snapshot(self) -> dict[str, Any]:
        """生成发给前端的 RTVI server message data."""
        return {
            "type": "agent_status",
            "agents": {n: {"status": s} for n, s in self._statuses.items()},
        }
