/**
 * MICHA Hyper-Personalization — Feed Hook
 * Combines multiple signals for the ultimate personalised feed:
 * - User taste profile (categories, brands, price range)
 * - Time of day context (morning/lunch/evening)
 * - Province (local sellers first)
 * - Recently viewed (avoid repeats)
 * - Purchase history (don't show already bought)
 * - Stock urgency (limited stock shown first)
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import client from '@/api/client'

export default function usePersonalisedFeed() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [cursor, setCursor] = useState(null)
  const [hasMore, setHasMore] = useState(true)
  const [feedType, setFeedType] = useState('personalised')
  const loadedIds = useRef(new Set())

  const getTimeContext = () => {
    const h = new Date().getHours()
    if (h >= 6 && h < 11) return 'morning'
    if (h >= 11 && h < 15) return 'lunch'
    if (h >= 18 && h < 23) return 'evening'
    return 'default'
  }

  const getUserProvince = () => {
    try {
      const profile = JSON.parse(localStorage.getItem('micha_user_profile') || '{}')
      return profile.province || ''
    } catch { return '' }
  }

  const loadFeed = useCallback(async (reset = false) => {
    if (!hasMore && !reset) return
    setLoading(true)

    try {
      const params = {
        cursor: reset ? null : cursor,
        time_context: getTimeContext(),
        province: getUserProvince(),
        limit: 20,
      }

      // Try personalised feed first
      const res = await client.get('/api/v1/ai/feed/', { params })
        .catch(() => client.get('/api/v1/recommendations/feed/', { params }))

      const data = res.data
      const newProducts = (data.results || data.products || data || [])
        .filter(p => !loadedIds.current.has(p.id))

      newProducts.forEach(p => loadedIds.current.add(p.id))

      if (reset) {
        setProducts(newProducts)
        loadedIds.current = new Set(newProducts.map(p => p.id))
      } else {
        setProducts(prev => [...prev, ...newProducts])
      }

      setCursor(data.next_cursor || data.next || null)
      setHasMore(!!data.next_cursor || !!data.next)
      setFeedType(data.feed_type || 'personalised')

    } catch {
      setHasMore(false)
    } finally {
      setLoading(false)
    }
  }, [cursor, hasMore])

  useEffect(() => {
    loadFeed(true)
  }, [])

  const refresh = () => {
    loadedIds.current = new Set()
    setCursor(null)
    setHasMore(true)
    loadFeed(true)
  }

  return { products, loading, hasMore, loadMore: loadFeed, refresh, feedType }
}
