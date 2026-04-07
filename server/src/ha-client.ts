import WebSocket from 'ws';
import { broadcast } from './events';

const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';

export const MOCK_ENTITIES: Record<string, unknown> = {
  'weather.home': {
    entity_id: 'weather.home',
    state: 'partly-cloudy-day',
    attributes: {
      temperature: 72,
      temperature_unit: '°F',
      humidity: 55,
      wind_speed: 8,
      forecast: [
        { datetime: new Date().toISOString(), condition: 'sunny', temperature: 78, templow: 61 },
        { datetime: new Date(Date.now() + 86400000).toISOString(), condition: 'rainy', temperature: 65, templow: 55 },
        { datetime: new Date(Date.now() + 172800000).toISOString(), condition: 'cloudy', temperature: 68, templow: 58 },
        { datetime: new Date(Date.now() + 259200000).toISOString(), condition: 'sunny', temperature: 75, templow: 62 },
        { datetime: new Date(Date.now() + 345600000).toISOString(), condition: 'partly-cloudy-day', temperature: 73, templow: 60 },
        { datetime: new Date(Date.now() + 432000000).toISOString(), condition: 'thunderstorm', temperature: 66, templow: 54 },
        { datetime: new Date(Date.now() + 518400000).toISOString(), condition: 'sunny', temperature: 79, templow: 63 },
      ],
    },
  },
  'timer.kitchen': { entity_id: 'timer.kitchen', state: 'active', attributes: { duration: '00:10:00', remaining: '00:07:32', friendly_name: 'Kitchen Timer' } },
  'timer.laundry': { entity_id: 'timer.laundry', state: 'active', attributes: { duration: '00:45:00', remaining: '00:31:15', friendly_name: 'Laundry Timer' } },
  'light.living_room': { entity_id: 'light.living_room', state: 'on', attributes: { brightness: 200, friendly_name: 'Living Room', supported_color_modes: ['brightness'] } },
  'light.bedroom': { entity_id: 'light.bedroom', state: 'off', attributes: { brightness: 0, friendly_name: 'Bedroom', supported_color_modes: ['brightness'] } },
  'light.kitchen': { entity_id: 'light.kitchen', state: 'on', attributes: { brightness: 255, friendly_name: 'Kitchen', supported_color_modes: ['brightness'] } },
  'climate.home': { entity_id: 'climate.home', state: 'heat_cool', attributes: { current_temperature: 71, temperature: 72, target_temp_high: 75, target_temp_low: 68, hvac_modes: ['off', 'heat', 'cool', 'heat_cool'], friendly_name: 'Thermostat' } },
  'scene.evening': { entity_id: 'scene.evening', state: 'scening', attributes: { friendly_name: 'Evening' } },
  'scene.movie': { entity_id: 'scene.movie', state: 'scening', attributes: { friendly_name: 'Movie Night' } },
  'scene.morning': { entity_id: 'scene.morning', state: 'scening', attributes: { friendly_name: 'Morning' } },
  'scene.away': { entity_id: 'scene.away', state: 'scening', attributes: { friendly_name: 'Away' } },
  'camera.front_door': { entity_id: 'camera.front_door', state: 'idle', attributes: { friendly_name: 'Front Door', entity_picture: '' } },
};

export function startHaClient(haUrl: string, token: string): void {
  if (DEV_MODE) {
    console.log('[DEV] HA client mocked — sending mock entity state');
    setTimeout(() => {
      broadcast({ type: 'ha_states', payload: Object.values(MOCK_ENTITIES) });
    }, 500);
    setInterval(() => {
      broadcast({ type: 'ha_states', payload: Object.values(MOCK_ENTITIES) });
    }, 30000);
    return;
  }

  if (!haUrl || !token) {
    console.warn('[ha-client] No HA URL/token configured, skipping connection');
    return;
  }

  let msgId = 1;

  function connect() {
    const wsUrl = haUrl.replace(/^http/, 'ws') + '/api/websocket';
    const ws = new WebSocket(wsUrl);

    ws.on('open', () => console.log('[ha-client] connected'));
    ws.on('close', () => { setTimeout(connect, 5000); });
    ws.on('error', (e) => console.error('[ha-client] error:', e.message));
    ws.on('message', (raw) => {
      try {
        const msg = JSON.parse(raw.toString()) as { type: string; result?: unknown; event?: { event_type: string; data: unknown } };
        if (msg.type === 'auth_required') {
          ws.send(JSON.stringify({ type: 'auth', access_token: token }));
        } else if (msg.type === 'auth_ok') {
          ws.send(JSON.stringify({ id: msgId++, type: 'get_states' }));
          ws.send(JSON.stringify({ id: msgId++, type: 'subscribe_events', event_type: 'state_changed' }));
        } else if (msg.type === 'result' && msg.result) {
          broadcast({ type: 'ha_states', payload: msg.result });
        } else if (msg.type === 'event' && msg.event?.event_type === 'state_changed') {
          broadcast({ type: 'ha_state_changed', payload: msg.event.data });
        }
      } catch { /* ignore parse errors */ }
    });
  }
  connect();
}
