// Shared by LoginPage (post-login navigate) and PublicOnlyRoute (redirect
// an already-authenticated visitor away from /login or /). Both need the
// same answer to "where was this user actually headed" -- previously
// duplicated as `location.state?.from?.pathname ?? '/documents'` in both
// places, and only carried pathname (dropping search/hash: a deep link
// like /documents?filter=x would lose the query string after login).
export function getRedirectTarget(location) {
  const from = location.state?.from
  if (!from) return '/documents'
  return `${from.pathname}${from.search ?? ''}${from.hash ?? ''}`
}
