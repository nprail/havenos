import WeatherIcon from '../components/WeatherIcon';
import { useStore } from '../store';
import { format } from 'date-fns';

interface Props { detail?: boolean }

export default function WeatherModule({ detail = false }: Props) {
  const { ha, settings } = useStore();
  const entity = ha.entities[settings.weather.entity];

  if (!entity) {
    return <div className="p-4 text-white/40 text-sm">No weather data</div>;
  }

  const temp = entity.attributes.temperature as number;
  const tempUnit = String(entity.attributes.temperature_unit ?? '°F');
  const condition = entity.state;
  const forecast = (entity.attributes.forecast as Array<{ datetime: string; condition: string; temperature: number; templow?: number }>) ?? [];

  if (!detail) {
    return (
      <div className="p-4 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <WeatherIcon condition={condition} size={32} />
          <span className="text-white text-3xl font-light">{temp}°</span>
        </div>
        <p className="text-white/60 text-sm capitalize">{condition.replace(/-/g, ' ')}</p>
        {forecast[0] && (
          <p className="text-white/50 text-xs">H:{forecast[0].temperature}° L:{forecast[0].templow ?? '--'}°</p>
        )}
        <div className="flex gap-2 overflow-x-auto mt-1">
          {forecast.slice(0, 4).map((f, i) => (
            <div key={i} className="flex flex-col items-center gap-1 min-w-[40px]">
              <span className="text-white/50 text-xs">{i === 0 ? 'Now' : `+${i}h`}</span>
              <WeatherIcon condition={f.condition} size={20} />
              <span className="text-white text-xs">{f.temperature}°</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4">
      <div className="flex items-center gap-6">
        <WeatherIcon condition={condition} size={80} />
        <div>
          <div className="text-white text-6xl font-thin">{temp}{tempUnit}</div>
          <div className="text-white/70 text-lg capitalize">{condition.replace(/-/g, ' ')}</div>
          <div className="text-white/50 text-sm mt-1">
            Humidity: {String(entity.attributes.humidity ?? '--')}% · Wind: {String(entity.attributes.wind_speed ?? '--')} mph
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-white/50 text-sm uppercase tracking-wide mb-3">7-Day Forecast</h3>
        <div className="flex flex-col gap-2">
          {forecast.map((f, i) => (
            <div key={i} className="flex items-center gap-3 bg-white/5 rounded-xl px-4 py-2">
              <span className="text-white/60 text-sm w-24">{i === 0 ? 'Today' : format(new Date(f.datetime), 'EEE')}</span>
              <WeatherIcon condition={f.condition} size={24} />
              <div className="flex-1 flex justify-end gap-3">
                <span className="text-white/40 text-sm">{f.templow ?? '--'}°</span>
                <span className="text-white text-sm font-medium">{f.temperature}°</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
