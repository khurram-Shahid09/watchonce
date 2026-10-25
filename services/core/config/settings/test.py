import os

# Tests must not depend on a developer's secrets; provide safe defaults before base reads the env.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production-" + "x" * 20)
os.environ.setdefault("DATABASE_URL", "postgres://watchonce:watchonce@localhost:5433/watchonce")

from .base import *  # noqa: E402, F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only  # noqa: S303
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGE_BACKEND = "memory"
LLM_PROVIDER = "fake"  # tests never call a real AI
