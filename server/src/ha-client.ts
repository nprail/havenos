import {
  createConnection,
  createLongLivedTokenAuth,
  callService,
  getStates,
  type Connection,
  type StateChangedEvent,
} from 'home-assistant-js-websocket'
import WebSocket from 'ws'
import { broadcast } from './events'

// Polyfill WebSocket for Node.js (home-assistant-js-websocket expects a browser-like global)
if (!('WebSocket' in globalThis)) {
  Object.assign(globalThis, { WebSocket })
}

const HA_DEV_MODE = process.env.HA_DEV_MODE === 'true'

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
        {
          datetime: new Date().toISOString(),
          condition: 'sunny',
          temperature: 78,
          templow: 61,
        },
        {
          datetime: new Date(Date.now() + 86400000).toISOString(),
          condition: 'rainy',
          temperature: 65,
          templow: 55,
        },
        {
          datetime: new Date(Date.now() + 172800000).toISOString(),
          condition: 'cloudy',
          temperature: 68,
          templow: 58,
        },
        {
          datetime: new Date(Date.now() + 259200000).toISOString(),
          condition: 'sunny',
          temperature: 75,
          templow: 62,
        },
        {
          datetime: new Date(Date.now() + 345600000).toISOString(),
          condition: 'partly-cloudy-day',
          temperature: 73,
          templow: 60,
        },
        {
          datetime: new Date(Date.now() + 432000000).toISOString(),
          condition: 'thunderstorm',
          temperature: 66,
          templow: 54,
        },
        {
          datetime: new Date(Date.now() + 518400000).toISOString(),
          condition: 'sunny',
          temperature: 79,
          templow: 63,
        },
      ],
    },
  },
  'timer.kitchen': {
    entity_id: 'timer.kitchen',
    state: 'active',
    attributes: {
      duration: '00:10:00',
      remaining: '00:07:32',
      friendly_name: 'Kitchen Timer',
    },
  },
  'timer.laundry': {
    entity_id: 'timer.laundry',
    state: 'active',
    attributes: {
      duration: '00:45:00',
      remaining: '00:31:15',
      friendly_name: 'Laundry Timer',
    },
  },
  'light.living_room': {
    entity_id: 'light.living_room',
    state: 'on',
    attributes: {
      brightness: 200,
      friendly_name: 'Living Room',
      supported_color_modes: ['brightness'],
    },
  },
  'light.bedroom': {
    entity_id: 'light.bedroom',
    state: 'off',
    attributes: {
      brightness: 0,
      friendly_name: 'Bedroom',
      supported_color_modes: ['brightness'],
    },
  },
  'light.kitchen': {
    entity_id: 'light.kitchen',
    state: 'on',
    attributes: {
      brightness: 255,
      friendly_name: 'Kitchen',
      supported_color_modes: ['brightness'],
    },
  },
  'climate.home': {
    entity_id: 'climate.home',
    state: 'heat_cool',
    attributes: {
      current_temperature: 71,
      temperature: 72,
      target_temp_high: 75,
      target_temp_low: 68,
      hvac_modes: ['off', 'heat', 'cool', 'heat_cool'],
      friendly_name: 'Thermostat',
    },
  },
  'scene.evening': {
    entity_id: 'scene.evening',
    state: 'scening',
    attributes: { friendly_name: 'Evening' },
  },
  'scene.movie': {
    entity_id: 'scene.movie',
    state: 'scening',
    attributes: { friendly_name: 'Movie Night' },
  },
  'scene.morning': {
    entity_id: 'scene.morning',
    state: 'scening',
    attributes: { friendly_name: 'Morning' },
  },
  'scene.away': {
    entity_id: 'scene.away',
    state: 'scening',
    attributes: { friendly_name: 'Away' },
  },
  'camera.front_door': {
    entity_id: 'camera.front_door',
    state: 'idle',
    attributes: { friendly_name: 'Front Door', entity_picture: '' },
  },
}

export const MOCK_AREAS = [
  { area_id: 'living_room', name: 'Living Room' },
  { area_id: 'bedroom', name: 'Bedroom' },
  { area_id: 'kitchen', name: 'Kitchen' },
]

export const MOCK_ENTITY_REGISTRY = [
  { entity_id: 'light.living_room', area_id: 'living_room' },
  { entity_id: 'light.bedroom', area_id: 'bedroom' },
  { entity_id: 'light.kitchen', area_id: 'kitchen' },
]

let haConn: Connection | null = null

export async function callHaService(
  domain: string,
  service: string,
  data?: Record<string, unknown>,
): Promise<void> {
  if (!haConn) throw new Error('[ha-client] Not connected to HA')
  await callService(haConn, domain, service, data)
}

export function startHaClient(haUrl: string, token: string): void {
  console.log('[ha-client] Starting HA client with URL:', haUrl)
  if (HA_DEV_MODE) {
    console.log('[DEV] HA client mocked — sending mock entity state')
    setTimeout(() => {
      broadcast({ type: 'ha_states', payload: Object.values(MOCK_ENTITIES) })
      broadcast({ type: 'ha_areas', payload: MOCK_AREAS })
      broadcast({ type: 'ha_entity_registry', payload: MOCK_ENTITY_REGISTRY })
    }, 500)
    setInterval(() => {
      broadcast({ type: 'ha_states', payload: Object.values(MOCK_ENTITIES) })
    }, 30000)
    return
  }

  if (!haUrl || !token) {
    console.warn('[ha-client] No HA URL/token configured, skipping connection')
    return
  }

  const auth = createLongLivedTokenAuth(haUrl, token)

  async function setup(): Promise<void> {
    try {
      const conn = await createConnection({ auth })
      haConn = conn
      console.log('[ha-client] connected')

      async function fetchAndBroadcastAll(): Promise<void> {
        const [states, areas, entityRegistry] = await Promise.all([
          getStates(conn),
          conn.sendMessagePromise<unknown[]>({ type: 'config/area_registry/list' }),
          conn.sendMessagePromise<unknown[]>({ type: 'config/entity_registry/list' }),
        ])
        broadcast({ type: 'ha_states', payload: states })
        broadcast({ type: 'ha_areas', payload: areas })
        broadcast({ type: 'ha_entity_registry', payload: entityRegistry })
      }

      // Fetch initial state snapshot
      await fetchAndBroadcastAll()

      // Re-fetch full state on every reconnect
      conn.addEventListener('ready', () => {
        console.log('[ha-client] reconnected')
        fetchAndBroadcastAll().catch(console.error)
      })

      conn.addEventListener('disconnected', () => {
        console.log('[ha-client] disconnected — will reconnect automatically')
      })

      // Stream incremental state changes
      await conn.subscribeEvents<StateChangedEvent>(
        (event) => {
          broadcast({ type: 'ha_state_changed', payload: event.data })
        },
        'state_changed',
      )
    } catch (e) {
      console.error('[ha-client] connection failed, retrying in 5s:', e)
      haConn = null
      setTimeout(() => void setup(), 5000)
    }
  }

  void setup()
}
