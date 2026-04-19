import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SearchBar({ onSearch, placeholder = 'Pesquisar produtos...' }) {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const handleSubmit = () => {
    if (query.trim()) {
      navigate('/explore', { state: { query: query.trim() } })
    }
  }

  return (
    <div style={{
      padding: '0 16px',
      display: 'flex',
      gap: 10,
      alignItems: 'center',
    }}>
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        background: '#1E1E1E',
        border: '1px solid #2A2A2A',
        borderRadius: 14,
        padding: '12px 16px',
        transition: 'border-color 0.2s',
      }}
        onClick={() => navigate('/explore')}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <span style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: 14, color: '#9A9A9A',
          flex: 1,
        }}>
          {placeholder}
        </span>
      </div>

      {/* Filter button */}
      <button style={{
        width: 46, height: 46, borderRadius: 14, flexShrink: 0,
        background: '#1E1E1E', border: '1px solid #2A2A2A',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer',
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="4" y1="6" x2="20" y2="6" />
          <line x1="8" y1="12" x2="16" y2="12" />
          <line x1="11" y1="18" x2="13" y2="18" />
        </svg>
      </button>
    </div>
  )
}
