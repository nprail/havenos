import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useStore, type HAEntity } from '../store'

interface Props {
  detail?: boolean
}

const MODE_LABELS: Record<string, string> = {
  off: 'Off',
  heat: 'Heat',
  cool: 'Cool',
  heat_cool: 'Heat/Cool',
  auto: 'Auto',
  dry: 'Dry',
  fan_only: 'Fan',
}

// --- Nest-style dial helpers ---
const DIAL_SIZE = 240
const CX = DIAL_SIZE / 2
const CY = DIAL_SIZE / 2
const RADIUS = 92
const STROKE_W = 14
const START_ANGLE = 220 // degrees clockwise from top (≈ 7 o'clock)
const TOTAL_ARC = 280 // degrees sweep

function toRad(deg: number) {
  return (deg * Math.PI) / 180
}
function angleToPoint(angleDeg: number) {
  const r = toRad(angleDeg)
  return { x: CX + RADIUS * Math.sin(r), y: CY - RADIUS * Math.cos(r) }
}
function describeArc(startAngle: number, arcDeg: number) {
  if (arcDeg <= 0) return ''
  const clampedArc = Math.min(arcDeg, 359.99)
  const start = angleToPoint(startAngle)
  const end = angleToPoint(startAngle + clampedArc)
  const largeArc = clampedArc > 180 ? 1 : 0
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`
}
function tempToArc(
  temp: number,
  minTemp: number,
  maxTemp: number,
): number {
  const frac = Math.max(0, Math.min(1, (temp - minTemp) / (maxTemp - minTemp)))
  return frac * TOTAL_ARC
}
function pointToTemp(
  px: number,
  py: number,
  minTemp: number,
  maxTemp: number,
): number {
  const dx = px - CX
  const dy = py - CY
  let angle = (Math.atan2(dx, -dy) * 180) / Math.PI
  if (angle < 0) angle += 360
  let normalized = angle - START_ANGLE
  if (normalized < 0) normalized += 360
  normalized = Math.max(0, Math.min(TOTAL_ARC, normalized))
  const frac = normalized / TOTAL_ARC
  return Math.round(minTemp + frac * (maxTemp - minTemp))
}

const MIN_TEMP_GAP = 2 // minimum degrees between heat low and cool high

function RangeDial({ climate }: { climate: HAEntity }) {
  const { callService } = useStore()
  const svgRef = useRef<SVGSVGElement>(null)
  const draggingRef = useRef<'low' | 'high' | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [localLow, setLocalLow] = useState<number | null>(null)
  const [localHigh, setLocalHigh] = useState<number | null>(null)

  const minTemp = (climate.attributes.min_temp as number | undefined) ?? 60
  const maxTemp = (climate.attributes.max_temp as number | undefined) ?? 90
  const currentTemp = climate.attributes.current_temperature as number
  const baseLow = climate.attributes.target_temp_low as number
  const baseHigh = climate.attributes.target_temp_high as number

  const displayLow = localLow ?? baseLow
  const displayHigh = localHigh ?? baseHigh

  const lowArc = tempToArc(displayLow, minTemp, maxTemp)
  const highArc = tempToArc(displayHigh, minTemp, maxTemp)
  const lowPos = angleToPoint(START_ANGLE + lowArc)
  const highPos = angleToPoint(START_ANGLE + highArc)

  const getSVGCoords = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const scale = DIAL_SIZE / rect.width
    return {
      x: (e.clientX - rect.left) * scale,
      y: (e.clientY - rect.top) * scale,
    }
  }

  const distSq = (ax: number, ay: number, bx: number, by: number) =>
    (ax - bx) ** 2 + (ay - by) ** 2

  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    e.stopPropagation()
    e.currentTarget.setPointerCapture(e.pointerId)
    const { x, y } = getSVGCoords(e)
    const dLow = distSq(x, y, lowPos.x, lowPos.y)
    const dHigh = distSq(x, y, highPos.x, highPos.y)
    draggingRef.current = dLow <= dHigh ? 'low' : 'high'
  }

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!draggingRef.current) return
    const { x, y } = getSVGCoords(e)
    const rawTemp = pointToTemp(x, y, minTemp, maxTemp)
    if (draggingRef.current === 'low') {
      const clamped = Math.min(rawTemp, displayHigh - MIN_TEMP_GAP)
      setLocalLow(clamped)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        void callService('climate', 'set_temperature', {
          entity_id: climate.entity_id,
          target_temp_low: clamped,
          target_temp_high: displayHigh,
        })
      }, 300)
    } else {
      const clamped = Math.max(rawTemp, displayLow + MIN_TEMP_GAP)
      setLocalHigh(clamped)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        void callService('climate', 'set_temperature', {
          entity_id: climate.entity_id,
          target_temp_low: displayLow,
          target_temp_high: clamped,
        })
      }, 300)
    }
  }

  const handlePointerUp = () => {
    const which = draggingRef.current
    draggingRef.current = null
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (which === 'low' && localLow !== null) {
      void callService('climate', 'set_temperature', {
        entity_id: climate.entity_id,
        target_temp_low: localLow,
        target_temp_high: displayHigh,
      })
      setLocalLow(null)
    } else if (which === 'high' && localHigh !== null) {
      void callService('climate', 'set_temperature', {
        entity_id: climate.entity_id,
        target_temp_low: displayLow,
        target_temp_high: localHigh,
      })
      setLocalHigh(null)
    }
  }

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: DIAL_SIZE, height: DIAL_SIZE }}
    >
      <svg
        ref={svgRef}
        width={DIAL_SIZE}
        height={DIAL_SIZE}
        viewBox={`0 0 ${DIAL_SIZE} ${DIAL_SIZE}`}
        className="absolute inset-0 touch-none select-none"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {/* Background track */}
        <path
          d={describeArc(START_ANGLE, TOTAL_ARC)}
          fill="none"
          stroke="rgba(255,255,255,0.12)"
          strokeWidth={STROKE_W}
          strokeLinecap="round"
        />
        {/* Heat arc: start → low handle (orange) */}
        {lowArc > 0 && (
          <path
            d={describeArc(START_ANGLE, lowArc)}
            fill="none"
            stroke="#fb923c"
            strokeWidth={STROKE_W}
            strokeLinecap="round"
          />
        )}
        {/* Comfort zone: low → high (subtle amber) */}
        {highArc - lowArc > 0 && (
          <path
            d={describeArc(START_ANGLE + lowArc, highArc - lowArc)}
            fill="none"
            stroke="rgba(251,191,36,0.3)"
            strokeWidth={STROKE_W}
            strokeLinecap="round"
          />
        )}
        {/* Cool arc: high → end (cyan) */}
        {TOTAL_ARC - highArc > 0 && (
          <path
            d={describeArc(START_ANGLE + highArc, TOTAL_ARC - highArc)}
            fill="none"
            stroke="#22d3ee"
            strokeWidth={STROKE_W}
            strokeLinecap="round"
          />
        )}
        {/* Heat handle */}
        <circle
          cx={lowPos.x}
          cy={lowPos.y}
          r={16}
          fill="#fb923c"
          stroke="white"
          strokeWidth={3}
          style={{ filter: 'drop-shadow(0 0 8px rgba(0,0,0,0.6))' }}
        />
        <circle cx={lowPos.x} cy={lowPos.y} r={7} fill="white" />
        {/* Cool handle */}
        <circle
          cx={highPos.x}
          cy={highPos.y}
          r={16}
          fill="#22d3ee"
          stroke="white"
          strokeWidth={3}
          style={{ filter: 'drop-shadow(0 0 8px rgba(0,0,0,0.6))' }}
        />
        <circle cx={highPos.x} cy={highPos.y} r={7} fill="white" />
      </svg>
      {/* Center readout */}
      <div className="flex flex-col items-center pointer-events-none">
        <span className="text-white/50 text-xs uppercase tracking-widest mb-1">
          Indoor
        </span>
        <span className="text-white font-thin" style={{ fontSize: 48 }}>
          {currentTemp}°
        </span>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-orange-400 text-sm font-medium">{displayLow}°</span>
          <span className="text-white/30 text-xs">–</span>
          <span className="text-cyan-400 text-sm font-medium">{displayHigh}°</span>
        </div>
      </div>
    </div>
  )
}

function TempDial({
  climate,
  setTemp,
}: {
  climate: HAEntity
  setTemp: number
}) {
  const { callService } = useStore()
  const svgRef = useRef<SVGSVGElement>(null)
  const isDraggingRef = useRef(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [localTemp, setLocalTemp] = useState<number | null>(null)

  const displayTemp = localTemp ?? setTemp
  const mode = climate.state
  const minTemp = (climate.attributes.min_temp as number | undefined) ?? 60
  const maxTemp = (climate.attributes.max_temp as number | undefined) ?? 90
  const currentTemp = climate.attributes.current_temperature as number

  const arcColor =
    mode === 'heat'
      ? '#fb923c'
      : mode === 'cool'
        ? '#22d3ee'
        : mode === 'heat_cool'
          ? '#f59e0b'
          : '#60a5fa'

  const filledArc = tempToArc(displayTemp, minTemp, maxTemp)
  const handlePos = angleToPoint(START_ANGLE + filledArc)

  const getSVGCoords = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const scale = DIAL_SIZE / rect.width
    return {
      x: (e.clientX - rect.left) * scale,
      y: (e.clientY - rect.top) * scale,
    }
  }

  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    e.stopPropagation()
    isDraggingRef.current = true
    e.currentTarget.setPointerCapture(e.pointerId)
    const { x, y } = getSVGCoords(e)
    setLocalTemp(pointToTemp(x, y, minTemp, maxTemp))
  }

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!isDraggingRef.current) return
    const { x, y } = getSVGCoords(e)
    const temp = pointToTemp(x, y, minTemp, maxTemp)
    setLocalTemp(temp)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      void callService('climate', 'set_temperature', {
        entity_id: climate.entity_id,
        temperature: temp,
      })
    }, 300)
  }

  const handlePointerUp = () => {
    isDraggingRef.current = false
    if (localTemp !== null) {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      void callService('climate', 'set_temperature', {
        entity_id: climate.entity_id,
        temperature: localTemp,
      })
      setLocalTemp(null)
    }
  }

  return (
    <div className="relative flex items-center justify-center" style={{ width: DIAL_SIZE, height: DIAL_SIZE }}>
      <svg
        ref={svgRef}
        width={DIAL_SIZE}
        height={DIAL_SIZE}
        viewBox={`0 0 ${DIAL_SIZE} ${DIAL_SIZE}`}
        className="absolute inset-0 touch-none select-none"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {/* Background track */}
        <path
          d={describeArc(START_ANGLE, TOTAL_ARC)}
          fill="none"
          stroke="rgba(255,255,255,0.12)"
          strokeWidth={STROKE_W}
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {filledArc > 0 && (
          <path
            d={describeArc(START_ANGLE, filledArc)}
            fill="none"
            stroke={arcColor}
            strokeWidth={STROKE_W}
            strokeLinecap="round"
          />
        )}
        {/* Handle */}
        <circle
          cx={handlePos.x}
          cy={handlePos.y}
          r={16}
          fill={arcColor}
          stroke="white"
          strokeWidth={3}
          style={{ filter: 'drop-shadow(0 0 8px rgba(0,0,0,0.6))' }}
        />
        <circle cx={handlePos.x} cy={handlePos.y} r={7} fill="white" />
      </svg>
      {/* Center readout */}
      <div className="flex flex-col items-center pointer-events-none">
        <span className="text-white/50 text-xs uppercase tracking-widest mb-1">
          Indoor
        </span>
        <span className="text-white font-thin" style={{ fontSize: 52 }}>
          {currentTemp}°
        </span>
        <span style={{ color: arcColor }} className="text-lg font-medium mt-0.5">
          → {displayTemp}°
        </span>
      </div>
    </div>
  )
}

function ClimateCard({ climate }: { climate: HAEntity }) {
  const { callService } = useStore()
  const setTemp = climate.attributes.temperature as number | null
  const mode = climate.state
  const isRange = mode === 'heat_cool' || mode === 'auto'
  const name = (climate.attributes.friendly_name as string) ?? climate.entity_id
  const modes = (climate.attributes.hvac_modes as string[]) ?? []

  return (
    <div className="flex flex-col items-center gap-6 p-4 border-r border-white/10 last:border-r-0">
      <p className="text-white/60 text-sm uppercase tracking-wide">{name}</p>

      {isRange ? (
        /* Dual-handle dial for heat/cool range mode */
        <RangeDial climate={climate} />
      ) : (
        /* Single setpoint: Nest-style draggable dial */
        <TempDial climate={climate} setTemp={setTemp ?? 70} />
      )}

      <div className="flex flex-wrap gap-2 justify-center">
        {modes.map((m) => (
          <motion.button
            key={m}
            className={`px-4 py-2 rounded-xl text-sm font-medium ${m === mode ? 'bg-blue-500 text-white' : 'bg-white/10 text-white/70'}`}
            onPointerDown={() =>
              void callService('climate', 'set_hvac_mode', {
                entity_id: climate.entity_id,
                hvac_mode: m,
              })
            }
            whileTap={{ scale: 0.95 }}
          >
            {MODE_LABELS[m] ?? m.replace(/_/g, ' ')}
          </motion.button>
        ))}
      </div>
    </div>
  )
}

export default function ClimateModule({ detail = false }: Props) {
  const { ha, settings } = useStore()
  const allowedEntities = settings.climate?.entities ?? []
  const allClimates = Object.values(ha.entities).filter((e) =>
    e.entity_id.startsWith('climate.'),
  )
  const climates =
    allowedEntities.length > 0
      ? allClimates.filter((e) => allowedEntities.includes(e.entity_id))
      : allClimates

  if (climates.length === 0) {
    return <div className="p-4 text-white/40 text-sm">No climate entities</div>
  }

  if (!detail) {
    return (
      <div className="p-4 flex flex-row flex-wrap gap-4">
        {climates.map((climate) => {
          const currentTemp = climate.attributes.current_temperature as number
          const setTemp = climate.attributes.temperature as number | null
          const tempLow = climate.attributes.target_temp_low as number
          const tempHigh = climate.attributes.target_temp_high as number
          const mode = climate.state
          const isRange = mode === 'heat_cool' || mode === 'auto'
          const name =
            (climate.attributes.friendly_name as string) ?? climate.entity_id
          return (
            <div key={climate.entity_id} className="flex flex-col gap-0.5">
              <p className="text-white/60 text-xs uppercase tracking-wide">
                {name}
              </p>
              <p className="text-white text-2xl font-light">{currentTemp}°</p>
              <p className="text-white/50 text-sm">
                {isRange
                  ? `${tempLow}° – ${tempHigh}°`
                  : `Set: ${setTemp}°`}{' '}
                · {MODE_LABELS[mode] ?? mode}
              </p>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="flex flex-row flex-wrap justify-center">
      {climates.map((climate) => (
        <ClimateCard key={climate.entity_id} climate={climate} />
      ))}
    </div>
  )
}
