/**
 * useSessions —— 会话管理：列表 / 新建 / 切换 / 删除.
 *
 * 通过 RTVI client-request 跟后端交互：
 *   list_sessions            → { sessions, active_session_id, active_persona }
 *   new_session              → { ok, session }
 *   switch_session(sid)      → { ok, session }
 *   delete_session(sid)      → { ok }
 *
 * 后端也会主动推 sessions_update server message（连接时 / 增删切后），
 * 本 hook 同时监听它来同步状态，不依赖手动 refetch.
 */
import { useCallback, useEffect, useState } from 'react';
import { usePipecatClient } from '@pipecat-ai/client-react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';

export interface SessionInfo {
  session_id: string;
  title: string;
  active_persona: string;
  created_at: string;
  updated_at: string;
}

export interface UseSessionsResult {
  sessions: SessionInfo[];
  activeSessionId: string;
  activePersona: string;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createSession: (persona?: string) => Promise<SessionInfo | null>;
  switchSession: (sid: string) => Promise<boolean>;
  deleteSession: (sid: string) => Promise<boolean>;
  renameSession: (sid: string, title: string) => Promise<boolean>;
}

function errToString(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  if (err && typeof err === 'object') {
    const anyErr = err as any;
    if (anyErr.data?.error) return String(anyErr.data.error);
    if (anyErr.error) return String(anyErr.error);
  }
  return String(err);
}

export function useSessions(): UseSessionsResult {
  const client = usePipecatClient();
  const { events } = usePipecatEventStream({ maxEvents: 500 });
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [activePersona, setActivePersona] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 监听后端主动推的 sessions_update server message
  useEffect(() => {
    for (const ev of events as any[]) {
      const t = ev?.type;
      const d = ev?.data;
      if (
        (t === 'serverMessage' || t === 'server-message') &&
        d?.type === 'sessions_update'
      ) {
        setSessions(Array.isArray(d.sessions) ? d.sessions : []);
        setActiveSessionId(String(d.active_session_id ?? ''));
        setActivePersona(String(d.active_persona ?? ''));
        break; // 只处理最新一条即可
      }
    }
  }, [events]);

  const refresh = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    setError(null);
    try {
      const resp = (await client.sendClientRequest('list_sessions', {}, 5000)) as any;
      setSessions(Array.isArray(resp?.sessions) ? resp.sessions : []);
      setActiveSessionId(String(resp?.active_session_id ?? ''));
      setActivePersona(String(resp?.active_persona ?? ''));
    } catch (err) {
      setError(`list_sessions failed: ${errToString(err)}`);
    } finally {
      setLoading(false);
    }
  }, [client]);

  const createSession = useCallback(
    async (persona?: string): Promise<SessionInfo | null> => {
      if (!client) return null;
      try {
        const resp = (await client.sendClientRequest(
          'new_session',
          persona ? { persona } : {},
          5000,
        )) as any;
        if (resp?.ok && resp.session) {
          // 新会话也要 reload 清空旧消息列表
          const sid = resp.session.session_id as string;
          window.location.href = `${window.location.pathname}?session=${encodeURIComponent(sid)}`;
          return resp.session as SessionInfo;
        }
        setError(resp?.error || 'new_session failed');
        return null;
      } catch (err) {
        setError(`new_session failed: ${errToString(err)}`);
        return null;
      }
    },
    [client],
  );

  const switchSession = useCallback(
    async (sid: string): Promise<boolean> => {
      if (!client) return false;
      // jotani 会话消息列表没有公开 clear API，切会话靠整页 reload 重置。
      // reload 时 URL 带 ?session=sid，连接成功后 SessionActivator 发 switch_session
      // 给后端真正切换 + 推 history_replay。不预切换（reload 是全新 bot，预切换是冗余副作用）。
      window.location.href = `${window.location.pathname}?session=${encodeURIComponent(sid)}`;
      return true;
    },
    [client],
  );

  const deleteSession = useCallback(
    async (sid: string): Promise<boolean> => {
      if (!client) return false;
      try {
        const resp = (await client.sendClientRequest(
          'delete_session',
          { session_id: sid },
          5000,
        )) as any;
        if (resp?.ok) return true;
        setError(resp?.error || 'delete_session failed');
        return false;
      } catch (err) {
        setError(`delete_session failed: ${errToString(err)}`);
        return false;
      }
    },
    [client],
  );

  const renameSession = useCallback(
    async (sid: string, title: string): Promise<boolean> => {
      if (!client) return false;
      try {
        const resp = (await client.sendClientRequest(
          'rename_session',
          { session_id: sid, title },
          5000,
        )) as any;
        if (resp?.ok) return true;
        setError(resp?.error || 'rename_session failed');
        return false;
      } catch (err) {
        setError(`rename_session failed: ${errToString(err)}`);
        return false;
      }
    },
    [client],
  );

  return {
    sessions,
    activeSessionId,
    activePersona,
    loading,
    error,
    refresh,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
  };
}
