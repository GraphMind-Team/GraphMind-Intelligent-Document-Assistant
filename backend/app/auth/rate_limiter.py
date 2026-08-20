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
hammering many different emails. `change_password` (Story 5.1) is keyed by
the authenticated user's id alone, not IP -- the caller already holds a
valid access token by the time this route runs, so the threat isn't an
anonymous source grinding accounts, it's that same token being used (e.g.
after theft) to brute-force `current_password` against the one account it
belongs to. `resend_verification` (Story 1.6) is keyed like login --
(client IP, normalized email) -- since the attack shape is the same one
being guarded against there: a source spamming a specific victim's inbox
with verification emails, not grinding many different accounts (which
would call for an IP-only key, like register).

`resend_verification` also gets a second, IP-only limiter alongside the
(IP, email) one -- the pair key alone bounds spam against any *one*
victim's inbox, but puts no ceiling on a single source rotating through
many different target emails, each getting its own fresh 5/window budget
under the pair key. The IP-only limiter closes that: `register`'s exact
reasoning ("one source hammering many different emails"), applied here
because that's a real, separate attack shape resend-verification is
equally exposed to. Its ceiling is set higher than the pair limiter's so
it never gets in the way of someone legitimately retrying a resend for
their own one address -- it only bites a source spraying many addresses.

`login` follows up with `limiter.reset(...)` on success so legitimate
repeat logins don't erode the same budget as failed guesses; `register`
has no equivalent -- a given email can only register once, so there's no
"legitimate repeat" to protect. `resend_verification` also has no
equivalent -- every resend is a "legitimate repeat" of the same action, so
there's no success/failure split to reset on.
"""

from app.shared.rate_limiter import RateLimiter

__all__ = [
    "RateLimiter",
    "get_login_rate_limiter",
    "get_register_rate_limiter",
    "get_change_password_rate_limiter",
    "get_resend_verification_rate_limiter",
    "get_resend_verification_ip_rate_limiter",
]

_default_login_limiter = RateLimiter(detail="Too many login attempts. Try again later.")
_default_register_limiter = RateLimiter(detail="Too many registration attempts. Try again later.")
_default_change_password_limiter = RateLimiter(
    detail="Too many password change attempts. Try again later."
)
_default_resend_verification_limiter = RateLimiter(
    detail="Too many verification email requests. Try again later."
)
# Wider ceiling than the pair limiter above -- see this module's docstring
# for why one source rotating target emails needs its own, separate cap.
_default_resend_verification_ip_limiter = RateLimiter(
    max_attempts=20,
    window_seconds=60.0,
    detail="Too many verification email requests. Try again later.",
)


def get_login_rate_limiter() -> RateLimiter:
    return _default_login_limiter


def get_register_rate_limiter() -> RateLimiter:
    return _default_register_limiter


def get_change_password_rate_limiter() -> RateLimiter:
    return _default_change_password_limiter


def get_resend_verification_rate_limiter() -> RateLimiter:
    return _default_resend_verification_limiter


def get_resend_verification_ip_rate_limiter() -> RateLimiter:
    return _default_resend_verification_ip_limiter
