"""Backend-sent text (verification emails, API error `detail` strings),
translated per the user's saved `language` or, pre-account, the
registration request's Accept-Language header. A small, hand-maintained
dict-of-dicts -- no runtime file I/O or template-file dependency, matching
`shared/email/__init__.py`'s own "everything read lazily, minimal infra"
convention.
"""

from typing import Final

SUPPORTED_LANGUAGES: Final = ("en", "bg", "de")
DEFAULT_LANGUAGE: Final = "en"

_MESSAGES: Final[dict[str, dict[str, str]]] = {
    "en": {
        "verify_email.subject": "Verify your GraphMind email address",
        "verify_email.body": (
            "Hi {full_name},\n\n"
            "Thanks for signing up for GraphMind. Confirm your email address "
            "by opening the link below:\n\n"
            "{verify_url}\n\n"
            "This link expires in {expire_hours} hours. If you didn't create "
            "a GraphMind account, you can ignore this email.\n"
        ),
        "error.invalid_credentials": "Invalid email or password.",
        "error.email_exists": "An account with this email already exists.",
        "error.email_not_verified": "Please verify your email address before logging in. We sent a link when you registered.",
        "error.not_authenticated": "Not authenticated.",
        "error.invalid_verification_link": "This verification link is invalid or has expired.",
        "error.current_password_incorrect": "Current password is incorrect.",
        "error.document_still_processing": "Document is still being processed and can't be deleted yet.",
    },
    "bg": {
        "verify_email.subject": "Потвърдете своя имейл адрес в GraphMind",
        "verify_email.body": (
            "Здравейте, {full_name},\n\n"
            "Благодарим ви, че се регистрирахте в GraphMind. Потвърдете имейл "
            "адреса си, като отворите линка по-долу:\n\n"
            "{verify_url}\n\n"
            "Този линк изтича след {expire_hours} часа. Ако не сте създавали "
            "акаунт в GraphMind, можете да пренебрегнете този имейл.\n"
        ),
        "error.invalid_credentials": "Невалиден имейл или парола.",
        "error.email_exists": "Вече съществува акаунт с този имейл.",
        "error.email_not_verified": "Моля, потвърдете имейл адреса си, преди да влезете. Изпратихме линк при регистрацията ви.",
        "error.not_authenticated": "Не сте удостоверени.",
        "error.invalid_verification_link": "Този линк за потвърждение е невалиден или е изтекъл.",
        "error.current_password_incorrect": "Текущата парола е грешна.",
        "error.document_still_processing": "Документът все още се обработва и не може да бъде изтрит все още.",
    },
    "de": {
        "verify_email.subject": "Bestätige deine GraphMind-E-Mail-Adresse",
        "verify_email.body": (
            "Hallo {full_name},\n\n"
            "danke, dass du dich bei GraphMind registriert hast. Bestätige "
            "deine E-Mail-Adresse, indem du den folgenden Link öffnest:\n\n"
            "{verify_url}\n\n"
            "Dieser Link läuft in {expire_hours} Stunden ab. Falls du kein "
            "GraphMind-Konto erstellt hast, kannst du diese E-Mail ignorieren.\n"
        ),
        "error.invalid_credentials": "Ungültige E-Mail oder ungültiges Passwort.",
        "error.email_exists": "Es existiert bereits ein Konto mit dieser E-Mail-Adresse.",
        "error.email_not_verified": "Bitte bestätige deine E-Mail-Adresse, bevor du dich anmeldest. Wir haben dir bei der Registrierung einen Link geschickt.",
        "error.not_authenticated": "Nicht authentifiziert.",
        "error.invalid_verification_link": "Dieser Bestätigungslink ist ungültig oder abgelaufen.",
        "error.current_password_incorrect": "Das aktuelle Passwort ist falsch.",
        "error.document_still_processing": "Das Dokument wird noch verarbeitet und kann noch nicht gelöscht werden.",
    },
}


def resolve_language(raw: str | None) -> str:
    """Normalizes a `User.language` value or an `Accept-Language` header's
    primary tag to a supported code, falling back to English -- mirrors the
    frontend detector's own supportedLngs+fallback rule so both halves of
    the app apply the exact same "closest supported language, else
    English" logic."""
    if not raw:
        return DEFAULT_LANGUAGE
    primary = raw.split(",")[0].split("-")[0].strip().lower()
    return primary if primary in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, language: str, **kwargs: object) -> str:
    lang = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    template = _MESSAGES.get(lang, _MESSAGES[DEFAULT_LANGUAGE]).get(key) or _MESSAGES[DEFAULT_LANGUAGE][key]
    return template.format(**kwargs) if kwargs else template
