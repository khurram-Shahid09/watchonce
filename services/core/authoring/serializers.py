from rest_framework import serializers

from .models import AuthoringSession


class AuthoringSessionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", default="", read_only=True)
    version_number = serializers.IntegerField(
        source="version.version", default=None, read_only=True
    )

    class Meta:
        model = AuthoringSession
        fields = [
            "id",
            "mode",
            "status",
            "start_url",
            "instructions",
            "base_version",
            "source_run",
            "steps",
            "question",
            "workflow",
            "workflow_name",
            "version_number",
            "error_code",
            "error_message",
            "llm_cost_usd",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class AuthoringCreateSerializer(serializers.Serializer):
    instructions = serializers.CharField(max_length=8000, trim_whitespace=True)
    start_url = serializers.URLField(max_length=2000, required=False, allow_blank=True)
    run_id = serializers.CharField(max_length=40, required=False, allow_blank=True)

    def validate_start_url(self, value: str) -> str:
        if value and not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("Use an http:// or https:// link.")
        return value


class AuthoringDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
