/**
 * events / flags — PII scrub contract.
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  default: { post: vi.fn(() => Promise.resolve()), get: vi.fn() },
}))

import { scrubProps } from './events'


describe('scrubProps', () => {
  it('drops PII keys', () => {
    const out = scrubProps({
      email: 'a@b.c',
      Password: 'secret',
      auth_token: 'eyJ...',
      nif: '123',
      bi: '456',
      pin: '7890',
      cvv: '111',
      credit_card: '4111-...',
      product_id: 42,
      quantity: 3,
    })
    expect(out).toEqual({ product_id: 42, quantity: 3 })
  })

  it('truncates long strings', () => {
    const long = 'x'.repeat(2000)
    const out = scrubProps({ note: long })
    expect(out.note.length).toBeLessThan(1100)
    expect(out.note.endsWith('…')).toBe(true)
  })

  it('returns {} for non-object input', () => {
    expect(scrubProps(null)).toEqual({})
    expect(scrubProps('foo')).toEqual({})
    expect(scrubProps(42)).toEqual({})
  })

  it('preserves non-PII keys', () => {
    expect(scrubProps({ session_id: 'abc', utm_source: 'fb' }))
      .toEqual({ session_id: 'abc', utm_source: 'fb' })
  })
})
