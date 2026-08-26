"""Limiters for the question-answering routes (`POST /chat/sessions/{id}/ask`
and its `.../messages/{id}/edit` sibling).

Both key on `user_id`, not client IP -- these are authenticated routes, so
the account is the real actor, exactly the reasoning
`documents/rate_limiter.py` already states for upload.

These two routes were the only expensive endpoints in the app with no
limiter of any kind, which is what makes this worth its own module rather
than a "nice to have": a single `/ask` costs one OpenRouter routing call,
one *metered* Weaviate embedding request, and up to two OpenRouter chat
completions, and it occupies an anyio threadpool worker for as long as all
of that takes (`chat/service.py::ask_question`'s own capacity note). None
of those costs are paid by the caller, and one of them is not even paid
per-account: Weaviate Embeddings bills against a cluster-wide free-tier
quota of 2,000 requests/day, so one account looping this endpoint takes
retrieval down for *every* user, not just itself.

`edit` gets the identical treatment because it is not a cheaper operation
-- it re-runs `ask_question` end to end (`chat/service.py::edit_message`),
so leaving it unlimited would just relocate the same abuse one URL over.
They deliberately share one budget rather than getting a limiter each: the
resource being protected (upstream quota, threadpool workers) is shared, so
splitting the allowance would let a caller spend both.

Two limits, guarding two different failure modes -- the same split, for the
same reasons, that upload already draws:

- Rate (`get_ask_rate_limiter`): 5 questions/minute per account. Above
  what a human asking questions and reading answers reaches (each answer
  takes seconds to generate and longer to read), and low enough to be a
  real ceiling rather than a decorative one.
- Daily (`get_ask_daily_rate_limiter`): 25 questions/day per account.
  This is the limit that actually matters, and the per-minute one above
  was originally set to 15 without it -- which, measured against the real
  upstream ceiling, was no limit at all. OpenRouter's free tier allows
  **50 requests per day across the whole API key**, and one `/ask` spends
  2-3 of them (one routing call plus one or two generation attempts). The
  entire daily budget is therefore ~17-25 questions for all users
  combined, which 15/minute would burn in under four minutes.
- Concurrency (`get_ask_concurrency_limiter`): 3 in-flight per account.
  The more load-bearing of the two here, and the one a per-minute window
  structurally cannot provide: a sync route runs in Starlette's
  fixed-size threadpool, and each in-flight question holds its worker for
  the whole generation (up to ~120s with retries). Without this, one
  account opening N parallel questions occupies N workers and stalls every
  other in-flight request in the process -- including uploads and logins,
  which have nothing to do with chat. A human has one question in flight;
  3 leaves room for a retry racing a slow original.

Be honest about what the daily limiter does and does not buy. It is
per-account, but the budget it protects is global to the API key, so
three busy accounts still exhaust it -- and it is an in-process counter,
so a restart (routine on Render's free tier) resets it. What it stops is
one client looping the endpoint and taking the day's answers down for
everyone in minutes, which is the failure this project has actually seen.
It is not a quota system, and the honest fix for that is a paid tier or a
shared store, not a bigger number here.

None of these are distributed (see `shared/rate_limiter`'s module
docstring) -- correct for the single-process deployment, and would need a
shared store behind multiple workers.
"""

from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter

_ONE_DAY_SECONDS = 60.0 * 60 * 24

_default_ask_rate_limiter = RateLimiter(
    max_attempts=5,
    detail="Too many questions. Try again in a minute.",
)
_default_ask_daily_rate_limiter = RateLimiter(
    max_attempts=25,
    window_seconds=_ONE_DAY_SECONDS,
    detail="You've reached today's question limit. It resets tomorrow.",
)
_default_ask_concurrency_limiter = ConcurrencyLimiter(
    max_concurrent=3,
    detail="Too many questions in progress. Wait for the current one to finish.",
)


def get_ask_rate_limiter() -> RateLimiter:
    return _default_ask_rate_limiter


def get_ask_daily_rate_limiter() -> RateLimiter:
    return _default_ask_daily_rate_limiter


def get_ask_concurrency_limiter() -> ConcurrencyLimiter:
    return _default_ask_concurrency_limiter
