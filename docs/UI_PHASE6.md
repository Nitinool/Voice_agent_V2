# UI Phase 6：Agent 设置面板 + Provider 只读展示

> 已存在最简版 Settings 下拉（仅 agent displayName）。本阶段扩展为**右侧滑出抽屉**，
> 分 Agents / Provider 两 tab：Agents 可改 prompt / voice / style / displayName，
> Provider 只读展示当前后端使用的 LLM / TTS / STT 元信息。

---

## 1. 设计决策一览（用户已确认）

| # | 决策 | 选择 |
|---|------|------|
| Q1 | API key 是否可改 | **去掉**（敏感字段不暴露前端） |
| Q2 | Agent 配置何时生效 | **下次切到该 persona 时**（A） |
| Q3 | 抽屉位置/宽度 | **右侧滑出，宽 400-450px**（A） |
| Q4 | Reset 粒度 | **每 agent 一个 + 顶部"全部恢复"**（B） |
| Q5 | 后端默认值 | personas.yaml = source of truth；前端进面板时拉一次 |
| Q6 | Apply 按钮 | 抽屉底部固定，dirty 时高亮 "Apply N changes" |
| Q7 | 后端响应 | `update_config` RTVI client-message → 写内存覆盖；不写盘 |
| Q8 | Provider 标签页 | **只读展示**（C），不让改任何字段 |

---

## 2. UI 结构

```
点 ⚙️ Settings 按钮 → 右侧滑出抽屉（width 420px）
┌─────────────────────────────────────┐
│ Settings                       [X] │
│ ─────────────────────────────────── │
│ [ Agents ] [ Provider ]            │  ← tabs
│ ─────────────────────────────────── │
│ Body (scrollable)                  │
│                                     │
│  Agents tab:                       │
│    Agent: 豆包  [Reset agent]      │
│      Display name [____________]   │
│      System prompt                 │
│      [______________________]      │
│      [______________________]      │
│      TTS voice  [冰糖 ▾]          │
│      Style prompt [____________]   │
│    ──────                          │
│    Agent: 小爱同学 [Reset agent]   │
│      ...                           │
│    ...                              │
│                                     │
│  Provider tab (只读):              │
│    LLM                             │
│      Provider:  cix AIHub          │
│      Model:     deepseek-v4-pro    │
│      Base URL:  …api.example.com   │
│    TTS                             │
│      Provider:  MiMo v2.5          │
│      Sample rate: 24000 Hz         │
│    STT                             │
│      Provider:  Deepgram nova-3    │
│      Language:  zh-CN              │
│ ─────────────────────────────────── │
│ [Reset all]      [Cancel] [Apply]  │ ← footer，固定底部
└─────────────────────────────────────┘
```

---

## 3. 数据流

### 3.1 进入设置面板

```
用户点 ⚙️
  → 抽屉打开
  → 前端发 RTVI client-request: { t: "get_config" }
  → 后端返回:
       { 
         personas_default: { doubao: {prompt, voice, style, ...}, ... },  // personas.yaml 原始值
         personas_current: { doubao: {prompt, voice, style, ...}, ... },  // 合并 override 后的当前值
         provider: { llm:{...}, tts:{...}, stt:{...} }
       }
  → 前端把 personas_current 灌进抽屉的 form state
  → 前端记 personas_default 用于 "reset" / "dirty 检测"
```

### 3.2 用户改完点 Apply

```
用户改 form
  → 抽屉 footer 显示 "Apply N changes"（N = 实际改动条目数）
用户点 Apply
  → 前端 sendClientMessage('update_config', { personas: {...diff...} })
  → 后端把 diff 合并进内存 override
  → 前端关抽屉 + 显示 toast "Applied. Next switch to agent will use new config."
```

### 3.3 用户点 Reset agent

```
点 "Reset 豆包"
  → 把豆包的 form fields 重置为 personas_default[doubao]
  → 还没 Apply，需要点 Apply 才生效（也可全部撤销 / Cancel）
```

### 3.4 用户点 Reset all

```
点 "Reset all"
  → 所有 4 个 persona 全重置为 personas_default
  → 显示一行警告 "Pending: all agents reset. Apply to commit."
```

### 3.5 用户点 Cancel

```
点 Cancel 或 X
  → 抽屉关闭，form state 丢弃，不影响后端
```

---

## 4. 后端改动

### 4.1 新增 `persona_overrides` 内存字典

`server/persona_router.py` 或新建 `server/persona_overrides.py`：

```python
# 全局内存，key=persona_id, value=Partial[PersonaConfig]
_PERSONA_OVERRIDES: dict[str, dict] = {}

def get_persona_config(persona_id: str) -> PersonaConfig:
    """返回 personas.yaml base + override 合并后的配置."""
    base = PERSONAS_YAML[persona_id]
    override = _PERSONA_OVERRIDES.get(persona_id, {})
    return PersonaConfig(**{**base, **override})

def update_persona_overrides(updates: dict[str, dict]) -> None:
    """前端 update_config 时调用，diff 合并到内存覆盖."""
    for pid, fields in updates.items():
        _PERSONA_OVERRIDES.setdefault(pid, {}).update(fields)
```

PersonaRouter 切 persona 时调 `get_persona_config(target)` 拿最新配置。

### 4.2 新增 RTVI client-message handler

`server/bot.py`：

```python
@worker.rtvi.event_handler("on_client_message")
async def handle_client_message(rtvi, message):
    if message.t == "set_persona":            # 已有
        await persona_router.switch_to(message.d["persona"])
    elif message.t == "get_config":           # 新增
        await rtvi.send_server_response({
            "personas_default": personas_yaml_raw,
            "personas_current": {p: asdict(get_persona_config(p)) for p in PERSONA_IDS},
            "provider": collect_provider_metadata(),
        })
    elif message.t == "update_config":         # 新增
        update_persona_overrides(message.d.get("personas", {}))
        await rtvi.send_server_response({"ok": True})
```

### 4.3 Provider 元数据收集

```python
def collect_provider_metadata() -> dict:
    """收集当前 service 的只读元信息，给前端展示."""
    return {
        "llm": {
            "provider": "cix AIHub",
            "model": os.environ.get("CIX_AI_HUB_MODEL", "deepseek-v4-pro"),
            "base_url": os.environ.get("CIX_AI_HUB_BASE_URL", ""),
        },
        "tts": {
            "provider": "MiMo v2.5",
            "sample_rate": MIMO_SAMPLE_RATE,
            "base_url": os.environ.get("MIMO_BASE_URL", DEFAULT_BASE_URL),
        },
        "stt": {
            "provider": "Deepgram nova-3",
            "language": "zh-CN",
        },
    }
```

---

## 5. 前端改动

### 5.1 新建文件

| 文件 | 作用 |
|------|------|
| `src/SettingsDrawer.tsx` | 抽屉组件（包含 Tabs + Footer 按钮） |
| `src/SettingsAgentsTab.tsx` | Agents 标签页 |
| `src/SettingsProviderTab.tsx` | Provider 只读标签页 |
| `src/useServerConfig.ts` | hook：通过 RTVI 拉 / 推 config |

### 5.2 改动文件

| 文件 | 改动 |
|------|------|
| `src/HistorySidebar.tsx` | ⚙️ 按钮：原下拉菜单 → 点击打开抽屉 |
| `src/useSettings.ts` | 加上 `agentOverrides` 字段（缓存到 localStorage），但**不再是真的应用层** —— 仅作"前端记忆 + 离线编辑" |
| `src/index.css` | 抽屉样式 |

### 5.3 useServerConfig hook

```tsx
type ServerConfig = {
  personas_default: Record<string, PersonaConfig>;
  personas_current: Record<string, PersonaConfig>;
  provider: { llm: {...}, tts: {...}, stt: {...} };
};

export function useServerConfig() {
  const client = usePipecatClient();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  
  const fetchConfig = useCallback(async () => {
    if (!client) return;
    const resp = await client.sendClientRequest('get_config', {}, 5000);
    setConfig(resp as ServerConfig);
  }, [client]);
  
  const applyConfig = useCallback(async (diff: { personas: Record<string, Partial<PersonaConfig>> }) => {
    if (!client) return;
    await client.sendClientMessage('update_config', diff);
    await fetchConfig();  // refresh
  }, [client, fetchConfig]);
  
  return { config, fetchConfig, applyConfig };
}
```

### 5.4 抽屉 dirty 检测逻辑

```tsx
// 在 SettingsAgentsTab 里维护本地 form state
const [draft, setDraft] = useState<Record<string, PersonaConfig>>(config?.personas_current ?? {});

// 计算改动数
const dirtyCount = useMemo(() => {
  let n = 0;
  for (const pid of PERSONA_IDS) {
    for (const field of ['displayName', 'systemPrompt', 'voice', 'stylePrompt']) {
      if (draft[pid]?.[field] !== config?.personas_current[pid]?.[field]) n++;
    }
  }
  return n;
}, [draft, config]);
```

### 5.5 抽屉 CSS

```css
.settings-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 420px;
  height: 100dvh;
  background: var(--color-card);
  border-left: 1px solid var(--color-border);
  z-index: 100;
  transform: translateX(100%);
  transition: transform 250ms ease;
  display: flex;
  flex-direction: column;
}
.settings-drawer.is-open {
  transform: translateX(0);
}
.settings-drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 99;
  opacity: 0;
  pointer-events: none;
  transition: opacity 250ms;
}
.settings-drawer-backdrop.is-open {
  opacity: 1;
  pointer-events: auto;
}
.settings-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.settings-drawer-footer {
  border-top: 1px solid var(--color-border);
  padding: 12px 16px;
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
```

---

## 6. 实施步骤

1. **后端先动** `server/personas.yaml` schema 确认 4 个字段：`label / system_prompt / voice / style_prompt`
2. **后端**：`get_persona_config` + `update_persona_overrides` + RTVI handler `get_config` / `update_config`
3. **后端**：`collect_provider_metadata`
4. **前端**：`useServerConfig` hook
5. **前端**：`SettingsDrawer` + Tabs + Footer
6. **前端**：`SettingsAgentsTab`（每 agent 卡片 + per-agent reset）
7. **前端**：`SettingsProviderTab`（只读列表）
8. **前端**：`HistorySidebar` 用抽屉替换原下拉菜单
9. **前端**：CSS
10. **联调**：tsc 0 错；启动连接 → 打开设置 → 改 prompt → Apply → 切走再切回来 → 看新 prompt 生效

---

## 7. 风险与确认

- **personas.yaml 当前实际字段**：要先看一遍当前 yaml 结构，确保 prompt / voice / style 等字段名跟前端对得上。
- **client.sendClientRequest 是否支持** —— 已确认 PipecatClient 1.10 有 `sendClientRequest(msgType, data, timeout)` 公开 API（client-js index.d.ts:934）。
- **provider metadata 收集**需要后端在启动时记录服务对象，不能从 .env 直接读（如果 .env 没设而用了 default 值会显示错）。后端建议在 main.py 启动时把实际 service 用的参数挂到全局 dict 上，`collect_provider_metadata` 读这个 dict。
- **抽屉 z-index**：注意不要被 dropdown menu 等盖住。

---

## 8. 不在本阶段做的

- API key 修改
- TTS voice 试听
- 配置导入/导出
- 后端配置写盘持久化（personas.yaml 永远不变）
- 实时 hot reload（必须切走 persona 再切回来）
