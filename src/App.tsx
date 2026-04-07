import { useEffect, useRef, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import useWebSocket from 'react-use-websocket';
import { useStore } from './store';
import type { AppSettings } from './store';
import AmbientScreen from './screens/AmbientScreen';
import ActiveScreen from './screens/ActiveScreen';
import ListeningScreen from './screens/ListeningScreen';
import ModuleDetail from './components/ModuleDetail';
import HaDashboard from './screens/HaDashboard';
import BroadcastOverlay from './components/BroadcastOverlay';
import SettingsScreen from './settings/SettingsScreen';

const DEV_MODE = import.meta.env.DEV;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/events`;

export default function App() {
  const { screen, navigate, setHaEntities, updateHaEntity, setVoiceState, queueBroadcast } = useStore();
  const inactivityTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetInactivity = useCallback(() => {
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current);
    if (screen === 'active') {
      inactivityTimer.current = setTimeout(() => navigate('ambient'), 30000);
    } else if (screen === 'detail' || screen === 'ha-dashboard' || screen === 'settings') {
      inactivityTimer.current = setTimeout(() => navigate('ambient'), 60000);
    }
  }, [screen, navigate]);

  useEffect(() => {
    resetInactivity();
    return () => { if (inactivityTimer.current) clearTimeout(inactivityTimer.current); };
  }, [screen, resetInactivity]);

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((cfg) => { useStore.getState().setSettings(cfg as AppSettings); })
      .catch(console.error);
  }, []);

  useWebSocket(WS_URL, {
    onMessage: (event) => {
      try {
        const msg = JSON.parse(event.data as string) as { type: string; payload: unknown };
        if (msg.type === 'ha_states') {
          setHaEntities(msg.payload as Parameters<typeof setHaEntities>[0]);
        } else if (msg.type === 'ha_state_changed') {
          const { new_state } = msg.payload as { new_state: Parameters<typeof updateHaEntity>[0] };
          if (new_state) updateHaEntity(new_state);
        } else if (msg.type === 'voice_wake') {
          setVoiceState('wake');
          navigate('listening');
        } else if (msg.type === 'voice_transcript') {
          setVoiceState('listening', (msg.payload as { transcript: string }).transcript);
        } else if (msg.type === 'voice_response') {
          setVoiceState('responding', undefined, (msg.payload as { response: string }).response);
        } else if (msg.type === 'voice_done') {
          setVoiceState('idle');
          setTimeout(() => navigate('active'), 1000);
        } else if (msg.type === 'broadcast') {
          queueBroadcast(msg.payload as { message: string; duration: number });
        }
      } catch { /* ignore */ }
    },
    shouldReconnect: () => true,
    reconnectInterval: 3000,
  });

  const handlePointerDown = useCallback(() => {
    resetInactivity();
    if (screen === 'ambient') navigate('active');
  }, [screen, navigate, resetInactivity]);

  return (
    <div
      className="relative w-full h-full overflow-hidden bg-black"
      onPointerDown={handlePointerDown}
      onPointerMove={resetInactivity}
    >
      <AnimatePresence mode="wait">
        {screen === 'ambient' && (
          <motion.div key="ambient" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }}>
            <AmbientScreen />
          </motion.div>
        )}
        {screen === 'active' && (
          <motion.div key="active" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <ActiveScreen />
          </motion.div>
        )}
        {screen === 'listening' && (
          <motion.div key="listening" className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ListeningScreen />
          </motion.div>
        )}
        {screen === 'detail' && (
          <motion.div key="detail" className="absolute inset-0" initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }} transition={{ type: 'spring', damping: 30, stiffness: 300 }}>
            <ModuleDetail />
          </motion.div>
        )}
        {screen === 'ha-dashboard' && (
          <motion.div key="ha-dashboard" className="absolute inset-0" initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }} transition={{ type: 'spring', damping: 30, stiffness: 300 }}>
            <HaDashboard />
          </motion.div>
        )}
        {screen === 'settings' && (
          <motion.div key="settings" className="absolute inset-0" initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }} transition={{ type: 'spring', damping: 30, stiffness: 300 }}>
            <SettingsScreen />
          </motion.div>
        )}
      </AnimatePresence>

      <BroadcastOverlay />

      {DEV_MODE && (
        <div className="fixed top-2 left-2 z-50 bg-yellow-500/80 text-black text-xs font-bold px-2 py-1 rounded pointer-events-none">
          DEV MODE
        </div>
      )}
    </div>
  );
}
