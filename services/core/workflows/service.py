"""Creating versions. Specs are immutable: saving always makes version N+1."""

import hashlib
import json
from typing import Any

from django.db import transaction
from django.db.models import Max

from .models import Workflow, WorkflowVersion


def spec_hash(spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_version(
    workflow: Workflow,
    spec: dict[str, Any],
    *,
    created_by: str,
    sop_markdown: str = "",
    warnings: list[str] | None = None,
    parent: WorkflowVersion | None = None,
    change_note: str = "",
    activate: bool = False,
    compile_info: dict[str, Any] | None = None,
) -> WorkflowVersion:
    with transaction.atomic():
        # Lock the workflow row so concurrent saves get distinct version numbers.
        Workflow.objects.select_for_update().filter(pk=workflow.pk).first()
        latest = workflow.versions.aggregate(n=Max("version"))["n"] or 0
        version = WorkflowVersion.objects.create(
            org_id=workflow.org_id,
            workflow=workflow,
            version=latest + 1,
            spec=spec,
            spec_hash=spec_hash(spec),
            sop_markdown=sop_markdown,
            warnings=warnings or [],
            created_by=created_by,
            parent_version=parent,
            change_note=change_note,
            compile_info=compile_info or {},
        )
        if activate:
            activate_version(version)
        return version


def activate_version(version: WorkflowVersion) -> None:
    with transaction.atomic():
        workflow = Workflow.objects.select_for_update().get(pk=version.workflow_id)
        workflow.versions.filter(status=WorkflowVersion.Status.ACTIVE).exclude(
            pk=version.pk
        ).update(status=WorkflowVersion.Status.ARCHIVED)
        version.status = WorkflowVersion.Status.ACTIVE
        version.save(update_fields=["status", "updated_at"])
        workflow.active_version = version
        workflow.save(update_fields=["active_version", "updated_at"])
