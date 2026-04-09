import { motion } from 'framer-motion'
import { useStore } from '../store'
import WeatherModule from '../modules/WeatherModule'
import MusicModule from '../modules/MusicModule'
import TimersModule from '../modules/TimersModule'
import LightsModule from '../modules/LightsModule'
import ClimateModule from '../modules/ClimateModule'
import CamerasModule from '../modules/CamerasModule'
import ScenesModule from '../modules/ScenesModule'

const MODULE_TITLES: Record<string, string> = {
  weather: 'Weather',
  music: 'Music',
  timers: 'Timers',
  lights: 'Lights',
  climate: 'Climate',
  cameras: 'Cameras',
  scenes: 'Scenes',
}

export default function ModuleDetail() {
  const { activeModule, navigate } = useStore()

  return (
    <div className="absolute inset-0 bg-zinc-900/95 backdrop-blur-xl flex flex-col">
      <div className="flex items-center gap-3 px-6 pt-6 pb-4">
        <motion.button
          className="w-12 h-12 flex items-center justify-center rounded-full bg-white/10 text-white text-2xl"
          onPointerDown={() => navigate('active')}
          whileTap={{ scale: 0.92 }}
        >
          ‹
        </motion.button>
        <h1 className="text-white text-2xl font-semibold">
          {MODULE_TITLES[activeModule ?? ''] ?? activeModule}
        </h1>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-6">
        {activeModule === 'weather' && <WeatherModule detail />}
        {activeModule === 'music' && <MusicModule detail />}
        {activeModule === 'timers' && <TimersModule detail />}
        {activeModule === 'lights' && <LightsModule detail />}
        {activeModule === 'climate' && <ClimateModule detail />}
        {activeModule === 'cameras' && <CamerasModule detail />}
        {activeModule === 'scenes' && <ScenesModule detail />}
      </div>
    </div>
  )
}
