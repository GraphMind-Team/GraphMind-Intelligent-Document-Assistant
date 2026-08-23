import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSlowRequestHint } from './useSlowRequestHint'

describe('useSlowRequestHint', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('stays false before the delay elapses', () => {
    const { result } = renderHook(() => useSlowRequestHint(true, 5000))

    expect(result.current).toBe(false)

    act(() => {
      vi.advanceTimersByTime(4999)
    })
    expect(result.current).toBe(false)
  })

  it('turns true once active has held continuously through the delay', () => {
    const { result } = renderHook(() => useSlowRequestHint(true, 5000))

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(result.current).toBe(true)
  })

  it('never turns true for a request that finishes before the delay', () => {
    const { result, rerender } = renderHook(({ active }) => useSlowRequestHint(active, 5000), {
      initialProps: { active: true },
    })

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    rerender({ active: false })
    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(result.current).toBe(false)
  })

  it('resets to false the instant a fresh request goes active again', () => {
    const { result, rerender } = renderHook(({ active }) => useSlowRequestHint(active, 5000), {
      initialProps: { active: true },
    })
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(result.current).toBe(true)

    rerender({ active: false })
    expect(result.current).toBe(false)

    // A new request starts its own fresh clock, not one that inherits
    // however close the previous request already was to the threshold.
    rerender({ active: true })
    act(() => {
      vi.advanceTimersByTime(4999)
    })
    expect(result.current).toBe(false)
  })
})
