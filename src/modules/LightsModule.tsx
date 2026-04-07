import { motion } from 'framer-motion';
import { useStore } from '../store';

interface Props { detail?: boolean }

export default function LightsModule({ detail = false }: Props) {
  const { ha, callService } = useStore();
  const lights = Object.values(ha.entities).filter((e) => e.entity_id.startsWith('light.'));

  if (!detail) {
    const onCount = lights.filter((l) => l.state === 'on').length;
    return (
      <div className="p-4 flex flex-col gap-2">
        <p className="text-white/60 text-xs uppercase tracking-wide">Lights</p>
        <p className="text-white text-2xl font-light">{onCount} <span className="text-white/50 text-base">on</span></p>
        <p className="text-white/40 text-xs">{lights.length} total</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {lights.map((light) => {
        const isOn = light.state === 'on';
        const brightness = (light.attributes.brightness as number ?? 0) / 255 * 100;
        return (
          <div key={light.entity_id} className="bg-white/5 rounded-2xl p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-white font-medium">{String(light.attributes.friendly_name ?? light.entity_id)}</span>
              <motion.button
                className={`w-14 h-7 rounded-full relative transition-colors ${isOn ? 'bg-yellow-400' : 'bg-white/20'}`}
                onPointerDown={() => void callService('light', isOn ? 'turn_off' : 'turn_on', { entity_id: light.entity_id })}
                whileTap={{ scale: 0.95 }}
              >
                <motion.div
                  className="w-5 h-5 rounded-full bg-white absolute top-1"
                  animate={{ x: isOn ? 32 : 4 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                />
              </motion.button>
            </div>
            {isOn && (
              <input type="range" min={0} max={100} value={Math.round(brightness)}
                className="w-full h-1 appearance-none bg-white/20 rounded-full"
                onChange={(e) => { void callService('light', 'turn_on', { entity_id: light.entity_id, brightness_pct: parseInt(e.target.value) }); }} />
            )}
          </div>
        );
      })}
      {lights.length === 0 && <p className="text-white/30 text-sm">No lights found</p>}
    </div>
  );
}
