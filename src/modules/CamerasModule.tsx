import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../store'

interface Props {
  detail?: boolean
}

export default function CamerasModule({ detail = false }: Props) {
  const { ha, settings } = useStore()
  const [selected, setSelected] = useState<string | null>(null)
  const cameras = Object.values(ha.entities).filter((e) =>
    e.entity_id.startsWith('camera.'),
  )

  const cameraUrl = (entityId: string) =>
    `${settings.ha.url}/api/camera_proxy/${entityId}?token=${settings.ha.token}`

  if (!detail) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <p className="text-white/60 text-xs uppercase tracking-wide">Cameras</p>
        <p className="text-white text-2xl font-light">{cameras.length}</p>
        <p className="text-white/40 text-xs">cameras</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="grid grid-cols-2 gap-3">
        {cameras.map((cam) => (
          <motion.div
            key={cam.entity_id}
            className="relative aspect-video bg-black rounded-xl overflow-hidden"
            onPointerDown={() => setSelected(cam.entity_id)}
            whileTap={{ scale: 0.97 }}
          >
            <img
              src={cameraUrl(cam.entity_id)}
              alt={String(cam.attributes.friendly_name ?? cam.entity_id)}
              className="w-full h-full object-cover"
              onError={(e) => {
                ;(e.target as HTMLImageElement).style.display = 'none'
              }}
            />
            <p className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-xs p-1 text-center">
              {String(cam.attributes.friendly_name ?? cam.entity_id)}
            </p>
          </motion.div>
        ))}
      </div>

      <AnimatePresence>
        {selected && (
          <motion.div
            className="fixed inset-0 bg-black z-50 flex flex-col"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="flex items-center p-4">
              <motion.button
                className="w-10 h-10 bg-white/10 rounded-full text-white text-xl flex items-center justify-center"
                onPointerDown={() => setSelected(null)}
                whileTap={{ scale: 0.9 }}
              >
                ‹
              </motion.button>
            </div>
            <img
              src={cameraUrl(selected)}
              alt=""
              className="flex-1 object-contain"
            />
          </motion.div>
        )}
      </AnimatePresence>

      {cameras.length === 0 && (
        <p className="text-white/30 text-sm">No cameras found</p>
      )}
    </div>
  )
}
