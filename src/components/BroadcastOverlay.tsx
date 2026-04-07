import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../store';

export default function BroadcastOverlay() {
  const { broadcasts, dismissBroadcast } = useStore();
  const current = broadcasts.current;

  useEffect(() => {
    if (!current) return;
    const timer = setTimeout(() => dismissBroadcast(), current.duration);
    return () => clearTimeout(timer);
  }, [current, dismissBroadcast]);

  return (
    <AnimatePresence>
      {current && (
        <motion.div
          key={current.message}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 max-w-lg w-full px-4"
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        >
          <div className="relative overflow-hidden rounded-2xl backdrop-blur-xl bg-white/10 border border-white/20 p-4 shadow-2xl">
            <p className="text-white text-base font-medium">{current.message}</p>
            <motion.div
              className="absolute bottom-0 left-0 h-1 bg-blue-400 rounded"
              initial={{ width: '100%' }}
              animate={{ width: '0%' }}
              transition={{ duration: current.duration / 1000, ease: 'linear' }}
            />
            <motion.button
              className="absolute top-3 right-3 text-white/60 text-xl leading-none"
              onPointerDown={(e) => { e.stopPropagation(); dismissBroadcast(); }}
              whileTap={{ scale: 0.9 }}
            >
              ×
            </motion.button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
