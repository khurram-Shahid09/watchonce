"""Settings shared by every environment. Environment-specific overrides live in dev/prod/test."""

from datetime import timedelta
from pathlib import Path

import environ

CORE_DIR = Path(__file__).resolve().parents[2]  # services/core
REPO_ROOT = CORE_DIR.parents[1]

env = environ.Env()
# Local development reads the repo-root .env. In containers the variables come from the environment.
if (REPO_ROOT / ".env").is_file():
    # parse_comments: .env.example documents values with trailing "# ..." comments.
    env.read_env(str(REPO_ROOT / ".env"), overwrite=False, parse_comments=True)

APP_ENV = env.str("APP_ENV", default="local")
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
APP_BASE_URL = env.str("APP_BASE_URL", default="http://localhost:3000")
API_BASE_URL = env.str("API_BASE_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "channels",
    "rest_framework_simplejwt.token_blacklist",
    # watchonce
    "common",
    "accounts",
    "audit",
    "recordings",
    "workflows",
    "metering",
    "secrets_vault",
    "runs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = CORE_DIR / "staticfiles"

REDIS_URL = env.str("REDIS_URL", default="redis://localhost:6379/0")

# --- DRF / OpenAPI ---
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.PersonalAccessTokenAuthentication",  # "Bearer pat_..."
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # "Bearer <jwt>"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.CursorPagination",
    "DEFAULT_THROTTLE_RATES": {
        "login_ip": "20/min",
        "login_email": "5/min",  # with login_ip: brute-force lockout per account
        "register": "10/hour",
    },
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "WatchOnce API",
    "DESCRIPTION": "Record a browser task once; run it deterministically; self-heal on UI change.",
    "VERSION": "1.0.0",
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Several models have a "status" field with different choices; name each enum.
    "ENUM_NAME_OVERRIDES": {
        "RecordingStatusEnum": "recordings.models.Recording.Status",
        "VersionStatusEnum": "workflows.models.WorkflowVersion.Status",
        "RunStatusEnum": "runs.models.Run.Status",
        "RunStepStatusEnum": "runs.models.RunStep.Status",
        "HealDecisionEnum": "runs.models.HealEvent.Decision",
        "ApproveRejectEnum": ["approve", "reject"],
    },
}

# --- Auth tokens (docs/10-api-spec.md) ---
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "AUTH_HEADER_TYPES": ("Bearer",),
}
REFRESH_COOKIE = {
    "key": "wo_refresh",
    "path": "/api/v1/auth/",
    "httponly": True,
    "secure": not DEBUG,
    "samesite": "Lax",  # served first-party through the dashboard's proxy (see docs/03)
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
}

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# --- Channels ---
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# --- Celery ---
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_DEFAULT_QUEUE = "compile"
CELERY_TASK_ROUTES = {
    "engine.compiler.*": {"queue": "compile", "routing_key": "compile"},
    "engine.runner.*": {"queue": "run", "routing_key": "run"},
    "engine.healer.*": {"queue": "heal", "routing_key": "heal"},
}

# --- Object storage (SeaweedFS locally, R2 in production; common/storage.py) ---
STORAGE_BACKEND = env.str("STORAGE_BACKEND", default="s3")  # "memory" in tests
S3_ENDPOINT = env.str("S3_ENDPOINT", default="")
# Host browsers/the extension use for presigned URLs, when it differs from S3_ENDPOINT.
S3_PUBLIC_ENDPOINT = env.str("S3_PUBLIC_ENDPOINT", default="")
S3_REGION = env.str("S3_REGION", default="auto")
S3_BUCKET = env.str("S3_BUCKET", default="")
S3_ACCESS_KEY_ID = env.str("S3_ACCESS_KEY_ID", default="")
S3_SECRET_ACCESS_KEY = env.str("S3_SECRET_ACCESS_KEY", default="")
# Origins allowed to PUT to presigned URLs (bucket CORS, set by `manage.py setup_storage`).
# The presigned URL itself is the credential, so any origin is acceptable.
S3_UPLOAD_CORS_ORIGINS = env.list("S3_UPLOAD_CORS_ORIGINS", default=["*"])

# --- Recordings (docs/07-recorder-extension.md) ---
RECORDING_UPLOAD_URL_TTL = 15 * 60  # seconds
RECORDING_MAX_EVENTS = 5000
RECORDING_MAX_FRAMES = 300
RECORDING_MAX_EVENTS_BYTES = 20 * 1024 * 1024
RECORDING_MAX_FRAME_BYTES = 2 * 1024 * 1024


# --- AI providers (engine/llm, docs/06-ai-pipeline.md) ---
def _setting(name: str, default: str = "") -> str:
    return env.str(name, default=default).strip()  # .env lines may carry padding before "# ..."


LLM_PROVIDER = _setting("LLM_PROVIDER", "gemini").lower()  # claude | gemini | fake
LLM_PROVIDER_UNDERSTAND = _setting("LLM_PROVIDER_UNDERSTAND")
LLM_PROVIDER_SOP = _setting("LLM_PROVIDER_SOP")
LLM_PROVIDER_REPAIR = _setting("LLM_PROVIDER_REPAIR")
ANTHROPIC_API_KEY = _setting("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _setting("CLAUDE_MODEL") or "claude-opus-5-5"
CLAUDE_EFFORT_UNDERSTAND = _setting("CLAUDE_EFFORT_UNDERSTAND") or "high"
CLAUDE_EFFORT_SOP = _setting("CLAUDE_EFFORT_SOP") or "medium"
CLAUDE_EFFORT_REPAIR = _setting("CLAUDE_EFFORT_REPAIR") or "high"
GEMINI_API_KEY = _setting("GEMINI_API_KEY")
GEMINI_MODEL = _setting("GEMINI_MODEL") or "gemini-3.8-flash"
GEMINI_FALLBACK_MODELS = env.list(
    "GEMINI_FALLBACK_MODELS", default=["gemini-3.6-flash", "gemini-3.5-flash"]
)
# Per-workspace monthly AI spend cap; compiles stop with a clear error once reached.
LLM_MONTHLY_BUDGET_USD = env.float("LLM_MONTHLY_BUDGET_USD", default=10.0)
COMPILE_MAX_FRAMES = 25  # screenshots per Understand call
COMPILE_MAX_CANDIDATES = 120

# --- Runner (engine/runner, docs/08) ---
RUN_MAX_SECONDS = env.int("RUN_MAX_SECONDS", default=600)  # time waiting for approval excluded
RUN_CHECKPOINT_TIMEOUT_S = env.int("RUN_CHECKPOINT_TIMEOUT_S", default=30 * 60)
# Hosts a workflow may reach besides its allowed_domains (e.g. a CDN the app loads from).
RUNNER_EXTRA_ALLOWED_HOSTS = env.list("RUNNER_EXTRA_ALLOWED_HOSTS", default=[])

# --- Secrets vault ---
SECRETS_MASTER_KEY = env.str("SECRETS_MASTER_KEY", default="")

# --- Logging: structured-ish single-line logs to stdout ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "line": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "line"}},
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
}
