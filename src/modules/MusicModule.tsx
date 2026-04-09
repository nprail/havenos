import { motion } from 'framer-motion'
import { useStore } from '../store'

interface Props {
  detail?: boolean
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function MusicModule({ detail = false }: Props) {
  const { nowPlaying, callService } = useStore()

  const isPlaying = nowPlaying.state === 'playing'

  if (!detail) {
    return (
      <div className="p-4 flex flex-col gap-2">
        {nowPlaying.artUrl ? (
          <img
            src={nowPlaying.artUrl}
            alt=""
            className="w-full h-24 object-cover rounded-lg"
          />
        ) : (
          <div className="w-full h-24 bg-white/5 rounded-lg flex items-center justify-center">
            <span className="text-4xl">♪</span>
          </div>
        )}
        <p className="text-white text-sm font-medium truncate">
          {nowPlaying.title || 'Nothing playing'}
        </p>
        <p className="text-white/50 text-xs truncate">{nowPlaying.artist}</p>
        <div className="flex items-center gap-3 mt-1">
          <motion.button
            className="text-white/70 text-lg w-8 h-8 flex items-center justify-center"
            onPointerDown={() => {
              void callService('media_player', 'media_previous_track')
            }}
            whileTap={{ scale: 0.9 }}
          >
            ⏮
          </motion.button>
          <motion.button
            className="text-white text-2xl w-10 h-10 flex items-center justify-center"
            onPointerDown={() => {
              void callService(
                'media_player',
                isPlaying ? 'media_pause' : 'media_play',
              )
            }}
            whileTap={{ scale: 0.9 }}
          >
            {isPlaying ? '⏸' : '▶'}
          </motion.button>
          <motion.button
            className="text-white/70 text-lg w-8 h-8 flex items-center justify-center"
            onPointerDown={() => {
              void callService('media_player', 'media_next_track')
            }}
            whileTap={{ scale: 0.9 }}
          >
            ⏭
          </motion.button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-6 p-4">
      {nowPlaying.artUrl ? (
        <img
          src={nowPlaying.artUrl}
          alt=""
          className="w-48 h-48 object-cover rounded-2xl shadow-2xl"
        />
      ) : (
        <div className="w-48 h-48 bg-white/10 rounded-2xl flex items-center justify-center">
          <span className="text-6xl">♪</span>
        </div>
      )}
      <div className="text-center">
        <p className="text-white text-xl font-semibold">
          {nowPlaying.title || 'Nothing playing'}
        </p>
        <p className="text-white/60 text-base">{nowPlaying.artist}</p>
        <p className="text-white/40 text-sm">{nowPlaying.album}</p>
      </div>

      {nowPlaying.duration > 0 && (
        <div className="w-full">
          <div className="h-1 bg-white/20 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all"
              style={{
                width: `${(nowPlaying.position / nowPlaying.duration) * 100}%`,
              }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-white/40 text-xs">
              {formatTime(nowPlaying.position)}
            </span>
            <span className="text-white/40 text-xs">
              {formatTime(nowPlaying.duration)}
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-6">
        <motion.button
          className="text-white/70 text-2xl w-12 h-12 flex items-center justify-center"
          onPointerDown={() => {
            void callService('media_player', 'media_previous_track')
          }}
          whileTap={{ scale: 0.9 }}
        >
          ⏮
        </motion.button>
        <motion.button
          className="text-white text-4xl w-16 h-16 bg-white/10 rounded-full flex items-center justify-center"
          onPointerDown={() => {
            void callService(
              'media_player',
              isPlaying ? 'media_pause' : 'media_play',
            )
          }}
          whileTap={{ scale: 0.93 }}
        >
          {isPlaying ? '⏸' : '▶'}
        </motion.button>
        <motion.button
          className="text-white/70 text-2xl w-12 h-12 flex items-center justify-center"
          onPointerDown={() => {
            void callService('media_player', 'media_next_track')
          }}
          whileTap={{ scale: 0.9 }}
        >
          ⏭
        </motion.button>
      </div>

      <div className="w-full flex items-center gap-3">
        <span className="text-white/40 text-sm">🔈</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={nowPlaying.volume}
          className="flex-1 h-1 bg-white/20 rounded-full appearance-none"
          onChange={(e) => {
            void callService('media_player', 'volume_set', {
              volume_level: parseFloat(e.target.value),
            })
          }}
        />
        <span className="text-white/40 text-sm">🔊</span>
      </div>
    </div>
  )
}
