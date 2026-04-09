import { useEffect, useRef, useCallback, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import useWebSocket from 'react-use-websocket'
import { useStore } from './store'
import type { AppSettings, HAArea, HAEntityRegistryEntry } from './store'
import AmbientScreen from './screens/AmbientScreen'
import ActiveScreen from './screens/ActiveScreen'
import ListeningScreen from './screens/ListeningScreen'
import ModuleDetail from './components/ModuleDetail'
import HaDashboard from './screens/HaDashboard'
import BroadcastOverlay from './components/BroadcastOverlay'
import SettingsScreen from './settings/SettingsScreen'

const DEV_MODE = import.meta.env.DEV
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/events`

export default function App() {
  const {
    screen,
    navigate,
    setHaEntities,
    updateHaEntity,
    setHaAreas,
    setHaEntityRegistry,
    setVoiceState,
    queueBroadcast,
    triggerPhotoNav,
  } = useStore()
  const inactivityTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pointerStartRef = useRef<{ x: number; y: number } | null>(null)
  const [countdownWarning, setCountdownWarning] = useState(false)
  const [countdownSeconds, setCountdownSeconds] = useState(10)

  const clearCountdown = useCallback(() => {
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
      countdownIntervalRef.current = null
    }
    setCountdownWarning(false)
    setCountdownSeconds(10)
  }, [])

  const resetInactivity = useCallback(() => {
    clearCountdown()
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current)

    let timeout = 0
    if (screen === 'active') timeout = 30000
    else if (
      screen === 'detail' ||
      screen === 'ha-dashboard' ||
      screen === 'settings'
    )
      timeout = 60000

    if (!timeout) return

    inactivityTimer.current = setTimeout(() => {
      setCountdownWarning(true)
      let remaining = 10
      setCountdownSeconds(remaining)
      countdownIntervalRef.current = setInterval(() => {
        remaining -= 1
        setCountdownSeconds(remaining)
        if (remaining <= 0) {
          clearInterval(countdownIntervalRef.current!)
          countdownIntervalRef.current = null
          setCountdownWarning(false)
          navigate('ambient')
        }
      }, 1000)
    }, Math.max(0, timeout - 10000))
  }, [screen, navigate, clearCountdown])

  useEffect(() => {
    resetInactivity()
    return () => {
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
    }
  }, [screen, resetInactivity])

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((cfg) => {
        useStore.getState().setSettings(cfg as AppSettings)
      })
      .catch(console.error)
  }, [])

  useWebSocket(WS_URL, {
    onMessage: (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type: string
          payload: unknown
        }
        if (msg.type === 'ha_states') {
          setHaEntities(msg.payload as Parameters<typeof setHaEntities>[0])
        } else if (msg.type === 'ha_areas') {
          setHaAreas(msg.payload as HAArea[])
        } else if (msg.type === 'ha_entity_registry') {
          setHaEntityRegistry(msg.payload as HAEntityRegistryEntry[])
        } else if (msg.type === 'ha_state_changed') {
          const { new_state } = msg.payload as {
            new_state: Parameters<typeof updateHaEntity>[0]
          }
          if (new_state) updateHaEntity(new_state)
        } else if (msg.type === 'voice_wake') {
          setVoiceState('wake')
          navigate('listening')
        } else if (msg.type === 'voice_transcript') {
          setVoiceState(
            'listening',
            (msg.payload as { transcript: string }).transcript,
          )
        } else if (msg.type === 'voice_response') {
          setVoiceState(
            'responding',
            undefined,
            (msg.payload as { response: string }).response,
          )
        } else if (msg.type === 'voice_done') {
          setVoiceState('idle')
          setTimeout(() => navigate('active'), 1000)
        } else if (msg.type === 'broadcast') {
          queueBroadcast(msg.payload as { message: string; duration: number })
        }
      } catch {
        /* ignore */
      }
    },
    shouldReconnect: () => true,
    reconnectInterval: 3000,
  })

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      pointerStartRef.current = { x: e.clientX, y: e.clientY }
      resetInactivity()
    },
    [resetInactivity],
  )

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!pointerStartRef.current) return
      const dx = e.clientX - pointerStartRef.current.x
      const dy = e.clientY - pointerStartRef.current.y
      const startY = pointerStartRef.current.y
      pointerStartRef.current = null

      const isHSwipe =
        Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.5
      const isDSwipe =
        dy > 80 && startY < 80 && dy > Math.abs(dx) * 1.5

      // Swipe-down from top 80px dismisses detail/dashboard overlays
      if (isDSwipe && (screen === 'detail' || screen === 'ha-dashboard')) {
        navigate('active')
        return
      }

      // Horizontal swipe in ambient navigates photos
      if (isHSwipe && screen === 'ambient') {
        triggerPhotoNav(dx < 0 ? 'next' : 'prev')
        return
      }

      // Tap-in-ambient → active (no significant movement)
      if (screen === 'ambient' && Math.abs(dx) < 20 && Math.abs(dy) < 20) {
        navigate('active')
      }
    },
    [screen, navigate, triggerPhotoNav],
  )

  return (
    <div
      className="relative w-full h-full overflow-hidden bg-black"
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerMove={resetInactivity}
    >
      <AnimatePresence mode="wait">
        {screen === 'ambient' && (
          <motion.div
            key="ambient"
            className="absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
          >
            <AmbientScreen />
          </motion.div>
        )}
        {screen === 'active' && (
          <motion.div
            key="active"
            className="absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <ActiveScreen />
          </motion.div>
        )}
        {screen === 'listening' && (
          <motion.div
            key="listening"
            className="absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <ListeningScreen />
          </motion.div>
        )}
        {screen === 'detail' && (
          <motion.div
            key="detail"
            className="absolute inset-0"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            <ModuleDetail />
          </motion.div>
        )}
        {screen === 'ha-dashboard' && (
          <motion.div
            key="ha-dashboard"
            className="absolute inset-0"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            <HaDashboard />
          </motion.div>
        )}
        {screen === 'settings' && (
          <motion.div
            key="settings"
            className="absolute inset-0"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            <SettingsScreen />
          </motion.div>
        )}
      </AnimatePresence>

      <BroadcastOverlay />

      <AnimatePresence>
        {countdownWarning && (
          <motion.div
            key="countdown"
            className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 bg-black/70 backdrop-blur-sm"
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            <span className="text-white/80 text-sm">
              Returning to home in {countdownSeconds}s
            </span>
            <motion.button
              className="px-5 py-2 bg-white/20 rounded-full text-white text-sm font-medium"
              onPointerDown={(e) => {
                e.stopPropagation()
                resetInactivity()
              }}
              whileTap={{ scale: 0.95 }}
            >
              Stay
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>

      {DEV_MODE && (
        <div className="fixed top-2 left-2 z-50 bg-yellow-500/80 text-black text-xs font-bold px-2 py-1 rounded pointer-events-none">
          DEV MODE
        </div>
      )}
    </div>
  )
}
