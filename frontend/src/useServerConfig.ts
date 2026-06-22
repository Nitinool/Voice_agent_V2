/**
 * useServerConfig —— 通过 RTVI client-request 跟后端拉/推 Settings 数据.
 *
 * 后端协议：
 *   get_config    → { personas_default, personas_current, active_persona, default_persona, provider }
 *   update_config(diff) → { ok, applied: { [pid]: changedFields[] } }
 *
 * 设计要点：
 *   - 仅在 client 就绪 + 已连接时才能调（PipecatClient.sendClientRequest 要求连接）
 *   - 拉到的数据缓存在 state；保存后自动重拉一次保证一致性
 *   - 不写 localStorage —— 后端是 source of truth，前端只缓存当前 session
 */
import { useCallback, useState } from 'react';
import { usePipecatClient } from '@pipecat-ai/client-react';

/** 后端 PersonaConfig（dataclass.__dict__ 直接序列化的形态） */
export interface ServerPersonaConfig {
  name: string;
  display_name: string;
  aliases: string[];
  color: string;
  avatar: string;
  tts_voice_id: string;
  system_prompt: string;
}

export interface ServerProviderInfo {
  llm: { provider: string; model: string; base_url: string };
  tts: { provider: string; base_url: string; sample_rate: number };
  stt: { provider: string; model: string; language: string };
}

export interface ServerConfig {
  personas_default: Record<string, ServerPersonaConfig>;
  personas_current: Record<string, ServerPersonaConfig>;
  active_persona: string;
  default_persona: string;
  provider: ServerProviderInfo;
}

/** 前端发给后端的 diff（仅可改字段） */
export type PersonaOverridePatch = Partial<
  Pick<ServerPersonaConfig, 'display_name' | 'system_prompt' | 'tts_voice_id'>
>;
export type PersonasOverrideDiff = Record<string, PersonaOverridePatch>;

export interface UseServerConfigResult {
  config: ServerConfig | null;
  loading: boolean;
  error: string | null;
  /** 主动拉一次（一般在打开 Settings 抽屉时调用）. */
  fetchConfig: () => Promise<ServerConfig | null>;
  /** 把 diff 发给后端，成功后自动 refetch. */
  applyConfig: (diff: PersonasOverrideDiff) => Promise<boolean>;
}

/** PipecatClient.sendClientRequest 失败时 reject 的不是 Error 而是 RTVIMessage 对象 ——
 *  其 data 里有 {error, msgType, fatal}. 这里把任意错误形态归一成可读字符串. */
function errToString(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  if (err && typeof err === 'object') {
    const anyErr = err as any;
    // RTVIMessage(type='error-response', data={error, msgType, data, fatal})
    if (anyErr.data?.error) return String(anyErr.data.error);
    if (anyErr.error) return String(anyErr.error);
    try {
      return JSON.stringify(err);
    } catch {
      // ignore
    }
  }
  return String(err);
}

export function useServerConfig(): UseServerConfigResult {
  const client = usePipecatClient();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async (): Promise<ServerConfig | null> => {
    if (!client) {
      setError('Pipecat client not ready');
      return null;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = (await client.sendClientRequest('get_config', {}, 5000)) as ServerConfig;
      setConfig(resp);
      return resp;
    } catch (err) {
      console.error('[useServerConfig] get_config error', err);
      setError(`get_config failed: ${errToString(err)}`);
      return null;
    } finally {
      setLoading(false);
    }
  }, [client]);

  const applyConfig = useCallback(
    async (diff: PersonasOverrideDiff): Promise<boolean> => {
      if (!client) {
        setError('Pipecat client not ready');
        return false;
      }
      setLoading(true);
      setError(null);
      try {
        await client.sendClientRequest(
          'update_config',
          { personas: diff },
          5000,
        );
        // 拉一次刷新 personas_current
        await fetchConfig();
        return true;
      } catch (err) {
        console.error('[useServerConfig] update_config error', err);
        setError(`update_config failed: ${errToString(err)}`);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [client, fetchConfig],
  );

  return { config, loading, error, fetchConfig, applyConfig };
}
