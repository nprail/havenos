import { WebSocketServer, WebSocket } from 'ws'
import type { Server } from 'http'

export type HavenEvent = {
  type: string
  payload: unknown
}

const clients: Set<WebSocket> = new Set()

export function setupEventHub(server: Server): void {
  const wss = new WebSocketServer({ server, path: '/events' })
  wss.on('connection', (ws) => {
    clients.add(ws)
    ws.on('close', () => clients.delete(ws))
    ws.on('error', () => clients.delete(ws))
  })
}

export function broadcast(event: HavenEvent): void {
  const msg = JSON.stringify(event)
  clients.forEach((ws) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(msg)
  })
}
