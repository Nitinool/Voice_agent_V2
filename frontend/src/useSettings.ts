/**
 * useSettings —— localStorage 持久化的演示设置.
 *
 * 纯前端，不入库、不动后端 personas.yaml。刷新后保留，换机重置.
 *
 * 字段：
 *   agentNames: { [personaId]: 显示名 } —— 覆盖 config.ts 的 label
 *   collapsed: boolean —— 左侧 sidebar 是否折叠成窄条
 *
 * 风格对齐官方 hook：UseXxxResult + readonly + setter.
 */
import { useCallback, useEffect, useState } from 'react';
import { PERSONAS } from './config';

const STORAGE_KEY = 'voice-agent-demo-settings';

export interface DemoSettings {
  agentNames: Record<string, string>;
  collapsed: boolean;
}

const DEFAULTS: DemoSettings = {
  agentNames: Object.fromEntries(PERSONAS.map((p) => [p.id, p.label])),
  collapsed: false,
};

function load(): DemoSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<DemoSettings>;
    return {
      agentNames: { ...DEFAULTS.agentNames, ...(parsed.agentNames ?? {}) },
      collapsed: parsed.collapsed ?? false,
    };
  } catch {
    return DEFAULTS;
  }
}

export interface UseSettingsResult {
  readonly settings: DemoSettings;
  setAgentName: (personaId: string, name: string) => void;
  setCollapsed: (collapsed: boolean) => void;
}

export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<DemoSettings>(DEFAULTS);

  useEffect(() => {
    setSettings(load());
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* 忽略写入失败（隐私模式等） */
    }
  }, [settings]);

  const setAgentName = useCallback((personaId: string, name: string) => {
    setSettings((s) => ({
      ...s,
      agentNames: { ...s.agentNames, [personaId]: name || DEFAULTS.agentNames[personaId] },
    }));
  }, []);

  const setCollapsed = useCallback((collapsed: boolean) => {
    setSettings((s) => ({ ...s, collapsed }));
  }, []);

  return { settings, setAgentName, setCollapsed } as const;
}
