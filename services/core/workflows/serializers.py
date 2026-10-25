from rest_framework import serializers

from .models import Workflow, WorkflowVersion


class VersionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowVersion
        fields = ["id", "version", "status", "created_by", "change_note", "created_at"]
        read_only_fields = fields


class WorkflowSerializer(serializers.ModelSerializer):
    active_version = VersionSummarySerializer(read_only=True)
    step_count = serializers.SerializerMethodField()
    input_count = serializers.SerializerMethodField()

    class Meta:
        model = Workflow
        fields = [
            "id",
            "name",
            "description",
            "recording_id",
            "active_version",
            "step_count",
            "input_count",
            "manual_duration_sec",
            "archived_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "recording_id",
            "active_version",
            "archived_at",
            "created_at",
            "updated_at",
        ]

    def _spec(self, wf: Workflow) -> dict:
        return wf.active_version.spec if wf.active_version else {}

    def get_step_count(self, wf: Workflow) -> int:
        return len(self._spec(wf).get("steps", []))

    def get_input_count(self, wf: Workflow) -> int:
        return len(self._spec(wf).get("inputs", []))


class WorkflowDetailSerializer(WorkflowSerializer):
    versions = VersionSummarySerializer(many=True, read_only=True)

    class Meta(WorkflowSerializer.Meta):
        fields = [*WorkflowSerializer.Meta.fields, "versions"]


class WorkflowUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = ["name", "description", "manual_duration_sec"]


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowVersion
        fields = [
            "id",
            "workflow_id",
            "version",
            "status",
            "spec",
            "spec_hash",
            "sop_markdown",
            "warnings",
            "created_by",
            "parent_version_id",
            "change_note",
            "compile_info",
            "created_at",
        ]
        read_only_fields = fields


class VersionCreateSerializer(serializers.Serializer):
    spec = serializers.JSONField()
    change_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    base_version = serializers.IntegerField(
        min_value=1, required=False, help_text="The version this edit started from."
    )
    activate = serializers.BooleanField(default=False, help_text="Owners only.")
