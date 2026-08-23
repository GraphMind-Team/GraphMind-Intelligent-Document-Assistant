import { useEffect, useState } from 'react'

// Render's free tier spins the backend down after ~15 minutes idle, and
// the first request after that can take up to a minute to come back
// (README.md) -- indistinguishable, from a plain "Loading..." caption,
// from the app just being broken. This turns true only once `active` has
// stayed true continuously for `delayMs` (default 5s, comfortably longer
// than any ordinary warm-backend request), so a caller can swap in a
// "this is taking longer than usual" hint without showing it on every
// routine wait. Resets to `false` the instant `active` goes false, so a
// fast follow-up request starts the clock over rather than inheriting a
// stale "slow" flag.
export function useSlowRequestHint(active, delayMs = 5000) {
  const [isSlow, setIsSlow] = useState(false)

  useEffect(() => {
    if (!active) {
      setIsSlow(false)
      return undefined
    }
    const timer = setTimeout(() => setIsSlow(true), delayMs)
    return () => clearTimeout(timer)
  }, [active, delayMs])

  return isSlow
}
