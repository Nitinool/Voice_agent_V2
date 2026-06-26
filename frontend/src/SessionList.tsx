/**
 * SessionList —— 会话列表（新建/切换/删除）.
 *
 * 放在 sidebar header 下方、消息区上方。展示所有会话，点击切换，
 * hover 显示删除按钮。当前 active 会话高亮。
 *
 * 折叠状态下整个组件不渲染（由 HistorySidebar 控制）。
 */
import { useState } from 'react';
import { Button, cn } from '@pipecat-ai/voice-ui-kit';
import { Plus, Trash2 } from './icons';
import { PERSONAS } from './config';
import { useSessions } from './useSessions';

function personaEmoji(pid: string): string {
  return PERSONAS.find((p) => p.id === pid)?.emoji ?? '💬';
}

export function SessionList() {
  const { sessions, activeSessionId, createSession, switchSession, deleteSession } = useSessions();
  const [busy, setBusy] = useState(false);

  const onNew = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await createSession();
    } finally {
      setBusy(false);
    }
  };

  const onSwitch = async (sid: string) => {
    if (busy || sid === activeSessionId) return;
    setBusy(true);
    try {
      await switchSession(sid);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (sid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (busy) return;
    if (!confirm('删除这个会话？')) return;
    setBusy(true);
    try {
      await deleteSession(sid);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="session-list">
      <div className="session-list-header">
        <span className="session-list-title">Sessions</span>
        <Button
          variant="ghost"
          size="sm"
          isIcon
          onClick={onNew}
          disabled={busy}
          aria-label="New session"
          title="New session"
        >
          <Plus />
        </Button>
      </div>
      <div className="session-list-items">
        {sessions.length === 0 && (
          <div className="session-empty">No sessions</div>
        )}
        {sessions.map((s) => {
          const isActive = s.session_id === activeSessionId;
          return (
            <div
              key={s.session_id}
              className={cn('session-item', isActive && 'is-active')}
              onClick={() => onSwitch(s.session_id)}
              role="button"
              tabIndex={0}
            >
              <span className="session-item-emoji">{personaEmoji(s.active_persona)}</span>
              <span className="session-item-title">{s.title || '新会话'}</span>
              <button
                className="session-item-del"
                onClick={(e) => onDelete(s.session_id, e)}
                aria-label="Delete session"
                title="Delete session"
              >
                <Trash2 />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
