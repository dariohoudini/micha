/**
 * MICHA Intent Detector
 * Tracks micro-behaviors during browsing and sends them to the engine
 * in real time. This is what makes the feed feel psychic.
 *
 * Signals tracked:
 * - Time spent on product (dwell)
 * - Scroll depth on product page
 * - Image gallery interactions
 * - Review reading
 * - Price comparison behavior
 * - Return visits to same product
 * - Rapid bouncing (negative signal)
 */
import { useEffect, useRef, useCallback } from 'react'
import client from '@/api/client'

const SESSION_START = Date.now()
const TRACKED_PRODUCTS = new Map() // productId -> {firstSeen, dwellStart, events}

// Debounced event sender
let pendingEvents = []
let flushTimer = null

const flushEvents = async () => {
  if (pendingEvents.length === 0) return
  const toSend = [...pendingEvents]
  pendingEvents = []

  try {
    // Batch send all pending events
    await Promise.allSettled(
      toSend.map(event =>
        client.post('/api/v1/ai/event/', event)
      )
    )
  } catch {
    // Silent fail — tracking should never break UX
  }
}

const queueEvent = (event) => {
  pendingEvents.push({
    ...event,
    session_seconds: Math.floor((Date.now() - SESSION_START) / 1000),
  })
  clearTimeout(flushTimer)
  // Flush after 2s of inactivity, or immediately for high-value events
  const delay = ['cart_add', 'purchase', 'checkout_start'].includes(event.event_type) ? 0 : 2000
  flushTimer = setTimeout(flushEvents, delay)
}

// Track page visibility (tab switching)
let hiddenAt = null
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    hiddenAt = Date.now()
  } else if (hiddenAt) {
    const away = Date.now() - hiddenAt
    hiddenAt = null
    // If away for < 30s, don't count as session end
  }
})

/**
 * useProductTracking — call on every product detail page
 * Automatically tracks dwell time, scroll depth, image views
 */
export function useProductTracking(product) {
  const dwellStart = useRef(Date.now())
  const maxScroll = useRef(0)
  const imageCount = useRef(0)
  const dwellIntervals = useRef([])

  useEffect(() => {
    if (!product?.id) return

    const productId = String(product.id)
    const category = product.category?.name || ''
    const price = product.price

    // Record initial view
    queueEvent({
      event_type: 'view',
      product_id: productId,
      category,
      price,
      source: 'product_detail',
    })

    dwellStart.current = Date.now()

    // Dwell time milestones (10s, 30s, 60s)
    const milestones = [
      { seconds: 10, event: 'dwell_10' },
      { seconds: 30, event: 'dwell_30' },
      { seconds: 60, event: 'dwell_60' },
    ]

    milestones.forEach(({ seconds, event }) => {
      const timer = setTimeout(() => {
        queueEvent({
          event_type: event,
          product_id: productId,
          category,
          price,
          dwell_seconds: seconds,
        })
      }, seconds * 1000)
      dwellIntervals.current.push(timer)
    })

    // Scroll tracking
    const handleScroll = () => {
      const scrollPct = Math.round(
        (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100
      )
      if (scrollPct > maxScroll.current) {
        maxScroll.current = scrollPct
        if (scrollPct >= 75 && maxScroll.current < 75) {
          // Scrolled deep — high intent
          queueEvent({
            event_type: 'scroll_images',
            product_id: productId,
            category,
            price,
            scroll_depth_pct: scrollPct,
          })
        }
      }
    }

    window.addEventListener('scroll', handleScroll, { passive: true })

    // Bounce detection — left within 5 seconds
    const bounceTimer = setTimeout(() => {
      // After 5s they're not bouncing
    }, 5000)

    return () => {
      // Cleanup — send final dwell time on unmount
      const totalDwell = Math.floor((Date.now() - dwellStart.current) / 1000)

      dwellIntervals.current.forEach(clearTimeout)
      clearTimeout(bounceTimer)
      window.removeEventListener('scroll', handleScroll)

      if (totalDwell < 3) {
        // They left in under 3 seconds — bounce
        queueEvent({
          event_type: 'bounce',
          product_id: productId,
          category,
          price,
          dwell_seconds: totalDwell,
        })
      }

      flushEvents()
    }
  }, [product?.id])

  // Expose tracking functions for manual events
  const trackReviewRead = useCallback(() => {
    if (!product?.id) return
    queueEvent({
      event_type: 'read_reviews',
      product_id: String(product.id),
      category: product.category?.name || '',
      price: product.price,
    })
  }, [product])

  const trackImageView = useCallback((imageIndex) => {
    imageCount.current = Math.max(imageCount.current, imageIndex + 1)
    if (imageCount.current >= 3) {
      queueEvent({
        event_type: 'scroll_images',
        product_id: String(product?.id || ''),
        category: product?.category?.name || '',
        price: product?.price,
        metadata: { images_viewed: imageCount.current },
      })
    }
  }, [product])

  return { trackReviewRead, trackImageView }
}

/**
 * useFeedTracking — call on home/feed pages
 * Tracks which feed items get clicked
 */
export function useFeedTracking() {
  const trackFeedClick = useCallback((product, position) => {
    if (!product?.id) return
    queueEvent({
      event_type: 'click_rec',
      product_id: String(product.id),
      category: product.category?.name || '',
      price: product.price,
      source: 'home_feed',
      metadata: { position },
    })
  }, [])

  const trackSearchClick = useCallback((product, query) => {
    if (!product?.id) return
    queueEvent({
      event_type: 'search_click',
      product_id: String(product.id),
      category: product.category?.name || '',
      price: product.price,
      source: 'search',
      metadata: { query },
    })
  }, [])

  return { trackFeedClick, trackSearchClick }
}

/**
 * trackHighValueEvent — call from anywhere for critical events
 */
export function trackHighValueEvent(eventType, product, extra = {}) {
  if (!product?.id) return
  queueEvent({
    event_type: eventType,
    product_id: String(product.id),
    category: product.category?.name || '',
    price: product.price,
    ...extra,
  })
  flushEvents() // Immediate flush for high-value events
}
