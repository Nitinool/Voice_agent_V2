/**
 * SessionList —— 会话列表（新建/切换/删除/重命名）.
 *
 * 放在 sidebar header 下方、消息区上方。展示所有会话：
 *   - 点击切换会话
 *   - hover 显示删除按钮 + 重命名按钮
 *   - 双击标题进入内联编辑，回车保存，Esc 取消
 * 当前 active 会话高亮。
 *
 * 折叠状态下整个组件不渲染（由 HistorySidebar 控制）。
 */
import { useEffect, useRef, useState } from 'react';
import { Button, cn } from '@pipecat-ai/voice-ui-kit';
import { Plus, Trash2, Pencil } from './icons';
import { PERSONAS } from './config';
import { useSessions } from './useSessions';

function personaEmoji(pid: string): string {
  return PERSONAS.find((p) => p.id === pid)?.emoji ?? '💬';
}

export function SessionList() {
  const { sessions, activeSessionId, createSession, switchSession, deleteSession, renameSession } =
    useSessions();
  const [busy, setBusy] = useState(false);
  // 正在编辑的会话 id + 编辑中的标题
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

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
    if (busy || sid === activeSessionId || editingId) return;
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

  const startEdit = (sid: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(sid);
    setEditValue(currentTitle);
  };

  const commitEdit = async () => {
    const sid = editingId;
    const title = editValue.trim();
    setEditingId(null);
    if (!sid || !title) return;
    setBusy(true);
    try {
      await renameSession(sid, title);
    } finally {
      setBusy(false);
    }
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const onEditKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void commitEdit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelEdit();
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
        {sessions.length === 0 && <div className="session-empty">No sessions</div>}
        {sessions.map((s) => {
          const isActive = s.session_id === activeSessionId;
          const isEditing = editingId === s.session_id;
          return (
            <div
              key={s.session_id}
              className={cn('session-item', isActive && 'is-active')}
              onClick={() => onSwitch(s.session_id)}
              role="button"
              tabIndex={0}
            >
              <span className="session-item-emoji">{personaEmoji(s.active_persona)}</span>
              {isEditing ? (
                <input
                  ref={inputRef}
                  className="session-item-input"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={commitEdit}
                  onKeyDown={onEditKey}
                  onClick={(e) => e.stopPropagation()}
                  maxLength={50}
                />
              ) : (
                <span
                  className="session-item-title"
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setEditingId(s.session_id);
                    setEditValue(s.title || '新会话');
                  }}
                  title="双击重命名"
                >
                  {s.title || '新会话'}
                </span>
              )}
              {!isEditing && (
                <>
                  <button
                    className="session-item-edit"
                    onClick={(e) => startEdit(s.session_id, s.title || '新会话', e)}
                    aria-label="Rename session"
                    title="Rename session"
                  >
                    <Pencil />
                  </button>
                  <button
                    className="session-item-del"
                    onClick={(e) => onDelete(s.session_id, e)}
                    aria-label="Delete session"
                    title="Delete session"
                  >
                    <Trash2 />
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
