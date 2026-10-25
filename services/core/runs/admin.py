from django.contrib import admin

from .models import CheckpointDecision, Run, RunStep


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id", "workflow", "status", "triggered_by", "created_at", "finished_at")
    list_filter = ("status",)
    readonly_fields = [f.name for f in Run._meta.fields]


@admin.register(RunStep)
class RunStepAdmin(admin.ModelAdmin):
    list_display = ("run", "seq", "step_id", "status", "rung")
    readonly_fields = [f.name for f in RunStep._meta.fields]


@admin.register(CheckpointDecision)
class CheckpointDecisionAdmin(admin.ModelAdmin):
    list_display = ("run", "step_id", "decision", "decided_by", "created_at")
    readonly_fields = [f.name for f in CheckpointDecision._meta.fields]
