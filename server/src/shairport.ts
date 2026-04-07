import fs from 'fs';

const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';

export type NowPlayingData = {
  title: string;
  artist: string;
  album: string;
  duration: number;
  position: number;
};

export function watchShairport(
  pipePath: string,
  onUpdate: (data: NowPlayingData | null) => void
): () => void {
  if (DEV_MODE) {
    console.log('[DEV] shairport-sync pipe watcher mocked');
    return () => {};
  }
  if (!fs.existsSync(pipePath)) {
    console.warn(`[shairport] pipe not found: ${pipePath}`);
    return () => {};
  }
  const stream = fs.createReadStream(pipePath, { encoding: 'utf-8' });
  stream.on('data', (chunk: string) => {
    try { onUpdate(JSON.parse(chunk)); } catch { /* ignore */ }
  });
  return () => stream.destroy();
}
