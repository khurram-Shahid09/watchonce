"""Runs (docs/10-api-spec.md "Runs"): start, follow live, approve checkpoints, cancel."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User
from accounts.views_base import OrgScopedViewMixin, resolve_membership
from audit.service import record
from common import quotas
from common.exceptions import ApiError
from common.storage import get_storage
from workflows.models import Workflow

from . import live
from .models import Batch, CheckpointDecision, HealEvent, Run, RunStep
from .serializers import (
    BatchCreateSerializer,
    BatchDetailSerializer,
    BatchSerializer,
    CheckpointDecisionInputSerializer,
    HealDecisionSerializer,
    HealSerializer,
    RunCreateSerializer,
    RunDetailSerializer,
    RunSerializer,
)
from .service import approve_waiting_run, clean_inputs, missing_secrets

SCREENSHOT_TTL = 10 * 60


def _enqueue_run(run_id: str) -> None:
    from engine.runner.tasks import execute_run

    execute_run.delay(run_id)


class WorkflowRunsView(OrgScopedViewMixin, generics.ListCreateAPIView):
    queryset = Run.objects.select_related("version", "workflow")
    serializer_class = RunSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workflow_id=self.kwargs["workflow_id"])
            .order_by("-created_at", "-id")
        )

    @extend_schema(request=RunCreateSerializer, responses={202: RunSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        workflow = get_object_or_404(
            Workflow.objects.for_org(self.org).filter(archived_at__isnull=True),
            pk=kwargs["workflow_id"],
        )
        data = RunCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        wanted = data.validated_data.get("version")
        version = (
            workflow.versions.filter(version=wanted).first() if wanted else workflow.active_version
        )
        if version is None:
            raise ApiError("version_not_found", "That version doesn't exist.", status_code=404)

        inputs, errors = clean_inputs(version.spec, data.validated_data["inputs"])
        if errors:
            raise ApiError(
                "invalid_inputs",
                "Some inputs need fixing.",
                status_code=422,
                details={"inputs": errors},
            )
        missing = missing_secrets(self.org, version.spec)
        if missing:
            raise ApiError(
                "missing_secrets",
                "Save the logins this workflow uses before running it.",
                status_code=409,
                details={"missing": missing},
            )
        quotas.check_runs(self.org)
        run = Run.objects.create(
            org=self.org,
            workflow=workflow,
            version=version,
            user=cast(User, request.user),
            triggered_by=f"user:{request.user.pk}",
            inputs=inputs,
        )
        record(
            "run.started",
            org=self.org,
            request=request,
            entity=run,
            metadata={"workflow_id": workflow.id, "version": version.version},
        )
        transaction.on_commit(lambda: _enqueue_run(run.id))
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class RunListView(OrgScopedViewMixin, generics.ListAPIView):
    queryset = Run.objects.select_related("version", "workflow")
    serializer_class = RunSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("workflow_id", str, required=False),
            OpenApiParameter("status", str, required=False),
        ]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if wf := self.request.query_params.get("workflow_id"):
            qs = qs.filter(workflow_id=wf)
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        return qs


class RunDetailView(OrgScopedViewMixin, generics.RetrieveAPIView):
    queryset = Run.objects.select_related("version", "workflow").prefetch_related(
        "steps", "decisions__decided_by"
    )
    serializer_class = RunDetailSerializer
    lookup_url_kwarg = "run_id"


class RunCancelView(OrgScopedViewMixin, generics.GenericAPIView):
    queryset = Run.objects.select_related("version", "workflow")
    serializer_class = RunSerializer
    lookup_url_kwarg = "run_id"

    @extend_schema(request=None, responses={202: RunSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        run = self.get_object()
        if run.finished:
            raise ApiError("run_finished", "This run has already finished.", status_code=409)
        if run.status == Run.Status.QUEUED:
            # Not picked up yet: cancel right here; the runner skips cancelled runs.
            Run.objects.filter(pk=run.pk, status=Run.Status.QUEUED).update(
                status=Run.Status.CANCELLED, finished_at=timezone.now(), error_code="cancelled"
            )
        live.request_cancel(run.id)
        record("run.cancel_requested", org=self.org, request=request, entity=run)
        run.refresh_from_db()
        return Response(RunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class CheckpointDecisionView(OrgScopedViewMixin, generics.GenericAPIView):
    """Approve or reject the step a run is waiting on. Owners can decide on any run;
    members on runs they started (docs/11 roles)."""

    queryset = Run.objects.select_related("version", "workflow")
    serializer_class = RunSerializer
    lookup_url_kwarg = "run_id"

    @extend_schema(request=CheckpointDecisionInputSerializer, responses={200: RunSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        data = CheckpointDecisionInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            run = get_object_or_404(
                Run.objects.for_org(self.org).select_for_update(), pk=kwargs["run_id"]
            )
            if not self.membership.is_owner and run.user_id != request.user.pk:
                raise exceptions.PermissionDenied(
                    "Only the person who started this run or an owner can decide.",
                    code="not_allowed",
                )
            if (
                run.status != Run.Status.AWAITING_APPROVAL
                or run.current_step_id != kwargs["step_id"]
            ):
                raise ApiError(
                    "not_waiting",
                    "This run isn't waiting for approval at that step.",
                    status_code=409,
                    details={"status": run.status, "current_step_id": run.current_step_id},
                )
            waiting = (
                RunStep.objects.filter(run=run, step_id=kwargs["step_id"]).order_by("-seq").first()
            )
            decision = CheckpointDecision.objects.create(
                org=self.org,
                run=run,
                step_id=kwargs["step_id"],
                decision=data.validated_data["decision"],
                decided_by=cast(User, request.user),
                note=data.validated_data.get("note", ""),
                screenshot_ref=waiting.screenshot_ref if waiting else "",
            )
            # The runner sets the next status; this marks that someone answered.
            run.status = Run.Status.RUNNING
            run.save(update_fields=["status", "updated_at"])
            record(
                f"run.checkpoint.{decision.decision}d",
                org=self.org,
                request=request,
                entity=run,
                metadata={"step_id": decision.step_id, "note": decision.note},
            )
            transaction.on_commit(lambda: live.send_decision(run.id, decision.decision))
        return Response(RunSerializer(run).data)


class RunScreenshotView(OrgScopedViewMixin, generics.GenericAPIView):
    queryset = Run.objects.all()
    serializer_class = RunSerializer
    lookup_url_kwarg = "run_id"
    throttle_classes: list = []  # a run page loads one per step; each is just a redirect

    @extend_schema(responses={302: None})
    def get(self, request: Request, *args, **kwargs) -> HttpResponseRedirect:
        run = self.get_object()
        name = kwargs["name"]
        if not (
            RunStep.objects.filter(run=run, screenshot_ref=name).exists()
            or HealEvent.objects.filter(run=run, after_image_ref=name).exists()
            or CheckpointDecision.objects.filter(run=run, screenshot_ref=name).exists()
        ):
            raise exceptions.NotFound("Screenshot not found.")
        response = HttpResponseRedirect(
            get_storage().presign_get(run.artifacts_prefix + name, SCREENSHOT_TTL)
        )
        response["Cache-Control"] = f"private, max-age={SCREENSHOT_TTL // 2}"
        return response


# --- Live events (Server-Sent Events) ---
#
# The dashboard proxies this stream through its own server (it holds the session), so a
# plain HTTP stream is simpler than a WebSocket there: one direction is all live view needs;
# approvals go through the REST endpoint above.

HEARTBEAT_S = 15


def _authorize(request: HttpRequest, run_id: str) -> dict[str, Any]:
    """DRF authentication + tenancy for a plain Django view; returns the run snapshot."""
    from rest_framework.views import APIView

    view = APIView()
    drf_request = view.initialize_request(request)
    if not drf_request.user or not drf_request.user.is_authenticated:
        raise exceptions.NotAuthenticated()
    membership = resolve_membership(drf_request)
    run = (
        Run.objects.for_org(membership.org)
        .select_related("version", "workflow")
        .prefetch_related("steps", "decisions__decided_by")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        raise exceptions.NotFound("Run not found.")
    return dict(RunDetailSerializer(run).data)


def _sse(event: dict[str, Any]) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n".encode()


async def run_events(request: HttpRequest, run_id: str):
    """``GET /runs/{id}/events``: a snapshot, the latest frame, then live events until done."""
    try:
        snapshot = await sync_to_async(_authorize)(request, run_id)
    except exceptions.APIException as exc:
        code = getattr(exc.detail, "code", None) or exc.default_code
        return JsonResponse(
            {"error": {"code": code, "message": str(exc.detail), "details": {}}},
            status=exc.status_code,
        )

    import redis.asyncio as aredis
    from django.conf import settings

    async def stream() -> AsyncIterator[bytes]:
        conn = aredis.Redis.from_url(settings.REDIS_URL)
        pubsub = conn.pubsub()
        await pubsub.subscribe(live.events_channel(run_id))  # before the snapshot: no gaps
        try:
            yield _sse({"type": "snapshot", "run": snapshot})
            frame = await sync_to_async(live.last_frame)(run_id)
            if frame:
                yield _sse(frame)
            if snapshot["status"] in Run.FINISHED:
                yield _sse({"type": "done", "status": snapshot["status"]})
                return
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_S
                )
                if message is None:
                    yield b": keep-alive\n\n"
                    continue
                event = json.loads(message["data"])
                yield _sse(event)
                if event.get("type") == "done":
                    return
        except asyncio.CancelledError:  # the viewer went away
            raise
        finally:
            await pubsub.aclose()
            await conn.aclose()

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Caddy/nginx: don't buffer the stream
    return response


# --- Heals (docs/10-api-spec.md "Heals") ---


class HealListView(OrgScopedViewMixin, generics.ListAPIView):
    queryset = HealEvent.objects.select_related("run__version", "resulting_version", "decided_by")
    serializer_class = HealSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("workflow_id", str, required=False),
            OpenApiParameter("decision", str, required=False),
        ]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if wf := self.request.query_params.get("workflow_id"):
            qs = qs.filter(workflow_id=wf)
        if decision := self.request.query_params.get("decision"):
            qs = qs.filter(decision=decision)
        return qs


class HealDetailView(OrgScopedViewMixin, generics.RetrieveAPIView):
    queryset = HealEvent.objects.select_related("run__version", "resulting_version", "decided_by")
    serializer_class = HealSerializer
    lookup_url_kwarg = "heal_id"


class HealDecisionView(OrgScopedViewMixin, generics.GenericAPIView):
    """Approve: the healed version becomes the one that runs. Reject: it is archived.
    Every heal saved in that version gets the same decision (owners only)."""

    queryset = HealEvent.objects.select_related("run__version", "resulting_version", "decided_by")
    serializer_class = HealSerializer
    lookup_url_kwarg = "heal_id"
    owner_methods = frozenset({"POST"})

    @extend_schema(request=HealDecisionSerializer, responses={200: HealSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        from workflows.models import WorkflowVersion
        from workflows.service import activate_version

        data = HealDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        heal = self.get_object()
        version = heal.resulting_version
        if heal.decision != HealEvent.Decision.PENDING or version is None:
            raise ApiError("already_decided", "This heal was already decided.", status_code=409)
        approve = data.validated_data["decision"] == "approve"
        with transaction.atomic():
            if approve:
                activate_version(version)
            elif version.status == WorkflowVersion.Status.PENDING_HEAL:
                version.status = WorkflowVersion.Status.ARCHIVED
                version.save(update_fields=["status", "updated_at"])
            HealEvent.objects.for_org(self.org).filter(resulting_version=version).update(
                decision=HealEvent.Decision.APPROVED if approve else HealEvent.Decision.REJECTED,
                decided_by=request.user,
                decided_at=timezone.now(),
            )
            record(
                "heal.approved" if approve else "heal.rejected",
                org=self.org,
                request=request,
                entity=version,
                metadata={"heal_id": heal.id, "version": version.version},
            )
        heal.refresh_from_db()
        return Response(HealSerializer(heal).data)


# --- Batches (docs/10-api-spec.md "Runs": batches) ---


def _enqueue_batch(batch_id: str) -> None:
    from engine.runner.tasks import execute_batch

    execute_batch.delay(batch_id)


class WorkflowBatchesView(OrgScopedViewMixin, generics.ListCreateAPIView):
    queryset = Batch.objects.select_related("version", "workflow", "approved_by")
    serializer_class = BatchSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workflow_id=self.kwargs["workflow_id"])
            .order_by("-created_at", "-id")
        )

    @extend_schema(
        request={"multipart/form-data": BatchCreateSerializer}, responses={202: BatchSerializer}
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        from .batches import BatchFileError, default_column_map, parse_csv, validate_rows

        workflow = get_object_or_404(
            Workflow.objects.for_org(self.org).filter(archived_at__isnull=True),
            pk=kwargs["workflow_id"],
        )
        data = BatchCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        wanted = data.validated_data.get("version")
        version = (
            workflow.versions.filter(version=wanted).first() if wanted else workflow.active_version
        )
        if version is None:
            raise ApiError("version_not_found", "That version doesn't exist.", status_code=404)
        upload = data.validated_data["file"]
        try:
            columns, rows = parse_csv(upload.read())
        except BatchFileError as exc:
            raise ApiError("invalid_file", str(exc), status_code=422) from None
        column_map = data.validated_data.get("column_map") or default_column_map(
            version.spec, columns
        )
        if not isinstance(column_map, dict) or any(c not in columns for c in column_map.values()):
            raise ApiError(
                "invalid_column_map",
                "column_map must map input names to CSV columns.",
                status_code=422,
            )
        cleaned, errors = validate_rows(version.spec, rows, column_map)
        if errors:
            raise ApiError(
                "invalid_rows",
                f"{len(errors)} problem(s) in the file. Nothing was started.",
                status_code=422,
                details={
                    "errors": dict(list(errors.items())[:20]),
                    "columns": columns,
                    "column_map": column_map,
                },
            )
        missing = missing_secrets(self.org, version.spec)
        if missing:
            raise ApiError(
                "missing_secrets",
                "Save the logins this workflow uses before running it.",
                status_code=409,
                details={"missing": missing},
            )
        quotas.check_runs(self.org, len(cleaned))
        user = cast(User, request.user)
        with transaction.atomic():
            batch = Batch.objects.create(
                org=self.org,
                workflow=workflow,
                version=version,
                user=user,
                file_name=(getattr(upload, "name", "") or "")[:200],
                columns=columns,
                rows=rows,
                column_map=column_map,
                total=len(rows),
            )
            for n, values in enumerate(cleaned, start=1):
                Run.objects.create(
                    org=self.org,
                    workflow=workflow,
                    version=version,
                    user=user,
                    triggered_by="batch",
                    inputs=values,
                    batch=batch,
                    row_index=n,
                )
            record(
                "batch.started",
                org=self.org,
                request=request,
                entity=batch,
                metadata={
                    "workflow_id": workflow.id,
                    "rows": len(rows),
                    "version": version.version,
                },
            )
            transaction.on_commit(lambda: _enqueue_batch(batch.id))
        return Response(BatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)


class BatchDetailView(OrgScopedViewMixin, generics.RetrieveAPIView):
    queryset = Batch.objects.select_related("version", "workflow", "approved_by").prefetch_related(
        "runs"
    )
    serializer_class = BatchDetailSerializer
    lookup_url_kwarg = "batch_id"


class BatchResultsView(OrgScopedViewMixin, generics.GenericAPIView):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    lookup_url_kwarg = "batch_id"

    @extend_schema(responses={(200, "text/csv"): str})
    def get(self, request: Request, *args, **kwargs) -> HttpResponse:
        from .batches import results_csv

        batch = self.get_object()
        body = results_csv(batch, list(batch.runs.all()))
        # The byte-order mark makes Excel read the file as UTF-8.
        response = HttpResponse("﻿" + body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="results-{batch.id}.csv"'
        return response


class BatchApproveAllView(OrgScopedViewMixin, generics.GenericAPIView):
    """Approve every checkpoint of this batch from now on, including the one waiting now.
    Owners only, after reviewing a checkpoint (docs/08 "Batch runs")."""

    queryset = Batch.objects.select_related("version", "workflow", "approved_by")
    serializer_class = BatchSerializer
    lookup_url_kwarg = "batch_id"
    owner_methods = frozenset({"POST"})

    @extend_schema(request=None, responses={200: BatchSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        batch = self.get_object()
        if batch.status in (Batch.Status.FINISHED, Batch.Status.CANCELLED):
            raise ApiError("batch_finished", "This batch has already finished.", status_code=409)
        user = cast(User, request.user)
        batch.approve_all, batch.approved_by = True, user
        batch.save(update_fields=["approve_all", "approved_by", "updated_at"])
        record(
            "batch.approved_all",
            org=self.org,
            request=request,
            entity=batch,
            metadata={"rows": batch.total},
        )
        for run in batch.runs.filter(status=Run.Status.AWAITING_APPROVAL):
            approve_waiting_run(run, user, "Approved for the whole batch")
        return Response(BatchSerializer(batch).data)


class BatchCancelView(OrgScopedViewMixin, generics.GenericAPIView):
    queryset = Batch.objects.select_related("version", "workflow", "approved_by")
    serializer_class = BatchSerializer
    lookup_url_kwarg = "batch_id"

    @extend_schema(request=None, responses={202: BatchSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        batch = self.get_object()
        if batch.status in (Batch.Status.FINISHED, Batch.Status.CANCELLED):
            raise ApiError("batch_finished", "This batch has already finished.", status_code=409)
        batch.status = Batch.Status.CANCELLED
        batch.finished_at = timezone.now()
        batch.save(update_fields=["status", "finished_at", "updated_at"])
        batch.runs.filter(status=Run.Status.QUEUED).update(
            status=Run.Status.CANCELLED, error_code="cancelled", finished_at=timezone.now()
        )
        for run in batch.runs.filter(status__in=[Run.Status.RUNNING, Run.Status.AWAITING_APPROVAL]):
            live.request_cancel(run.id)
        record("batch.cancelled", org=self.org, request=request, entity=batch)
        return Response(BatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)
