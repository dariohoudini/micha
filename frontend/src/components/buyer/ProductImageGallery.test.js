/**
 * ProductImageGallery — pure-helper unit tests.
 *
 * Component-level tests would need @testing-library/react + jsdom +
 * a mock for touch events. Vitest deps aren't installed yet (operator
 * decision) so we exercise the testable contracts of the data
 * normaliser and verify the default export shape.
 */
import { describe, it, expect } from 'vitest'

import Gallery, { normaliseImageList } from './ProductImageGallery'


describe('default export', () => {
  it('is a React component', () => {
    expect(typeof Gallery).toBe('function')
    expect(Gallery.name).toBe('ProductImageGallery')
  })
})


describe('normaliseImageList', () => {
  it('handles empty / nullish', () => {
    expect(normaliseImageList(undefined)).toEqual([])
    expect(normaliseImageList(null)).toEqual([])
    expect(normaliseImageList([])).toEqual([])
  })

  it('accepts plain string URLs', () => {
    expect(normaliseImageList(['a.jpg', 'b.png'])).toEqual([
      { url: 'a.jpg' },
      { url: 'b.png' },
    ])
  })

  it('accepts {url, alt} objects', () => {
    expect(normaliseImageList([
      { url: 'a.jpg', alt: 'red' },
      { url: 'b.png' },
    ])).toEqual([
      { url: 'a.jpg', alt: 'red' },
      { url: 'b.png', alt: undefined },
    ])
  })

  it('accepts {image, alt} objects (Django serializer shape)', () => {
    expect(normaliseImageList([
      { image: 'a.jpg', alt: 'red' },
    ])).toEqual([
      { url: 'a.jpg', alt: 'red' },
    ])
  })

  it('drops falsy entries', () => {
    expect(normaliseImageList([
      'a.jpg', null, undefined, '', { url: 'b.png' },
    ])).toEqual([
      { url: 'a.jpg' },
      { url: 'b.png', alt: undefined },
    ])
  })

  it('drops objects without url or image', () => {
    expect(normaliseImageList([
      { alt: 'no source' },
      { url: 'ok.jpg' },
    ])).toEqual([
      { url: 'ok.jpg', alt: undefined },
    ])
  })
})
