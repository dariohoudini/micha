/**
 * SearchBar — Tier 3 F10 overhaul.
 *
 * What changed vs pre-F10
 * ───────────────────────
 *  • Recent searches (top 5, localStorage) — shown immediately on focus
 *    so users see useful content even before typing
 *  • Trending searches (/api/v1/search/trending/) — backend endpoint
 *    already exists; pre-F10 it was never called
 *  • Grouped suggestions — products / categories / brands (backend
 *    returns ``{products, categories, brands}`` when typed query
 *    reaches 2 chars; the previous code path treated all as a flat list)
 *  • Bug fix: clear-input button referenced a setSuggestions that
 *    didn't exist on the parent, so suggestions never actually cleared
 *  • Bug fix: focus didn't restore to input after clear on iOS
 *  • Keyboard navigation cycles cleanly across groups + recents
 *  • Empty/error states for the dropdown
 *  • Records the chosen search to localStorage so it shows in recents
 *    on next session
 *  • Records to /search/event/ for backend analytics (already wired
 *    by ExplorePage; now also captured at the bar level)
 *
 * Backward compatible: ``<SearchBar onSearch placeholder />`` props
 * unchanged. Drop-in replacement.
 */
import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'


const RECENT_LS = 'micha-search-recents-v1'
const MAX_RECENTS = 5


function readRecents() {
  try {
    const raw = localStorage.getItem(RECENT_LS)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}


function writeRecents(list) {
  try {
    localStorage.setItem(RECENT_LS, JSON.stringify(list.slice(0, MAX_RECENTS)))
  } catch {}
}


/**
 * Group + normalise the suggestion response. Backend may return:
 *   • flat array of strings or {text} objects (legacy)
 *   • {products: [], categories: [], brands: []} (preferred)
 * We always emit a single ordered array of {type, text, count?, slug?}
 * for rendering.
 */
function normaliseSuggestions(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw.map((s) => ({
      type: 'product',
      text: typeof s === 'string' ? s : (s.text || s.name || ''),
      count: typeof s === 'object' ? s.count : undefined,
    })).filter(s => s.text)
  }
  // Preferred grouped shape.
  const out = []
  for (const c of (raw.categories || [])) {
    out.push({ type: 'category', text: c.name || c.text || c,
               slug: c.slug, count: c.count })
  }
  for (const b of (raw.brands || [])) {
    out.push({ type: 'brand', text: b.name || b.text || b,
               count: b.count })
  }
  for (const p of (raw.products || raw.suggestions || [])) {
    out.push({ type: 'product', text: p.text || p.name || p,
               count: p.count })
  }
  return out
}


function useSearchSuggestions(query, debounceMs = 280) {
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!query || query.length < 2) {
      setSuggestions([])
      setLoading(false)
      setError(false)
      return
    }
    setLoading(true); setError(false)
    const t = setTimeout(() => {
      client.get('/api/v1/search/suggestions/', { params: { q: query } })
        .then((r) => {
          setSuggestions(normaliseSuggestions(r.data?.suggestions ?? r.data))
        })
        .catch((e) => {
          // Aborted (axios cancel) shouldn't surface an error.
          if (e?.code !== 'ERR_CANCELED' && e?.name !== 'CanceledError') {
            setError(true)
            setSuggestions([])
          }
        })
        .finally(() => setLoading(false))
    }, debounceMs)
    return () => { clearTimeout(t) }
  }, [query, debounceMs])

  return { suggestions, loading, error }
}


function useTrending(active) {
  const [trending, setTrending] = useState([])

  useEffect(() => {
    if (!active || trending.length > 0) return
    let cancelled = false
    client.get('/api/v1/search/trending/')
      .then((r) => {
        if (cancelled) return
        const list = r.data?.results || r.data?.trending || r.data || []
        setTrending(
          (Array.isArray(list) ? list : [])
            .slice(0, 6)
            .map((t) => ({
              type: 'trending',
              text: t.text || t.term || t.query || t,
            }))
            .filter((t) => t.text),
        )
      })
      .catch(() => {
        if (!cancelled) setTrending([])
      })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

  return trending
}


/* ─── Icons (inline SVG — no extra deps) ──────────────────────────── */

function MagnifyIcon({ color = '#9A9A9A', size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}
function ClockIcon({ color = '#9A9A9A', size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}
function FireIcon({ color = '#C9A84C', size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color}
         aria-hidden="true">
      <path d="M13.5 0.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14a8 8 0 0 0 16 0c0-4.16-2-7.88-6.5-13.33zM11.71 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 4.62-2.58.39 1.29.59 2.65.59 4.04 0 2.65-2.15 4.8-4.8 4.8z"/>
    </svg>
  )
}
function TagIcon({ color = '#9A9A9A', size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  )
}
function ArrowUpRightIcon({ color = '#9A9A9A', size = 12 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d="M7 17L17 7M7 7h10v10" />
    </svg>
  )
}


const TYPE_ICON = {
  recent:   ClockIcon,
  trending: FireIcon,
  category: TagIcon,
  brand:    TagIcon,
  product:  MagnifyIcon,
}
const TYPE_LABEL = {
  recent:   'Pesquisas recentes',
  trending: 'Em alta',
  category: 'Categorias',
  brand:    'Marcas',
  product:  'Produtos',
}


/* ─── Component ──────────────────────────────────────────────────── */

export default function SearchBar({ onSearch, placeholder = 'Pesquisar produtos…' }) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [recents, setRecents] = useState(() => readRecents())
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const wrapRef = useRef(null)

  const trimmed = query.trim()
  const typing = trimmed.length >= 2
  const { suggestions, loading, error } = useSearchSuggestions(typing ? trimmed : '')
  const trending = useTrending(focused && !typing)

  // Build the rendered list. Either:
  //   typing  → grouped suggestion results (or no-results recovery)
  //   focused-no-text → recents + trending
  const rendered = useMemo(() => {
    if (typing) {
      return suggestions.map((s) => ({ ...s }))
    }
    const blocks = []
    for (const r of recents) blocks.push({ type: 'recent', text: r })
    for (const t of trending) blocks.push({ ...t })
    return blocks
  }, [typing, suggestions, recents, trending])

  const showDropdown = focused && (
    typing
      ? (loading || error || rendered.length > 0 || trimmed.length >= 2)
      : rendered.length > 0
  )

  const persistRecent = (term) => {
    if (!term) return
    setRecents((prev) => {
      const next = [term, ...prev.filter((p) => p !== term)].slice(0, MAX_RECENTS)
      writeRecents(next)
      return next
    })
  }

  const doSearch = useCallback((q) => {
    const term = (q || '').trim()
    if (!term) return
    persistRecent(term)
    setFocused(false)
    setQuery(term)
    setActiveIdx(-1)
    // Track search event (best-effort, ignore failure).
    client.post('/api/v1/search/event/', { q: term })
      .catch(() => {})
    navigate('/explore', { state: { query: term } })
    onSearch?.(term)
    inputRef.current?.blur()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, onSearch])

  const removeRecent = (term) => {
    setRecents((prev) => {
      const next = prev.filter((p) => p !== term)
      writeRecents(next)
      return next
    })
  }

  const clearQuery = () => {
    setQuery('')
    setActiveIdx(-1)
    inputRef.current?.focus()
  }

  /* Keyboard nav across the rendered flat list. */
  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      setFocused(false)
      inputRef.current?.blur()
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0 && rendered[activeIdx]) {
        doSearch(rendered[activeIdx].text)
      } else {
        doSearch(trimmed)
      }
      return
    }
    if (!showDropdown || rendered.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, rendered.length - 1))
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, -1))
    }
  }

  // Reset active index when the rendered list changes.
  useEffect(() => { setActiveIdx(-1) }, [rendered.length, typing])

  // Close on outside click.
  useEffect(() => {
    const handler = (e) => {
      if (!wrapRef.current?.contains(e.target)) setFocused(false)
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('touchstart', handler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('touchstart', handler)
    }
  }, [])

  return (
    <div ref={wrapRef} style={{ padding: '0 16px', position: 'relative', zIndex: 20 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        {/* Search input */}
        <div
          role="combobox"
          aria-expanded={showDropdown}
          aria-haspopup="listbox"
          aria-owns={showDropdown ? 'search-suggestions' : undefined}
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            background: '#1E1E1E',
            border: `1px solid ${focused ? '#C9A84C44' : '#2A2A2A'}`,
            borderRadius: 14,
            padding: '12px 16px',
            transition: 'border-color 0.2s',
          }}
        >
          <MagnifyIcon size={16} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            aria-label="Pesquisar produtos"
            aria-autocomplete="list"
            aria-controls={showDropdown ? 'search-suggestions' : undefined}
            aria-activedescendant={activeIdx >= 0 ? `suggestion-${activeIdx}` : undefined}
            autoComplete="off"
            inputMode="search"
            enterKeyHint="search"
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              outline: 'none',
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 14,
              color: '#FFFFFF',
              minWidth: 0,
            }}
          />
          {query && (
            <button
              type="button"
              onClick={clearQuery}
              aria-label="Limpar pesquisa"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 4, lineHeight: 0,
                minWidth: 28, minHeight: 28,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                   stroke="#9A9A9A" strokeWidth="2.5"
                   strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
          {loading && (
            <div
              aria-hidden="true"
              style={{
                width: 14, height: 14, borderRadius: '50%',
                border: '2px solid #C9A84C', borderTopColor: 'transparent',
                animation: 'searchbar-spin 0.7s linear infinite',
                flexShrink: 0,
              }}
            />
          )}
          <style>{`
            @keyframes searchbar-spin { to { transform: rotate(360deg); } }
          `}</style>
        </div>

        {/* Filter button */}
        <button
          type="button"
          aria-label="Filtros"
          onClick={() => navigate('/explore')}
          style={{
            width: 46, height: 46, borderRadius: 14, flexShrink: 0,
            background: '#1E1E1E', border: '1px solid #2A2A2A',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
               stroke="#C9A84C" strokeWidth="2" strokeLinecap="round"
               strokeLinejoin="round" aria-hidden="true">
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="8" y1="12" x2="16" y2="12" />
            <line x1="11" y1="18" x2="13" y2="18" />
          </svg>
        </button>
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <Dropdown
          rendered={rendered}
          activeIdx={activeIdx}
          setActiveIdx={setActiveIdx}
          onPick={doSearch}
          onRemoveRecent={removeRecent}
          typing={typing}
          loading={loading}
          error={error}
          query={trimmed}
        />
      )}
    </div>
  )
}


/* ─── Dropdown ───────────────────────────────────────────────────── */

function Dropdown({
  rendered, activeIdx, setActiveIdx, onPick,
  onRemoveRecent, typing, loading, error, query,
}) {
  // Group by type for visual section headers. Each item carries its
  // ORIGINAL flat-list index (_idx) so activeIdx navigation matches.
  const groups = useMemo(() => {
    const acc = []
    let i = 0
    for (const item of rendered) {
      acc.push({ ...item, _idx: i++ })
    }
    const out = []
    let lastType = null
    for (const item of acc) {
      if (item.type !== lastType) {
        out.push({ type: item.type, items: [item] })
        lastType = item.type
      } else {
        out[out.length - 1].items.push(item)
      }
    }
    return out
  }, [rendered])

  return (
    <ul
      id="search-suggestions"
      role="listbox"
      aria-label="Sugestões de pesquisa"
      style={{
        position: 'absolute',
        top: '100%',
        left: 16,
        right: 70,
        marginTop: 6,
        background: '#141414',
        border: '1px solid #2A2A2A',
        borderRadius: 14,
        overflow: 'hidden',
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
        listStyle: 'none',
        padding: 0,
        margin: '6px 0 0',
        maxHeight: 360,
        overflowY: 'auto',
      }}
    >
      {/* Empty: backend returned no results AND we're typing */}
      {typing && !loading && rendered.length === 0 && !error && (
        <NoResultsRow query={query} onSuggest={onPick} />
      )}

      {/* Error */}
      {typing && error && (
        <li role="alert" style={{
          padding: '14px 16px', fontSize: 13, color: '#F87171',
          background: 'rgba(239, 68, 68, 0.08)',
        }}>
          Erro ao carregar sugestões. Tenta de novo.
        </li>
      )}

      {/* Loading skeleton (when typing) */}
      {typing && loading && rendered.length === 0 && (
        <>
          {[0, 1, 2].map((i) => (
            <li key={i} style={{
              padding: '12px 16px', borderBottom: '1px solid #1E1E1E',
            }}>
              <div style={{
                height: 12, width: `${80 - i * 15}%`,
                background: 'linear-gradient(90deg, #1E1E1E 25%, #2A2A2A 50%, #1E1E1E 75%)',
                backgroundSize: '200% 100%',
                animation: 'searchbar-shimmer 1.4s ease infinite',
                borderRadius: 4,
              }} />
              <style>{`
                @keyframes searchbar-shimmer {
                  0% { background-position: -200% 0; }
                  100% { background-position: 200% 0; }
                }
              `}</style>
            </li>
          ))}
        </>
      )}

      {/* Grouped rows */}
      {groups.length > 0 && groups.map((g) => (
        <div key={g.type}>
          {!typing && (
            <li role="presentation" aria-hidden="true" style={{
              padding: '8px 16px 4px',
              fontSize: 10, fontWeight: 700,
              color: '#9A9A9A', textTransform: 'uppercase',
              letterSpacing: '0.08em',
              borderBottom: '1px solid #1E1E1E',
            }}>
              {TYPE_LABEL[g.type] || g.type}
            </li>
          )}
          {g.items.map((s) => (
            <SuggestionRow
              key={s._idx}
              idx={s._idx}
              item={s}
              isActive={s._idx === activeIdx}
              onHover={() => setActiveIdx(s._idx)}
              onPick={() => onPick(s.text)}
              onRemove={
                s.type === 'recent'
                  ? () => onRemoveRecent(s.text)
                  : null
              }
            />
          ))}
        </div>
      ))}
    </ul>
  )
}


function SuggestionRow({ idx, item, isActive, onHover, onPick, onRemove }) {
  const Icon = TYPE_ICON[item.type] || MagnifyIcon
  return (
    <li
      id={`suggestion-${idx}`}
      role="option"
      aria-selected={isActive}
      onMouseDown={(e) => {
        // mousedown (not click) so the input blur doesn't close the
        // list before the click fires.
        e.preventDefault()
        onPick()
      }}
      onMouseEnter={onHover}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        cursor: 'pointer',
        background: isActive ? 'rgba(201,168,76,0.08)' : 'transparent',
        borderBottom: '1px solid #1E1E1E',
        transition: 'background 0.12s',
      }}
    >
      <Icon color={isActive ? '#C9A84C' : '#9A9A9A'} />
      <span style={{
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 14,
        color: isActive ? '#FFFFFF' : '#CCCCCC',
        flex: 1, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {item.text}
      </span>
      {item.count != null && (
        <span style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 11, color: '#9A9A9A',
        }}>{item.count}</span>
      )}
      {onRemove ? (
        <button
          type="button"
          aria-label={`Remover ${item.text} dos recentes`}
          onMouseDown={(e) => {
            e.preventDefault(); e.stopPropagation()
            onRemove()
          }}
          style={{
            background: 'none', border: 'none', padding: 4,
            cursor: 'pointer', lineHeight: 0,
            minWidth: 28, minHeight: 28,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
               stroke="#9A9A9A" strokeWidth="2.5"
               strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      ) : (
        <ArrowUpRightIcon />
      )}
    </li>
  )
}


function NoResultsRow({ query, onSuggest }) {
  // Did-you-mean: simple character-distance suggestions from common
  // marketplace queries. For an AO marketplace, "carros", "telemóveis",
  // "roupa", "casa" are recurrent typos.
  const HINTS = [
    'telemóveis', 'electrónica', 'roupa', 'carros',
    'casa e cozinha', 'beleza',
  ]
  const suggestion = useMemo(() => {
    const q = (query || '').toLowerCase()
    if (!q) return null
    let best = null
    let bestDistance = Infinity
    for (const h of HINTS) {
      const d = levenshtein(q, h)
      if (d < bestDistance) { bestDistance = d; best = h }
    }
    // Only show suggestion if it's reasonably close.
    return bestDistance <= Math.max(2, Math.floor(q.length / 2))
      ? best : null
  }, [query])

  return (
    <li role="option" aria-selected="false" style={{
      padding: '14px 16px', display: 'flex',
      flexDirection: 'column', gap: 6,
    }}>
      <div style={{
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 13, color: '#FFFFFF',
      }}>
        Sem sugestões para <strong>"{query}"</strong>
      </div>
      {suggestion && (
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); onSuggest(suggestion) }}
          style={{
            background: 'none', border: 'none', padding: 0,
            cursor: 'pointer', textAlign: 'left',
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 12, color: '#C9A84C',
          }}
        >
          Quis dizer <strong>{suggestion}</strong>?
        </button>
      )}
      <button
        type="button"
        onMouseDown={(e) => { e.preventDefault(); onSuggest(query) }}
        style={{
          background: 'none', border: 'none', padding: '4px 0',
          cursor: 'pointer', textAlign: 'left',
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 12, color: '#9A9A9A',
        }}
      >
        Pesquisar "{query}" mesmo assim →
      </button>
    </li>
  )
}


function levenshtein(a, b) {
  if (a === b) return 0
  const m = a.length, n = b.length
  if (!m) return n
  if (!n) return m
  const prev = new Array(n + 1).fill(0)
  for (let j = 0; j <= n; j++) prev[j] = j
  for (let i = 1; i <= m; i++) {
    let cur = i
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      const next = Math.min(prev[j] + 1, cur + 1, prev[j - 1] + cost)
      prev[j - 1] = cur
      cur = next
    }
    prev[n] = cur
  }
  return prev[n]
}
