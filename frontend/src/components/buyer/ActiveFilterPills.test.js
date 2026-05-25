/**
 * ActiveFilterPills tests — pure helpers.
 */
import { describe, it, expect } from 'vitest'
import { chipsFromFilters, formatPrice } from './ActiveFilterPills'


describe('chipsFromFilters', () => {
  it('returns [] for null/empty', () => {
    expect(chipsFromFilters(null)).toEqual([])
    expect(chipsFromFilters({})).toEqual([])
  })

  it('produces a price chip for min-only / max-only / both', () => {
    expect(chipsFromFilters({ minPrice: 1000 })).toMatchObject([
      { key: 'price', label: expect.stringMatching(/Mín/) },
    ])
    expect(chipsFromFilters({ maxPrice: 5000 })).toMatchObject([
      { key: 'price', label: expect.stringMatching(/Máx/) },
    ])
    const both = chipsFromFilters({ minPrice: 1000, maxPrice: 5000 })
    expect(both).toHaveLength(1)
    expect(both[0].label).toMatch(/–/)
  })

  it('skips province=Todas', () => {
    expect(chipsFromFilters({ province: 'Todas' })).toEqual([])
    expect(chipsFromFilters({ province: 'Luanda' })).toEqual([
      { key: 'province', label: 'Luanda' },
    ])
  })

  it('maps condition to friendly pt-AO labels', () => {
    expect(chipsFromFilters({ condition: 'new' })[0].label).toBe('Novo')
    expect(chipsFromFilters({ condition: 'used' })[0].label).toBe('Usado')
    expect(chipsFromFilters({ condition: 'refurbished' })[0].label).toBe('Recondicionado')
  })

  it('skips minRating=0 and shows ★+ otherwise', () => {
    expect(chipsFromFilters({ minRating: 0 })).toEqual([])
    expect(chipsFromFilters({ minRating: 4 })).toEqual([
      { key: 'minRating', label: '4★+' },
    ])
  })

  it('renders one chip per brand', () => {
    const chips = chipsFromFilters({ brands: ['Samsung', 'Apple'] })
    expect(chips).toHaveLength(2)
    expect(chips[0]).toMatchObject({ key: 'brand', value: 'Samsung' })
    expect(chips[1]).toMatchObject({ key: 'brand', value: 'Apple' })
  })

  it('combines multiple filter types correctly', () => {
    const chips = chipsFromFilters({
      minPrice: 1000, maxPrice: 5000,
      province: 'Luanda', condition: 'new',
      minRating: 4, hasDiscount: true,
      brands: ['Nike'],
    })
    expect(chips).toHaveLength(6)
    const keys = chips.map(c => c.key)
    expect(keys).toEqual(['price', 'province', 'condition',
                          'minRating', 'hasDiscount', 'brand'])
  })
})


describe('formatPrice', () => {
  it('formats millions and thousands compactly', () => {
    expect(formatPrice(1_500_000)).toBe('1.5M')
    expect(formatPrice(25_000)).toBe('25K')
    expect(formatPrice(900)).toBe('900')
  })

  it('passes through non-numeric input', () => {
    expect(formatPrice('not-a-number')).toBe('not-a-number')
  })
})
