/**
 * SettingsDrawer —— 右侧滑出的设置抽屉.
 *
 * 两个 tab：
 *   Agents   —— 每个 persona 一张卡片，可改 display_name / system_prompt / tts_voice_id
 *   Provider —— 只读展示当前 LLM / TTS / STT 元信息
 *
 * 状态机：
 *   - 打开时 fetchConfig 拉最新 personas_current + personas_default + provider
 *   - 本地维护 draft（用户改动），不立刻下发
 *   - 底部 Footer 显示 dirty count；点 Apply 才 applyConfig，成功后关抽屉
 *   - Reset agent / Reset all 只动 draft，仍需 Apply
 *   - Cancel / X 关闭，丢弃 draft
 *
 * 生效时机：后端把 override 写内存，下次切到该 persona 时新 prompt/voice 才生效.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Input,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  cn,
} from '@pipecat-ai/voice-ui-kit';
import { usePipecatClient } from '@pipecat-ai/client-react';
import {
  useServerConfig,
  type PersonasOverrideDiff,
  type ServerPersonaConfig,
} from './useServerConfig';

/** mimo 4 个中文预置音色（来自 mimo_tts.py 的 VALID_VOICES） */
const MIMO_VOICES = ['冰糖', '茉莉', '苏打', '白桦'] as const;

/** 可改字段：display_name / system_prompt / tts_voice_id */
type Draft = Record<string, ServerPersonaConfig>;

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsDrawer({ open, onClose }: SettingsDrawerProps) {
  const client = usePipecatClient();
  const { config, loading, error, fetchConfig, applyConfig } = useServerConfig();
  const [draft, setDraft] = useState<Draft>({});
  const [tab, setTab] = useState<'agents' | 'provider'>('agents');

  // 打开抽屉时拉一次配置；client 未就绪时不拉
  useEffect(() => {
    if (!open || !client) return;
    fetchConfig().then((cfg) => {
      if (cfg) setDraft({ ...cfg.personas_current });
    });
  }, [open, client, fetchConfig]);

  // 计算 dirty：每 persona 对比 draft vs config.personas_current
  const dirtyDiff = useMemo<PersonasOverrideDiff>(() => {
    if (!config) return {};
    const diff: PersonasOverrideDiff = {};
    for (const pid of Object.keys(config.personas_current)) {
      const orig = config.personas_current[pid];
      const cur = draft[pid];
      if (!cur || !orig) continue;
      const patch: Partial<ServerPersonaConfig> = {};
      if (cur.display_name !== orig.display_name) patch.display_name = cur.display_name;
      if (cur.system_prompt !== orig.system_prompt) patch.system_prompt = cur.system_prompt;
      if (cur.tts_voice_id !== orig.tts_voice_id) patch.tts_voice_id = cur.tts_voice_id;
      if (Object.keys(patch).length > 0) diff[pid] = patch;
    }
    return diff;
  }, [config, draft]);

  const dirtyCount = useMemo(
    () =>
      Object.values(dirtyDiff).reduce((sum, patch) => sum + Object.keys(patch).length, 0),
    [dirtyDiff],
  );

  const updateField = (
    pid: string,
    field: 'display_name' | 'system_prompt' | 'tts_voice_id',
    value: string,
  ) => {
    setDraft((prev) => ({
      ...prev,
      [pid]: { ...prev[pid], [field]: value },
    }));
  };

  const resetAgent = (pid: string) => {
    if (!config) return;
    setDraft((prev) => ({ ...prev, [pid]: { ...config.personas_default[pid] } }));
  };

  const resetAll = () => {
    if (!config) return;
    setDraft({ ...config.personas_default });
  };

  const onApply = async () => {
    if (dirtyCount === 0) return;
    const ok = await applyConfig(dirtyDiff);
    if (ok) onClose();
  };

  // backdrop / drawer container 永远渲染（用 CSS class 控制动画），避免每次开关重建 DOM
  return (
    <>
      <div
        className={cn('settings-drawer-backdrop', open && 'is-open')}
        onClick={onClose}
      />
      <aside className={cn('settings-drawer', open && 'is-open')}>
        <div className="settings-drawer-header">
          <span className="settings-drawer-title">Settings</span>
          <Button variant="ghost" size="sm" isIcon onClick={onClose} aria-label="Close">
            <CloseIcon />
          </Button>
        </div>

        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as 'agents' | 'provider')}
          className="settings-drawer-tabs-root"
        >
          <TabsList className="settings-drawer-tabs">
            <TabsTrigger value="agents">Agents</TabsTrigger>
            <TabsTrigger value="provider">Provider</TabsTrigger>
          </TabsList>

          <div className="settings-drawer-body">
            {loading && <div className="settings-loading">Loading…</div>}
            {error && <div className="settings-error">{error}</div>}
            {!loading && !error && !config && !client && (
              <div className="settings-empty">Connect to load settings.</div>
            )}

            <TabsContent value="agents">
              {config &&
                Object.entries(config.personas_current).map(([pid, orig]) => {
                  const cur = draft[pid] ?? orig;
                  const isDirty = !!dirtyDiff[pid];
                  return (
                    <div key={pid} className="settings-agent-card">
                      <div className="settings-agent-head">
                        <span
                          className="settings-agent-emoji"
                          style={{ background: orig.color }}
                        >
                          {emojiForPersona(pid)}
                        </span>
                        <span className="settings-agent-id">{pid}</span>
                        {isDirty && <span className="settings-dirty-dot" />}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => resetAgent(pid)}
                          disabled={!isDirty}
                        >
                          Reset
                        </Button>
                      </div>

                      <label className="settings-field">
                        <span>Display name</span>
                        <Input
                          value={cur.display_name}
                          onChange={(e) =>
                            updateField(pid, 'display_name', e.target.value)
                          }
                          size="sm"
                        />
                      </label>

                      <label className="settings-field">
                        <span>System prompt</span>
                        <Textarea
                          value={cur.system_prompt}
                          onChange={(e) =>
                            updateField(pid, 'system_prompt', e.target.value)
                          }
                          rows={6}
                        />
                      </label>

                      <label className="settings-field">
                        <span>TTS voice</span>
                        <select
                          className="settings-select"
                          value={cur.tts_voice_id}
                          onChange={(e) =>
                            updateField(pid, 'tts_voice_id', e.target.value)
                          }
                        >
                          {MIMO_VOICES.map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                          {!MIMO_VOICES.includes(cur.tts_voice_id as typeof MIMO_VOICES[number]) && (
                            <option value={cur.tts_voice_id}>{cur.tts_voice_id}（custom）</option>
                          )}
                        </select>
                      </label>
                    </div>
                  );
                })}
            </TabsContent>

            <TabsContent value="provider">
              {config && (
                <div className="settings-provider">
                  <ProviderGroup title="LLM" rows={[
                    ['Provider', config.provider.llm.provider],
                    ['Model', config.provider.llm.model || '—'],
                    ['Base URL', config.provider.llm.base_url || '—'],
                  ]} />
                  <ProviderGroup title="TTS" rows={[
                    ['Provider', config.provider.tts.provider],
                    ['Base URL', config.provider.tts.base_url || '—'],
                    ['Sample rate', `${config.provider.tts.sample_rate} Hz`],
                  ]} />
                  <ProviderGroup title="STT" rows={[
                    ['Provider', config.provider.stt.provider],
                    ['Model', config.provider.stt.model],
                    ['Language', config.provider.stt.language],
                  ]} />
                  <p className="settings-provider-note">
                    Provider settings are read-only. To change them, update the server
                    environment variables and restart the bot.
                  </p>
                </div>
              )}
            </TabsContent>
          </div>
        </Tabs>

        <div className="settings-drawer-footer">
          <Button variant="outline" size="sm" onClick={resetAll} disabled={!config}>
            Reset all
          </Button>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={onApply}
            disabled={dirtyCount === 0 || loading}
          >
            {dirtyCount > 0 ? `Apply ${dirtyCount} change${dirtyCount > 1 ? 's' : ''}` : 'Apply'}
          </Button>
        </div>
      </aside>
    </>
  );
}

function ProviderGroup({
  title,
  rows,
}: {
  title: string;
  rows: [string, string | number][];
}) {
  return (
    <div className="settings-provider-group">
      <div className="settings-provider-title">{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="settings-provider-row">
          <span className="settings-provider-key">{k}</span>
          <span className="settings-provider-val">{String(v)}</span>
        </div>
      ))}
    </div>
  );
}

/** 通过 persona id 拿前端 emoji（跟 config.ts 的 PERSONAS 一致） */
function emojiForPersona(pid: string): string {
  const map: Record<string, string> = {
    doubao: '🤗',
    xiaoai: '❤️',
    siri: '🎙️',
    deepseek: '🐳',
  };
  return map[pid] ?? '🤖';
}

function CloseIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}
