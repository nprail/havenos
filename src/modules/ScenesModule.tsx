import { motion } from 'framer-motion';
import { useStore } from '../store';

interface Props { detail?: boolean }

export default function ScenesModule({ detail = false }: Props) {
  const { ha, callService } = useStore();
  const scenes = Object.values(ha.entities).filter((e) => e.entity_id.startsWith('scene.'));

  if (!detail) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <p className="text-white/60 text-xs uppercase tracking-wide">Scenes</p>
        <p className="text-white text-2xl font-light">{scenes.length}</p>
        <p className="text-white/40 text-xs">scenes available</p>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="grid grid-cols-2 gap-3">
        {scenes.map((scene) => (
          <motion.button key={scene.entity_id}
            className="bg-white/10 backdrop-blur-md rounded-2xl p-4 text-left min-h-[80px] flex flex-col justify-between"
            onPointerDown={() => void callService('scene', 'turn_on', { entity_id: scene.entity_id })}
            whileTap={{ scale: 0.95 }}>
            <span className="text-2xl">✨</span>
            <span className="text-white font-medium text-sm">{String(scene.attributes.friendly_name ?? scene.entity_id.replace('scene.', ''))}</span>
          </motion.button>
        ))}
      </div>
      {scenes.length === 0 && <p className="text-white/30 text-sm">No scenes found</p>}
    </div>
  );
}
