import { motion } from 'framer-motion'
import { format } from 'date-fns'
import { useEffect, useState } from 'react'
import PhotoBackground from '../components/PhotoBackground'
import WeatherIcon from '../components/WeatherIcon'
import WeatherModule from '../modules/WeatherModule'
import MusicModule from '../modules/MusicModule'
import TimersModule from '../modules/TimersModule'
import { useStore } from '../store'

export default function ActiveScreen() {
  const { ha, settings, navigate } = useStore()
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const weatherEntity = ha.entities[settings.weather.entity]

  const quickControls = [
    { id: 'lights', label: 'Lights', icon: '💡' },
    { id: 'climate', label: 'Climate', icon: '🌡️' },
    { id: 'cameras', label: 'Cameras', icon: '📷' },
    { id: 'scenes', label: 'Scenes', icon: '✨' },
  ]

  return (
    <div className="absolute inset-0 flex flex-col">
      <PhotoBackground dimmed />
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />

      <div className="relative z-10 flex flex-col h-full px-4 py-4 gap-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-white text-4xl font-thin">
              {format(now, 'HH:mm')}
            </div>
            <div className="text-white/70 text-sm">
              {format(now, 'EEEE, MMMM d')}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {weatherEntity && (
              <>
                <WeatherIcon condition={weatherEntity.state} size={28} />
                <span className="text-white text-2xl font-light">
                  {String(weatherEntity.attributes.temperature)}°
                </span>
              </>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 flex-1">
          <motion.div
            className="rounded-2xl bg-white/10 backdrop-blur-md overflow-hidden"
            whileTap={{ scale: 0.97 }}
            onPointerDown={() => navigate('detail', 'weather')}
          >
            <WeatherModule />
          </motion.div>
          <motion.div
            className="rounded-2xl bg-white/10 backdrop-blur-md overflow-hidden"
            whileTap={{ scale: 0.97 }}
            onPointerDown={() => navigate('detail', 'music')}
          >
            <MusicModule />
          </motion.div>
          <motion.div
            className="rounded-2xl bg-white/10 backdrop-blur-md overflow-hidden"
            whileTap={{ scale: 0.97 }}
            onPointerDown={() => navigate('detail', 'timers')}
          >
            <TimersModule />
          </motion.div>
        </div>

        <div className="grid grid-cols-6 gap-2">
          {quickControls.map((c) => (
            <motion.button
              key={c.id}
              className="flex flex-col items-center gap-1 bg-white/10 backdrop-blur-md rounded-xl py-3 px-2 min-h-[56px]"
              onPointerDown={() => navigate('detail', c.id)}
              whileTap={{ scale: 0.93 }}
            >
              <span className="text-xl">{c.icon}</span>
              <span className="text-white/80 text-xs">{c.label}</span>
            </motion.button>
          ))}
          <motion.button
            className="flex flex-col items-center gap-1 bg-white/10 backdrop-blur-md rounded-xl py-3 px-2 min-h-[56px]"
            onPointerDown={() => navigate('ha-dashboard')}
            whileTap={{ scale: 0.93 }}
          >
            <span className="text-xl">🏠</span>
            <span className="text-white/80 text-xs">HA</span>
          </motion.button>
          <motion.button
            className="flex flex-col items-center gap-1 bg-white/10 backdrop-blur-md rounded-xl py-3 px-2 min-h-[56px]"
            onPointerDown={() => navigate('settings')}
            whileTap={{ scale: 0.93 }}
          >
            <span className="text-xl">⚙️</span>
            <span className="text-white/80 text-xs">Settings</span>
          </motion.button>
        </div>
      </div>
    </div>
  )
}
