"""
WhalWatch Bot — Django 5.2 Settings
Reference: https://docs.djangoproject.com/en/5.2/ref/settings/
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ───────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-me-in-production")
DEBUG = os.environ.get("DEBUG", "False") == "True"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:8000")

ALLOWED_HOSTS_ENV = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = (
    ALLOWED_HOSTS_ENV.split(",")
    if ALLOWED_HOSTS_ENV
    else ["localhost", "127.0.0.1", ".railway.app", ".wasmer.io", ".devtunnels.ms", "healthcheck.railway.app"]
)

# Derive host from WEBHOOK_URL for ALLOWED_HOSTS
_webhook_host = WEBHOOK_URL.replace("https://", "").replace("http://", "").split("/")[0]
if _webhook_host and _webhook_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_webhook_host)

CSRF_TRUSTED_ORIGINS = [WEBHOOK_URL, "http://localhost:8000"]

# ── Application definition ──────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Sites framework — required by allauth
    # https://docs.djangoproject.com/en/5.2/ref/contrib/sites/
    "django.contrib.sites",
    # django-allauth
    # https://docs.allauth.org/en/latest/installation/quickstart.html
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    # Project apps
    "bot.accounts",
    "bot.core",
    "bot.directory",
    "bot.memecoin",

    # Subapps — needed so Celery autodiscover finds tasks in subpackages
    # and so Django can import these modules cleanly
    "bot.memecoin.scanner",
    "bot.memecoin.deployer",
    "bot.memecoin.rugcheck",
    "bot.memecoin.pumpfun",
    "bot.memecoin.whale_entry",
    "bot.memecoin.momentum",
    "bot.digest",
    "bot.dormant",
    "bot.scoring",
    "bot.prices",
    "bot.blockchain",
    "bot.exchange_flow",
    "bot.token_alerts",
    "bot.thresholds",
    "bot.multichain",
    "bot.copy_trade",
    "bot.nft"
]

SITE_ID = 1  # Required by allauth

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # allauth AccountMiddleware — must come after SessionMiddleware
    # https://docs.allauth.org/en/latest/account/advanced.html
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "bot" / "accounts" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                # request — required by allauth
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# ── Database ────────────────────────────────────────────────────────────────────
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# https://github.com/jazzband/dj-database-url
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3"),
        conn_max_age=600,
    )
}

# ── Cache / Redis ───────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ── Celery ──────────────────────────────────────────────────────────────────────
# https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "celery.beat:PersistentScheduler"
CELERY_BEAT_SCHEDULE_FILENAME = str(BASE_DIR / "celerybeatdb" / "celerybeat-schedule")

# ── Authentication ─────────────────────────────────────────────────────────────
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    # Django's default model backend
    "django.contrib.auth.backends.ModelBackend",
    # allauth auth backend
    "allauth.account.auth_backends.AuthenticationBackend",
]

# ── allauth account config ──────────────────────────────────────────────────────
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER = "bot.accounts.adapters.WhaleWatchAccountAdapter"

# v65 syntax: use dict for LOGIN_METHODS, list for SIGNUP_FIELDS
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True

# mandatory — user cannot log in until email is verified
# https://docs.allauth.org/en/latest/account/configuration.html#account-email-verification
ACCOUNT_EMAIL_VERIFICATION = "mandatory"

# 6-digit code instead of click-link (better UX on mobile)
# https://docs.allauth.org/en/latest/account/configuration.html#account-email-verification-by-code-enabled
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True

LOGIN_REDIRECT_URL = "/accounts/dashboard/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

# Rate limits — protect signup and login endpoints
# https://docs.allauth.org/en/latest/account/rate-limits.html
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m",
    "signup": "20/1h",
}

SITE_NAME = "Cryptocate"

# ── allauth social account config ───────────────────────────────────────────────
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER = "bot.accounts.adapters.WhaleWatchSocialAccountAdapter"

# Google and GitHub already verify emails — no second verification needed
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

# Auto-connect social login if email matches existing local account
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_EMAIL_REQUIRED = True

# OAuth2 provider credentials — loaded from environment
# https://docs.allauth.org/en/latest/socialaccount/provider_configuration.html
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        # https://docs.allauth.org/en/latest/socialaccount/providers/google.html
        "APPS": [
            {
                "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                "key": "",
            }
        ],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        # Trust Google's email verification
        "VERIFIED_EMAIL": True,
    },
}

# ── Email backend ───────────────────────────────────────────────────────────────
# https://docs.djangoproject.com/en/5.2/topics/email/
# Local dev: console backend (no SMTP config needed)
# Production: set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Cryptocate <noreply@cryptocate.com>",
)

# ── Internationalisation ────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static files ────────────────────────────────────────────────────────────────
# https://whitenoise.readthedocs.io/en/stable/django.html
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Default primary key ─────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Telegram ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ── Blockchain APIs ─────────────────────────────────────────────────────────────
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
ARBISCAN_API_KEY = os.environ.get("ARBISCAN_API_KEY", "") or ETHERSCAN_API_KEY
BASESCAN_API_KEY = os.environ.get("BASESCAN_API_KEY", "") or ETHERSCAN_API_KEY

# ── Paddle Billing ──────────────────────────────────────────────────────────────
PADDLE_API_KEY = os.environ.get("PADDLE_API_KEY", "")
PADDLE_WEBHOOK_SECRET = os.environ.get("PADDLE_WEBHOOK_SECRET", "")
PADDLE_PRICE_ID = os.environ.get("PADDLE_PRICE_ID", "")
PADDLE_SANDBOX = os.environ.get("PADDLE_SANDBOX", "True") == "True"

# ── CoinGecko ──────────────────────────────────────────────────────────────────
# Demo API key — free at https://www.coingecko.com/en/api/pricing
# Auth header: x-cg-demo-api-key (recommended over query param)
# Reference: https://docs.coingecko.com/v3.0.1/reference/authentication
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

# ── Memecoin ────────────────────────────────────────────────────────────────────
RUGCHECK_API_KEY = os.environ.get("RUGCHECK_API_KEY", "")
MEME_SCAN_ENABLED = os.environ.get("MEME_SCAN_ENABLED", "True") == "True"
MEME_MIN_LIQUIDITY_USD = float(os.environ.get("MEME_MIN_LIQUIDITY_USD", "5000"))
MEME_MIN_BUYS_1H = int(os.environ.get("MEME_MIN_BUYS_1H", "20"))
PUMP_FUN_GRADUATION_MCAP = int(os.environ.get("PUMP_FUN_GRADUATION_MCAP", "69000"))