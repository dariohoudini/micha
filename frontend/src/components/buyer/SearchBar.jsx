import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import client from '@/api/client'

function useSearchSuggestions(query) {
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!query || query.length < 2) { setSuggestions([]); return }
    setLoading(true)
    const t = setTimeout(() => {
      client.get('/api/v1/search/suggestions/', { params: { q: query } })
        .then(r => setSuggestions(r.data.suggestions || r.data || []))
        .catch(() => setSuggestions([]))
        .finally(() => setLoading(false))
    }, 280)
    return () => { clearTimeout(t); setLoading(false) }
  }, [query])

  return { suggestions, loading }
}

export default function SearchBar({ onSearch, placeholder = 'Pesquisar produtos...' }) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const wrapRef = useRef(null)
  const { suggestions, loading } = useSearchSuggestions(focused ? query : '')

  const showDropdown = focused && query.length >= 2 && (suggestions.length > 0 || loading)

  const doSearch = useCallback((q) => {
    if (!q?.trim()) return
    setFocused(false)
    setQuery(q)
    navigate('/explore', { state: { query: q.trim() } })
    onSearch?.(q.trim())
  }, [navigate, onSearch])

  const handleKeyDown = (e) => {
    if (!showDropdown) {
      if (e.key === 'Enter') doSearch(query)
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, suggestions.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, -1)) }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0) doSearch(suggestions[activeIdx]?.text || suggestions[activeIdx])
      else doSearch(query)
    }
    if (e.key === 'Escape') { setFocused(false); inputRef.current?.blur() }
  }

  useEffect(() => { setActiveIdx(-1) }, [suggestions])

  // Close on outside click
  useEffect(() => {
    const handler = (e) => { if (!wrapRef.current?.contains(e.target)) setFocused(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={wrapRef} style={{ padding: '0 16px', position: 'relative', zIndex: 20 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        {/* Search input */}
        <div
          role="combobox"
          aria-expanded={showDropdown}
          aria-haspopup="listbox"
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
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            aria-label="Pesquisar produtos"
            aria-autocomplete="list"
            aria-controls={showDropdown ? 'search-suggestions' : undefined}
            aria-activedescendant={activeIdx >= 0 ? `suggestion-${activeIdx}` : undefined}
            style={{
              flex: 1,
              background: 'none',
              border: 'none',
              outline: 'none',
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 14,
              color: '#FFFFFF',
            }}
          />
          {query && (
            <button
              onClick={() => { setQuery(''); setSuggestions?.(); inputRef.current?.focus() }}
              aria-label="Limpar pesquisa"
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, lineHeight: 0 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
          {loading && (
            <div style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid #C9A84C', borderTopColor: 'transparent', animation: 'spin 0.7s linear infinite', flexShrink: 0 }}>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          )}
        </div>

        {/* Filter button */}
        <button
          aria-label="Filtros"
          onClick={() => navigate('/explore')}
          style={{
            width: 46, height: 46, borderRadius: 14, flexShrink: 0,
            background: '#1E1E1E', border: '1px solid #2A2A2A',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="8" y1="12" x2="16" y2="12" />
            <line x1="11" y1="18" x2="13" y2="18" />
          </svg>
        </button>
      </div>

      {/* Autocomplete dropdown */}
      {showDropdown && (
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
          }}
        >
          {suggestions.map((s, i) => {
            const text = s?.text || s
            const isActive = i === activeIdx
            return (
              <li
                key={i}
                id={`suggestion-${i}`}
                role="option"
                aria-selected={isActive}
                onMouseDown={() => doSearch(text)}
                onMouseEnter={() => setActiveIdx(i)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '12px 16px',
                  cursor: 'pointer',
                  background: isActive ? 'rgba(201,168,76,0.08)' : 'transparent',
                  borderBottom: i < suggestions.length - 1 ? '1px solid #1E1E1E' : 'none',
                  transition: 'background 0.15s',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={isActive ? '#C9A84C' : '#9A9A9A'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: isActive ? '#FFFFFF' : '#CCCCCC', flex: 1 }}>
                  {text}
                </span>
                {s?.count != null && (
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>
                    {s.count}
                  </span>
                )}
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M7 17L17 7M7 7h10v10" />
                </svg>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
