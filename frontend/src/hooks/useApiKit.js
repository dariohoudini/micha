/**
 * useApiKit — small wrappers around the axios client that give the
 * whole codebase one consistent loading / error / toast contract.
 *
 * Why not @tanstack/react-query
 * ──────────────────────────────
 * Project already depends on it for some pages. These hooks deliberately
 * stay framework-light because:
 *   • the admin pages don't need cache invalidation across the app
 *   • simple state semantics keep the code reviewable
 *   • mixing patterns is fine — use react-query where you need its
 *     server-cache features; use these for "fetch once, optimistic
 *     mutate, toast" flows.
 *
 * Why a new file (not extending useApi.js)
 * ─────────────────────────────────────────
 * The existing useApi.js exports a `useApi(apiFn)` callback hook with
 * different semantics (caller passes the axios call). Keeping the two
 * side-by-side avoids breaking imports while introducing the richer
 * query/mutation pattern progressively.
 *
 * Hooks
 * ─────
 *   useApiQuery(path, params?)
 *       Returns {data, error, status, refetch}. Status ∈
 *       'idle' | 'loading' | 'success' | 'error'.
 *       Re-fetches when the JSON-stringified params change.
 *       Cancels in-flight requests on unmount or re-fetch.
 *
 *   useApiMutation(method, pathFactory, opts?)
 *       Returns {mutate, status, error, reset}. ``mutate(input)``
 *       returns a Promise. On success: toast.success(opts.successMessage),
 *       calls opts.onSuccess(data). On error: toast.error with backend
 *       message; calls opts.onError(err).
 *
 *   useOptimisticMutation(opts)
 *       Updates UI immediately via opts.apply(input), then calls
 *       opts.commit; on failure rolls back via opts.rollback(snapshot).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import client from '@/api/client'
import { toast } from '@/components/ui/Toast'
import { errorVariantFromStatus } from '@/components/ui/ErrorState'


/* ─── useApiQuery ─────────────────────────────────────────────────── */

export function useApiQuery(path, params) {
  const [state, setState] = useState({
    status: 'idle',
    data: null,
    error: null,
  })
  const paramsKey = useMemo(
    () => (params ? JSON.stringify(params) : ''),
    [params],
  )
  // Real cancellation via AbortController (replaces the previous
  // soft-flag approach that left the network request running on
  // unmount, wasting mobile bandwidth on flaky connections).
  const abortRef = useRef(null)

  const fetcher = useCallback(async () => {
    // Cancel any in-flight request first.
    if (abortRef.current) {
      try { abortRef.current.abort() } catch {}
    }
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setState((s) => ({ ...s, status: 'loading', error: null }))
    try {
      const res = await client.get(path, { params, signal: ctrl.signal })
      if (ctrl.signal.aborted) return
      setState({ status: 'success', data: res.data, error: null })
    } catch (e) {
      // Axios surfaces aborted requests with code 'ERR_CANCELED' OR
      // the request gets a CanceledError. Treat both as silent.
      if (
        ctrl.signal.aborted
        || e?.code === 'ERR_CANCELED'
        || e?.name === 'CanceledError'
        || e?.message === 'canceled'
      ) {
        return
      }
      const status = e?.response?.status
      const detail = e?.response?.data?.detail || e?.message || 'unknown'
      setState({
        status: 'error',
        data: null,
        error: {
          status,
          detail,
          variant: errorVariantFromStatus(status),
          raw: e,
        },
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, paramsKey])

  useEffect(() => {
    fetcher()
    return () => {
      if (abortRef.current) {
        try { abortRef.current.abort() } catch {}
      }
    }
  }, [fetcher])

  return {
    ...state,
    refetch: fetcher,
    isLoading: state.status === 'loading' || state.status === 'idle',
    isError: state.status === 'error',
    isSuccess: state.status === 'success',
  }
}


/* ─── useApiMutation ──────────────────────────────────────────────── */

export function useApiMutation(method, pathOrFactory, opts = {}) {
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)

  const optsRef = useRef(opts)
  optsRef.current = opts

  const mutate = useCallback(async (input = {}) => {
    setStatus('loading'); setError(null)
    const o = optsRef.current
    const path = typeof pathOrFactory === 'function'
      ? pathOrFactory(input) : pathOrFactory
    try {
      const fn = client[method]
      const res = method === 'delete'
        ? await fn(path, { data: input })
        : await fn(path, input)
      setStatus('success')
      if (o.successMessage) toast.success(o.successMessage)
      o.onSuccess?.(res.data, input)
      return res.data
    } catch (e) {
      setStatus('error')
      const httpStatus = e?.response?.status
      const detail = e?.response?.data?.detail
        || e?.response?.data?.error
        || e?.message
        || 'unknown'
      const errState = {
        status: httpStatus, detail,
        variant: errorVariantFromStatus(httpStatus),
        raw: e,
      }
      setError(errState)
      const message = typeof o.errorMessage === 'function'
        ? o.errorMessage(e) : o.errorMessage || detail
      if (message) toast.error(message)
      o.onError?.(e, input)
      throw e
    }
  }, [method, pathOrFactory])

  return {
    mutate,
    status,
    error,
    isLoading: status === 'loading',
    isError: status === 'error',
    isSuccess: status === 'success',
    reset: () => { setStatus('idle'); setError(null) },
  }
}


/* ─── useOptimisticMutation ───────────────────────────────────────── */

export function useOptimisticMutation(opts) {
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)

  const optsRef = useRef(opts)
  optsRef.current = opts

  const mutate = useCallback(async (input = {}) => {
    setStatus('loading'); setError(null)
    const o = optsRef.current
    let snapshot
    try {
      snapshot = o.apply(input)
    } catch (e) {
      setStatus('error')
      setError(e)
      toast.error(o.errorMessage || 'Falhou')
      throw e
    }
    try {
      const data = await o.commit(input)
      setStatus('success')
      if (o.successMessage) toast.success(o.successMessage)
      return data
    } catch (e) {
      setStatus('error')
      setError(e)
      try { o.rollback?.(snapshot, e) } catch {}
      toast.error(
        o.errorMessage
        || e?.response?.data?.detail
        || 'Não foi possível guardar.'
      )
      throw e
    }
  }, [])

  return {
    mutate, status, error,
    isLoading: status === 'loading',
    isError: status === 'error',
  }
}
