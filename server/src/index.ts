import express from 'express';
import http from 'http';
import path from 'path';
import axios from 'axios';
import { readConfig, writeConfig } from './config';
import { setupEventHub, broadcast } from './events';
import { setBrightness } from './brightness';
import { startHaClient } from './ha-client';
import { createESPhomeClient } from './esphome';

const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';
const PORT = parseInt(process.env.PORT ?? '3001', 10);

const app = express();
app.use(express.json());

const config = readConfig();

if (!DEV_MODE) {
  const distPath = path.join(__dirname, '../../dist');
  app.use(express.static(distPath));
}

app.get('/api/config', (_req, res) => { res.json(readConfig()); });
app.post('/api/config', (req, res) => {
  writeConfig(req.body as Parameters<typeof writeConfig>[0]);
  res.json({ ok: true });
});

app.post('/api/brightness', async (req, res) => {
  const { level } = req.body as { level: number };
  await setBrightness(level);
  res.json({ ok: true });
});

app.post('/api/broadcast', (req, res) => {
  const { message, duration } = req.body as { message: string; duration?: number };
  broadcast({ type: 'broadcast', payload: { message, duration: duration ?? 5000 } });
  res.json({ ok: true });
});

const esphome = createESPhomeClient(config.voice.host, config.voice.port);
app.post('/api/wake-word', (req, res) => {
  const { enabled } = req.body as { enabled: boolean };
  esphome.setWakeWord(enabled);
  broadcast({ type: 'wake_word_state', payload: { enabled } });
  res.json({ ok: true });
});

const HA_IDENT_RE = /^[a-z0-9_]+$/;

app.post('/api/ha/service', async (req, res) => {
  const { domain, service, data } = req.body as { domain: string; service: string; data: unknown };
  if (typeof domain !== 'string' || typeof service !== 'string' || !HA_IDENT_RE.test(domain) || !HA_IDENT_RE.test(service)) {
    res.status(400).json({ error: 'Invalid domain or service identifier' });
    return;
  }
  if (DEV_MODE) {
    console.log('[DEV] HA service call:', domain, service, data);
    res.json({ ok: true });
    return;
  }
  const cfg = readConfig();
  const serviceUrl = new URL(`/api/services/${domain}/${service}`, cfg.ha.url).toString();
  try {
    const r = await axios.post(
      serviceUrl,
      data ?? {},
      { headers: { Authorization: `Bearer ${cfg.ha.token}` } }
    );
    res.json(r.data);
  } catch (e) {
    res.status(500).json({ error: String(e) });
  }
});

const server = http.createServer(app);
setupEventHub(server);

const cfg = readConfig();
startHaClient(cfg.ha.url, cfg.ha.token);

if (DEV_MODE) {
  // Dev-only endpoint to manually trigger voice events for demo/testing
  app.post('/api/dev/voice', (req, res) => {
    const { type, payload } = req.body as { type: string; payload?: unknown };
    const allowed = ['voice_wake', 'voice_transcript', 'voice_response', 'voice_done'];
    if (!allowed.includes(type)) {
      res.status(400).json({ error: 'Unknown event type' });
      return;
    }
    broadcast({ type, payload: payload ?? {} });
    res.json({ ok: true });
  });

  let demoStep = 0;
  setInterval(() => {
    demoStep++;
    if (demoStep % 4 === 0) {
      broadcast({ type: 'voice_wake', payload: {} });
      setTimeout(() => broadcast({ type: 'voice_transcript', payload: { transcript: 'Turn on the living room lights' } }), 1500);
      setTimeout(() => broadcast({ type: 'voice_response', payload: { response: 'Living room lights are on!' } }), 3000);
      setTimeout(() => broadcast({ type: 'voice_done', payload: {} }), 5000);
    }
  }, 45000);
}

server.listen(PORT, () => {
  console.log(`havenOS server running on http://localhost:${PORT} [${DEV_MODE ? 'DEV' : 'PROD'}]`);
});
