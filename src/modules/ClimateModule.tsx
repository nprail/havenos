import { motion } from 'framer-motion';
import { useStore } from '../store';

interface Props { detail?: boolean }

// Display range for the circular temp gauge (°F)
const TEMP_MIN = 60;
const TEMP_MAX = 100;
// Circle circumference: 2π × r where r = 80 → 2 × 3.14159 × 80 ≈ 502.7
const CIRCUMFERENCE = 2 * Math.PI * 80;

export default function ClimateModule({ detail = false }: Props) {
  const { ha, callService } = useStore();
  const climate = Object.values(ha.entities).find((e) => e.entity_id.startsWith('climate.'));

  if (!climate) {
    return <div className="p-4 text-white/40 text-sm">No climate entities</div>;
  }

  const currentTemp = climate.attributes.current_temperature as number;
  const setTemp = climate.attributes.temperature as number;
  const mode = climate.state;

  if (!detail) {
    return (
      <div className="p-4 flex flex-col gap-1">
        <p className="text-white/60 text-xs uppercase tracking-wide">Climate</p>
        <p className="text-white text-3xl font-light">{currentTemp}°</p>
        <p className="text-white/50 text-sm">Set: {setTemp}° · {mode}</p>
      </div>
    );
  }

  const modes = (climate.attributes.hvac_modes as string[] ?? []);
  // Fraction of arc to fill based on clamped temperature within TEMP_MIN–TEMP_MAX range
  const fraction = Math.max(0, Math.min(1, (currentTemp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)));
  const dashFilled = fraction * CIRCUMFERENCE;

  return (
    <div className="flex flex-col items-center gap-6 p-4">
      <div className="relative w-48 h-48">
        <svg width="192" height="192" viewBox="0 0 192 192">
          <circle cx="96" cy="96" r="80" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="12" />
          <circle cx="96" cy="96" r="80" fill="none" stroke="#3b82f6" strokeWidth="12"
            strokeDasharray={`${dashFilled} ${CIRCUMFERENCE}`}
            strokeLinecap="round" transform="rotate(-90 96 96)" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-white/50 text-sm">Current</span>
          <span className="text-white text-5xl font-thin">{currentTemp}°</span>
          <span className="text-white/50 text-sm">Set: {setTemp}°</span>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <motion.button className="w-14 h-14 rounded-full bg-blue-500/20 text-blue-400 text-2xl flex items-center justify-center"
          onPointerDown={() => void callService('climate', 'set_temperature', { entity_id: climate.entity_id, temperature: setTemp - 1 })}
          whileTap={{ scale: 0.92 }}>−</motion.button>
        <span className="text-white text-3xl font-light">{setTemp}°</span>
        <motion.button className="w-14 h-14 rounded-full bg-red-500/20 text-red-400 text-2xl flex items-center justify-center"
          onPointerDown={() => void callService('climate', 'set_temperature', { entity_id: climate.entity_id, temperature: setTemp + 1 })}
          whileTap={{ scale: 0.92 }}>+</motion.button>
      </div>

      <div className="flex flex-wrap gap-2 justify-center">
        {modes.map((m) => (
          <motion.button key={m}
            className={`px-4 py-2 rounded-xl text-sm font-medium ${m === mode ? 'bg-blue-500 text-white' : 'bg-white/10 text-white/70'}`}
            onPointerDown={() => void callService('climate', 'set_hvac_mode', { entity_id: climate.entity_id, hvac_mode: m })}
            whileTap={{ scale: 0.95 }}>
            {m.replace(/_/g, ' ')}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
