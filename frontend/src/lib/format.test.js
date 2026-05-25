/**
 * format helpers — Tier 8 i18n.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import FMT, {
  formatCurrency, formatInteger, formatCompact,
  formatTimeAgo, formatPercent,
} from './format'


describe('formatCurrency', () => {
  it('appends Kz by default', () => {
    expect(formatCurrency(1000)).toMatch(/Kz$/)
  })
  it('supports compact', () => {
    expect(formatCurrency(1_500_000, { compact: true })).toBe('1.5M Kz')
    expect(formatCurrency(25_000, { compact: true })).toBe('25K Kz')
    expect(formatCurrency(500, { compact: true })).toMatch(/^500 Kz/)
  })
  it('suppresses suffix when withSuffix=false', () => {
    expect(formatCurrency(1000, { withSuffix: false }))
      .not.toMatch(/Kz$/)
  })
  it('handles invalid input gracefully', () => {
    expect(formatCurrency('not-a-number')).toMatch(/^0/)
    expect(formatCurrency(null)).toMatch(/^0/)
  })
})


describe('formatInteger', () => {
  it('rounds + locale-formats', () => {
    expect(formatInteger(1234.5)).toBe('1235')
    expect(formatInteger(0)).toBe('0')
  })
})


describe('formatCompact', () => {
  it('handles billions/millions/thousands', () => {
    expect(formatCompact(2_500_000_000)).toBe('2.5B')
    expect(formatCompact(1_500_000)).toBe('1.5M')
    expect(formatCompact(25_000)).toBe('25K')
    expect(formatCompact(500)).toBe('500')
  })
})


describe('formatPercent', () => {
  it('uses percent style with 1 decimal default', () => {
    const out = formatPercent(0.235)
    expect(out).toMatch(/23,5|23\.5/)
    expect(out).toContain('%')
  })
})


describe('formatTimeAgo', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-05-28T12:00:00Z')) })
  afterEach(() => { vi.useRealTimers() })

  it('handles seconds / minutes / hours / days', () => {
    expect(formatTimeAgo(new Date('2026-05-28T12:00:00Z'))).toBe('agora')
    expect(formatTimeAgo(new Date('2026-05-28T11:59:30Z'))).toBe('30s atrás')
    expect(formatTimeAgo(new Date('2026-05-28T11:30:00Z'))).toBe('30min atrás')
    expect(formatTimeAgo(new Date('2026-05-28T08:00:00Z'))).toBe('4h atrás')
    expect(formatTimeAgo(new Date('2026-05-25T12:00:00Z'))).toBe('3d atrás')
    expect(formatTimeAgo(new Date('2026-05-14T12:00:00Z'))).toBe('2sem atrás')
  })

  it('handles invalid input', () => {
    expect(formatTimeAgo(null)).toBe('')
    expect(formatTimeAgo('not-a-date')).toBe('')
  })
})


describe('default export', () => {
  it('exposes all named exports', () => {
    expect(typeof FMT.currency).toBe('function')
    expect(typeof FMT.integer).toBe('function')
    expect(typeof FMT.timeAgo).toBe('function')
  })
})
