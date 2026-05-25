/**
 * useApiKit tests — unit-level coverage of the query/mutation hooks.
 *
 * Run via ``cd frontend && npm test`` (requires Vitest deps —
 * see vitest.config.js comment).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

// Mock the axios client BEFORE importing the hook.
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

// Mock toast — captures calls without rendering.
vi.mock('@/components/ui/Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import client from '@/api/client'
import { toast } from '@/components/ui/Toast'
import {
  useApiQuery,
  useApiMutation,
  useOptimisticMutation,
} from './useApiKit'


beforeEach(() => {
  vi.clearAllMocks()
})


describe('useApiQuery', () => {
  it('moves through idle → loading → success', async () => {
    client.get.mockResolvedValueOnce({ data: { ok: 1 } })
    const { result } = renderHook(() => useApiQuery('/foo'))

    expect(result.current.isLoading).toBe(true)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ ok: 1 })
  })

  it('captures error variant from HTTP status', async () => {
    client.get.mockRejectedValueOnce({
      response: { status: 403, data: { detail: 'nope' } },
    })
    const { result } = renderHook(() => useApiQuery('/foo'))
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error.status).toBe(403)
    expect(result.current.error.variant).toBe('forbidden')
    expect(result.current.error.detail).toBe('nope')
  })

  it('refetch re-runs the request', async () => {
    client.get
      .mockResolvedValueOnce({ data: 'a' })
      .mockResolvedValueOnce({ data: 'b' })
    const { result } = renderHook(() => useApiQuery('/x'))
    await waitFor(() => expect(result.current.data).toBe('a'))
    await act(() => result.current.refetch())
    await waitFor(() => expect(result.current.data).toBe('b'))
  })

  it('re-fetches when params change', async () => {
    client.get.mockResolvedValue({ data: 'ok' })
    const { result, rerender } = renderHook(
      ({ p }) => useApiQuery('/x', p),
      { initialProps: { p: { a: 1 } } },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(client.get).toHaveBeenCalledTimes(1)

    rerender({ p: { a: 2 } })
    await waitFor(() => expect(client.get).toHaveBeenCalledTimes(2))
  })
})


describe('useApiMutation', () => {
  it('POSTs and calls onSuccess with returned data', async () => {
    client.post.mockResolvedValueOnce({ data: { id: 7 } })
    const onSuccess = vi.fn()
    const { result } = renderHook(() => useApiMutation(
      'post', '/things/',
      { successMessage: 'Saved!', onSuccess },
    ))
    await act(() => result.current.mutate({ name: 'x' }))

    expect(client.post).toHaveBeenCalledWith('/things/', { name: 'x' })
    expect(toast.success).toHaveBeenCalledWith('Saved!')
    expect(onSuccess).toHaveBeenCalledWith({ id: 7 }, { name: 'x' })
    expect(result.current.isSuccess).toBe(true)
  })

  it('toasts the backend detail on failure', async () => {
    client.post.mockRejectedValueOnce({
      response: { status: 400, data: { detail: 'Bad data' } },
    })
    const onError = vi.fn()
    const { result } = renderHook(() => useApiMutation(
      'post', '/things/', { onError },
    ))
    await expect(
      act(() => result.current.mutate({})),
    ).rejects.toBeTruthy()

    expect(toast.error).toHaveBeenCalledWith('Bad data')
    expect(onError).toHaveBeenCalled()
    expect(result.current.isError).toBe(true)
    expect(result.current.error.variant).toBe('generic')
  })

  it('uses a path factory when provided', async () => {
    client.delete.mockResolvedValueOnce({ data: { ok: true } })
    const { result } = renderHook(() => useApiMutation(
      'delete', (id) => `/things/${id}/`,
    ))
    await act(() => result.current.mutate(42))
    expect(client.delete).toHaveBeenCalledWith('/things/42/', { data: 42 })
  })
})


describe('useOptimisticMutation', () => {
  it('apply runs before commit; success leaves UI as-applied', async () => {
    const apply = vi.fn().mockReturnValue({ snapshot: 'old' })
    const commit = vi.fn().mockResolvedValueOnce({ done: true })
    const rollback = vi.fn()

    const { result } = renderHook(() => useOptimisticMutation({
      apply, commit, rollback, successMessage: 'Done',
    }))
    await act(() => result.current.mutate({ x: 1 }))
    expect(apply).toHaveBeenCalledBefore(commit)
    expect(rollback).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('Done')
  })

  it('rolls back when commit fails', async () => {
    const apply = vi.fn().mockReturnValue({ snapshot: 'state-before' })
    const commit = vi.fn().mockRejectedValueOnce(
      new Error('boom'),
    )
    const rollback = vi.fn()

    const { result } = renderHook(() => useOptimisticMutation({
      apply, commit, rollback, errorMessage: 'Falhou',
    }))
    await expect(
      act(() => result.current.mutate({})),
    ).rejects.toBeTruthy()
    expect(rollback).toHaveBeenCalledWith({ snapshot: 'state-before' }, expect.any(Error))
    expect(toast.error).toHaveBeenCalledWith('Falhou')
  })
})
