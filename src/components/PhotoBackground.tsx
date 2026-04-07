import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../store';

const DEV_MODE = import.meta.env.DEV;

const GRADIENT_BACKGROUNDS = [
  'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
  'linear-gradient(135deg, #2d1b69 0%, #11998e 100%)',
  'linear-gradient(135deg, #3a1c71 0%, #d76d77 50%, #ffaf7b 100%)',
  'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
  'linear-gradient(135deg, #1f4037 0%, #99f2c8 100%)',
];

interface Props {
  dimmed?: boolean;
}

export default function PhotoBackground({ dimmed = false }: Props) {
  const { settings } = useStore();
  const [photos, setPhotos] = useState<string[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentPhoto, setCurrentPhoto] = useState<string | null>(null);
  const [isPortrait, setIsPortrait] = useState(false);
  const [gradientIndex, setGradientIndex] = useState(0);

  const cycleInterval = (settings.cycleInterval ?? 60) * 1000;

  const loadImmichPhotos = useCallback(async () => {
    if (DEV_MODE || !settings.immich.url || !settings.immich.apiKey) return;
    try {
      const url = settings.immich.mode === 'album' && settings.immich.albumId
        ? `${settings.immich.url}/api/albums/${settings.immich.albumId}/assets`
        : `${settings.immich.url}/api/assets?isFavorite=true&type=IMAGE&size=50`;
      const res = await fetch(url, { headers: { 'x-api-key': settings.immich.apiKey } });
      const data = await res.json() as Array<{ id: string }>;
      const urls = data.map((a) => `${settings.immich.url}/api/assets/${a.id}/thumbnail?size=preview`);
      setPhotos(urls);
    } catch (e) {
      console.error('[PhotoBackground] immich error', e);
    }
  }, [settings.immich]);

  useEffect(() => { void loadImmichPhotos(); }, [loadImmichPhotos]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (DEV_MODE) {
        setGradientIndex((i) => (i + 1) % GRADIENT_BACKGROUNDS.length);
      } else if (photos.length > 0) {
        setCurrentIndex((i) => (i + 1) % photos.length);
      }
    }, cycleInterval);
    return () => clearInterval(timer);
  }, [photos, cycleInterval]);

  useEffect(() => {
    if (DEV_MODE || photos.length === 0) return;
    const url = photos[currentIndex];
    const img = new Image();
    img.onload = () => {
      setIsPortrait(img.naturalHeight > img.naturalWidth);
      setCurrentPhoto(url);
    };
    img.src = url ?? '';
  }, [currentIndex, photos]);

  if (DEV_MODE) {
    return (
      <AnimatePresence mode="wait">
        <motion.div
          key={gradientIndex}
          className="absolute inset-0"
          style={{ background: GRADIENT_BACKGROUNDS[gradientIndex] }}
          initial={{ opacity: 0 }}
          animate={{ opacity: dimmed ? 0.4 : 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.8 }}
        />
      </AnimatePresence>
    );
  }

  if (!currentPhoto) {
    return <div className="absolute inset-0 bg-zinc-900" style={{ opacity: dimmed ? 0.4 : 1 }} />;
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div key={currentPhoto} className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: dimmed ? 0.4 : 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.8 }}>
        {isPortrait ? (
          <>
            <div className="absolute inset-0 bg-cover bg-center blur-2xl scale-110" style={{ backgroundImage: `url(${currentPhoto})` }} />
            <img src={currentPhoto} alt="" className="absolute inset-0 m-auto max-h-full object-contain" />
          </>
        ) : (
          <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${currentPhoto})` }} />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
