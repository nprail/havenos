import { WebSocketServer, WebSocket } from 'ws'
import type { Server } from 'http'

export type HavenEvent = {
  type: string
  payload: unknown
}

const clients: Set<WebSocket> = new Set()
const cachedEvents: Map<string, HavenEvent> = new Map()

const CACHED_EVENT_TYPES = new Set(['ha_states', 'ha_areas', 'ha_entity_registry', 'now_playing', 'wake_word_state'])

export function setupEventHub(server: Server): void {
  const wss = new WebSocketServer({ server, path: '/events' })
  wss.on('connection', (ws) => {
    clients.add(ws)
    // Replay last known state to newly connected clients
    for (const event of cachedEvents.values()) {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(event))
    }
    ws.on('close', () => clients.delete(ws))
    ws.on('error', () => clients.delete(ws))
  })
}

export function broadcast(event: HavenEvent): void {
  if (CACHED_EVENT_TYPES.has(event.type)) {
    cachedEvents.set(event.type, event)
  }
  const msg = JSON.stringify(event)
  clients.forEach((ws) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(msg)
  })
}
