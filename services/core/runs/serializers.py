from rest_framework import serializers

from .models import Batch, CheckpointDecision, HealEvent, Run, RunStep


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


class HealSerializer(serializers.ModelSerializer):
    step_intent = serializers.SerializerMethodField()
    resulting_version = serializers.SerializerMethodField()
    decided_by = serializers.SerializerMethodField()

    class Meta:
        model = HealEvent
        fields = [
            "id",
            "run_id",
            "workflow_id",
            "step_id",
            "step_intent",
            "rung",
            "score",
            "model_confidence",
            "explanation",
            "before_locators",
            "after_locators",
            "before_image_ref",
            "after_image_ref",
            "resulting_version",
            "decision",
            "decided_by",
            "decided_at",
            "cost_usd",
            "created_at",
        ]
        read_only_fields = fields

    def get_step_intent(self, obj) -> str:
        step = next(
            (s for s in obj.run.version.spec.get("steps", []) if s["id"] == obj.step_id), None
        )
        return step["intent"] if step else obj.step_id

    def get_resulting_version(self, obj) -> dict | None:
        v = obj.resulting_version
        return {"version": v.version, "status": v.status} if v else None

    def get_decided_by(self, obj) -> str | None:
        return obj.decided_by.email if obj.decided_by else None


class HealDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])


class BatchRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = Run
        fields = [
            "id",
            "row_index",
            "status",
            "inputs",
            "outputs",
            "current_step_id",
            "error_message",
        ]
        read_only_fields = fields


class BatchSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(source="version.version", read_only=True)
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    approved_by = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = [
            "id",
            "workflow_id",
            "workflow_name",
            "version",
            "status",
            "file_name",
            "columns",
            "column_map",
            "total",
            "succeeded",
            "failed",
            "approve_all",
            "approved_by",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_approved_by(self, obj: Batch) -> str | None:
        return obj.approved_by.email if obj.approved_by else None


class BatchDetailSerializer(BatchSerializer):
    runs = BatchRunSerializer(many=True, read_only=True)

    class Meta(BatchSerializer.Meta):
        fields = [*BatchSerializer.Meta.fields, "runs"]
        read_only_fields = fields


class BatchCreateSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="CSV with one row per run; headers name the inputs.")
    column_map = serializers.JSONField(
        required=False,
        help_text='Input name -> CSV column, e.g. {"amount": "Total"}. Defaults to matching names.',
    )
    version = serializers.IntegerField(min_value=1, required=False)
