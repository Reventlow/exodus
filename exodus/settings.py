"""Django settings for exodus project."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-me-in-production-exodus-wod-2024",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "accounts",
    "characters",
    "agencies",
    "comms",
    "npcs",
    "news",
    "starmap",
    "starships",
    "spacebattle",
    "gm_workspace",
    "exodus",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "exodus.mcp_auth.MCPTokenAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "exodus.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "exodus.context_processors.version",
                "exodus.context_processors.changelog",
                "exodus.context_processors.game_date",
                "comms.context_processors.unread_count",
                "exodus.context_processors.impersonation",
                "exodus.context_processors.map_visibility",
                "gm_workspace.context_processors.shared_briefs_count",
            ],
        },
    },
]

WSGI_APPLICATION = "exodus.wsgi.application"
ASGI_APPLICATION = "exodus.asgi.application"

# Channel Layers (WebSocket backend)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("DATABASE_DIR", BASE_DIR)) / "db.sqlite3",
        "OPTIONS": {
            # Bump SQLite's busy-wait so concurrent writes back off cleanly
            # instead of raising ``database is locked`` under contention.
            # Default is 5 seconds; 20 seconds gives ample headroom for
            # Daphne worker threads doing per-request writes (sessions,
            # section PATCHes, etc.) without ever timing out in practice.
            "timeout": 20,
            "init_command": (
                # WAL mode lets readers run while a writer holds the write
                # lock and dramatically reduces SQLITE_BUSY frequency under
                # concurrent load. Required for the optimistic-concurrency
                # CAS on agency / base section PATCHes to behave correctly
                # under real-world contention.
                "PRAGMA journal_mode=WAL;"
                # ``synchronous=NORMAL`` is safe in WAL mode and faster
                # than the SQLite default of FULL.
                "PRAGMA synchronous=NORMAL;"
                # Foreign keys (Django relies on these for CASCADE).
                "PRAGMA foreign_keys=ON;"
            ),
            # Use BEGIN IMMEDIATE for transactions so the write lock is
            # acquired at BEGIN time. Without this, two concurrent
            # transactions can both BEGIN-DEFERRED + SELECT, and when the
            # second one tries to UPDATE it fails *immediately* with
            # ``database is locked`` (SQLite refuses the read-to-write
            # upgrade to avoid deadlock — the busy_timeout doesn't apply).
            # IMMEDIATE makes BEGIN itself wait on the busy timeout, which
            # serialises concurrent writers cleanly.
            "transaction_mode": "IMMEDIATE",
        },
        "TEST": {
            # Use a file-based test DB instead of the default in-memory
            # shared-cache backend. The shared-cache backend's
            # connection-level isolation has known thread-safety issues
            # with the Python sqlite3 driver under concurrent writes
            # (LiveServerTestCase spins per-request threads), which
            # produces spurious 500s in the concurrent-write regression
            # tests. A file-backed DB matches production semantics
            # (Daphne writes to /app/data/db.sqlite3) and serialises
            # concurrent writes cleanly via SQLite's file lock.
            "NAME": Path(BASE_DIR) / "test_db.sqlite3",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_DIR", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# HTTPS behind reverse proxy (Nginx Proxy Manager)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    "https://exodus.blacklog.net",
]
