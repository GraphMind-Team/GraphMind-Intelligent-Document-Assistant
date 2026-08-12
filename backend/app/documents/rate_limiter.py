"""Upload limiters for POST /documents.

Both key on `user_id` (not client IP): upload is an authenticated route,
so the account is the real actor, and IP-keying would both lump colleagues
behind one office NAT into a shared budget and let one account rotate IPs
to escape it.

Two limits, guarding two different failure modes:

- Rate (`get_upload_rate_limiter`): 30 uploads/minute per account. Higher
  than auth's 5/minute because a legitimate batch drop of a whole folder
  is a normal, intended action here -- unlike 5 login attempts, which is
  already generous for a human. Guards sustained scripted abuse filling
  Postgres (`content` bytes live in the DB, so this is a storage-cost
  attack, not just request volume).
- Concurrency (`get_upload_concurrency_limiter`): 5 in-flight uploads per
  account. The frontend deliberately fires one request per queued file in
  parallel, so a 50-file drop would otherwise be 50 simultaneous requests
  each holding up to 20MB in memory -- enough to exhaust Render's free
  tier for every user, not just the uploader. A per-minute window can't
  catch this: 50 requests in one instant is one window's worth.
"""

from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter

_default_upload_rate_limiter = RateLimiter(
    max_attempts=30,
    detail="Too many uploads. Try again in a minute.",
)
_default_upload_concurrency_limiter = ConcurrencyLimiter(
    max_concurrent=5,
    detail="Too many uploads in progress. Wait for the current ones to finish.",
)


def get_upload_rate_limiter() -> RateLimiter:
    return _default_upload_rate_limiter


def get_upload_concurrency_limiter() -> ConcurrencyLimiter:
    return _default_upload_concurrency_limiter
