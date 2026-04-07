const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';

export interface ESPhomeClient {
  setWakeWord(enabled: boolean): void;
  destroy(): void;
}

export function createESPhomeClient(_host: string, _port: number): ESPhomeClient {
  if (DEV_MODE) {
    console.log('[DEV] ESPHome client mocked');
    return {
      setWakeWord: (enabled: boolean) => console.log(`[DEV] wake word ${enabled ? 'enabled' : 'disabled'}`),
      destroy: () => {},
    };
  }
  return {
    setWakeWord: (_e: boolean) => {},
    destroy: () => {},
  };
}
