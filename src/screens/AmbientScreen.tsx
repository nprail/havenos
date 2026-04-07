import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { format } from 'date-fns';
import PhotoBackground from '../components/PhotoBackground';
import WeatherIcon from '../components/WeatherIcon';
import { useStore } from '../store';

export default function AmbientScreen() {
  const { ha, settings, nowPlaying } = useStore();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const weatherEntity = ha.entities[settings.weather.entity];
  const weatherForecast = weatherEntity
    ? (weatherEntity.attributes.forecast as Array<{ temperature: number; templow?: number }> | undefined)
    : undefined;
  const timers = Object.values(ha.entities).filter((e) => e.entity_id.startsWith('timer.') && e.state === 'active');

  return (
    <div className="absolute inset-0">
      <PhotoBackground />

      <div className="absolute bottom-0 left-0 right-0 h-64 bg-gradient-to-t from-black/70 to-transparent" />

      {timers.length > 0 && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-black/40 backdrop-blur-md rounded-full px-4 py-2 flex items-center gap-2">
          <span className="text-orange-400 text-sm">⏱</span>
          <span className="text-white text-sm font-medium">{timers.length} timer{timers.length > 1 ? 's' : ''} active</span>
        </div>
      )}

      <div className="absolute bottom-6 left-6">
        <div className="bg-black/30 backdrop-blur-sm rounded-2xl px-5 py-4">
          <div className="text-white font-thin leading-none" style={{ fontSize: 96 }}>
            {format(now, 'HH:mm')}
          </div>
          <div className="text-white/80 text-2xl mt-1 font-light">
            {format(now, 'EEEE, MMMM d')}
          </div>
        </div>
      </div>

      {weatherEntity && (
        <div className="absolute bottom-6 right-6">
          <div className="bg-black/30 backdrop-blur-sm rounded-2xl px-5 py-4 flex flex-col items-end gap-1">
            <div className="flex items-center gap-3">
              <WeatherIcon condition={weatherEntity.state} size={48} />
              <span className="text-white font-light" style={{ fontSize: 56 }}>
                {String(weatherEntity.attributes.temperature)}°
              </span>
            </div>
            <div className="text-white/70 text-base">
              H:{String(weatherForecast?.[0]?.temperature ?? weatherEntity?.attributes.temperature ?? '--')}° L:{String(weatherForecast?.[0]?.templow ?? '--')}°
            </div>
          </div>
        </div>
      )}

      {nowPlaying.state === 'playing' && nowPlaying.title && (
        <motion.div
          className="absolute bottom-0 left-0 right-0 bg-black/50 backdrop-blur-md px-6 py-3 flex items-center gap-4"
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
        >
          {nowPlaying.artUrl && <img src={nowPlaying.artUrl} alt="" className="w-10 h-10 rounded object-cover" />}
          <div className="flex-1 min-w-0">
            <p className="text-white text-sm font-medium truncate">{nowPlaying.title}</p>
            <p className="text-white/60 text-xs truncate">{nowPlaying.artist}</p>
          </div>
          <div className="text-white/60 text-lg">♪</div>
        </motion.div>
      )}
    </div>
  );
}
