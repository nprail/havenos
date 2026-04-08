import { motion } from 'framer-motion'
import Waveform from '../components/Waveform'
import { useStore } from '../store'

const STATE_LABELS: Record<string, string> = {
  wake: 'Listening...',
  listening: 'Listening...',
  processing: 'Thinking...',
  responding: 'Responding',
  idle: 'Ready',
}

export default function ListeningScreen() {
  const { voice, navigate, setVoiceState } = useStore()

  const handleDismiss = () => {
    setVoiceState('idle')
    navigate('active')
  }

  return (
    <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex flex-col items-center justify-end pb-12">
      <motion.div
        className="w-full max-w-lg bg-zinc-900/95 backdrop-blur-xl rounded-3xl mx-4 p-6 flex flex-col gap-4"
        initial={{ y: 200 }}
        animate={{ y: 0 }}
        transition={{ type: 'spring', damping: 28, stiffness: 280 }}
      >
        <div className="flex items-center justify-between">
          <span className="text-white/80 text-sm font-medium tracking-wide uppercase">
            {STATE_LABELS[voice.state] ?? 'Listening'}
          </span>
          <motion.button
            className="w-10 h-10 rounded-full bg-white/10 text-white/70 text-lg flex items-center justify-center"
            onPointerDown={handleDismiss}
            whileTap={{ scale: 0.9 }}
          >
            ✕
          </motion.button>
        </div>

        <Waveform />

        {voice.transcript && (
          <div className="bg-white/5 rounded-xl px-4 py-3">
            <p className="text-white/50 text-xs mb-1">You said</p>
            <p className="text-white text-base">{voice.transcript}</p>
          </div>
        )}

        {voice.response && (
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3">
            <p className="text-blue-400/70 text-xs mb-1">Response</p>
            <p className="text-white text-base">{voice.response}</p>
          </div>
        )}
      </motion.div>
    </div>
  )
}
