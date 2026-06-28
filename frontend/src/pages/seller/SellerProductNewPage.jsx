import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import SellerLayout from '@/layouts/SellerLayout'
import client from '@/api/client'

/**
 * SellerProductNewPage — multi-step product creation wizard.
 *
 * Implements §8–§16 of the AliExpress Process Flow spec
 * (Casa Cabaça Tech, v1.0), adapted for mobile (single column,
 * one section per step, sticky bottom CTA).
 *
 * Step map (spec → screen):
 *   1) Categoria          §9   3-level cascading picker w/ search
 *   2) Título & Descrição §10  SEO score bar, char counters
 *   3) Imagens & Vídeo    §11  9-slot grid, main-image marker, video
 *   4) Preço & Stock      §12  Selling, original (compare-at), quantity, SKU
 *   5) Variantes          §13  Toggle + per-SKU price/qty grid
 *   6) Envio              §14  Free/paid toggle, processing days, weight
 *   7) Atributos          §15  Category-specific fields
 *   8) Revisão & Publicar §16  Section completion + publish
 *
 * What this file deliberately does NOT implement
 * ──────────────────────────────────────────────
 *   • AI title suggestions (§10.2) — needs LLM endpoint
 *   • In-browser image crop / BG remove (§11.6) — heavy lib
 *   • Video transcoding preview (§11.7) — happens server-side
 *   • Shipping templates UI (§14.1) — would need a dedicated mgmt
 *     page; we use a simplified per-product shipping form instead
 *   • Save-as-draft (§16.3) — needs a Draft model; out of scope
 */

const S = { fontFamily: "'DM Sans', sans-serif" }
const inputStyle = {
  width: '100%', background: '#141414', border: '1px solid #2A2A2A',
  borderRadius: 12, padding: '12px 14px', ...S, fontSize: 14,
  color: '#FFFFFF', outline: 'none', boxSizing: 'border-box',
}
const labelStyle = {
  ...S, fontSize: 11, color: '#9A9A9A', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.08em',
  marginBottom: 6, display: 'block',
}


// ── SEO score §10.1 ────────────────────────────────────────────────
// Heuristic blended from: length (sweet spot 60–100), presence of
// numeric/spec markers (sizes, GB, colour tokens), absence of all
// caps. Not LLM-perfect but matches the spec's intent.
function seoScore(title = '') {
  let s = 0
  const t = title.trim()
  if (t.length >= 20) s += 20
  if (t.length >= 40) s += 20
  if (t.length >= 60 && t.length <= 100) s += 20
  else if (t.length > 100) s += 10
  if (/\b(GB|TB|cm|kg|ml|XS|S|M|L|XL|XXL|\d{2,})\b/i.test(t)) s += 15
  if (/^[^A-Z]*[A-Z][a-z]/.test(t)) s += 10
  if (t === t.toUpperCase() && t.length > 5) s -= 20
  if (/[!?]{2,}/.test(t)) s -= 10
  return Math.max(0, Math.min(100, s))
}
function seoBand(n) {
  if (n >= 91) return { label: 'Excelente', color: '#10b981' }
  if (n >= 71) return { label: 'Bom',       color: '#34d399' }
  if (n >= 41) return { label: 'Razoável',  color: '#f59e0b' }
  return { label: 'Fraco',     color: '#ef4444' }
}


// ── Step indicator ────────────────────────────────────────────────
function StepDots({ total, current, completed }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '10px 16px',
      background: '#0F0F0F', borderBottom: '1px solid #1A1A1A',
      overflowX: 'auto', flexShrink: 0,
    }}>
      {Array.from({ length: total }).map((_, i) => {
        const idx = i + 1
        const isDone = completed.has(idx)
        const isCurrent = idx === current
        return (
          <div key={idx} style={{
            flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 6,
            opacity: isCurrent || isDone ? 1 : 0.4,
          }}>
            <div style={{
              width: 24, height: 24, borderRadius: '50%',
              background: isCurrent ? '#C9A84C' : (isDone ? '#10b981' : '#2A2A2A'),
              color: isCurrent ? '#0A0A0A' : '#FFFFFF',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              ...S, fontSize: 11, fontWeight: 700,
            }}>{isDone ? '✓' : idx}</div>
            {idx < total && <div style={{ width: 12, height: 1, background: '#2A2A2A' }} />}
          </div>
        )
      })}
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 1 — CATEGORY  (§9)
// ════════════════════════════════════════════════════════════════════
function CategoryStep({ form, setForm, onNext }) {
  const [tree, setTree] = useState([])
  const [search, setSearch] = useState('')
  const [topId, setTopId] = useState(form.category_path?.[0]?.id || null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/api/v1/products/categories/')
      .then(r => setTree(r.data?.results || r.data || []))
      .catch(() => setTree([]))
      .finally(() => setLoading(false))
  }, [])

  const top = useMemo(() => tree.find(c => c.id === topId), [tree, topId])
  const subs = top?.subcategories || []

  // Search flattens the tree and matches by leaf name.
  const filtered = useMemo(() => {
    if (!search.trim()) return null
    const q = search.toLowerCase()
    const out = []
    for (const a of tree) {
      for (const b of (a.subcategories || [])) {
        if (b.name.toLowerCase().includes(q) || a.name.toLowerCase().includes(q)) {
          out.push({ topId: a.id, topName: a.name, leafId: b.id, leafName: b.name })
        }
      }
    }
    return out.slice(0, 12)
  }, [tree, search])

  const pickLeaf = (topRow, leafRow) => {
    setForm(f => ({ ...f, category: leafRow.id, category_path: [topRow, leafRow] }))
    onNext()
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <h2 style={{ ...S, fontSize: 18, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>
          Categoria do produto
        </h2>
        <p style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>
          Escolha onde os compradores vão encontrar o seu produto.
        </p>
      </div>

      <div style={{ position: 'relative' }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }}>
          <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          placeholder="Procurar (ex: vestido, telemóvel)"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ ...inputStyle, paddingLeft: 36 }}
        />
      </div>

      {loading && (
        <p style={{ ...S, fontSize: 13, color: '#9A9A9A', textAlign: 'center', padding: 24 }}>A carregar…</p>
      )}

      {!loading && filtered && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtered.length === 0 && (
            <p style={{ ...S, fontSize: 13, color: '#9A9A9A', padding: 12 }}>Sem correspondências.</p>
          )}
          {filtered.map(row => (
            <button key={`${row.topId}-${row.leafId}`}
              onClick={() => pickLeaf({ id: row.topId, name: row.topName }, { id: row.leafId, name: row.leafName })}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: 12,
                background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12,
                ...S, fontSize: 13, color: '#FFFFFF', textAlign: 'left', cursor: 'pointer',
              }}>
              <span style={{ color: '#9A9A9A' }}>{row.topName} ›</span>
              <span style={{ color: '#C9A84C', fontWeight: 600 }}>{row.leafName}</span>
            </button>
          ))}
        </div>
      )}

      {!loading && !filtered && (
        <>
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 4 }}>
            {topId ? 'Sub-categoria' : 'Categoria principal'}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(topId ? subs : tree).map(c => (
              <button key={c.id}
                onClick={() => topId ? pickLeaf(top, c) : setTopId(c.id)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  gap: 10, padding: '14px 16px',
                  background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12,
                  ...S, fontSize: 14, color: '#FFFFFF', cursor: 'pointer',
                }}>
                <span>{c.name}</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9A9A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
              </button>
            ))}
          </div>
          {topId && (
            <button onClick={() => setTopId(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', ...S, fontSize: 12, color: '#9A9A9A', padding: 8, alignSelf: 'flex-start' }}>
              ← Voltar às categorias principais
            </button>
          )}
        </>
      )}
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 2 — TITLE & DESCRIPTION  (§10)
// ════════════════════════════════════════════════════════════════════
function TitleStep({ form, setForm }) {
  const score = seoScore(form.title)
  const band = seoBand(score)
  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <label style={labelStyle}>Título do produto</label>
        <input
          maxLength={128}
          value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
          placeholder="Ex: Vestido Capulana Premium Tamanho M"
          style={inputStyle}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
          <span style={{ ...S, fontSize: 11, color: '#9A9A9A' }}>{form.title.length} / 128</span>
          <span style={{ ...S, fontSize: 11, color: band.color, fontWeight: 600 }}>
            SEO: {score} — {band.label}
          </span>
        </div>
        {/* SEO score bar */}
        <div style={{ marginTop: 6, height: 4, background: '#1E1E1E', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ width: `${score}%`, height: '100%', background: band.color, transition: 'width 0.25s' }} />
        </div>
      </div>

      <div>
        <label style={labelStyle}>Descrição detalhada</label>
        <textarea
          maxLength={5000}
          rows={8}
          value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          placeholder="Descreva materiais, dimensões, características, instruções de uso…"
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.55 }}
        />
        <div style={{ ...S, fontSize: 11, color: form.description.length < 50 ? '#f59e0b' : '#9A9A9A', marginTop: 6 }}>
          {form.description.length} / 5000 {form.description.length < 50 && '(mínimo 50)'}
        </div>
      </div>

      <div>
        <label style={labelStyle}>Marca (opcional)</label>
        <input
          maxLength={100}
          value={form.brand}
          onChange={e => setForm(f => ({ ...f, brand: e.target.value }))}
          placeholder="Ex: Samsung, Nike, Própria"
          style={inputStyle}
        />
      </div>

      <div>
        <label style={labelStyle}>Estado do produto</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {[
            { v: 'new', l: 'Novo' },
            { v: 'used', l: 'Usado' },
            { v: 'refurbished', l: 'Recondicionado' },
          ].map(opt => (
            <button key={opt.v} type="button"
              onClick={() => setForm(f => ({ ...f, condition: opt.v }))}
              style={{
                flex: 1, padding: '11px 0', borderRadius: 10,
                border: `1.5px solid ${form.condition === opt.v ? '#C9A84C' : '#2A2A2A'}`,
                background: form.condition === opt.v ? 'rgba(201,168,76,0.1)' : 'transparent',
                ...S, fontSize: 13, color: form.condition === opt.v ? '#C9A84C' : '#9A9A9A',
                cursor: 'pointer',
              }}>{opt.l}</button>
          ))}
        </div>
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 3 — IMAGES & VIDEO  (§11)
// ════════════════════════════════════════════════════════════════════
function ImagesStep({ images, setImages, video, setVideo, showToast }) {
  const fileRef = useRef()
  const videoRef = useRef()
  const [importUrl, setImportUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [dragIdx, setDragIdx] = useState(null)
  const MAX = 9

  const onPick = (e) => {
    const files = Array.from(e.target.files || [])
    const room = MAX - images.length
    const next = files.slice(0, room).map(file => ({
      file,
      url: URL.createObjectURL(file),
    }))
    setImages(prev => [...prev, ...next])
    e.target.value = ''
  }

  // §11.3 — import image from URL.
  const importFromUrl = async () => {
    const u = importUrl.trim()
    if (!u) return
    if (!/^https?:\/\//i.test(u)) { showToast?.('URL deve começar com http(s).', 'error'); return }
    setImporting(true)
    try {
      const res = await fetch(u, { mode: 'cors' })
      if (!res.ok) throw new Error('fetch failed')
      const blob = await res.blob()
      if (!blob.type.startsWith('image/')) throw new Error('not an image')
      const file = new File([blob], u.split('/').pop() || 'imported.jpg', { type: blob.type })
      setImages(prev => prev.length < MAX ? [...prev, { file, url: URL.createObjectURL(file) }] : prev)
      setImportUrl('')
    } catch {
      showToast?.('Falha ao importar imagem. CORS ou URL inválido?', 'error')
    } finally {
      setImporting(false)
    }
  }

  // §11.5 — drag-to-reorder via HTML5 DnD.
  const onDragStart = (i) => setDragIdx(i)
  const onDragOver = (e) => e.preventDefault()
  const onDrop = (i) => {
    if (dragIdx === null || dragIdx === i) return
    setImages(prev => {
      const next = [...prev]
      const [moved] = next.splice(dragIdx, 1)
      next.splice(i, 0, moved)
      return next
    })
    setDragIdx(null)
  }

  const onPickVideo = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('video/')) { alert('Só MP4 / vídeos são aceites.'); return }
    if (file.size > 500 * 1024 * 1024) { alert('Vídeo máximo 500MB.'); return }
    setVideo({ file, url: URL.createObjectURL(file) })
    e.target.value = ''
  }

  const remove = (i) => setImages(prev => prev.filter((_, j) => j !== i))
  const makeMain = (i) => setImages(prev => {
    if (i === 0) return prev
    const next = [...prev]
    const [picked] = next.splice(i, 1)
    return [picked, ...next]
  })

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h2 style={{ ...S, fontSize: 17, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>
          Imagens do produto
        </h2>
        <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>
          Primeira imagem = capa. Fundo claro recomendado. Mínimo 1, máximo 9.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {images.map((img, i) => (
          <div key={i}
            draggable
            onDragStart={() => onDragStart(i)}
            onDragOver={onDragOver}
            onDrop={() => onDrop(i)}
            style={{
              position: 'relative', aspectRatio: '1',
              background: '#1E1E1E', borderRadius: 12, overflow: 'hidden',
              border: i === 0 ? '2px solid #C9A84C' : '1px solid #2A2A2A',
              cursor: 'grab',
              opacity: dragIdx === i ? 0.5 : 1,
            }}>
            <img src={img.url} alt={`img ${i}`} style={{ width: '100%', height: '100%', objectFit: 'cover', pointerEvents: 'none' }} />
            {i === 0 && (
              <div style={{ position: 'absolute', top: 6, left: 6, background: '#C9A84C', color: '#0A0A0A', borderRadius: 6, padding: '2px 6px', ...S, fontSize: 9, fontWeight: 700 }}>
                CAPA
              </div>
            )}
            <button onClick={() => remove(i)}
              style={{ position: 'absolute', top: 6, right: 6, width: 22, height: 22, borderRadius: '50%', background: 'rgba(0,0,0,0.7)', border: 'none', color: '#FFFFFF', ...S, fontSize: 11, cursor: 'pointer', lineHeight: 1 }}>✕</button>
            {i !== 0 && (
              <button onClick={() => makeMain(i)}
                style={{ position: 'absolute', bottom: 6, left: 6, right: 6, background: 'rgba(10,10,10,0.85)', border: '1px solid rgba(201,168,76,0.4)', borderRadius: 6, padding: '4px 0', ...S, fontSize: 10, color: '#C9A84C', cursor: 'pointer' }}>
                Definir como capa
              </button>
            )}
          </div>
        ))}
        {images.length < MAX && (
          <button onClick={() => fileRef.current?.click()}
            style={{ aspectRatio: '1', background: '#141414', border: '2px dashed #2A2A2A', borderRadius: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: 'pointer' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.8" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            <span style={{ ...S, fontSize: 10, color: '#555' }}>Adicionar</span>
          </button>
        )}
      </div>
      <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={onPick} />

      {/* §11.5 — drag hint + §11.3 import from URL */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <p style={{ ...S, fontSize: 10, color: '#555' }}>↔ Arraste para reordenar — primeira posição = capa.</p>
        <div style={{ display: 'flex', gap: 6 }}>
          <input value={importUrl} onChange={e => setImportUrl(e.target.value)} placeholder="https://… (importar URL)"
            style={{ ...inputStyle, fontSize: 12 }} />
          <button disabled={importing || !importUrl.trim()} onClick={importFromUrl}
            style={{ padding: '0 14px', borderRadius: 10, border: '1px solid #2A2A2A', background: importing ? 'transparent' : '#1E1E1E', ...S, fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>
            {importing ? '…' : 'Importar'}
          </button>
        </div>
      </div>

      {/* Video upload */}
      <div>
        <label style={labelStyle}>Vídeo (opcional)</label>
        {video ? (
          <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden', background: '#1E1E1E' }}>
            <video src={video.url} controls style={{ width: '100%', display: 'block' }} />
            <button onClick={() => setVideo(null)}
              style={{ position: 'absolute', top: 8, right: 8, background: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: 6, padding: '4px 8px', ...S, fontSize: 11, color: '#FFFFFF', cursor: 'pointer' }}>
              Remover
            </button>
          </div>
        ) : (
          <button onClick={() => videoRef.current?.click()}
            style={{ width: '100%', padding: '14px', background: '#141414', border: '2px dashed #2A2A2A', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, cursor: 'pointer' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="1.8" strokeLinecap="round"><polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" /></svg>
            <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Adicionar vídeo (MP4 · máx 500MB)</span>
          </button>
        )}
        <input ref={videoRef} type="file" accept="video/mp4,video/*" style={{ display: 'none' }} onChange={onPickVideo} />
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 4 — PRICING & INVENTORY  (§12)
// ════════════════════════════════════════════════════════════════════
function PricingStep({ form, setForm }) {
  const sell = Number(form.price) || 0
  const orig = Number(form.compare_at_price) || 0
  const origInvalid = orig > 0 && orig <= sell
  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <label style={labelStyle}>Preço de venda (Kz) *</label>
        <input
          type="number" inputMode="decimal" min="1"
          value={form.price}
          onChange={e => setForm(f => ({ ...f, price: e.target.value }))}
          placeholder="0"
          style={inputStyle}
        />
      </div>
      <div>
        <label style={labelStyle}>Preço original (opcional)</label>
        <input
          type="number" inputMode="decimal" min="0"
          value={form.compare_at_price}
          onChange={e => setForm(f => ({ ...f, compare_at_price: e.target.value }))}
          placeholder="Preço antes do desconto"
          style={{ ...inputStyle, borderColor: origInvalid ? '#ef4444' : '#2A2A2A' }}
        />
        {origInvalid && (
          <p style={{ ...S, fontSize: 11, color: '#ef4444', marginTop: 6 }}>
            Preço original deve ser maior que o de venda para mostrar como desconto.
          </p>
        )}
      </div>
      <div>
        <label style={labelStyle}>Quantidade em stock *</label>
        <input
          type="number" inputMode="numeric" min="0"
          value={form.quantity}
          onChange={e => setForm(f => ({ ...f, quantity: e.target.value }))}
          placeholder="1"
          style={inputStyle}
        />
        {Number(form.quantity) === 0 && (
          <p style={{ ...S, fontSize: 11, color: '#f59e0b', marginTop: 6 }}>
            ⚠ Com stock 0 o produto não será visível para compradores.
          </p>
        )}
      </div>
      <div>
        <label style={labelStyle}>Código SKU (opcional)</label>
        <input
          maxLength={50}
          value={form.sku}
          onChange={e => setForm(f => ({ ...f, sku: e.target.value }))}
          placeholder="Auto-gerado se ficar vazio"
          style={inputStyle}
        />
      </div>

      {/* §12.3 — Promotional pricing (flash sale window) */}
      <div style={{ marginTop: 6 }}>
        <button type="button"
          onClick={() => setForm(f => ({ ...f, _promo_open: !f._promo_open }))}
          style={{ width: '100%', background: 'transparent', border: '1px dashed #2A2A2A', borderRadius: 10, padding: 11, ...S, fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>
          {form._promo_open ? '− Fechar promoção' : '+ Adicionar promoção'}
        </button>
        {form._promo_open && (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <label style={labelStyle}>Preço promocional (Kz)</label>
              <input type="number" min="0" value={form.promo_price}
                onChange={e => setForm(f => ({ ...f, promo_price: e.target.value }))}
                placeholder="≤ preço de venda" style={inputStyle} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div>
                <label style={labelStyle}>Início</label>
                <input type="datetime-local" value={form.promo_start}
                  onChange={e => setForm(f => ({ ...f, promo_start: e.target.value }))}
                  style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>Fim</label>
                <input type="datetime-local" value={form.promo_end}
                  onChange={e => setForm(f => ({ ...f, promo_end: e.target.value }))}
                  style={{ ...inputStyle, borderColor: form.promo_end && form.promo_start && form.promo_end <= form.promo_start ? '#ef4444' : '#2A2A2A' }} />
              </div>
            </div>
            {form.promo_end && form.promo_start && form.promo_end <= form.promo_start && (
              <p style={{ ...S, fontSize: 11, color: '#ef4444' }}>Fim deve ser após o início.</p>
            )}
            <div>
              <label style={labelStyle}>Máximo unidades em promoção</label>
              <input type="number" min="0" value={form.promo_max_units}
                onChange={e => setForm(f => ({ ...f, promo_max_units: e.target.value }))}
                placeholder="Sem limite se vazio" style={inputStyle} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 5 — VARIANTS  (§13)  — full rich UI with colour swatches +
// editable SKU grid + bulk actions
// ════════════════════════════════════════════════════════════════════
function VariantsStep({ form, setForm }) {
  const enabled = form.has_variants
  const variants = form.variants || []
  const sizeChartRef = useRef()

  // Each variant row shape now:
  //   { type: 'colour'|'size'|'material'|'style'|'custom',
  //     name: string,         // user-visible label (esp. for custom)
  //     values: [{ label, hex?, swatch_file? }] }
  const upd = (i, patch) => setForm(f => ({
    ...f, variants: f.variants.map((v, j) => j === i ? { ...v, ...patch } : v),
  }))
  const addRow = () => setForm(f => ({
    ...f, variants: [...(f.variants || []), { type: 'colour', name: 'Cor', values: [] }],
  }))
  const removeRow = (i) => setForm(f => ({
    ...f, variants: f.variants.filter((_, j) => j !== i),
  }))
  const addValue = (i) => {
    upd(i, { values: [...(variants[i].values || []), { label: '', hex: '#000000' }] })
  }
  const updValue = (i, j, patch) => {
    upd(i, { values: variants[i].values.map((v, k) => k === j ? { ...v, ...patch } : v) })
  }
  const removeValue = (i, j) => {
    upd(i, { values: variants[i].values.filter((_, k) => k !== j) })
  }

  // ── Cartesian SKU grid §13.4 ────────────────────────────────────
  const groups = useMemo(() => variants
    .filter(v => (v.name || '').trim() && (v.values || []).length)
    .map(v => ({ name: v.name.trim(), values: v.values.map(x => x.label || '').filter(Boolean) }))
    .filter(g => g.values.length)
  , [variants])

  const combos = useMemo(() => {
    if (!groups.length) return []
    let acc = [[]]
    for (const g of groups) {
      const next = []
      for (const c of acc) for (const val of g.values) next.push([...c, { type: g.name, value: val }])
      acc = next
    }
    return acc.slice(0, 60)
  }, [groups])

  // SKU overrides keyed by stable "Vermelho|S" composite.
  const keyFor = (combo) => combo.map(x => x.value).join('|')
  const skuMap = form.sku_grid || {}
  const setSkuCell = (combo, patch) => setForm(f => ({
    ...f,
    sku_grid: { ...(f.sku_grid || {}), [keyFor(combo)]: { ...(f.sku_grid?.[keyFor(combo)] || {}), ...patch } },
  }))

  // §13.5 Bulk actions
  const fillAll = (field, value) => {
    const next = { ...(form.sku_grid || {}) }
    for (const c of combos) {
      const k = keyFor(c)
      next[k] = { ...(next[k] || {}), [field]: value }
    }
    setForm(f => ({ ...f, sku_grid: next }))
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <p style={{ ...S, fontSize: 14, color: '#FFFFFF', fontWeight: 600 }}>Tem variantes?</p>
          <p style={{ ...S, fontSize: 12, color: '#9A9A9A', marginTop: 2 }}>Ex: cor, tamanho, material</p>
        </div>
        <button onClick={() => setForm(f => ({ ...f, has_variants: !f.has_variants, variants: f.variants || [], sku_grid: f.sku_grid || {} }))}
          style={{ width: 44, height: 24, borderRadius: 12, border: 'none',
            background: enabled ? '#C9A84C' : '#2A2A2A', position: 'relative', cursor: 'pointer' }}>
          <div style={{ position: 'absolute', top: 2, left: enabled ? 22 : 2, width: 20, height: 20, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s' }} />
        </button>
      </div>

      {enabled && (
        <>
          {variants.map((row, i) => (
            <div key={i} style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <select value={row.type}
                  onChange={e => {
                    const t = e.target.value
                    const defaults = { colour: 'Cor', size: 'Tamanho', material: 'Material', style: 'Estilo', custom: row.name || '' }
                    upd(i, { type: t, name: defaults[t] })
                  }}
                  style={{ ...inputStyle, width: 'auto', padding: '8px 10px', fontSize: 12 }}>
                  <option value="colour">Cor</option>
                  <option value="size">Tamanho</option>
                  <option value="material">Material</option>
                  <option value="style">Estilo</option>
                  <option value="custom">Personalizado</option>
                </select>
                <button onClick={() => removeRow(i)} style={{ background: 'none', border: 'none', color: '#ef4444', ...S, fontSize: 12, cursor: 'pointer' }}>Remover</button>
              </div>
              {row.type === 'custom' && (
                <input placeholder="Nome da variante" value={row.name} onChange={e => upd(i, { name: e.target.value })} style={{ ...inputStyle, marginBottom: 8, fontSize: 12 }} />
              )}

              {/* Values */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {(row.values || []).map((v, j) => (
                  <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {row.type === 'colour' && (
                      <input type="color" value={v.hex || '#000000'} onChange={e => updValue(i, j, { hex: e.target.value })}
                        style={{ width: 36, height: 32, border: '1px solid #2A2A2A', borderRadius: 8, background: 'transparent', cursor: 'pointer' }} />
                    )}
                    <input placeholder={row.type === 'colour' ? 'Vermelho' : row.type === 'size' ? 'M' : 'Valor'}
                      value={v.label} onChange={e => updValue(i, j, { label: e.target.value })}
                      style={{ ...inputStyle, flex: 1, padding: '8px 10px', fontSize: 12 }} />
                    <button onClick={() => removeValue(i, j)} style={{ width: 28, height: 28, borderRadius: 8, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 12, color: '#9A9A9A', cursor: 'pointer' }}>✕</button>
                  </div>
                ))}
                <button onClick={() => addValue(i)}
                  style={{ alignSelf: 'flex-start', padding: '6px 14px', borderRadius: 16, border: '1px dashed #C9A84C', background: 'transparent', ...S, fontSize: 11, color: '#C9A84C', cursor: 'pointer' }}>
                  + Valor
                </button>
              </div>

              {/* §13.3 size chart upload for Size variants */}
              {row.type === 'size' && (
                <div style={{ marginTop: 10 }}>
                  <button onClick={() => sizeChartRef.current?.click()} style={{ width: '100%', padding: 10, borderRadius: 10, background: '#0F0F0F', border: '1px dashed #2A2A2A', ...S, fontSize: 12, color: '#9A9A9A', cursor: 'pointer' }}>
                    {form.size_chart_file ? `Tabela: ${form.size_chart_file.name}` : '+ Tabela de tamanhos (opcional)'}
                  </button>
                  <input ref={sizeChartRef} type="file" accept="image/*" style={{ display: 'none' }}
                    onChange={e => setForm(f => ({ ...f, size_chart_file: e.target.files?.[0] || null }))} />
                </div>
              )}
            </div>
          ))}
          <button onClick={addRow}
            style={{ padding: '12px 0', background: 'transparent', border: '1.5px dashed #C9A84C', borderRadius: 12, ...S, fontSize: 13, color: '#C9A84C', cursor: 'pointer' }}>
            + Adicionar tipo de variante
          </button>

          {/* §13.4 SKU grid + §13.5 bulk actions */}
          {combos.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {combos.length} SKU(s)
                </p>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => {
                    const v = prompt('Aplicar preço a todos os SKUs:')
                    if (v) fillAll('price', v)
                  }} style={{ padding: '4px 10px', borderRadius: 8, background: '#1E1E1E', border: 'none', ...S, fontSize: 10, color: '#C9A84C', cursor: 'pointer' }}>Preço a todos</button>
                  <button onClick={() => {
                    const v = prompt('Aplicar stock a todos os SKUs:')
                    if (v) fillAll('quantity', v)
                  }} style={{ padding: '4px 10px', borderRadius: 8, background: '#1E1E1E', border: 'none', ...S, fontSize: 10, color: '#C9A84C', cursor: 'pointer' }}>Stock a todos</button>
                </div>
              </div>
              <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, padding: 8, maxHeight: 260, overflowY: 'auto' }}>
                {combos.map((c, idx) => {
                  const k = keyFor(c)
                  const cell = skuMap[k] || {}
                  return (
                    <div key={k} style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.9fr 0.6fr 30px', gap: 6, alignItems: 'center', padding: '6px 0', borderBottom: idx < combos.length - 1 ? '1px solid #1E1E1E' : 'none' }}>
                      <span style={{ ...S, fontSize: 11, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.map(x => x.value).join(' · ')}</span>
                      <input placeholder={form.price || 'Preço'} value={cell.price || ''}
                        onChange={e => setSkuCell(c, { price: e.target.value })}
                        style={{ ...inputStyle, padding: '6px 8px', fontSize: 11 }} />
                      <input placeholder={form.quantity || '0'} value={cell.quantity || ''}
                        onChange={e => setSkuCell(c, { quantity: e.target.value })}
                        style={{ ...inputStyle, padding: '6px 8px', fontSize: 11 }} />
                      <button onClick={() => setSkuCell(c, { disabled: !cell.disabled })}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: cell.disabled ? '#ef4444' : '#10b981', ...S, fontSize: 14 }}>
                        {cell.disabled ? '✕' : '✓'}
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 6 — SHIPPING  (§14)  — template picker + per-product overrides
// ════════════════════════════════════════════════════════════════════
function ShippingStep({ form, setForm }) {
  const navigate = useNavigate()
  const [templates, setTemplates] = useState([])
  useEffect(() => {
    client.get('/api/v1/shipping/templates/')
      .then(r => setTemplates(r.data?.results || r.data || []))
      .catch(() => setTemplates([]))
  }, [])
  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* §14.1 template picker */}
      <div>
        <label style={labelStyle}>Template de envio</label>
        <div style={{ display: 'flex', gap: 6 }}>
          <select value={form.shipping_template || ''}
            onChange={e => setForm(f => ({ ...f, shipping_template: e.target.value || null }))}
            style={{ ...inputStyle, flex: 1 }}>
            <option value="">— Personalizado (sem template) —</option>
            {templates.map(t => (
              <option key={t.id} value={t.id}>{t.name}{t.is_default ? ' · padrão' : ''}</option>
            ))}
          </select>
          <button type="button" onClick={() => navigate('/seller/shipping')}
            style={{ padding: '0 14px', borderRadius: 12, border: '1px solid #2A2A2A', background: '#1E1E1E', ...S, fontSize: 12, color: '#C9A84C', cursor: 'pointer' }}>
            Gerir
          </button>
        </div>
        {form.shipping_template && (
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 6 }}>
            Usar este template significa que os campos abaixo são ignorados — as regras vêm do template.
          </p>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#141414', border: '1px solid #1E1E1E', borderRadius: 12, padding: '14px 16px' }}>
        <div>
          <p style={{ ...S, fontSize: 14, color: '#FFFFFF', fontWeight: 600 }}>Envio grátis</p>
          <p style={{ ...S, fontSize: 11, color: '#9A9A9A', marginTop: 2 }}>Você suporta o custo</p>
        </div>
        <button onClick={() => setForm(f => ({ ...f, free_shipping: !f.free_shipping }))}
          style={{ width: 44, height: 24, borderRadius: 12, border: 'none',
            background: form.free_shipping ? '#10b981' : '#2A2A2A', position: 'relative', cursor: 'pointer' }}>
          <div style={{ position: 'absolute', top: 2, left: form.free_shipping ? 22 : 2, width: 20, height: 20, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s' }} />
        </button>
      </div>

      {!form.free_shipping && (
        <div>
          <label style={labelStyle}>Custo de envio (Kz)</label>
          <input type="number" inputMode="decimal" min="0"
            value={form.shipping_cost}
            onChange={e => setForm(f => ({ ...f, shipping_cost: e.target.value }))}
            placeholder="0" style={inputStyle} />
        </div>
      )}

      <div>
        <label style={labelStyle}>Tempo de processamento</label>
        <select value={form.processing_days}
          onChange={e => setForm(f => ({ ...f, processing_days: e.target.value }))}
          style={inputStyle}>
          {[1, 2, 3, 5, 7, 14].map(d => (
            <option key={d} value={d}>{d} dia(s) úteis</option>
          ))}
        </select>
      </div>

      <div>
        <label style={labelStyle}>Peso do pacote (kg)</label>
        <input type="number" inputMode="decimal" min="0" step="0.001"
          value={form.weight_kg}
          onChange={e => setForm(f => ({ ...f, weight_kg: e.target.value }))}
          placeholder="0.500" style={inputStyle} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        {[
          { f: 'length_cm', l: 'Comp. (cm)' },
          { f: 'width_cm',  l: 'Larg. (cm)' },
          { f: 'height_cm', l: 'Alt. (cm)' },
        ].map(d => (
          <div key={d.f}>
            <label style={labelStyle}>{d.l}</label>
            <input type="number" inputMode="decimal" min="0"
              value={form[d.f]}
              onChange={e => setForm(f => ({ ...f, [d.f]: e.target.value }))}
              placeholder="0" style={inputStyle} />
          </div>
        ))}
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 7 — ATTRIBUTES  (§15)  — fully dynamic from category schema
// ════════════════════════════════════════════════════════════════════
function AttributesStep({ form, setForm }) {
  const [schema, setSchema] = useState(null)  // null = unknown, [] = none
  const [loadingSchema, setLoadingSchema] = useState(false)

  useEffect(() => {
    if (!form.category) { setSchema([]); return }
    setLoadingSchema(true)
    client.get(`/api/v1/products/categories/${form.category}/`)
      .then(r => setSchema(r.data?.attribute_schema || []))
      .catch(() => setSchema([]))
      .finally(() => setLoadingSchema(false))
  }, [form.category])

  const setAttr = (key, value) => setForm(f => ({ ...f, attributes: { ...(f.attributes || {}), [key]: value } }))
  const get = (key) => form.attributes?.[key]

  const renderField = (a) => {
    const v = get(a.key)
    switch (a.type) {
      case 'select':
        return (
          <select value={v || ''} onChange={e => setAttr(a.key, e.target.value)} style={inputStyle}>
            <option value="">— Seleccione —</option>
            {(a.options || []).map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        )
      case 'multiselect': {
        const cur = Array.isArray(v) ? v : []
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {(a.options || []).map(o => {
              const on = cur.includes(o)
              return (
                <button key={o} type="button" onClick={() => setAttr(a.key, on ? cur.filter(x => x !== o) : [...cur, o])}
                  style={{ padding: '7px 14px', borderRadius: 18, border: `1.5px solid ${on ? '#C9A84C' : '#2A2A2A'}`, background: on ? 'rgba(201,168,76,0.1)' : 'transparent', ...S, fontSize: 12, color: on ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                  {o}
                </button>
              )
            })}
          </div>
        )
      }
      case 'number':
        return (
          <div style={{ display: 'flex', gap: 6 }}>
            <input type="number" inputMode="decimal" value={v || ''}
              onChange={e => setAttr(a.key, e.target.value)} style={{ ...inputStyle, flex: 1 }} />
            {a.unit && <span style={{ ...S, fontSize: 12, color: '#9A9A9A', alignSelf: 'center' }}>{a.unit}</span>}
          </div>
        )
      default:
        return <input value={v || ''} onChange={e => setAttr(a.key, e.target.value)} style={inputStyle} />
    }
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h2 style={{ ...S, fontSize: 17, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>Atributos do produto</h2>
        <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>
          {schema && schema.length > 0
            ? 'Específicos da categoria. Quanto mais preencher, melhor a descoberta.'
            : 'Nenhum atributo específico para esta categoria — preencha tags abaixo.'}
        </p>
      </div>
      {loadingSchema && <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>A carregar atributos…</p>}
      {schema && schema.map(a => (
        <div key={a.key}>
          <label style={labelStyle}>
            {a.label}{a.required ? ' *' : ''}
          </label>
          {renderField(a)}
        </div>
      ))}
      <div>
        <label style={labelStyle}>Tags (separadas por vírgula)</label>
        <input value={form.tags}
          onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
          placeholder="ex: capulana, vestido, africano" style={inputStyle} />
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// STEP 8 — REVIEW & PUBLISH  (§16)
// ════════════════════════════════════════════════════════════════════
function ReviewStep({ form, images, completed, total, onJump }) {
  const sections = [
    { idx: 1, label: 'Categoria',        value: form.category_path?.map(c => c.name).join(' › ') || '—' },
    { idx: 2, label: 'Título',           value: form.title || '—' },
    { idx: 3, label: 'Imagens',          value: `${images.length} foto(s)` },
    { idx: 4, label: 'Preço',            value: form.price ? `${Number(form.price).toLocaleString('pt-AO')} Kz` : '—' },
    { idx: 4, label: 'Stock',            value: form.quantity || '0' },
    { idx: 5, label: 'Variantes',        value: form.has_variants ? `${(form.variants || []).filter(v => v.name && v.values).length} tipo(s)` : 'Nenhuma' },
    { idx: 6, label: 'Envio',            value: form.free_shipping ? 'Grátis' : `${form.shipping_cost || 0} Kz` },
    { idx: 6, label: 'Processamento',    value: `${form.processing_days} dias` },
  ]
  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <h2 style={{ ...S, fontSize: 17, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>Rever e publicar</h2>
        <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>Confirme os detalhes antes de publicar a sua listagem.</p>
      </div>

      <div style={{ background: '#141414', border: '1px solid #1E1E1E', borderRadius: 14, padding: 14 }}>
        {sections.map((s, i) => (
          <div key={i} onClick={() => onJump(s.idx)} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 0',
            borderBottom: i < sections.length - 1 ? '1px solid #1E1E1E' : 'none',
            cursor: 'pointer',
          }}>
            <span style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>{s.label}</span>
            <span style={{ ...S, fontSize: 13, color: '#FFFFFF', maxWidth: '60%', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {s.value}
            </span>
          </div>
        ))}
      </div>

      {/* Section completion grid */}
      <div>
        <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Estado das secções</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
          {Array.from({ length: total }).map((_, i) => {
            const idx = i + 1
            const done = completed.has(idx)
            return (
              <div key={idx} onClick={() => onJump(idx)} style={{
                padding: '8px 4px', borderRadius: 8, textAlign: 'center', cursor: 'pointer',
                background: done ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
                border: `1px solid ${done ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`,
              }}>
                <div style={{ ...S, fontSize: 10, color: done ? '#10b981' : '#f59e0b', fontWeight: 700 }}>
                  {done ? '✓' : '!'} {idx}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}


// ════════════════════════════════════════════════════════════════════
// MAIN WIZARD
// ════════════════════════════════════════════════════════════════════
// Initial blank form, hoisted out so the draft-restore hook can
// merge over it without needing to inline the literal twice.
const DEFAULT_FORM = {
  category: null, category_path: null,
  title: '', description: '', brand: '', condition: 'new',
  price: '', compare_at_price: '', quantity: '1', sku: '',
  has_variants: false, variants: [],
  free_shipping: true, shipping_cost: '', processing_days: '2',
  weight_kg: '', length_cm: '', width_cm: '', height_cm: '',
  attributes: {}, tags: '',
}

export default function SellerProductNewPage() {
  const navigate = useNavigate()
  const TOTAL_STEPS = 8
  const [step, setStep] = useState(1)
  const [images, setImages] = useState([])
  const [video, setVideo] = useState(null)
  const [toast, setToast] = useState(null)
  const [publishing, setPublishing] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [dupModal, setDupModal] = useState(null)  // §18 duplicate detection
  const DRAFT_KEY = 'micha:product-draft-v1'
  const [form, setForm] = useState(() => {
    // §19.4 auto-save — recover an in-flight wizard if the seller
    // closes the app, switches network, or session expires. Drafts
    // are LOCAL only (sessionStorage); we deliberately don't ship
    // them to a server Draft model so this stays a single-turn
    // additive change. Trade-off: cross-device drafts are out.
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') return { ...DEFAULT_FORM, ...parsed }
      }
    } catch {}
    return DEFAULT_FORM
  })
  const [lastSavedAt, setLastSavedAt] = useState(null)

  useEffect(() => {
    // Persist on every form change, but trailing-debounce 800ms so
    // typing on the title doesn't slam sessionStorage every char.
    const t = setTimeout(() => {
      try {
        sessionStorage.setItem(DRAFT_KEY, JSON.stringify(form))
        setLastSavedAt(new Date())
      } catch {}
    }, 800)
    return () => clearTimeout(t)
  }, [form])

  // §19.3 — register the wizard as "has unsaved changes" so the
  // SessionGuard beforeunload hook prompts before close/reload.
  useEffect(() => {
    const dirty = Boolean(form.title || form.description || form.price)
    window.__michaUnsaved = dirty
    return () => { window.__michaUnsaved = false }
  }, [form])

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  // Per-step completion — informs the §16 review checklist.
  const completed = useMemo(() => {
    const s = new Set()
    if (form.category) s.add(1)
    if (form.title.trim().length >= 10 && form.description.trim().length >= 50) s.add(2)
    if (images.length >= 1) s.add(3)
    if (Number(form.price) > 0 && Number(form.quantity) >= 0) s.add(4)
    s.add(5)  // variants is always considered complete (optional toggle)
    if (form.processing_days) s.add(6)
    s.add(7)  // attributes are all optional
    return s
  }, [form, images])

  const canNext = (() => {
    switch (step) {
      case 1: return Boolean(form.category)
      case 2: return form.title.trim().length >= 10 && form.description.trim().length >= 50
      case 3: return images.length >= 1
      case 4: {
        const p = Number(form.price), q = Number(form.quantity)
        if (!(p > 0)) return false
        if (form.compare_at_price && Number(form.compare_at_price) <= p) return false
        if (isNaN(q) || q < 0) return false
        return true
      }
      case 5: return true
      case 6: return Boolean(form.processing_days)
      case 7: return true
      default: return true
    }
  })()

  const buildFormData = (forceCreate = false) => {
    const fd = new FormData()
    fd.append('title', form.title.trim())
    fd.append('description', form.description.trim())
    if (form.brand) fd.append('brand', form.brand.trim())
    fd.append('condition', form.condition)
    fd.append('price', form.price)
    if (form.compare_at_price) fd.append('compare_at_price', form.compare_at_price)
    fd.append('quantity', form.quantity || '0')
    if (form.sku) fd.append('sku', form.sku.trim())
    if (form.category) fd.append('category', String(form.category))
    if (form.weight_kg) fd.append('weight_kg', form.weight_kg)
    if (form.length_cm) fd.append('length_cm', form.length_cm)
    if (form.width_cm) fd.append('width_cm', form.width_cm)
    if (form.height_cm) fd.append('height_cm', form.height_cm)
    if (form.tags) fd.append('tags', form.tags.trim())
    if (form.shipping_template) fd.append('shipping_template', String(form.shipping_template))
    if (form.attributes && Object.keys(form.attributes).length) {
      fd.append('attributes', JSON.stringify(form.attributes))
    }
    // §12.3 promotional pricing
    if (form.promo_price) fd.append('promo_price', form.promo_price)
    if (form.promo_start) fd.append('promo_start', form.promo_start)
    if (form.promo_end) fd.append('promo_end', form.promo_end)
    if (form.promo_max_units) fd.append('promo_max_units', form.promo_max_units)
    // §13 variant combos with SKU grid overrides
    if (form.has_variants) {
      const groups = (form.variants || [])
        .filter(v => (v.name || '').trim() && (v.values || []).length)
        .map(v => ({ name: v.name.trim(), values: v.values.map(x => x.label || '').filter(Boolean) }))
      const combos = []
      const build = (i, acc) => {
        if (i === groups.length) {
          const k = Object.values(acc).join('|')
          const ovr = form.sku_grid?.[k] || {}
          if (ovr.disabled) return
          combos.push({
            options: { ...acc },
            price: Number(ovr.price || form.price),
            quantity: Number(ovr.quantity || form.quantity) || 0,
            sku: ovr.sku || '',
          })
          return
        }
        for (const v of groups[i].values) build(i + 1, { ...acc, [groups[i].name]: v })
      }
      if (groups.length) { build(0, {}); fd.append('variant_combos', JSON.stringify(combos)) }
    }
    if (forceCreate) fd.append('force_create', 'true')
    return fd
  }

  const handlePublish = async (forceCreate = false) => {
    if (completed.size < TOTAL_STEPS) {
      const missing = []
      for (let i = 1; i <= TOTAL_STEPS; i++) if (!completed.has(i)) missing.push(i)
      showToast(`Complete as secções: ${missing.join(', ')}`, 'error')
      return
    }
    setPublishing(true)
    try {
      // §16.4 — submit to backend
      const fd = buildFormData(forceCreate)
      const res = await client.post('/api/v1/products/create/', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const id = res.data?.id

      // Upload images in sequence (§11).
      let imgFail = 0
      for (const img of images) {
        const imgFd = new FormData()
        imgFd.append('image', img.file, img.file.name)
        try {
          await client.post(`/api/v1/products/${id}/images/`, imgFd, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        } catch { imgFail++ }
      }
      if (imgFail > 0) showToast(`Publicado, mas ${imgFail} imagem(ns) falhou.`, 'error')
      else showToast('Produto publicado!')
      // §19 — drop the draft once it's safely on the server.
      try { sessionStorage.removeItem(DRAFT_KEY) } catch {}
      setTimeout(() => navigate('/seller/products'), 900)
    } catch (err) {
      const data = err.response?.data
      // §18 — duplicate product detected. Open a modal letting the
      // seller pick "edit existing" or "create anyway".
      if (err.response?.status === 409 && data?.error === 'duplicate_product') {
        setDupModal({ id: data.existing_id, title: data.existing_title })
        return
      }
      let msg = 'Erro ao publicar. Tente novamente.'
      if (data?.detail) msg = data.detail
      else if (data && typeof data === 'object') {
        const skip = new Set(['request_id', 'trace_id', 'code', 'status'])
        for (const [k, v] of Object.entries(data)) {
          if (skip.has(k)) continue
          const val = Array.isArray(v) ? v[0] : v
          if (typeof val === 'string' && val.trim()) { msg = `${k}: ${val}`; break }
        }
      }
      showToast(msg, 'error')
    } finally {
      setPublishing(false)
    }
  }

  const stepEl = (() => {
    switch (step) {
      case 1: return <CategoryStep form={form} setForm={setForm} onNext={() => setStep(2)} />
      case 2: return <TitleStep form={form} setForm={setForm} />
      case 3: return <ImagesStep images={images} setImages={setImages} video={video} setVideo={setVideo} showToast={showToast} />
      case 4: return <PricingStep form={form} setForm={setForm} />
      case 5: return <VariantsStep form={form} setForm={setForm} />
      case 6: return <ShippingStep form={form} setForm={setForm} />
      case 7: return <AttributesStep form={form} setForm={setForm} />
      case 8: return <ReviewStep form={form} images={images} completed={completed} total={TOTAL_STEPS} onJump={setStep} />
      default: return null
    }
  })()

  return (
    <SellerLayout title="Novo produto" showBack>
      {toast && (
        <div style={{
          position: 'fixed', top: 70, left: '50%', transform: 'translateX(-50%)',
          zIndex: 999,
          background: toast.type === 'error' ? '#dc2626' : '#10b981',
          color: '#FFFFFF', padding: '10px 18px', borderRadius: 14,
          ...S, fontSize: 13, fontWeight: 600,
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>{toast.msg}</div>
      )}

      <StepDots total={TOTAL_STEPS} current={step} completed={completed} />

      {/* §16.2 Preview button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '6px 16px 0', flexShrink: 0 }}>
        <button onClick={() => setPreviewOpen(true)} disabled={!form.title || images.length === 0}
          style={{ background: 'transparent', border: '1px solid #2A2A2A', borderRadius: 18, padding: '5px 12px', ...S, fontSize: 11, color: '#C9A84C', cursor: 'pointer', opacity: !form.title || images.length === 0 ? 0.4 : 1 }}>
          👁 Pré-visualizar
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {stepEl}
        {/* §19 auto-save footnote — barely-there confirmation that
           the draft survives a tab close. Tap to wipe the draft. */}
        {lastSavedAt && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px 16px' }}>
            <span style={{ ...S, fontSize: 10, color: '#555' }}>
              ↺ Guardado às {lastSavedAt.toLocaleTimeString('pt-AO', { hour: '2-digit', minute: '2-digit' })}
            </span>
            <button onClick={() => {
              try { sessionStorage.removeItem(DRAFT_KEY) } catch {}
              setForm(DEFAULT_FORM)
              setImages([]); setVideo(null); setStep(1)
              showToast('Rascunho limpo.')
            }} style={{ background: 'none', border: 'none', cursor: 'pointer', ...S, fontSize: 10, color: '#9A9A9A' }}>
              Limpar rascunho
            </button>
          </div>
        )}
      </div>

      {/* Sticky CTA */}
      <div style={{
        padding: '12px 16px',
        paddingBottom: 'max(20px, env(safe-area-inset-bottom))',
        borderTop: '1px solid #1A1A1A', background: '#0F0F0F',
        display: 'flex', gap: 10, flexShrink: 0,
      }}>
        {step > 1 && (
          <button onClick={() => setStep(s => s - 1)}
            style={{ flex: 1, padding: '14px 0', borderRadius: 12, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 14, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer' }}>
            Voltar
          </button>
        )}
        {/* §18 — Duplicate detection modal */}
        {dupModal && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
            <div style={{ background: '#141414', border: '1px solid #2A2A2A', borderRadius: 16, padding: 20, maxWidth: 360, width: '100%' }}>
              <p style={{ ...S, fontSize: 16, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>Produto duplicado?</p>
              <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.55, marginBottom: 16 }}>
                Já tem um produto com o título <strong style={{ color: '#FFFFFF' }}>"{dupModal.title}"</strong>. Quer editar o existente ou criar mesmo assim?
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <button onClick={() => { navigate(`/seller/products/${dupModal.id}/edit`); setDupModal(null) }}
                  style={{ padding: '12px 0', borderRadius: 10, border: 'none', background: '#C9A84C', ...S, fontSize: 13, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>
                  Editar o existente
                </button>
                <button onClick={() => { setDupModal(null); handlePublish(true) }}
                  style={{ padding: '12px 0', borderRadius: 10, border: '1px solid #2A2A2A', background: 'transparent', ...S, fontSize: 13, color: '#FFFFFF', cursor: 'pointer' }}>
                  Criar mesmo assim
                </button>
                <button onClick={() => setDupModal(null)}
                  style={{ padding: '10px 0', border: 'none', background: 'transparent', ...S, fontSize: 12, color: '#9A9A9A', cursor: 'pointer' }}>
                  Cancelar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* §16.2 Preview overlay — buyer-view simulation */}
        {previewOpen && (
          <div style={{ position: 'fixed', inset: 0, background: '#0A0A0A', zIndex: 1000, display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '14px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #1A1A1A' }}>
              <span style={{ ...S, fontSize: 13, color: '#9A9A9A' }}>Pré-visualização</span>
              <button onClick={() => setPreviewOpen(false)}
                style={{ background: '#C9A84C', border: 'none', borderRadius: 10, padding: '6px 14px', ...S, fontSize: 12, fontWeight: 700, color: '#0A0A0A', cursor: 'pointer' }}>Fechar</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <div style={{ height: 280, background: '#1E1E1E' }}>
                {images[0] && <img src={images[0].url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
              </div>
              <div style={{ padding: 18 }}>
                <p style={{ ...S, fontSize: 22, fontWeight: 700, color: '#C9A84C', marginBottom: 4 }}>
                  {form.price ? `${Number(form.price).toLocaleString('pt-AO')} Kz` : '—'}
                </p>
                {form.compare_at_price && (
                  <p style={{ ...S, fontSize: 13, color: '#9A9A9A', textDecoration: 'line-through' }}>
                    {Number(form.compare_at_price).toLocaleString('pt-AO')} Kz
                  </p>
                )}
                <h1 style={{ ...S, fontSize: 18, fontWeight: 600, color: '#FFFFFF', marginTop: 12, marginBottom: 8 }}>{form.title || 'Título do produto'}</h1>
                {form.brand && <p style={{ ...S, fontSize: 12, color: '#9A9A9A' }}>Marca: {form.brand}</p>}
                <div style={{ marginTop: 16, padding: '14px 0', borderTop: '1px solid #1E1E1E' }}>
                  <p style={{ ...S, fontSize: 11, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Descrição</p>
                  <p style={{ ...S, fontSize: 13, color: '#BFBFBF', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{form.description || 'Sem descrição.'}</p>
                </div>
                {images.length > 1 && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginTop: 14 }}>
                    {images.slice(0, 8).map((img, i) => (
                      <div key={i} style={{ aspectRatio: '1', borderRadius: 8, overflow: 'hidden', background: '#1E1E1E' }}>
                        <img src={img.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {step < TOTAL_STEPS ? (
          <button disabled={!canNext} onClick={() => setStep(s => s + 1)}
            style={{ flex: 2, padding: '14px 0', borderRadius: 12, border: 'none', background: canNext ? '#C9A84C' : '#2A2A2A', ...S, fontSize: 14, fontWeight: 700, color: canNext ? '#0A0A0A' : '#555', cursor: canNext ? 'pointer' : 'not-allowed' }}>
            Continuar →
          </button>
        ) : (
          <button disabled={publishing || completed.size < TOTAL_STEPS} onClick={handlePublish}
            style={{ flex: 2, padding: '14px 0', borderRadius: 12, border: 'none', background: publishing ? 'rgba(201,168,76,0.5)' : '#C9A84C', ...S, fontSize: 14, fontWeight: 700, color: '#0A0A0A', cursor: publishing ? 'wait' : 'pointer' }}>
            {publishing ? 'A publicar…' : '🚀 Publicar produto'}
          </button>
        )}
      </div>
    </SellerLayout>
  )
}
