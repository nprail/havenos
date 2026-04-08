import { create } from 'zustand'

export type Screen =
  | 'ambient'
  | 'active'
  | 'listening'
  | 'detail'
  | 'ha-dashboard'
  | 'settings'

export interface HAEntity {
  entity_id: string
  state: string
  attributes: Record<string, unknown>
}

export interface NowPlaying {
  source: 'airplay' | 'ma' | null
  state: 'playing' | 'paused' | 'idle'
  title: string
  artist: string
  album: string
  artUrl: string
  duration: number
  position: number
  volume: number
  shuffle: boolean
  repeat: 'off' | 'one' | 'all'
}

export interface AppSettings {
  ha: { url: string; token: string }
  weather: { entity: string }
  music: { maUrl: string; playerId: string }
  voice: { host: string; port: number }
  immich: {
    url: string
    apiKey: string
    mode: string
    albumId: string
    isFavorite: boolean
  }
  display: {
    name: string
    brightness: number
    quietHoursStart: string
    quietHoursEnd: string
    theme: string
    accentColor: string
  }
  timers: { chimeFile: string; chimeVolume: number }
  cycleInterval: number
  haUrl: string
}

interface HavenStore {
  screen: Screen
  activeModule: string | null
  ha: { connected: boolean; stale: boolean; entities: Record<string, HAEntity> }
  voice: {
    state: 'idle' | 'wake' | 'listening' | 'processing' | 'responding'
    transcript: string
    response: string
    wakeWordEnabled: boolean
  }
  nowPlaying: NowPlaying
  display: { brightness: number; screenOn: boolean }
  broadcasts: {
    queue: Array<{ message: string; duration: number }>
    current: { message: string; duration: number } | null
  }
  photos: { current: string | null; queue: string[] }
  settings: AppSettings

  navigate: (screen: Screen, module?: string) => void
  setHaEntities: (entities: HAEntity[]) => void
  updateHaEntity: (entity: HAEntity) => void
  setVoiceState: (
    state: HavenStore['voice']['state'],
    transcript?: string,
    response?: string,
  ) => void
  setNowPlaying: (np: Partial<NowPlaying>) => void
  setBrightness: (level: number) => void
  queueBroadcast: (msg: { message: string; duration: number }) => void
  dismissBroadcast: () => void
  setPhoto: (url: string) => void
  setSettings: (s: AppSettings) => void
  callService: (
    domain: string,
    service: string,
    data?: Record<string, unknown>,
  ) => Promise<void>
}

export const useStore = create<HavenStore>((set) => ({
  screen: 'ambient',
  activeModule: null,
  ha: { connected: false, stale: false, entities: {} },
  voice: { state: 'idle', transcript: '', response: '', wakeWordEnabled: true },
  nowPlaying: {
    source: null,
    state: 'idle',
    title: '',
    artist: '',
    album: '',
    artUrl: '',
    duration: 0,
    position: 0,
    volume: 0.5,
    shuffle: false,
    repeat: 'off',
  },
  display: { brightness: 100, screenOn: true },
  broadcasts: { queue: [], current: null },
  photos: { current: null, queue: [] },
  settings: {
    ha: { url: 'http://homeassistant.local:8123', token: '' },
    weather: { entity: 'weather.home' },
    music: { maUrl: 'http://musicassistant.local:8095', playerId: '' },
    voice: { host: 'localhost', port: 6053 },
    immich: {
      url: 'http://immich.local:2283',
      apiKey: '',
      mode: 'favorites',
      albumId: '',
      isFavorite: true,
    },
    display: {
      name: 'havenOS Display',
      brightness: 100,
      quietHoursStart: '22:00',
      quietHoursEnd: '07:00',
      theme: 'auto',
      accentColor: 'blue',
    },
    timers: { chimeFile: '', chimeVolume: 80 },
    cycleInterval: 60,
    haUrl: '',
  },

  navigate: (screen, module) => set({ screen, activeModule: module ?? null }),

  setHaEntities: (entities) => {
    const map: Record<string, HAEntity> = {}
    entities.forEach((e) => {
      map[e.entity_id] = e
    })
    set((s) => ({ ha: { ...s.ha, connected: true, entities: map } }))
  },

  updateHaEntity: (entity) =>
    set((s) => ({
      ha: {
        ...s.ha,
        entities: { ...s.ha.entities, [entity.entity_id]: entity },
      },
    })),

  setVoiceState: (state, transcript = '', response = '') =>
    set((s) => ({
      voice: {
        ...s.voice,
        state,
        transcript: transcript || s.voice.transcript,
        response: response || s.voice.response,
      },
    })),

  setNowPlaying: (np) =>
    set((s) => ({ nowPlaying: { ...s.nowPlaying, ...np } })),

  setBrightness: (level) => {
    set((s) => ({ display: { ...s.display, brightness: level } }))
    fetch('/api/brightness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level }),
    }).catch(console.error)
  },

  queueBroadcast: (msg) =>
    set((s) => {
      if (!s.broadcasts.current)
        return { broadcasts: { queue: s.broadcasts.queue, current: msg } }
      return {
        broadcasts: {
          queue: [...s.broadcasts.queue, msg],
          current: s.broadcasts.current,
        },
      }
    }),

  dismissBroadcast: () =>
    set((s) => {
      const [next, ...rest] = s.broadcasts.queue
      return { broadcasts: { queue: rest, current: next ?? null } }
    }),

  setPhoto: (url) => set((s) => ({ photos: { ...s.photos, current: url } })),

  setSettings: (settings) => {
    set({ settings })
    fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }).catch(console.error)
  },

  callService: async (domain, service, data) => {
    await fetch('/api/ha/service', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, service, data }),
    })
  },
}))

// Expose store in dev mode for testing/debugging
if (import.meta.env.DEV) {
  ;(window as unknown as Record<string, unknown>).__havenStore = useStore
}
