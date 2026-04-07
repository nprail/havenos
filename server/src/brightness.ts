import fs from 'fs';

const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';
const BRIGHTNESS_PATH = '/sys/class/backlight/rpi_backlight/brightness';

export function setBrightness(level: number): Promise<void> {
  // Clamp to valid range and convert 0–100% to 0–255 sysfs value
  const clamped = Math.max(0, Math.min(100, Math.round(level)));
  const sysfsValue = Math.round(clamped * 2.55);

  if (DEV_MODE) {
    console.log(`[DEV] brightness set to ${clamped}% (${sysfsValue}/255)`);
    return Promise.resolve();
  }

  // Write directly to sysfs — no shell involved, eliminates injection risk
  return new Promise((resolve, reject) => {
    fs.writeFile(BRIGHTNESS_PATH, String(sysfsValue), (err) => {
      if (err) reject(err);
      else resolve();
    });
  });
}
