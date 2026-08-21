"""Reading environment variables that came from a copy-paste.

Every deployment secret in this project is typed or pasted into a hosting
dashboard by a human, and dashboard fields readily capture a trailing
newline or space that is completely invisible in the UI. Two separate
production outages here came from exactly that:

  * `FRONTEND_ORIGIN` -- a value that looked right in the dashboard but
    did not match the browser's `Origin`, so every cross-origin request
    was rejected with a CORS error naming an origin that appeared
    correct.
  * `OPENROUTER_API_KEY` -- a pasted key carrying a trailing "\\n". httpx
    refuses to send a header containing a newline (header-injection
    protection), so the request never left the server at all. It
    surfaced as "entity extraction failed after 3 attempts", which reads
    like a provider problem and is not one.

Both were invisible in the dashboard, produced no server-side error
naming the real cause, and cost real debugging time. `env_str` is the
single place that rule lives now, so a new call site cannot forget it.

Deliberately not a general config framework -- just the one rule that has
actually bitten, applied consistently.
"""

import os


def env_str(name: str, default: str = "") -> str:
    """The value of `name` with surrounding whitespace stripped, or
    `default` if it is unset OR set-but-blank.

    The set-but-blank case is the one `os.environ.get(name, default)` gets
    wrong: its two-argument form returns the default only when the key is
    ABSENT, so a key present with an empty value yields `""` and silently
    bypasses the fallback the caller thought it had. Deploying a service
    before a dependent URL exists means setting a variable blank on
    purpose, so this is a state that occurs in normal operation, not a
    typo.
    """
    return os.environ.get(name, "").strip() or default
