/**
 * ConfirmSheet — a confirm-with-note dialog primitive.
 *
 * Replaces the duplicated ad-hoc dialogs I inlined in
 * AdminChargebacksPage and AdminAMLPage, and the raw window.prompt()
 * usage in the moderator queue. One component, one focus-trap
 * implementation, one set of a11y attributes.
 *
 * Features
 * ────────
 *  • Full focus trap — Tab + Shift-Tab cycle inside the dialog
 *  • ESC dismisses (calls onCancel)
 *  • Restores focus to the previously-focused element on close
 *  • Optional radio-toggle for action choice (used by AML review)
 *  • Optional note textarea (used by everything)
 *  • Confirm button color configurable (red for destructive,
 *    green for positive, indigo for neutral)
 *  • Backdrop click does NOT dismiss (forces an explicit choice —
 *    accidental taps shouldn't undo a workflow step)
 *
 * Props
 * ─────
 *   open         show/hide
 *   title        dialog title
 *   noteLabel    label for the textarea
 *   notePlaceholder
 *   noteRequired default false
 *   actions      array of {id, label, color, isPrimary}
 *   onConfirm    (actionId, note) => void
 *   onCancel     () => void
 *   busy         disables confirm/cancel during async work
 */
import { useEffect, useRef, useState } from 'react'


const COLOR = {
  green:   { bg: '#22C55E', fg: 'white' },
  red:     { bg: '#EF4444', fg: 'white' },
  purple:  { bg: '#A855F7', fg: 'white' },
  indigo:  { bg: '#6366F1', fg: 'white' },
  neutral: { bg: 'transparent', fg: '#94A3B8', border: '1px solid #1A1A2E' },
}


export default function ConfirmSheet({
  open,
  title,
  noteLabel = 'Note (optional)',
  notePlaceholder = '',
  noteRequired = false,
  actions = [{ id: 'confirm', label: 'Confirm', color: 'indigo', isPrimary: true }],
  onConfirm,
  onCancel,
  busy = false,
  description,
  initialActionId,
}) {
  const [note, setNote] = useState('')
  const [activeAction, setActiveAction] = useState(
    initialActionId || actions.find((a) => a.isPrimary)?.id || actions[0]?.id,
  )
  const containerRef = useRef(null)
  const firstFocusableRef = useRef(null)
  const lastFocusableRef = useRef(null)
  const textareaRef = useRef(null)
  const previouslyFocused = useRef(null)

  // Reset state when dialog opens.
  useEffect(() => {
    if (open) {
      setNote('')
      setActiveAction(
        initialActionId || actions.find((a) => a.isPrimary)?.id || actions[0]?.id,
      )
    }
  }, [open, initialActionId, actions])

  // Focus management + ESC + focus trap.
  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement

    // Push focus into the textarea after mount.
    const focusTimer = setTimeout(() => {
      textareaRef.current?.focus()
    }, 50)

    const handleKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        if (!busy) onCancel?.()
        return
      }
      if (e.key !== 'Tab') return

      // Focus trap: Tab from the last element cycles to first,
      // Shift+Tab from the first cycles to last.
      const container = containerRef.current
      if (!container) return
      const focusables = container.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKey)
    return () => {
      clearTimeout(focusTimer)
      document.removeEventListener('keydown', handleKey)
      // Restore focus when dialog closes.
      try { previouslyFocused.current?.focus?.() } catch {}
    }
  }, [open, busy, onCancel])

  if (!open) return null

  const submit = () => {
    if (noteRequired && !note.trim()) {
      textareaRef.current?.focus()
      return
    }
    onConfirm?.(activeAction, note)
  }

  const confirmAction = actions.find((a) => a.id === activeAction)
  const confirmColor = COLOR[confirmAction?.color || 'indigo']

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirmsheet-title"
      style={styles.backdrop}
      // Don't dismiss on backdrop click — forces explicit choice.
    >
      <div ref={containerRef} style={styles.sheet}>
        <h2 id="confirmsheet-title" style={styles.title}>{title}</h2>

        {description && (
          <p style={styles.description}>{description}</p>
        )}

        {actions.length > 1 && (
          <fieldset style={styles.fieldset}>
            <legend className="sr-only">Action</legend>
            <div style={styles.radioRow}>
              {actions.map((a) => (
                <label key={a.id} style={styles.radioLabel}>
                  <input
                    ref={a.id === activeAction ? firstFocusableRef : null}
                    type="radio"
                    name="confirmsheet-action"
                    value={a.id}
                    checked={activeAction === a.id}
                    onChange={() => setActiveAction(a.id)}
                    disabled={busy}
                    style={styles.radio}
                  />
                  <span style={{ color: COLOR[a.color]?.bg || '#E2E8F0' }}>
                    {a.label}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        <label htmlFor="confirmsheet-note" style={styles.label}>
          {noteLabel}{noteRequired && ' *'}
        </label>
        <textarea
          ref={textareaRef}
          id="confirmsheet-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={notePlaceholder}
          rows={3}
          disabled={busy}
          style={styles.textarea}
        />

        <div style={styles.actionsRow}>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            style={styles.cancelButton}
          >
            Cancel
          </button>
          <button
            ref={lastFocusableRef}
            type="button"
            onClick={submit}
            disabled={busy || (noteRequired && !note.trim())}
            style={{
              ...styles.confirmButton,
              background: confirmColor.bg,
              color: confirmColor.fg,
              border: confirmColor.border || 'none',
              opacity: busy ? 0.6 : 1,
            }}
          >
            {busy ? 'A guardar…' : (confirmAction?.label || 'Confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}


const styles = {
  backdrop: {
    position: 'fixed', inset: 0, zIndex: 100,
    background: 'rgba(6,6,8,0.7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 16,
  },
  sheet: {
    background: '#111120',
    border: '1px solid #1A1A2E',
    borderRadius: 12, padding: 16,
    maxWidth: 500, width: '100%',
    boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
    maxHeight: '90vh', overflowY: 'auto',
  },
  title: {
    margin: 0, fontSize: 16, color: '#E2E8F0',
    marginBottom: 8,
  },
  description: {
    fontSize: 13, color: '#94A3B8', marginTop: 0, marginBottom: 12,
    lineHeight: 1.5,
  },
  fieldset: {
    border: 'none', padding: 0, margin: '0 0 12px 0',
  },
  radioRow: {
    display: 'flex', gap: 12, flexWrap: 'wrap',
  },
  radioLabel: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 13, cursor: 'pointer', color: '#E2E8F0',
    minHeight: 36,
  },
  radio: {
    width: 18, height: 18, accentColor: '#6366F1',
  },
  label: {
    display: 'block', fontSize: 12, color: '#94A3B8',
    marginBottom: 6,
  },
  textarea: {
    width: '100%', boxSizing: 'border-box',
    background: '#0D0D1A',
    border: '1px solid #1A1A2E',
    borderRadius: 6, color: '#E2E8F0',
    padding: 10, fontSize: 13, resize: 'vertical',
    minHeight: 60,
    fontFamily: 'inherit',
  },
  actionsRow: {
    display: 'flex', gap: 8, marginTop: 12,
    justifyContent: 'flex-end',
  },
  cancelButton: {
    background: 'transparent', color: '#94A3B8',
    border: '1px solid #1A1A2E',
    padding: '10px 18px', borderRadius: 6, fontSize: 13,
    cursor: 'pointer', minHeight: 40,
  },
  confirmButton: {
    padding: '10px 18px', borderRadius: 6, fontSize: 13,
    fontWeight: 600, cursor: 'pointer', minHeight: 40,
  },
}
