import { motion } from 'framer-motion';

interface Props {
  condition: string;
  size?: number;
  className?: string;
}

export default function WeatherIcon({ condition, size = 48, className = '' }: Props) {
  const s = size;

  switch (condition) {
    case 'sunny':
    case 'clear-day':
      return (
        <motion.svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}
          animate={{ rotate: 360 }} transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}>
          <circle cx="24" cy="24" r="9" fill="#FFD700" />
          {[0,45,90,135,180,225,270,315].map((a, i) => (
            <line key={i} x1="24" y1="4" x2="24" y2="10" stroke="#FFD700" strokeWidth="2.5" strokeLinecap="round"
              transform={`rotate(${a} 24 24)`} />
          ))}
        </motion.svg>
      );

    case 'clear-night':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <path d="M30 8C22 10 16 17 16 26C16 35 23 42 32 42C36 42 39.5 40.5 42 38C38 38 30 32 30 24C30 18 32 12 38 8C35.5 7.5 32.5 7.5 30 8Z" fill="#C8D6E5" />
        </svg>
      );

    case 'partly-cloudy-day':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <motion.g animate={{ rotate: 360 }} transition={{ duration: 20, repeat: Infinity, ease: 'linear' }} style={{ transformOrigin: '18px 18px' }}>
            <circle cx="18" cy="18" r="7" fill="#FFD700" />
            {[0,60,120,180,240,300].map((a, i) => (
              <line key={i} x1="18" y1="5" x2="18" y2="9" stroke="#FFD700" strokeWidth="2" strokeLinecap="round"
                transform={`rotate(${a} 18 18)`} />
            ))}
          </motion.g>
          <rect x="10" y="26" width="28" height="14" rx="7" fill="#B0C4DE" />
          <rect x="16" y="22" width="20" height="12" rx="6" fill="#C8D6E5" />
        </svg>
      );

    case 'partly-cloudy-night':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <path d="M22 6C17 8 13 13 13 20C13 24 14.5 27.5 17 30H10C8 30 8 26 11 26C9 24 8 22 8 20C8 13 14 8 21 8L22 6Z" fill="#C8D6E5" />
          <rect x="10" y="28" width="28" height="13" rx="6.5" fill="#8BA7C4" />
          <rect x="16" y="24" width="20" height="12" rx="6" fill="#A0B8CF" />
        </svg>
      );

    case 'cloudy':
    case 'overcast':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <rect x="6" y="26" width="36" height="16" rx="8" fill="#8BA7C4" />
          <rect x="12" y="18" width="26" height="16" rx="8" fill="#A0B8CF" />
          <rect x="18" y="12" width="18" height="14" rx="7" fill="#B8CCD9" />
        </svg>
      );

    case 'rainy':
    case 'pouring':
    case 'rain':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <rect x="6" y="8" width="36" height="16" rx="8" fill="#7896B2" />
          <rect x="12" y="4" width="26" height="14" rx="7" fill="#8BA7C4" />
          {[14, 22, 30, 38].map((x, i) => (
            <motion.line key={i} x1={x} y1="28" x2={x - 3} y2="40" stroke="#6080A0" strokeWidth="2.5" strokeLinecap="round"
              animate={{ y: [0, 5, 0] }} transition={{ duration: 0.8, delay: i * 0.2, repeat: Infinity }} />
          ))}
        </svg>
      );

    case 'snowy':
    case 'snow':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <rect x="6" y="8" width="36" height="16" rx="8" fill="#B8CCD9" />
          <rect x="12" y="4" width="26" height="14" rx="7" fill="#C8D6E5" />
          {[14, 22, 30, 38].map((x, i) => (
            <motion.circle key={i} cx={x} cy="34" r="2.5" fill="white"
              animate={{ y: [0, 6, 0] }} transition={{ duration: 1.2, delay: i * 0.3, repeat: Infinity }} />
          ))}
        </svg>
      );

    case 'windy':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          {[16, 24, 32].map((y, i) => (
            <motion.path key={i} d={`M8 ${y} Q20 ${y - 6} 32 ${y} Q40 ${y + 4} 40 ${y}`}
              stroke="#8BA7C4" strokeWidth="2.5" strokeLinecap="round" fill="none"
              animate={{ pathLength: [0, 1, 1, 0] }} transition={{ duration: 2, delay: i * 0.3, repeat: Infinity }} />
          ))}
        </svg>
      );

    case 'fog':
    case 'foggy':
    case 'hazy':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          {[12, 20, 28, 36].map((y, i) => (
            <motion.rect key={i} x="6" y={y} width={i % 2 === 0 ? 36 : 28} height="3" rx="1.5" fill="#8BA7C4"
              animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 2.5, delay: i * 0.4, repeat: Infinity }} />
          ))}
        </svg>
      );

    case 'lightning':
    case 'thunderstorm':
    case 'hail':
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <rect x="6" y="6" width="36" height="16" rx="8" fill="#5A6A7A" />
          <rect x="12" y="2" width="26" height="14" rx="7" fill="#6A7A8A" />
          <motion.path d="M22 26 L18 36 L24 34 L20 44 L30 30 L24 32Z" fill="#FFD700" stroke="#FFA500" strokeWidth="0.5"
            animate={{ opacity: [1, 0.3, 1, 0.3, 1] }} transition={{ duration: 1.5, repeat: Infinity }} />
        </svg>
      );

    default:
      return (
        <svg width={s} height={s} viewBox="0 0 48 48" fill="none" className={className}>
          <circle cx="24" cy="24" r="16" fill="#7896B2" opacity="0.5" />
          <text x="24" y="28" textAnchor="middle" fill="white" fontSize="12">?</text>
        </svg>
      );
  }
}
