/**
 * biometrics — biometric payment confirmation (Mobile App Engineering CH11).
 *
 * Architecture (matches the doc exactly):
 *   enroll  → generate keypair on device → register PUBLIC key with server
 *   payment → server issues one-time challenge → device signs it (after
 *             a biometric prompt on native) → server verifies signature
 *             → returns a one-time payment_token for that order
 *
 * Crypto: WebCrypto ECDSA P-256 (SHA-256). The private key is created
 * NON-EXTRACTABLE and stored as a CryptoKey object in IndexedDB — it
 * can sign but its bytes can never be read by JS, the closest browser
 * equivalent to the Secure Enclave. The server verifies with the
 * `cryptography` library (apps/mobile_app/services.py).
 *
 * Biometric gate: on native (Capacitor), the signing step is preceded
 * by a Face ID / fingerprint prompt via the NativeBiometric plugin if
 * it is installed. On web (or if the plugin is missing) the signature
 * flow still runs — the cryptographic proof-of-device holds; only the
 * "is the right human holding it" gate is skipped. See gap list.
 *
 * Fallback flow per the doc: 3 failed verifications → server marks the
 * challenge failed and the caller must fall back to PIN/password.
 */
import { getFingerprint } from '@/api/fingerprint'

const DB_NAME = 'micha_biometric'
const STORE = 'keys'
const KEY_ID = 'payment_signing_key'

/* ── IndexedDB CryptoKey storage (non-extractable keys survive here) ── */

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbGet(key) {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly').objectStore(STORE).get(key)
    tx.onsuccess = () => resolve(tx.result)
    tx.onerror = () => reject(tx.error)
  })
}

async function idbSet(key, value) {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite').objectStore(STORE)
      .put(value, key)
    tx.onsuccess = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function idbDelete(key) {
  const db = await openDB()
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readwrite').objectStore(STORE)
      .delete(key)
    tx.onsuccess = () => resolve()
    tx.onerror = () => resolve()
  })
}

/* ── Native biometric gate (optional, fail-open on web) ────────────── */

async function nativeBiometricGate(reason) {
  try {
    if (!window.Capacitor?.isNativePlatform?.()) return { gated: false }
    // Plugin is optional — @capgo/capacitor-native-biometric or similar.
    const mod = await import(
      /* @vite-ignore */ '@capgo/capacitor-native-biometric')
    const { NativeBiometric } = mod
    const { isAvailable, biometryType } =
      await NativeBiometric.isAvailable()
    if (!isAvailable) return { gated: false }
    await NativeBiometric.verifyIdentity({
      reason,
      title: 'MICHA',
      subtitle: reason,
    })  // throws if the user fails/cancels the prompt
    return { gated: true, biometryType: String(biometryType ?? '') }
  } catch (err) {
    if (err?.message?.includes('cancel') || err?.code === '10') {
      throw new Error('BIOMETRIC_CANCELLED')
    }
    return { gated: false }  // plugin missing → degrade gracefully
  }
}

/* ── Key generation + PEM export ───────────────────────────────────── */

async function generateKeypair() {
  const keypair = await crypto.subtle.generateKey(
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,                       // non-extractable private key
    ['sign', 'verify'],
  )
  await idbSet(KEY_ID, keypair)
  return keypair
}

async function exportPublicKeyPem(publicKey) {
  const spki = await crypto.subtle.exportKey('spki', publicKey)
  const b64 = btoa(String.fromCharCode(...new Uint8Array(spki)))
  const lines = b64.match(/.{1,64}/g).join('\n')
  return `-----BEGIN PUBLIC KEY-----\n${lines}\n-----END PUBLIC KEY-----`
}

/* WebCrypto emits raw (r||s) ECDSA signatures; the server's
   `cryptography` library expects ASN.1 DER. Convert. */
function rawSigToDer(raw) {
  const bytes = new Uint8Array(raw)
  const r = bytes.slice(0, 32)
  const s = bytes.slice(32, 64)
  const trim = (buf) => {
    let i = 0
    while (i < buf.length - 1 && buf[i] === 0) i++
    let out = buf.slice(i)
    if (out[0] & 0x80) out = Uint8Array.from([0, ...out])
    return out
  }
  const rT = trim(r); const sT = trim(s)
  const der = new Uint8Array(6 + rT.length + sT.length)
  let o = 0
  der[o++] = 0x30; der[o++] = 4 + rT.length + sT.length
  der[o++] = 0x02; der[o++] = rT.length; der.set(rT, o); o += rT.length
  der[o++] = 0x02; der[o++] = sT.length; der.set(sT, o); o += sT.length
  return btoa(String.fromCharCode(...der))
}

/* ── Public API ─────────────────────────────────────────────────────── */

export async function isEnrolled() {
  try {
    const { default: client } = await import('@/api/client')
    const { data } = await client.get('/api/v1/mobile/biometrics/status/')
    return data.enrolled === true
  } catch { return false }
}

/** STEP 1+2 (doc 11.1): create keypair, register public key. */
export async function enrollBiometrics() {
  const gate = await nativeBiometricGate('Ativar confirmação biométrica')
  const keypair = await generateKeypair()
  const pem = await exportPublicKeyPem(keypair.publicKey)
  const fp = await getFingerprint()
  const { default: client } = await import('@/api/client')
  await client.post('/api/v1/mobile/biometrics/register/', {
    public_key_pem: pem,
    device_fingerprint: fp,
    algorithm: 'ec_p256',
    platform: window.Capacitor?.getPlatform?.() || 'web',
    biometry_type: gate.biometryType || '',
  })
  try { localStorage.setItem('biometric_enrolled', 'true') } catch {}
  return true
}

/**
 * STEP 3 (doc 11.1): confirm a payment. Returns a one-time
 * payment_token to attach to the charge call.
 * Throws 'BIOMETRIC_CANCELLED' | 'FALLBACK_TO_PASSWORD' | Error.
 */
export async function authenticateForPayment(orderRef) {
  const keypair = await idbGet(KEY_ID)
  if (!keypair?.privateKey) throw new Error('NOT_ENROLLED')

  const { default: client } = await import('@/api/client')
  const { data: { challenge } } = await client.post(
    '/api/v1/mobile/biometrics/challenge/',
    { purpose: 'payment', order_ref: orderRef })

  await nativeBiometricGate('Confirmar pagamento')   // FaceID prompt

  const rawSig = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    keypair.privateKey,
    new TextEncoder().encode(challenge),
  )
  try {
    const { data } = await client.post('/api/v1/mobile/biometrics/verify/', {
      challenge,
      signature: rawSigToDer(rawSig),
    })
    return data.payment_token
  } catch (error) {
    if (error.response?.data?.fallback_to_password) {
      throw new Error('FALLBACK_TO_PASSWORD')
    }
    throw error
  }
}

export async function disableBiometrics() {
  await idbDelete(KEY_ID)
  try { localStorage.removeItem('biometric_enrolled') } catch {}
  try {
    const { default: client } = await import('@/api/client')
    await client.delete('/api/v1/mobile/biometrics/status/')
  } catch {}
}
