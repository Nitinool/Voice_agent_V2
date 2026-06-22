/**
 * HistorySidebar —— 左侧常驻历史记录栏（支持折叠成 48px 窄条）.
 *
 * 展开状态（300px，默认）：
 *   header: 4 agent 头像横排 + 状态指示 + 折叠按钮 + 设置齿轮
 *   body:   per-persona 历史消息列表
 *
 * 折叠状态（48px）：
 *   header: 展开按钮 + 4 agent 头像竖排 + 状态点（无文字） + 设置齿轮
 *   body:   隐藏
 *
 * 折叠状态由 useSettings.collapsed 控制，localStorage 持久化.
 */
import { useState } from 'react';
import {
  Button,
  cn,
} from '@pipecat-ai/voice-ui-kit';
import { usePipecatClient } from '@pipecat-ai/client-react';
import { Settings, PanelLeftClose, PanelLeftOpen } from './icons';
import { PERSONAS } from './config';
import { useActivePersona } from './useActivePersona';
import { useSettings } from './useSettings';
import { PersonaConversation } from './PersonaConversation';
import { AgentStatusInline } from './AgentStatusInline';
import { SettingsDrawer } from './SettingsDrawer';

export function HistorySidebar() {
  const client = usePipecatClient();
  const { activePersonaId } = useActivePersona();
  const { settings, setCollapsed } = useSettings();
  const collapsed = settings.collapsed;

  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleAvatarClick = (personaId: string) => {
    if (personaId === activePersonaId) return;
    client?.sendClientMessage('set_persona', { persona: personaId });
  };

  return (
    <aside className={cn('history-sidebar', collapsed && 'is-collapsed')}>
      <div className="history-header">
        <Button
          variant="ghost"
          size="sm"
          isIcon
          className="history-collapse-btn"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'Expand' : 'Collapse'}
          title={collapsed ? 'Expand' : 'Collapse'}
        >
          {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
        </Button>

        <div className="history-avatar-bar">
          {PERSONAS.map((p) => {
            const isActive = p.id === activePersonaId;
            const name = settings.agentNames[p.id] ?? p.label;
            return (
              <button
                key={p.id}
                className={cn('history-avatar', isActive && 'is-active')}
                style={{ ['--c' as any]: p.color }}
                onClick={() => handleAvatarClick(p.id)}
                title={isActive ? `${name} (current)` : `Switch to ${name}`}
                aria-label={`Switch to ${name}`}
                aria-pressed={isActive}
              >
                <span className="history-avatar-emoji" style={{ background: p.color }}>
                  {p.emoji}
                </span>
              </button>
            );
          })}
        </div>

        <AgentStatusInline />

        <Button
          variant="ghost"
          size="sm"
          isIcon
          aria-label="Settings"
          onClick={() => setSettingsOpen(true)}
        >
          <Settings />
        </Button>
      </div>

      <div className="history-body">
        <PersonaConversation />
      </div>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </aside>
  );
}
