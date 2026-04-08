import express from 'express'
import http from 'http'
import path from 'path'
import {
  init as initImmich,
  searchAssets,
  getAlbumInfo,
  viewAsset,
  AssetMediaSize,
  AssetTypeEnum,
} from '@immich/sdk'
import { readConfig, writeConfig } from './config'
import { setupEventHub, broadcast } from './events'
import { setBrightness } from './brightness'
import { startHaClient, callHaService } from './ha-client'
import { createESPhomeClient } from './esphome'

const DEV_MODE =
  process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development'
const HA_DEV_MODE = process.env.HA_DEV_MODE === 'true'
const PORT = parseInt(process.env.PORT ?? '3001', 10)

const app = express()
app.use(express.json())

const config = readConfig()

if (!DEV_MODE) {
  const distPath = path.join(__dirname, '../../dist')
  app.use(express.static(distPath))
}

app.get('/api/config', (_req, res) => {
  res.json(readConfig())
})
app.post('/api/config', (req, res) => {
  writeConfig(req.body as Parameters<typeof writeConfig>[0])
  res.json({ ok: true })
})

app.post('/api/brightness', async (req, res) => {
  const { level } = req.body as { level: number }
  await setBrightness(level)
  res.json({ ok: true })
})

app.post('/api/broadcast', (req, res) => {
  const { message, duration } = req.body as {
    message: string
    duration?: number
  }
  broadcast({
    type: 'broadcast',
    payload: { message, duration: duration ?? 5000 },
  })
  res.json({ ok: true })
})

const esphome = createESPhomeClient(config.voice.host, config.voice.port)
app.post('/api/wake-word', (req, res) => {
  const { enabled } = req.body as { enabled: boolean }
  esphome.setWakeWord(enabled)
  broadcast({ type: 'wake_word_state', payload: { enabled } })
  res.json({ ok: true })
})

const HA_IDENT_RE = /^[a-z0-9_]+$/

app.post('/api/ha/service', async (req, res) => {
  const { domain, service, data } = req.body as {
    domain: string
    service: string
    data: unknown
  }
  if (
    typeof domain !== 'string' ||
    typeof service !== 'string' ||
    !HA_IDENT_RE.test(domain) ||
    !HA_IDENT_RE.test(service)
  ) {
    res.status(400).json({ error: 'Invalid domain or service identifier' })
    return
  }
  if (HA_DEV_MODE) {
    console.log('[DEV] HA service call:', domain, service, data)
    res.json({ ok: true })
    return
  }
  try {
    await callHaService(
      domain,
      service,
      data as Record<string, unknown> | undefined,
    )
    res.json({ ok: true })
  } catch (e) {
    res.status(500).json({ error: String(e) })
  }
})

const IMMICH_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function initImmichClient() {
  const cfg = readConfig()
  initImmich({ baseUrl: `${cfg.immich.url}/api`, apiKey: cfg.immich.apiKey })
  return cfg
}

app.get('/api/immich/photos', async (_req, res) => {
  const cfg = initImmichClient()
  if (!cfg.immich.url || !cfg.immich.apiKey) {
    res.status(503).json({ error: 'Immich not configured' })
    return
  }
  try {
    if (cfg.immich.mode === 'album' && cfg.immich.albumId) {
      const album = await getAlbumInfo({ id: cfg.immich.albumId })
      res.json(album.assets.map((a) => a.id))
    } else {
      const result = await searchAssets({
        metadataSearchDto: {
          isFavorite: cfg.immich.isFavorite === false ? undefined : true,
          type: AssetTypeEnum.Image,
          size: 1000,
        },
      })
      res.json(result.assets.items.map((a) => a.id))
    }
  } catch (e) {
    res.status(502).json({ error: String(e) })
  }
})

app.get('/api/immich/thumbnail/:id', async (req, res) => {
  const { id } = req.params
  if (!IMMICH_ID_RE.test(id)) {
    res.status(400).json({ error: 'Invalid asset id' })
    return
  }
  const cfg = initImmichClient()
  if (!cfg.immich.url || !cfg.immich.apiKey) {
    res.status(503).json({ error: 'Immich not configured' })
    return
  }
  try {
    const blob = await viewAsset({ id, size: AssetMediaSize.Preview })
    const buffer = Buffer.from(await blob.arrayBuffer())
    res.set('Content-Type', blob.type || 'image/jpeg')
    res.set('Cache-Control', 'public, max-age=86400')
    res.send(buffer)
  } catch (e) {
    res.status(502).json({ error: String(e) })
  }
})

interface NasaSearchItem {
  links?: Array<{ href: string; rel: string; render?: string }>
  data: Array<{ [key: string]: unknown }>
}

interface NasaSearchResponse {
  collection: {
    items: NasaSearchItem[]
  }
}

app.get('/api/nasa/photos', async (_req, res) => {
  const cfg = readConfig()
  const query = cfg.nasa?.query || 'space'
  try {
    const apiUrl = `https://images-api.nasa.gov/asset/?orderby=popular&q=${encodeURIComponent(query)}&media_type=image&page_size=100&year_start=2025`
    const resp = await fetch(apiUrl)
    if (!resp.ok) {
      res.status(502).json({ error: 'NASA API error' })
      return
    }
    const data = (await resp.json()) as NasaSearchResponse
    const urls: string[] = []
    for (const item of data.collection.items) {
      if (item.data[0].media_type !== 'image') continue

      const preview = item.links?.find(
        (l) => l.rel === 'preview' && l.render === 'image',
      )
      if (preview?.href) {
        // Replace thumbnail suffix with large for higher resolution
        urls.push(preview.href.replace('~thumb.jpg', '~large.jpg'))
      }
    }
    res.set('Cache-Control', 'public, max-age=3600')
    res.json(urls)
  } catch (e) {
    console.log('NASA API error', e)
    res.status(502).json({ error: String(e) })
  }
})

const server = http.createServer(app)
setupEventHub(server)

const cfg = readConfig()
startHaClient(cfg.ha.url, cfg.ha.token)

if (DEV_MODE) {
  // Dev-only endpoint to manually trigger voice events for demo/testing
  app.post('/api/dev/voice', (req, res) => {
    const { type, payload } = req.body as { type: string; payload?: unknown }
    const allowed = [
      'voice_wake',
      'voice_transcript',
      'voice_response',
      'voice_done',
    ]
    if (!allowed.includes(type)) {
      res.status(400).json({ error: 'Unknown event type' })
      return
    }
    broadcast({ type, payload: payload ?? {} })
    res.json({ ok: true })
  })

  let demoStep = 0
  setInterval(() => {
    demoStep++
    if (demoStep % 4 === 0) {
      broadcast({ type: 'voice_wake', payload: {} })
      setTimeout(
        () =>
          broadcast({
            type: 'voice_transcript',
            payload: { transcript: 'Turn on the living room lights' },
          }),
        1500,
      )
      setTimeout(
        () =>
          broadcast({
            type: 'voice_response',
            payload: { response: 'Living room lights are on!' },
          }),
        3000,
      )
      setTimeout(() => broadcast({ type: 'voice_done', payload: {} }), 5000)
    }
  }, 45000)
}

server.listen(PORT, () => {
  console.log(
    `havenOS server running on http://localhost:${PORT} [${DEV_MODE ? 'DEV' : 'PROD'}]`,
  )
})
