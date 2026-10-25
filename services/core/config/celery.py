import os

from celery import Celery
from kombu import Exchange, Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("watchonce")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Explicit exchange + routing key per queue. Without them Celery binds every queue to the
# default ("compile") exchange/key, so run and heal tasks could be consumed by compile workers.
app.conf.task_queues = tuple(
    Queue(q, Exchange(q), routing_key=q) for q in ("compile", "run", "heal")
)
# Task modules outside Django apps (autodiscovery only searches INSTALLED_APPS).
app.conf.imports = ("engine.compiler.tasks",)
app.autodiscover_tasks()
