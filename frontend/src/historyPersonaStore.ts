/**
 * historyPersonaStore —— 历史回放消息的独立存储.
 *
 * usePipecatConversation 的 messages 会被自动合并（30s 内同 role 合一条），
 * 且 message 结构固定没法挂 persona 字段。所以历史消息**不走 jotai**，
 * 单独存在这里，PersonaConversation 直接渲染本 store 的历史 + jotai 的实时消息。
 *
 * 切会话/重连时 HistoryReplayInjector 收到 history_replay 后 reset 重建。
 */

export interface HistoryEntry {
  role: 'user' | 'assistant';
  content: string;
  persona: string;
}

let entries: HistoryEntry[] = [];
const listeners = new Set<() => void>();

export function setHistoryEntries(list: HistoryEntry[]): void {
  entries = list;
  emit();
}

export function getHistoryEntries(): HistoryEntry[] {
  return entries;
}

export function clearHistoryEntries(): void {
  entries = [];
  emit();
}

export function subscribeHistoryEntries(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(): void {
  for (const fn of listeners) fn();
}
