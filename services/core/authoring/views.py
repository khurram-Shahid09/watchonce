"""Authoring (docs/17-authoring-agent.md): build a workflow from instructions, or rebuild one whose
run failed, with the agent working live in a browser."""

from typing import Any, cast

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User
from accounts.views_base import OrgScopedViewMixin, resolve_membership
from audit.service import record
from common import quotas
from common.exceptions import ApiError
from runs import live
from runs.models import Run
from runs.views import stream_events

from .models import AuthoringSession
from .serializers import (
    AuthoringCreateSerializer,
    AuthoringDecisionSerializer,
    AuthoringSessionSerializer,
)


def _enqueue(session_id: str) -> None:
    from engine.runner.tasks import author_session

    author_session.delay(session_id)


def fix_instructions(run: Run, hint: str) -> str:
    """What the agent is told when it rebuilds a workflow whose run failed."""
    spec = run.version.spec
    lines = [f"Task: {spec.get('name', '')}. {spec.get('description', '')}".strip()]
    lines.append("The current workflow does these steps:")
    lines += [f"{n}. {s.get('intent', '')}" for n, s in enumerate(spec.get("steps", []), 1)]
    failed = next((s for s in spec.get("steps", []) if s.get("id") == run.current_step_id), None)
    where = f"at “{failed['intent']}”" if failed else ""
    lines.append(f"It failed {where}: {run.error_message or run.error_code}".replace("  ", " "))
    if run.inputs:
        lines.append("Use these values: " + "; ".join(f"{k} = {v}" for k, v in run.inputs.items()))
    lines.append(
        "Do the whole task again from the start. Keep the steps that still work, change what "
        "is needed, and follow the user's advice:"
    )
    lines.append(hint.strip() or "(no advice given: find what changed and work around it)")
    return "\n".join(lines)[:8000]


class AuthoringListCreateView(OrgScopedViewMixin, generics.ListCreateAPIView):
    queryset = AuthoringSession.objects.select_related("workflow", "version")
    serializer_class = AuthoringSessionSerializer

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at")

    @extend_schema(request=AuthoringCreateSerializer, responses={202: AuthoringSessionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        data = AuthoringCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        hint = data.validated_data["instructions"]
        run_id = data.validated_data.get("run_id")
        base_version, source_run = None, None
        if run_id:
            source_run = get_object_or_404(
                Run.objects.for_org(self.org).select_related("version", "workflow"), pk=run_id
            )
            if not source_run.finished:
                raise ApiError(
                    "run_not_finished", "Wait for the run to finish first.", status_code=409
                )
            base_version = source_run.version
            start_url = str(base_version.spec.get("start_url", ""))
            instructions = fix_instructions(source_run, hint)
        else:
            start_url = data.validated_data.get("start_url") or ""
            if not start_url:
                raise ApiError(
                    "invalid_request", "Give the link to start from.", status_code=400,
                    details={"start_url": ["Required."]},
                )  # fmt: skip
            instructions = hint
        quotas.check_compiles(self.org)  # building costs AI calls, like a compile

        session = AuthoringSession.objects.create(
            org=self.org,
            user=cast(User, request.user),
            mode=AuthoringSession.Mode.FIX if source_run else AuthoringSession.Mode.CREATE,
            start_url=start_url,
            instructions=instructions,
            base_version=base_version,
            source_run=source_run,
        )
        record(
            "authoring.started", org=self.org, request=request, entity=session,
            metadata={"mode": session.mode, "run_id": run_id or ""},
        )  # fmt: skip
        transaction.on_commit(lambda: _enqueue(session.id))
        return Response(AuthoringSessionSerializer(session).data, status=status.HTTP_202_ACCEPTED)


class AuthoringDetailView(OrgScopedViewMixin, generics.RetrieveAPIView):
    queryset = AuthoringSession.objects.select_related("workflow", "version")
    serializer_class = AuthoringSessionSerializer
    lookup_url_kwarg = "session_id"


class _Owned(OrgScopedViewMixin, generics.GenericAPIView):
    queryset = AuthoringSession.objects.all()
    serializer_class = AuthoringSessionSerializer

    def session_for_update(self, session_id: str) -> AuthoringSession:
        session = get_object_or_404(
            AuthoringSession.objects.for_org(self.org).select_for_update(), pk=session_id
        )
        if not self.membership.is_owner and session.user_id != self.request.user.pk:
            raise exceptions.PermissionDenied(
                "Only the person who started this or an owner can do that.", code="not_allowed"
            )
        return session


class AuthoringDecisionView(_Owned):
    """Approve or decline the risky step the agent is waiting on."""

    @extend_schema(request=AuthoringDecisionSerializer, responses={200: AuthoringSessionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        data = AuthoringDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            session = self.session_for_update(kwargs["session_id"])
            if session.status != AuthoringSession.Status.AWAITING_APPROVAL:
                raise ApiError(
                    "not_waiting", "The agent isn't waiting for approval.", status_code=409,
                    details={"status": session.status},
                )  # fmt: skip
            record(
                f"authoring.step.{data.validated_data['decision']}d", org=self.org, request=request,
                entity=session, metadata={"intent": session.question.get("intent", "")},
            )  # fmt: skip
        live.send_decision(session.id, data.validated_data["decision"])
        return Response(AuthoringSessionSerializer(session).data)


class AuthoringCancelView(_Owned):
    @extend_schema(request=None, responses={200: AuthoringSessionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        with transaction.atomic():
            session = self.session_for_update(kwargs["session_id"])
            if session.finished:
                return Response(AuthoringSessionSerializer(session).data)
            if session.status == AuthoringSession.Status.QUEUED:
                session.status = AuthoringSession.Status.CANCELLED
                session.error_code = "cancelled"
                session.error_message = "Cancelled before it started."
                session.save(update_fields=["status", "error_code", "error_message", "updated_at"])
            record("authoring.cancel_requested", org=self.org, request=request, entity=session)
        live.request_cancel(session.id)
        return Response(AuthoringSessionSerializer(session).data)


def _authorize(request: HttpRequest, session_id: str) -> dict[str, Any]:
    from rest_framework.views import APIView

    drf_request = APIView().initialize_request(request)
    if not drf_request.user or not drf_request.user.is_authenticated:
        raise exceptions.NotAuthenticated()
    membership = resolve_membership(drf_request)
    session = (
        AuthoringSession.objects.for_org(membership.org)
        .select_related("workflow", "version")
        .filter(pk=session_id)
        .first()
    )
    if session is None:
        raise exceptions.NotFound("Not found.")
    return dict(AuthoringSessionSerializer(session).data)


async def authoring_events(request: HttpRequest, session_id: str):
    """``GET /authoring/{id}/events``: a snapshot, the latest frame, then live events."""
    try:
        snapshot = await sync_to_async(_authorize)(request, session_id)
    except exceptions.APIException as exc:
        code = getattr(exc.detail, "code", None) or exc.default_code
        return JsonResponse(
            {"error": {"code": code, "message": str(exc.detail), "details": {}}},
            status=exc.status_code,
        )
    done = snapshot["status"] if snapshot["status"] in AuthoringSession.FINISHED else None
    return stream_events(session_id, {"type": "snapshot", "session": snapshot}, done_status=done)
