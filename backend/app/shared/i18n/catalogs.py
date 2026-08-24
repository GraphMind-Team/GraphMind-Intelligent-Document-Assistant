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
        # HTML verification email (`shared/email/templates.py`) -- the same
        # message as verify_email.body above, broken into the pieces that
        # template lays out. The product copy (eyebrow, hero title, the
        # feature and step blurbs) is deliberately the *landing page's* own
        # wording from frontend/src/i18n/locales/en.json, so a reader who
        # clicks through meets the same sentences rather than a second,
        # drifting description of the product. Key list: templates.py's
        # REQUIRED_COPY_KEYS.
        "verify_email.preheader": "Confirm your email address and start asking your documents questions.",
        "verify_email.eyebrow": "Grounded document intelligence",
        "verify_email.hero_title": "Your documents, finally answering back.",
        "verify_email.hero_body": "Confirm your email address to activate your account — it takes one click.",
        "verify_email.button": "Verify email address",
        "verify_email.greeting": "Hi {full_name},",
        "verify_email.intro": (
            "Welcome to GraphMind. It reads everything you upload, maps who and "
            "what is connected to what, and answers your questions using only "
            "what your own documents actually say — with a citation on every "
            "claim."
        ),
        "verify_email.what_you_get": "What you get",
        "verify_email.feature_upload_title": "Upload anything",
        "verify_email.feature_upload_body": "Drop in PDFs, docs and notes. GraphMind extracts the text, chapter by chapter, and tracks every file through ingestion.",
        "verify_email.feature_answers_title": "Answers with receipts",
        "verify_email.feature_answers_body": "Every answer is grounded in your own documents and carries citation chips back to the exact chapter it came from. No evidence, no answer.",
        "verify_email.feature_connections_title": "See the connections",
        "verify_email.feature_connections_body": "People, organizations, projects, products and places are pulled out into a live knowledge graph you can explore — or read as a list.",
        "verify_email.how_it_works": "How it works",
        "verify_email.step_add_title": "Add your documents",
        "verify_email.step_add_body": "Upload one file or a whole folder. Watch each one move from Uploaded to Ready.",
        "verify_email.step_ask_title": "Ask in plain language",
        "verify_email.step_ask_body": "Narrow the scope to the documents you care about, then just ask.",
        "verify_email.step_follow_title": "Follow the evidence",
        "verify_email.step_follow_body": "Open any citation to land on the source, or jump to the graph to see how it all connects.",
        "verify_email.fallback_intro": "Button not working? Copy this link into your browser:",
        "verify_email.expiry": "This link expires in {expire_hours} hours.",
        "verify_email.ignore": "If you didn't create a GraphMind account, you can safely ignore this email.",
        "verify_email.footer_tagline": "GraphMind — Intelligent Document Assistant",
        "verify_email.footer_copyright": "You received this email because this address was used to create a GraphMind account.",
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
        "verify_email.preheader": "Потвърдете имейл адреса си и започнете да задавате въпроси на документите си.",
        "verify_email.eyebrow": "Анализ на документи с доказателства",
        "verify_email.hero_title": "Вашите документи най-сетне проговарят.",
        "verify_email.hero_body": "Потвърдете имейл адреса си, за да активирате акаунта си — само с едно кликване.",
        "verify_email.button": "Потвърди имейл адреса",
        "verify_email.greeting": "Здравейте, {full_name},",
        "verify_email.intro": (
            "Добре дошли в GraphMind. Той прочита всичко, което качите, изгражда "
            "картина на връзките между хора, теми и факти, и отговаря на "
            "въпросите ви само въз основа на съдържанието на вашите документи — "
            "с цитат към всяко твърдение."
        ),
        "verify_email.what_you_get": "Какво получавате",
        "verify_email.feature_upload_title": "Качете каквото и да е",
        "verify_email.feature_upload_body": "Добавете PDF файлове, документи и бележки. GraphMind извлича текста глава по глава и следи всеки файл през целия процес на обработка.",
        "verify_email.feature_answers_title": "Отговори с доказателства",
        "verify_email.feature_answers_body": "Всеки отговор се основава на вашите собствени документи и включва цитат към точната глава, от която идва. Без доказателство — без отговор.",
        "verify_email.feature_connections_title": "Вижте връзките",
        "verify_email.feature_connections_body": "Хора, организации, проекти, продукти и места се подреждат в жив граф на знанието, който можете да разглеждате визуално — или просто като списък.",
        "verify_email.how_it_works": "Как работи",
        "verify_email.step_add_title": "Добавете документите си",
        "verify_email.step_add_body": "Качете един файл или цяла папка. Наблюдавайте как всеки преминава от „Качен“ към „Готов“.",
        "verify_email.step_ask_title": "Питайте на прост език",
        "verify_email.step_ask_body": "Стеснете обхвата до документите, които ви интересуват, и просто попитайте.",
        "verify_email.step_follow_title": "Проследете доказателството",
        "verify_email.step_follow_body": "Отворете всеки цитат, за да стигнете до източника, или преминете към графа, за да видите как всичко се свързва.",
        "verify_email.fallback_intro": "Бутонът не работи? Копирайте този линк в браузъра си:",
        "verify_email.expiry": "Този линк изтича след {expire_hours} часа.",
        "verify_email.ignore": "Ако не сте създавали акаунт в GraphMind, можете спокойно да пренебрегнете този имейл.",
        "verify_email.footer_tagline": "GraphMind — Интелигентен асистент за документи",
        "verify_email.footer_copyright": "Получавате този имейл, защото този адрес е използван за създаване на акаунт в GraphMind.",
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
        "verify_email.preheader": "Bestätige deine E-Mail-Adresse und stelle deinen Dokumenten Fragen.",
        "verify_email.eyebrow": "Intelligente Dokumentenanalyse mit Belegen",
        "verify_email.hero_title": "Deine Dokumente antworten endlich.",
        "verify_email.hero_body": "Bestätige deine E-Mail-Adresse, um dein Konto zu aktivieren — ein Klick genügt.",
        "verify_email.button": "E-Mail-Adresse bestätigen",
        "verify_email.greeting": "Hallo {full_name},",
        "verify_email.intro": (
            "Willkommen bei GraphMind. Es liest alles, was du hochlädst, zeigt "
            "dir, wie Personen, Themen und Fakten miteinander verknüpft sind, "
            "und beantwortet deine Fragen ausschließlich auf Basis dessen, was "
            "in deinen eigenen Dokumenten steht — mit einem Beleg für jede "
            "Aussage."
        ),
        "verify_email.what_you_get": "Das bekommst du",
        "verify_email.feature_upload_title": "Lade alles hoch",
        "verify_email.feature_upload_body": "Lade PDFs, Dokumente und Notizen hoch. GraphMind extrahiert den Text Kapitel für Kapitel und verfolgt jede Datei durch die gesamte Verarbeitung.",
        "verify_email.feature_answers_title": "Antworten mit Belegen",
        "verify_email.feature_answers_body": "Jede Antwort stützt sich auf deine eigenen Dokumente und verlinkt per Zitat genau zu dem Kapitel, aus dem sie stammt. Kein Beleg, keine Antwort.",
        "verify_email.feature_connections_title": "Verbindungen erkennen",
        "verify_email.feature_connections_body": "Personen, Organisationen, Projekte, Produkte und Orte werden automatisch in einem Wissensgraphen erfasst, den du visuell erkunden oder als Liste durchsehen kannst.",
        "verify_email.how_it_works": "So funktioniert's",
        "verify_email.step_add_title": "Füge deine Dokumente hinzu",
        "verify_email.step_add_body": "Lade eine Datei oder einen ganzen Ordner hoch. Verfolge, wie jede von „Hochgeladen“ zu „Bereit“ wechselt.",
        "verify_email.step_ask_title": "Frage in einfacher Sprache",
        "verify_email.step_ask_body": "Grenze den Umfang auf die Dokumente ein, die dich interessieren, und frag einfach.",
        "verify_email.step_follow_title": "Folge dem Beleg",
        "verify_email.step_follow_body": "Öffne jedes Zitat, um zur Quelle zu gelangen, oder springe zum Graphen, um zu sehen, wie alles zusammenhängt.",
        "verify_email.fallback_intro": "Button funktioniert nicht? Kopiere diesen Link in deinen Browser:",
        "verify_email.expiry": "Dieser Link läuft in {expire_hours} Stunden ab.",
        "verify_email.ignore": "Falls du kein GraphMind-Konto erstellt hast, kannst du diese E-Mail ignorieren.",
        "verify_email.footer_tagline": "GraphMind — Intelligenter Dokumentenassistent",
        "verify_email.footer_copyright": "Du erhältst diese E-Mail, weil mit dieser Adresse ein GraphMind-Konto erstellt wurde.",
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
