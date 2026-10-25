"""Workflows and their immutable versions (docs/10-api-spec.md "Workflows")."""

import re
from typing import Any

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.views_base import OrgScopedViewMixin
from audit.service import record
from common.exceptions import ApiError
from common.storage import get_storage
from engine.compiler.sop import render_basic_sop
from engine.spec.validate import validate_spec

from .models import Workflow, WorkflowVersion
from .serializers import (
    VersionCreateSerializer,
    VersionSerializer,
    VersionSummarySerializer,
    WorkflowDetailSerializer,
    WorkflowSerializer,
    WorkflowUpdateSerializer,
)
from .service import activate_version, create_version

SCREENSHOT_TTL = 10 * 60


def _actor(request: Request) -> str:
    return f"user:{request.user.pk}"


class WorkflowListView(OrgScopedViewMixin, generics.ListAPIView):
    queryset = Workflow.objects.select_related("active_version").filter(archived_at__isnull=True)
    serializer_class = WorkflowSerializer


class WorkflowDetailView(OrgScopedViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Workflow.objects.select_related("active_version").prefetch_related("versions")
    serializer_class = WorkflowDetailSerializer
    lookup_url_kwarg = "workflow_id"
    http_method_names = ["get", "patch", "delete"]

    @extend_schema(request=WorkflowUpdateSerializer, responses={200: WorkflowDetailSerializer})
    def patch(self, request: Request, *args, **kwargs) -> Response:
        workflow = self.get_object()
        data = WorkflowUpdateSerializer(workflow, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        data.save()
        record(
            "workflow.updated",
            org=self.org,
            request=request,
            entity=workflow,
            metadata={"fields": sorted(request.data)},
        )
        return Response(WorkflowDetailSerializer(self.get_object()).data)

    def perform_destroy(self, instance: Workflow) -> None:
        """Archive, never delete: runs and audit entries keep pointing at it."""
        if instance.archived_at is None:
            instance.archived_at = timezone.now()
            instance.save(update_fields=["archived_at", "updated_at"])
            record("workflow.archived", org=self.org, request=self.request, entity=instance)


class _VersionMixin(OrgScopedViewMixin):
    kwargs: dict[str, Any]

    def workflow(self) -> Workflow:
        return get_object_or_404(Workflow.objects.for_org(self.org), pk=self.kwargs["workflow_id"])

    def version(self) -> WorkflowVersion:
        return get_object_or_404(
            WorkflowVersion.objects.for_org(self.org).select_related("workflow"),
            workflow_id=self.kwargs["workflow_id"],
            version=self.kwargs["version"],
        )


class VersionListView(_VersionMixin, generics.ListCreateAPIView):
    queryset = WorkflowVersion.objects.all()
    serializer_class = VersionSummarySerializer
    pagination_class = None

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workflow_id=self.kwargs["workflow_id"])
            .order_by("-version")
        )

    def list(self, request: Request, *args, **kwargs) -> Response:
        self.workflow()  # 404 for unknown / foreign workflows
        return super().list(request, *args, **kwargs)

    @extend_schema(request=VersionCreateSerializer, responses={201: VersionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        """Save an edited spec as the next version. ``422 invalid_spec`` lists validator errors."""
        workflow = self.workflow()
        data = VersionCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        activate = data.validated_data["activate"]
        if activate and not self.membership.is_owner:
            raise PermissionDenied(
                "Only workspace owners can activate versions.", code="owner_required"
            )

        result = validate_spec(data.validated_data["spec"])
        if not result.ok:
            raise ApiError(
                "invalid_spec",
                "The workflow has errors and wasn't saved.",
                status_code=422,
                details={
                    "errors": [{"path": i.path, "message": i.message} for i in result.errors],
                    "warnings": [{"path": i.path, "message": i.message} for i in result.warnings],
                },
            )
        spec = data.validated_data["spec"]
        base = data.validated_data.get("base_version")
        parent = workflow.versions.filter(version=base).first() if base else workflow.active_version
        removed = _removed_checkpoints(parent.spec if parent else {}, spec)
        version = create_version(
            workflow,
            spec,
            created_by=_actor(request),
            sop_markdown=render_basic_sop(spec),
            warnings=[f"{i.path}: {i.message}" for i in result.warnings],
            parent=parent,
            change_note=data.validated_data.get("change_note", ""),
            activate=activate,
        )
        record(
            "workflow.version.created",
            org=self.org,
            request=request,
            entity=version,
            metadata={"version": version.version, "activated": activate},
        )
        if removed:  # threat T5: removing a safety stop is always on the record
            record(
                "workflow.checkpoint.removed",
                org=self.org,
                request=request,
                entity=version,
                metadata={"intents": removed},
            )
        if spec.get("name") and spec["name"] != workflow.name:
            workflow.name = spec["name"][:200]
            workflow.save(update_fields=["name", "updated_at"])
        return Response(VersionSerializer(version).data, status=status.HTTP_201_CREATED)


def _removed_checkpoints(old: dict, new: dict) -> list[str]:
    def guarded(spec: dict) -> set[str]:
        return {
            s.get("intent", "")
            for s in spec.get("steps", [])
            if (s.get("checkpoint") or {}).get("type") == "approval"
        }

    return sorted(guarded(old) - guarded(new))


class VersionDetailView(_VersionMixin, generics.GenericAPIView):
    queryset = WorkflowVersion.objects.all()
    serializer_class = VersionSerializer

    def get(self, request: Request, *args, **kwargs) -> Response:
        return Response(VersionSerializer(self.version()).data)


class VersionActivateView(_VersionMixin, generics.GenericAPIView):
    queryset = WorkflowVersion.objects.all()
    serializer_class = VersionSerializer
    owner_methods = frozenset({"POST"})

    @extend_schema(request=None, responses={200: VersionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        version = self.version()
        activate_version(version)
        record(
            "workflow.version.activated",
            org=self.org,
            request=request,
            entity=version,
            metadata={"version": version.version},
        )
        version.refresh_from_db()
        return Response(VersionSerializer(version).data)


class VersionSopView(_VersionMixin, generics.GenericAPIView):
    """Rewrite the SOP of a version with the AI (synchronous; takes up to a minute)."""

    queryset = WorkflowVersion.objects.all()
    serializer_class = VersionSerializer

    @extend_schema(request=None, responses={200: VersionSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        from engine.compiler.pipeline import write_sop
        from metering.service import budget_left

        version = self.version()
        recording = version.workflow.recording
        if recording is None:
            raise ApiError(
                "no_recording",
                "This workflow has no recording to take screenshots from.",
                status_code=409,
            )
        if not budget_left(self.org):
            raise ApiError(
                "budget_exceeded", "This workspace reached its monthly AI budget.", status_code=402
            )
        markdown, info, warnings = write_sop(recording, version.spec)
        if info.get("by") == "plain":  # the AI call failed; keep what's there
            raise ApiError(
                "llm_unavailable",
                "The AI couldn't write the SOP right now. Try again in a few minutes.",
                status_code=503,
                details={"warnings": warnings},
            )
        version.sop_markdown = markdown
        version.compile_info = {**version.compile_info, "sop": info}
        version.save(update_fields=["sop_markdown", "compile_info", "updated_at"])
        record("workflow.sop.regenerated", org=self.org, request=request, entity=version)
        return Response(VersionSerializer(version).data)


class ScreenshotView(_VersionMixin, generics.GenericAPIView):
    """302 to a short-lived link for one of the recording's screenshots."""

    queryset = WorkflowVersion.objects.all()
    serializer_class = VersionSerializer

    @extend_schema(responses={302: None})
    def get(self, request: Request, *args, **kwargs) -> HttpResponseRedirect:
        workflow = self.workflow()
        recording = workflow.recording
        name = kwargs["name"]
        if recording is None or name not in recording.frame_names:
            raise NotFound("Screenshot not found.")
        url = get_storage().presign_get(recording.key(name), SCREENSHOT_TTL)
        response = HttpResponseRedirect(url)
        response["Cache-Control"] = f"private, max-age={SCREENSHOT_TTL // 2}"
        return response


class VersionExportView(_VersionMixin, generics.GenericAPIView):
    """``GET /workflows/{id}/versions/{v}/export/playwright``: a standalone Python script."""

    queryset = WorkflowVersion.objects.all()
    serializer_class = VersionSerializer

    @extend_schema(responses={(200, "text/x-python"): str})
    def get(self, request: Request, *args, **kwargs) -> HttpResponse:
        from engine.export.playwright import export_playwright

        version = self.version()
        script = export_playwright(version.spec, version=version.version)
        slug = (
            re.sub(r"[^a-z0-9]+", "_", version.workflow.name.lower()).strip("_")[:50] or "workflow"
        )
        response = HttpResponse(script, content_type="text/x-python; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{slug}_v{version.version}.py"'
        record(
            "workflow.exported",
            org=self.org,
            request=request,
            entity=version,
            metadata={"format": "playwright"},
        )
        return response
