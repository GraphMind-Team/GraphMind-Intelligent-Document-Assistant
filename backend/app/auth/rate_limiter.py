"""Auth-specific rate limiters for POST /auth/login and POST /auth/register.

The `RateLimiter` class itself now lives in `app.shared.rate_limiter` --
`documents` (upload) needs the same mechanism, so it moved out of this
module rather than being imported across feature boundaries. Re-exported
here so `from app.auth.rate_limiter import RateLimiter` keeps working for
existing callers/tests.

Keying differs per route: login is (client IP, normalized email) so one
source can't grind a single account, while register is client IP alone --
there's no existing account to key off, and the attack it guards against
(enumeration via 409 vs. 201, or mass account creation) is one source
hammering many different emails.

`login` follows up with `limiter.reset(...)` on success so legitimate
repeat logins don't erode the same budget as failed guesses; `register`
has no equivalent -- a given email can only register once, so there's no
"legitimate repeat" to protect.
"""

from app.shared.rate_limiter import RateLimiter

__all__ = ["RateLimiter", "get_login_rate_limiter", "get_register_rate_limiter"]

_default_login_limiter = RateLimiter(detail="Too many login attempts. Try again later.")
_default_register_limiter = RateLimiter(detail="Too many registration attempts. Try again later.")


def get_login_rate_limiter() -> RateLimiter:
    return _default_login_limiter


def get_register_rate_limiter() -> RateLimiter:
    return _default_register_limiter
