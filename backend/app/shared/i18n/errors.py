"""Localized `HTTPException` construction -- a drop-in replacement for
`HTTPException(status_code=..., detail="literal English string")` at call
sites that already have a resolved language on hand (`current_user.language`
where authenticated, `resolve_language(request.headers.get("accept-language"))`
for unauthenticated paths like login/register).

Not a global exception-handler middleware: that would still require every
raise site to pass a *key* instead of literal text for the middleware to
know what to translate, so it buys nothing over calling `localized_error`
directly here, and `auth/service.py` already documents a "raises
HTTPException directly, no custom error envelope" precedent (AD-3) that a
middleware would cut across.
"""

from fastapi import HTTPException

from app.shared.i18n.catalogs import t


def localized_error(status_code: int, key: str, language: str, **kwargs: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=t(key, language, **kwargs))
