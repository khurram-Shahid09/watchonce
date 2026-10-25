"""Recording upload (docs/10-api-spec.md "Recordings").

1. ``POST /recordings`` creates the row and returns presigned PUT URLs (15 min).
2. The client PUTs ``events.json`` and every frame straight to object storage.
3. ``POST /recordings/{id}/complete`` checks the objects exist and enqueues compile.
"""

import json
from datetime import timedelta
from typing import cast

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User
from accounts.views_base import OrgScopedViewMixin
from audit.service import record
from common.exceptions import ApiError
from common.storage import get_storage

from .models import Recording
from .serializers import RecordingCreatedSerializer, RecordingCreateSerializer, RecordingSerializer

EVENTS = "events.json"
CANDIDATES = "candidates.json"


class RecordingListView(OrgScopedViewMixin, generics.ListCreateAPIView):
    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer

    @extend_schema(request=RecordingCreateSerializer, responses={201: RecordingCreatedSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        data = RecordingCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        recording = Recording.objects.create(
            org=self.org,
            user=cast(User, request.user),
            description=data.validated_data["description"],
            start_url=data.validated_data["start_url"],
            event_count=data.validated_data["event_count"],
            duration_ms=data.validated_data.get("duration_ms"),
            frame_names=data.validated_data["frames"],
        )
        record(
            "recording.created",
            org=self.org,
            request=request,
            entity=recording,
            metadata={"events": recording.event_count, "frames": recording.frame_count},
        )
        storage = get_storage()
        ttl = settings.RECORDING_UPLOAD_URL_TTL
        recording.upload = {  # type: ignore[attr-defined]  # response only
            "events_url": storage.presign_put(recording.key(EVENTS), "application/json", ttl),
            "frames": [
                {"name": name, "url": storage.presign_put(recording.key(name), "image/webp", ttl)}
                for name in recording.frame_names
            ],
            "expires_at": timezone.now() + timedelta(seconds=ttl),
        }
        return Response(RecordingCreatedSerializer(recording).data, status=status.HTTP_201_CREATED)


class RecordingDetailView(OrgScopedViewMixin, generics.RetrieveAPIView):
    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    lookup_url_kwarg = "recording_id"


class RecordingCompleteView(OrgScopedViewMixin, generics.GenericAPIView):
    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    lookup_url_kwarg = "recording_id"

    @extend_schema(request=None, responses={202: RecordingSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        with transaction.atomic():
            recording = (
                self.get_queryset().select_for_update().filter(pk=kwargs["recording_id"]).first()
            )
            if recording is None:
                raise NotFound("Recording not found.")
            if recording.status == Recording.Status.UPLOADING:  # else: already done, idempotent
                _verify_upload(recording)
                recording.status = Recording.Status.UPLOADED
                recording.uploaded_at = timezone.now()
                recording.save(update_fields=["status", "uploaded_at", "updated_at"])
                record("recording.uploaded", org=self.org, request=request, entity=recording)
                transaction.on_commit(lambda: _enqueue_compile(recording.id))
        return Response(RecordingSerializer(recording).data, status=status.HTTP_202_ACCEPTED)


def _verify_upload(recording: Recording) -> None:
    storage = get_storage()
    sizes = {name: storage.size(recording.key(name)) for name in [EVENTS, *recording.frame_names]}
    missing = [name for name, size in sizes.items() if size is None]
    if missing:
        raise ApiError(
            "upload_incomplete",
            f"{len(missing)} file(s) haven't been uploaded yet.",
            status_code=409,
            details={"missing": missing[:20]},
        )
    too_big = [name for name, size in sizes.items() if (size or 0) > _max_bytes(name)]
    if too_big:
        raise ApiError(
            "file_too_large",
            "Some uploaded files are larger than allowed.",
            status_code=413,
            details={"files": too_big[:20]},
        )


def _max_bytes(name: str) -> int:
    if name == EVENTS:
        return settings.RECORDING_MAX_EVENTS_BYTES
    return settings.RECORDING_MAX_FRAME_BYTES


def _enqueue_compile(recording_id: str) -> None:
    from engine.compiler.tasks import compile_recording

    compile_recording.delay(recording_id)


class RecordingCandidatesView(OrgScopedViewMixin, generics.GenericAPIView):
    """Normalized candidate steps (input to the Understand stage). For debugging and the
    dashboard's raw view; shape is in engine/compiler/normalize.py."""

    queryset = Recording.objects.all()
    serializer_class = RecordingSerializer
    lookup_url_kwarg = "recording_id"

    @extend_schema(responses={200: dict})
    def get(self, request: Request, *args, **kwargs) -> Response:
        recording = self.get_object()
        if recording.candidate_count is None:
            raise ApiError(
                "candidates_not_ready",
                "This recording hasn't been processed yet.",
                status_code=409,
                details={"status": recording.status},
            )
        return Response(json.loads(get_storage().get_bytes(recording.key(CANDIDATES))))
