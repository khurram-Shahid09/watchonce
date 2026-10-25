from rest_framework import serializers

from .models import CheckpointDecision, Run, RunStep


class RunStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = RunStep
        fields = [
            "step_id",
            "seq",
            "status",
            "rung",
            "locator_used",
            "started_at",
            "finished_at",
            "screenshot_ref",
            "error",
        ]
        read_only_fields = fields


class DecisionSerializer(serializers.ModelSerializer):
    decided_by = serializers.SerializerMethodField()

    class Meta:
        model = CheckpointDecision
        fields = ["step_id", "decision", "decided_by", "note", "created_at"]
        read_only_fields = fields

    def get_decided_by(self, obj: CheckpointDecision) -> str | None:
        return obj.decided_by.email if obj.decided_by else None


class RunSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(source="version.version", read_only=True)
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)

    class Meta:
        model = Run
        fields = [
            "id",
            "workflow_id",
            "workflow_name",
            "version",
            "status",
            "triggered_by",
            "inputs",
            "outputs",
            "current_step_id",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields


class RunDetailSerializer(RunSerializer):
    steps = RunStepSerializer(many=True, read_only=True)
    decisions = DecisionSerializer(many=True, read_only=True)

    class Meta(RunSerializer.Meta):
        fields = [*RunSerializer.Meta.fields, "steps", "decisions"]
        read_only_fields = fields


class RunCreateSerializer(serializers.Serializer):
    inputs = serializers.DictField(required=False, default=dict)
    version = serializers.IntegerField(
        min_value=1, required=False, help_text="Defaults to the active version."
    )


class CheckpointDecisionInputSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)
