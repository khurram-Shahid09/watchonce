from django.conf import settings
from rest_framework import serializers

from .models import Recording

FRAME_NAME = r"^frames/\d{4,6}\.webp$"
DAY_MS = 24 * 60 * 60 * 1000


class RecordingSerializer(serializers.ModelSerializer):
    frame_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Recording
        fields = [
            "id",
            "description",
            "status",
            "start_url",
            "event_count",
            "frame_count",
            "duration_ms",
            "candidate_count",
            "error",
            "created_at",
            "uploaded_at",
        ]
        read_only_fields = fields


class RecordingCreateSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=1000)
    start_url = serializers.URLField(max_length=2000)
    event_count = serializers.IntegerField(min_value=1, max_value=settings.RECORDING_MAX_EVENTS)
    duration_ms = serializers.IntegerField(min_value=0, max_value=DAY_MS, required=False)
    frames = serializers.ListField(
        child=serializers.RegexField(FRAME_NAME),
        max_length=settings.RECORDING_MAX_FRAMES,
        required=False,
        default=list,
        help_text='Screenshot names from the recording, e.g. "frames/0001.webp".',
    )

    def validate_start_url(self, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("Only http and https pages can be recorded.")
        return value

    def validate_frames(self, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Frame names must be unique.")
        return sorted(value)


class FrameUploadSerializer(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.CharField()


class UploadSerializer(serializers.Serializer):
    events_url = serializers.CharField(help_text="PUT events.json here (application/json).")
    frames = FrameUploadSerializer(many=True, help_text="PUT each frame here (image/webp).")
    expires_at = serializers.DateTimeField()


class RecordingCreatedSerializer(RecordingSerializer):
    upload = UploadSerializer(read_only=True)

    class Meta(RecordingSerializer.Meta):
        fields = [*RecordingSerializer.Meta.fields, "upload"]
        read_only_fields = fields
