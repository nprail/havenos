import { useEffect, useRef } from 'react';
import { useStore } from '../store';

const BAR_COUNT = 40;
const DEV_MODE = import.meta.env.DEV;

export default function Waveform() {
  const { voice } = useStore();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const amplitudesRef = useRef<number[]>(Array(BAR_COUNT).fill(0));
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const isActive = voice.state === 'listening' || voice.state === 'processing' || voice.state === 'responding';

    function animate() {
      if (!ctx || !canvas) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const amps = amplitudesRef.current;
      const barW = canvas.width / (BAR_COUNT * 2 + 1);
      const maxH = canvas.height * 0.9;
      const midY = canvas.height / 2;
      const gap = barW * 0.3;

      for (let i = 0; i < BAR_COUNT; i++) {
        if (isActive) {
          const target = DEV_MODE ? (Math.random() * 0.8 + 0.1) : 0.05;
          amps[i] = (amps[i] ?? 0) * 0.7 + target * 0.3;
        } else {
          amps[i] = (amps[i] ?? 0) * 0.92 + 0.02 * 0.08;
        }

        const h = (amps[i] ?? 0) * maxH;
        const x = barW * (i * 2 + 1);
        const mirrorX = canvas.width - x - barW + gap;

        ctx.fillStyle = `rgba(59, 130, 246, ${0.5 + (amps[i] ?? 0) * 0.5})`;
        const rnd = barW * 0.3;

        for (const bx of [x, mirrorX]) {
          const bW = barW - gap;
          const y = midY - h / 2;
          ctx.beginPath();
          ctx.roundRect(bx, y, bW, h, rnd);
          ctx.fill();
        }
      }

      rafRef.current = requestAnimationFrame(animate);
    }

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [voice.state]);

  return (
    <canvas
      ref={canvasRef}
      width={320}
      height={80}
      className="w-full h-20"
    />
  );
}
