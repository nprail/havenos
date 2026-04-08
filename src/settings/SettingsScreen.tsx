import { useState } from 'react'
import { motion } from 'framer-motion'
import { useStore } from '../store'
import type { AppSettings } from '../store'

type Tab = 'general' | 'ha' | 'photos' | 'voice' | 'timers' | 'advanced'

export default function SettingsScreen() {
  const { navigate, settings, setSettings } = useStore()
  const [tab, setTab] = useState<Tab>('general')
  const [form, setForm] = useState<AppSettings>(settings)

  const save = () => {
    setSettings(form)
    navigate('active')
  }

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: 'general', label: 'General' },
    { id: 'ha', label: 'Home Assistant' },
    { id: 'photos', label: 'Photos' },
    { id: 'voice', label: 'Voice' },
    { id: 'timers', label: 'Timers' },
    { id: 'advanced', label: 'Advanced' },
  ]

  return (
    <div className="absolute inset-0 bg-zinc-900 flex flex-col">
      <div className="flex items-center gap-3 px-6 pt-6 pb-3 border-b border-white/10">
        <motion.button
          className="w-12 h-12 flex items-center justify-center rounded-full bg-white/10 text-white text-2xl"
          onPointerDown={() => navigate('active')}
          whileTap={{ scale: 0.92 }}
        >
          ‹
        </motion.button>
        <h1 className="text-white text-xl font-semibold flex-1">Settings</h1>
        <motion.button
          className="px-4 py-2 bg-blue-500 rounded-xl text-white text-sm font-medium"
          onPointerDown={save}
          whileTap={{ scale: 0.95 }}
        >
          Save
        </motion.button>
      </div>

      <div className="flex gap-1 px-4 pt-3 overflow-x-auto">
        {tabs.map((t) => (
          <motion.button
            key={t.id}
            className={`px-3 py-2 rounded-lg text-sm whitespace-nowrap ${tab === t.id ? 'bg-white/20 text-white' : 'text-white/50'}`}
            onPointerDown={() => setTab(t.id)}
            whileTap={{ scale: 0.95 }}
          >
            {t.label}
          </motion.button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {tab === 'general' && (
          <div className="flex flex-col gap-4">
            <Field
              label="Display Name"
              value={form.display.name}
              onChange={(v) =>
                setForm((f) => ({ ...f, display: { ...f.display, name: v } }))
              }
            />
            <Field
              label="Photo Cycle Interval (seconds)"
              value={String(form.cycleInterval)}
              onChange={(v) =>
                setForm((f) => ({ ...f, cycleInterval: parseInt(v) || 60 }))
              }
              type="number"
            />
            <Field
              label="Accent Color"
              value={form.display.accentColor}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  display: { ...f.display, accentColor: v },
                }))
              }
            />
            <Field
              label="Quiet Hours Start"
              value={form.display.quietHoursStart}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  display: { ...f.display, quietHoursStart: v },
                }))
              }
            />
            <Field
              label="Quiet Hours End"
              value={form.display.quietHoursEnd}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  display: { ...f.display, quietHoursEnd: v },
                }))
              }
            />
          </div>
        )}

        {tab === 'ha' && (
          <div className="flex flex-col gap-4">
            <Field
              label="Home Assistant URL"
              value={form.ha.url}
              onChange={(v) =>
                setForm((f) => ({ ...f, ha: { ...f.ha, url: v } }))
              }
            />
            <Field
              label="Long-Lived Access Token"
              value={form.ha.token}
              onChange={(v) =>
                setForm((f) => ({ ...f, ha: { ...f.ha, token: v } }))
              }
              type="password"
            />
            <Field
              label="Weather Entity"
              value={form.weather.entity}
              onChange={(v) =>
                setForm((f) => ({ ...f, weather: { entity: v } }))
              }
            />
          </div>
        )}

        {tab === 'photos' && (
          <div className="flex flex-col gap-4">
            <Field
              label="Immich URL"
              value={form.immich.url}
              onChange={(v) =>
                setForm((f) => ({ ...f, immich: { ...f.immich, url: v } }))
              }
            />
            <Field
              label="Immich API Key"
              value={form.immich.apiKey}
              onChange={(v) =>
                setForm((f) => ({ ...f, immich: { ...f.immich, apiKey: v } }))
              }
              type="password"
            />
            <Toggle
              label="Favorites Only"
              value={form.immich.isFavorite ?? true}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  immich: { ...f.immich, isFavorite: v },
                }))
              }
            />
            <Select
              label="Source"
              value={form.immich.mode}
              options={[
                { value: 'favorites', label: 'Favorites / Whole Library' },
                { value: 'album', label: 'Album' },
              ]}
              onChange={(v) =>
                setForm((f) => ({ ...f, immich: { ...f.immich, mode: v } }))
              }
            />
            {form.immich.mode === 'album' && (
              <Field
                label="Album ID"
                value={form.immich.albumId}
                onChange={(v) =>
                  setForm((f) => ({
                    ...f,
                    immich: { ...f.immich, albumId: v },
                  }))
                }
              />
            )}
          </div>
        )}

        {tab === 'voice' && (
          <div className="flex flex-col gap-4">
            <Field
              label="Voice Assistant Host"
              value={form.voice.host}
              onChange={(v) =>
                setForm((f) => ({ ...f, voice: { ...f.voice, host: v } }))
              }
            />
            <Field
              label="Port"
              value={String(form.voice.port)}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  voice: { ...f.voice, port: parseInt(v) || 6053 },
                }))
              }
              type="number"
            />
          </div>
        )}

        {tab === 'timers' && (
          <div className="flex flex-col gap-4">
            <Field
              label="Chime File Path"
              value={form.timers.chimeFile}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  timers: { ...f.timers, chimeFile: v },
                }))
              }
            />
            <Field
              label="Chime Volume (0-100)"
              value={String(form.timers.chimeVolume)}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  timers: { ...f.timers, chimeVolume: parseInt(v) || 80 },
                }))
              }
              type="number"
            />
          </div>
        )}

        {tab === 'advanced' && (
          <div className="flex flex-col gap-4">
            <Field
              label="Music Assistant URL"
              value={form.music.maUrl}
              onChange={(v) =>
                setForm((f) => ({ ...f, music: { ...f.music, maUrl: v } }))
              }
            />
            <Field
              label="Player ID"
              value={form.music.playerId}
              onChange={(v) =>
                setForm((f) => ({ ...f, music: { ...f.music, playerId: v } }))
              }
            />
          </div>
        )}
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-white/50 text-xs uppercase tracking-wide">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-white/10 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-blue-500/50 min-h-[48px]"
      />
    </div>
  )
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-white/50 text-xs uppercase tracking-wide">
        {label}
      </span>
      <motion.button
        className={`w-12 h-7 rounded-full relative transition-colors ${value ? 'bg-blue-500' : 'bg-white/20'}`}
        onPointerDown={() => onChange(!value)}
        whileTap={{ scale: 0.95 }}
      >
        <span
          className={`absolute top-1 w-5 h-5 bg-white rounded-full shadow transition-all ${value ? 'left-6' : 'left-1'}`}
        />
      </motion.button>
    </div>
  )
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-white/50 text-xs uppercase tracking-wide">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-white/10 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-blue-500/50 min-h-[48px]"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-zinc-800">
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}
