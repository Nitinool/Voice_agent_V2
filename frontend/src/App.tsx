/**
 * voice-agent-demo 前端
 * P3.x 最终布局：左侧常驻 HistorySidebar（头像栏+状态+历史）+ 右侧主舞台.
 * Plasma 全屏背景，每个 persona 切换驱动 plasma 配色（usePersonaPlasma）.
 */
import '@pipecat-ai/voice-ui-kit/styles';

import { useMemo, useRef } from 'react';
import {
  PipecatAppBase,
  FullScreenContainer,
  ControlBar,
  ControlBarDivider,
  ConnectButton,
  UserAudioControl,
  UserVideoControl,
  TranscriptOverlay,
  type PipecatBaseChildProps,
} from '@pipecat-ai/voice-ui-kit';
import { Plasma, type PlasmaConfig, type PlasmaRef } from '@pipecat-ai/voice-ui-kit/webgl';

import { DEFAULT_PERSONA, getPersona } from './config';
import { usePersonaPlasma } from './usePersonaPlasma';
import { usePersonaPlasmaState } from './usePersonaPlasmaState';
import { HistorySidebar } from './HistorySidebar';
import { HistoryReplayInjector } from './HistoryReplayInjector';
import { SessionActivator } from './SessionActivator';
import { SendTextInput } from './SendTextInput';
import { StatusOverlay } from './StatusOverlay';
import { CameraPreview } from './CameraPreview';
import { PersonaKaraokeOverlay } from './PersonaKaraokeOverlay';

/** Plasma 全屏背景层。挂在 PipecatAppBase children 内才能拿到 RTVI events。 */
function PlasmaBackground() {
  const plasmaRef = useRef<PlasmaRef | null>(null);
  usePersonaPlasma({ plasmaRef });
  usePersonaPlasmaState({ plasmaRef });

  // 初始 config = default persona 配色，避免 plasma 一开始用默认彩虹再跳到 doubao 金色
  const initialConfig = useMemo<PlasmaConfig>(() => {
    const [c1, c2, c3] = getPersona(DEFAULT_PERSONA).plasmaColors;
    return {
      useCustomColors: true,
      color1: c1,
      color2: c2,
      color3: c3,
      colorCycleSpeed: 1.0,
    };
  }, []);

  return (
    <Plasma
      ref={plasmaRef}
      className="app-plasma"
      initialConfig={initialConfig}
      fallbackContent={<div className="app-plasma-fallback" />}
    />
  );
}

export default function App() {
  return (
    <FullScreenContainer>
      <PipecatAppBase
        transportType="smallwebrtc"
        connectParams={{ webrtcUrl: '/api/offer' }}
        clientOptions={{ enableMic: true, enableCam: true }}
        connectOnMount
      >
        {({ handleConnect, handleDisconnect }: PipecatBaseChildProps) => (
          <div className="app-shell">
            <HistoryReplayInjector />
            <SessionActivator />
            <HistorySidebar />
            <main className="app-main">
              <PlasmaBackground />
              <div className="top-bar">
                <div className="slogan">
                  <span className="slogan-text">The innovation to move this world</span>
                </div>
              </div>
              <div className="app-stage">
                <div className="transcript-stage">
                  <StatusOverlay />
                  <PersonaKaraokeOverlay />
                  <TranscriptOverlay
                    participant="local"
                    size="md"
                    fadeInDuration={300}
                    fadeOutDuration={4000}
                  />
                </div>
                {/* 摄像头小窗（画中画），plasma 主视觉保留 */}
                <CameraPreview />
              </div>
              <div className="app-control-bar">
                <ControlBar>
                  <UserAudioControl />
                  <UserVideoControl noVideo noDevicePicker />
                  {/*
                    Disconnect 后 small-webrtc-transport 内部的 DailyMediaManager
                    无法干净复用（Daily call 对象 leave() 后 startCamera() 不再
                    resolve，会卡在 "connecting"）—— 这是 SDK 层 bug。
                    取巧绕过：Connect 按钮触发整页 reload，让一切从头来一遍。
                  */}
                  <ConnectButton
                    onConnect={() => window.location.reload()}
                    onDisconnect={handleDisconnect}
                  />
                  <ControlBarDivider />
                  <SendTextInput />
                </ControlBar>
              </div>
            </main>
          </div>
        )}
      </PipecatAppBase>
    </FullScreenContainer>
  );
}
