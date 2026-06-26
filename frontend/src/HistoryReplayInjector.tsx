/**
 * HistoryReplayInjector —— 监听后端 history_replay server message，把历史消息存进独立 store.
 *
 * 历史消息**不注入 jotai**（usePipecatConversation 会合并 30s 内同 role 消息，且结构固定
 * 挂不了 persona 字段），而是存到 historyPersonaStore，PersonaConversation 直接渲染。
 * 实时消息仍走 usePipecatConversation。
 *
 * 分内外两层：外层用 usePipecatClient 探测，client 没就绪时 return null，
 * 避免内层 hook 在无 Provider 时抛错。
 */
import { useEffect } from 'react';
import { usePipecatClient } from '@pipecat-ai/client-react';
import { usePipecatEventStream } from '@pipecat-ai/voice-ui-kit';
import { setHistoryEntries, type HistoryEntry } from './historyPersonaStore';

interface HistoryMsg {
  role: 'user' | 'assistant';
  content: string;
  persona?: string;
}

export function HistoryReplayInjector() {
  const client = usePipecatClient();
  if (!client) return null;
  return <HistoryReplayInjectorInner />;
}

function HistoryReplayInjectorInner() {
  const { events } = usePipecatEventStream({ maxEvents: 500 });

  useEffect(() => {
    for (const ev of events as any[]) {
      const t = ev?.type;
      const d = ev?.data;
      if (
        (t === 'serverMessage' || t === 'server-message') &&
        d?.type === 'history_replay' &&
        Array.isArray(d.messages)
      ) {
        const list: HistoryEntry[] = [];
        for (const m of d.messages as HistoryMsg[]) {
          if (!m || (m.role !== 'user' && m.role !== 'assistant')) continue;
          if (typeof m.content !== 'string' || !m.content.trim()) continue;
          list.push({
            role: m.role,
            content: m.content,
            persona: m.persona || '',
          });
        }
        setHistoryEntries(list);
        break; // 只处理最新一条 history_replay
      }
    }
  }, [events]);

  return null;
}
