/**
 * SessionActivator —— 连接成功后，若 URL 带 ?session=<sid>，向后端发 switch_session.
 *
 * reload 切会话时 URL 带 ?session=sid。reload 是全新 bot 进程，后端默认激活最新会话，
 * 不是 URL 指定的那个。本组件在连接就绪后发 switch_session(sid)，后端真正切到目标会话
 * 并推 history_replay，前端 HistoryReplayInjector 据此显示目标会话历史。
 *
 * 只在连接后执行一次（用 ref 去重），成功后清掉 URL 上的 session 参数避免重复触发。
 */
import { useEffect, useRef } from 'react';
import { usePipecatClient } from '@pipecat-ai/client-react';
import { usePipecatConnectionState } from '@pipecat-ai/voice-ui-kit';

export function SessionActivator() {
  const client = usePipecatClient();
  const { isConnected } = usePipecatConnectionState();
  const fired = useRef(false);

  useEffect(() => {
    if (!client || !isConnected || fired.current) return;
    const sid = new URLSearchParams(window.location.search).get('session');
    if (!sid) {
      fired.current = true;
      return;
    }
    fired.current = true;
    // 发 switch_session 让后端切到目标会话；失败也无妨（保持默认会话）
    client
      .sendClientRequest('switch_session', { session_id: sid }, 5000)
      .then(() => {
        // 清掉 URL 上的 session 参数，避免刷新时重复切换
        const url = window.location.pathname;
        window.history.replaceState({}, '', url);
      })
      .catch((e: unknown) => console.error('SessionActivator switch_session failed', e));
  }, [client, isConnected]);

  return null;
}
