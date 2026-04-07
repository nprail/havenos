import { motion } from 'framer-motion';
import { useStore } from '../store';

export default function HaDashboard() {
  const { navigate, settings } = useStore();
  const haUrl = settings.ha.url || settings.haUrl;

  return (
    <div className="absolute inset-0 bg-zinc-900 flex flex-col">
      <div className="flex items-center gap-3 px-6 pt-6 pb-3 border-b border-white/10">
        <motion.button
          className="w-12 h-12 flex items-center justify-center rounded-full bg-white/10 text-white text-2xl"
          onPointerDown={() => navigate('active')}
          whileTap={{ scale: 0.92 }}
        >
          ‹
        </motion.button>
        <h1 className="text-white text-xl font-semibold">Home Assistant</h1>
      </div>
      {haUrl ? (
        <iframe
          src={`${haUrl}/lovelace/0`}
          className="flex-1 w-full border-0"
          title="Home Assistant Lovelace"
        />
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-white/50 text-center">No HA URL configured.<br/>Go to Settings to configure.</p>
        </div>
      )}
    </div>
  );
}
