// Shared by ProtectedRoute/PublicOnlyRoute for the up-to-AUTH_ME_CHECK_TIMEOUT_MS
// window while AuthContext's boot-time /auth/me check is in flight. Previously
// both guards rendered null here, which -- combined with no timeout on that
// check -- meant a stalled request (e.g. Render's ~1 min cold start) left a
// first-time visitor looking at a blank white page with no signal anything
// was happening.
export default function LoadingScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-bg">
      <p className="text-sm text-text2">Loading…</p>
    </main>
  )
}
