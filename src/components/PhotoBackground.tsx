import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useStore } from '../store'

const GRADIENT_BACKGROUNDS = [
  'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
  'linear-gradient(135deg, #2d1b69 0%, #11998e 100%)',
  'linear-gradient(135deg, #3a1c71 0%, #d76d77 50%, #ffaf7b 100%)',
  'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
  'linear-gradient(135deg, #1f4037 0%, #99f2c8 100%)',
]

interface Props {
  dimmed?: boolean
}

export default function PhotoBackground({ dimmed = false }: Props) {
  const { settings, photoNav } = useStore()
  const [photos, setPhotos] = useState<string[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [currentPhoto, setCurrentPhoto] = useState<string | null>(null)
  const [secondPhoto, setSecondPhoto] = useState<string | null>(null)
  const [isPortrait, setIsPortrait] = useState(false)
  const [gradientIndex, setGradientIndex] = useState(0)
  const photosRef = useRef<string[]>([])

  const cycleInterval = (settings.cycleInterval ?? 60) * 1000

  // Keep a ref so the nav effect can read photos.length without stale closure
  useEffect(() => {
    photosRef.current = photos
  }, [photos])

  // React to external photo navigation signals (swipe gestures)
  useEffect(() => {
    if (!photoNav.dir) return
    const len = photosRef.current.length
    if (len === 0) {
      setGradientIndex((i) =>
        photoNav.dir === 'next'
          ? (i + 1) % GRADIENT_BACKGROUNDS.length
          : (i - 1 + GRADIENT_BACKGROUNDS.length) % GRADIENT_BACKGROUNDS.length,
      )
      return
    }
    if (photoNav.dir === 'next') {
      setCurrentIndex((i) => (i + 1) % len)
    } else {
      setCurrentIndex((i) => (i - 1 + len) % len)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photoNav.id])

  const loadImmichPhotos = useCallback(async () => {
    if (!settings.immich.url || !settings.immich.apiKey) return
    try {
      const res = await fetch('/api/immich/photos')
      const ids = (await res.json()) as string[]
      const urls = ids.map((id) => `/api/immich/thumbnail/${id}`)
      for (let i = urls.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[urls[i], urls[j]] = [urls[j], urls[i]]
      }
      setPhotos(urls)
    } catch (e) {
      console.error('[PhotoBackground] immich error', e)
    }
  }, [settings.immich])

  const loadNasaPhotos = useCallback(async () => {
    try {
      const res = await fetch('/api/nasa/photos')
      const urls = (await res.json()) as string[]
      for (let i = urls.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[urls[i], urls[j]] = [urls[j], urls[i]]
      }
      setPhotos(urls)
    } catch (e) {
      console.error('[PhotoBackground] nasa error', e)
    }
  }, [])

  const isImmichConfigured = Boolean(
    settings.immich.url && settings.immich.apiKey,
  )
  const photoSource = settings.photoSource ?? 'auto'
  const useImmich =
    photoSource === 'immich' ||
    (photoSource === 'auto' && isImmichConfigured)

  useEffect(() => {
    if (useImmich) {
      void loadImmichPhotos()
    } else {
      void loadNasaPhotos()
    }
  }, [useImmich, loadImmichPhotos, loadNasaPhotos])

  useEffect(() => {
    const timer = setInterval(() => {
      if (photos.length === 0) {
        setGradientIndex((i) => (i + 1) % GRADIENT_BACKGROUNDS.length)
      } else {
        setCurrentIndex((i) => (i + 1) % photos.length)
      }
    }, cycleInterval)
    return () => clearInterval(timer)
  }, [photos, cycleInterval])

  useEffect(() => {
    if (photos.length === 0) return
    let cancelled = false
    const url = photos[currentIndex]
    const img = new Image()
    img.onload = () => {
      if (cancelled) return
      const portrait = img.naturalHeight > img.naturalWidth
      setIsPortrait(portrait)
      setCurrentPhoto(url)
      setSecondPhoto(null)

      if (portrait && photos.length > 1) {
        const checkNext = (offset: number) => {
          if (cancelled || offset > Math.min(photos.length - 1, 20)) return
          const nextUrl = photos[(currentIndex + offset) % photos.length]
          const nextImg = new Image()
          nextImg.onload = () => {
            if (cancelled) return
            if (nextImg.naturalHeight > nextImg.naturalWidth) {
              setSecondPhoto(nextUrl)
            } else {
              checkNext(offset + 1)
            }
          }
          nextImg.onerror = () => {
            if (!cancelled) checkNext(offset + 1)
          }
          nextImg.src = nextUrl ?? ''
        }
        checkNext(1)
      }
    }
    img.src = url ?? ''
    return () => {
      cancelled = true
    }
  }, [currentIndex, photos])

  if (photos.length === 0) {
    return (
      <AnimatePresence mode="wait">
        <motion.div
          key={gradientIndex}
          className="absolute inset-0"
          style={{ background: GRADIENT_BACKGROUNDS[gradientIndex] }}
          initial={{ opacity: 0 }}
          animate={{ opacity: dimmed ? 0.4 : 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.8 }}
        />
      </AnimatePresence>
    )
  }

  if (!currentPhoto) {
    return (
      <div
        className="absolute inset-0 bg-zinc-900"
        style={{ opacity: dimmed ? 0.4 : 1 }}
      />
    )
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={currentPhoto}
        className="absolute inset-0"
        initial={{ opacity: 0 }}
        animate={{ opacity: dimmed ? 0.4 : 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.8 }}
      >
        {isPortrait && secondPhoto ? (
          <div className="absolute inset-0 flex">
            <div className="relative flex-1 overflow-hidden">
              <div
                className="absolute inset-0 scale-110 bg-cover bg-center blur-2xl"
                style={{ backgroundImage: `url(${currentPhoto})` }}
              />
              <img
                src={currentPhoto}
                alt=""
                className="absolute inset-0 m-auto max-h-full object-contain"
              />
            </div>
            <div className="relative flex-1 overflow-hidden">
              <div
                className="absolute inset-0 scale-110 bg-cover bg-center blur-2xl"
                style={{ backgroundImage: `url(${secondPhoto})` }}
              />
              <img
                src={secondPhoto}
                alt=""
                className="absolute inset-0 m-auto max-h-full object-contain"
              />
            </div>
          </div>
        ) : isPortrait ? (
          <>
            <div
              className="absolute inset-0 bg-cover bg-center blur-2xl scale-110"
              style={{ backgroundImage: `url(${currentPhoto})` }}
            />
            <img
              src={currentPhoto}
              alt=""
              className="absolute inset-0 m-auto max-h-full object-contain"
            />
          </>
        ) : isPortrait ? (
          <>
            <div
              className="absolute inset-0 bg-cover bg-center blur-2xl scale-110"
              style={{ backgroundImage: `url(${currentPhoto})` }}
            />
            <img
              src={currentPhoto}
              alt=""
              className="absolute inset-0 m-auto max-h-full object-contain"
            />
          </>
        ) : (
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: `url(${currentPhoto})` }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  )
}
