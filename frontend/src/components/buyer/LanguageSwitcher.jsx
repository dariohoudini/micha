import { useTranslation } from 'react-i18next'
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

const GOLD = '#C9A84C'
const TEXT = '#FFFFFF'
const MUTED = '#9A9A9A'
const CARD = '#141414'
const BORDER = '#1E1E1E'
const S = { fontFamily: "'DM Sans', sans-serif" }

const LANGUAGES = [
  { code: 'pt', label: 'Português', flag: '🇦🇴' },
  { code: 'en', label: 'English', flag: '🇬🇧' },
]

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const updateUser = useAuthStore(s => s.updateUser)
  const current = i18n.language?.split('-')[0] || 'pt'

  const switchTo = async (code) => {
    if (code === current) return
    i18n.changeLanguage(code)
    localStorage.setItem('lang', code)
    updateUser?.({ language: code })
    client.patch('/api/v1/auth/profile/update/', { language: code }).catch(() => {})
  }

  return (
    <div style={{ background: CARD, borderRadius: 14, border: `1px solid ${BORDER}`, padding: 14, marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 16 }}>🌐</span>
        <p style={{ ...S, fontSize: 13, fontWeight: 600, color: TEXT, margin: 0 }}>Idioma · Language</p>
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {LANGUAGES.map(l => {
          const active = l.code === current
          return (
            <button key={l.code} onClick={() => switchTo(l.code)}
              style={{
                flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '10px 0', borderRadius: 10,
                border: `1px solid ${active ? GOLD : BORDER}`,
                background: active ? 'rgba(201,168,76,0.08)' : 'transparent',
                ...S, fontSize: 12, color: active ? GOLD : TEXT, cursor: 'pointer',
                fontWeight: active ? 600 : 400,
              }}>
              <span style={{ fontSize: 16 }}>{l.flag}</span>{l.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
