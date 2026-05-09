/**
 * Lightweight client-side device fingerprint.
 *
 * What we collect (all non-sensitive, all available without permission):
 *   • User-agent
 *   • Timezone offset
 *   • Screen dimensions + colour depth
 *   • Hardware concurrency (CPU thread count)
 *   • Languages
 *   • A canvas hash (a tiny rendered shape; differs slightly between GPUs/fonts)
 *
 * The components are concatenated and hashed with SHA-256. The hash is what
 * we send to the backend. The backend uses it only to detect *correlation*
 * between accounts (same hash across many users = farm) — never to
 * identify the device.
 *
 * Cached in localStorage so we don't recompute on every checkout.
 */

const STORAGE_KEY = 'micha_device_fp_v1'

async function sha256Hex(text) {
  const buf = new TextEncoder().encode(text)
  const hash = await crypto.subtle.digest('SHA-256', buf)
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('')
}

function canvasSignal() {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = 200; canvas.height = 50
    const ctx = canvas.getContext('2d')
    ctx.textBaseline = 'top'
    ctx.font = "14px 'Arial'"
    ctx.fillStyle = '#f60'
    ctx.fillRect(0, 0, 60, 20)
    ctx.fillStyle = '#069'
    ctx.fillText('MICHA·fp', 2, 15)
    ctx.fillStyle = 'rgba(102,204,0,0.7)'
    ctx.fillText('AO', 50, 17)
    return canvas.toDataURL().slice(0, 200)
  } catch {
    return ''
  }
}

async function compute() {
  const parts = [
    navigator.userAgent || '',
    new Date().getTimezoneOffset(),
    `${screen.width}x${screen.height}x${screen.colorDepth || ''}`,
    navigator.hardwareConcurrency || '',
    (navigator.languages || []).join(','),
    canvasSignal(),
  ]
  return sha256Hex(parts.join('|'))
}

export async function getFingerprint() {
  try {
    const cached = localStorage.getItem(STORAGE_KEY)
    if (cached && cached.length === 64) return cached
  } catch {}

  let fp
  try {
    fp = await compute()
  } catch {
    return ''
  }

  try {
    localStorage.setItem(STORAGE_KEY, fp)
  } catch {}

  return fp
}
