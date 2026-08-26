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

- Rate (`get_ask_rate_limiter`): 15 questions/minute per account. Well
  above what a human asking questions and reading answers reaches (each
  answer takes seconds to generate and longer to read), while turning an
  unbounded script into a bounded, slow, and therefore noticeable one.
  Deliberately not sold as a *daily* budget: a fixed per-minute window
  cannot bound the daily Weaviate quota, and pretending otherwise would be
  worse than stating the limit honestly. What it does buy is that
  exhausting that quota stops being instantaneous and accidental.
- Concurrency (`get_ask_concurrency_limiter`): 3 in-flight per account.
  The more load-bearing of the two here, and the one a per-minute window
  structurally cannot provide: a sync route runs in Starlette's
  fixed-size threadpool, and each in-flight question holds its worker for
  the whole generation (up to ~120s with retries). Without this, one
  account opening N parallel questions occupies N workers and stalls every
  other in-flight request in the process -- including uploads and logins,
  which have nothing to do with chat. A human has one question in flight;
  3 leaves room for a retry racing a slow original.

Neither is distributed (see `shared/rate_limiter`'s module docstring) --
correct for the single-process deployment, and would need a shared store
behind multiple workers.
"""

from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter

_default_ask_rate_limiter = RateLimiter(
    max_attempts=15,
    detail="Too many questions. Try again in a minute.",
)
_default_ask_concurrency_limiter = ConcurrencyLimiter(
    max_concurrent=3,
    detail="Too many questions in progress. Wait for the current one to finish.",
)


def get_ask_rate_limiter() -> RateLimiter:
    return _default_ask_rate_limiter


def get_ask_concurrency_limiter() -> ConcurrencyLimiter:
    return _default_ask_concurrency_limiter
