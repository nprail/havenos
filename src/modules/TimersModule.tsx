import { motion } from 'framer-motion';
import { useStore } from '../store';

interface Props { detail?: boolean }

function parseRemaining(remaining: string): number {
  const parts = remaining.split(':').map(Number);
  return (parts[0] ?? 0) * 3600 + (parts[1] ?? 0) * 60 + (parts[2] ?? 0);
}

function formatTime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

interface TimerEntity {
  entity_id: string;
  state: string;
  attributes: { duration?: string; remaining?: string; friendly_name?: string };
}

export default function TimersModule({ detail = false }: Props) {
  const { ha, callService } = useStore();

  const timers = Object.values(ha.entities).filter((e) => e.entity_id.startsWith('timer.')) as TimerEntity[];
  const active = timers.filter((t) => t.state === 'active' || t.state === 'paused');

  if (!detail) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <p className="text-white/60 text-xs uppercase tracking-wide">Timers</p>
        {active.length === 0 && <p className="text-white/30 text-sm">No active timers</p>}
        {active.slice(0, 2).map((t) => {
          const remaining = parseRemaining(String(t.attributes.remaining ?? '0:00:00'));
          const duration = parseRemaining(String(t.attributes.duration ?? '0:00:00'));
          const pct = duration > 0 ? (1 - remaining / duration) : 0;
          return (
            <div key={t.entity_id} className="flex items-center gap-3">
              <svg width="36" height="36" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="3" />
                <circle cx="18" cy="18" r="15" fill="none" stroke="#f97316" strokeWidth="3"
                  strokeDasharray={`${pct * 94.2} 94.2`} strokeLinecap="round" transform="rotate(-90 18 18)" />
              </svg>
              <div>
                <p className="text-white text-sm font-medium">{t.attributes.friendly_name ?? t.entity_id}</p>
                <p className="text-orange-400 text-xs">{formatTime(remaining)}</p>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h3 className="text-white/50 text-sm uppercase tracking-wide">Active Timers</h3>
      {active.map((t) => {
        const remaining = parseRemaining(String(t.attributes.remaining ?? '0:00:00'));
        const duration = parseRemaining(String(t.attributes.duration ?? '0:00:00'));
        const pct = duration > 0 ? (1 - remaining / duration) : 0;
        return (
          <div key={t.entity_id} className="bg-white/5 rounded-2xl p-4 flex items-center gap-4">
            <svg width="60" height="60" viewBox="0 0 60 60">
              <circle cx="30" cy="30" r="26" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="4" />
              <circle cx="30" cy="30" r="26" fill="none" stroke="#f97316" strokeWidth="4"
                strokeDasharray={`${pct * 163.4} 163.4`} strokeLinecap="round" transform="rotate(-90 30 30)" />
            </svg>
            <div className="flex-1">
              <p className="text-white font-medium">{t.attributes.friendly_name ?? t.entity_id}</p>
              <p className="text-orange-400 text-2xl font-mono">{formatTime(remaining)}</p>
            </div>
            <div className="flex gap-2">
              <motion.button className="w-10 h-10 bg-white/10 rounded-full flex items-center justify-center text-white"
                onPointerDown={() => void callService('timer', t.state === 'paused' ? 'start' : 'pause', { entity_id: t.entity_id })}
                whileTap={{ scale: 0.9 }}>
                {t.state === 'paused' ? '▶' : '⏸'}
              </motion.button>
              <motion.button className="w-10 h-10 bg-red-500/20 rounded-full flex items-center justify-center text-red-400"
                onPointerDown={() => void callService('timer', 'cancel', { entity_id: t.entity_id })}
                whileTap={{ scale: 0.9 }}>✕</motion.button>
            </div>
          </div>
        );
      })}

      <div className="bg-white/5 rounded-2xl p-4">
        <p className="text-white/50 text-sm mb-3">New Timer (minutes)</p>
        <div className="grid grid-cols-3 gap-2 mb-3">
          {[1, 5, 10, 15, 20, 30].map((m) => (
            <motion.button key={m}
              className="bg-white/10 rounded-xl py-3 text-white font-medium"
              onPointerDown={() => void callService('timer', 'start', { duration: `00:${String(m).padStart(2, '0')}:00` })}
              whileTap={{ scale: 0.95 }}>
              {m}m
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}
