import { exec } from 'child_process';

const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';

export function setBrightness(level: number): Promise<void> {
  const clamped = Math.max(0, Math.min(100, level));
  if (DEV_MODE) {
    console.log(`[DEV] brightness set to ${clamped}%`);
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    exec(`echo ${Math.round(clamped * 2.55)} > /sys/class/backlight/rpi_backlight/brightness`, (err) => {
      if (err) reject(err);
      else resolve();
    });
  });
}
