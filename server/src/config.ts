import fs from 'fs'
import path from 'path'
import os from 'os'

export interface AppConfig {
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

const CONFIG_DIR = path.join(os.homedir(), '.havenOS')
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json')

const DEFAULT_CONFIG: AppConfig = {
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
}

export function readConfig(): AppConfig {
  try {
    if (!fs.existsSync(CONFIG_FILE)) {
      writeConfig(DEFAULT_CONFIG)
      return DEFAULT_CONFIG
    }
    const raw = fs.readFileSync(CONFIG_FILE, 'utf-8')
    return { ...DEFAULT_CONFIG, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_CONFIG
  }
}

export function writeConfig(config: AppConfig): void {
  if (!fs.existsSync(CONFIG_DIR)) fs.mkdirSync(CONFIG_DIR, { recursive: true })
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf-8')
}
