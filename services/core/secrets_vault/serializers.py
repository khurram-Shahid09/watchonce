import re

from rest_framework import serializers

from .models import Secret

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SecretSerializer(serializers.ModelSerializer):
    """Names and field names only. Values are write-only, everywhere."""

    class Meta:
        model = Secret
        fields = ["id", "name", "fields", "created_at", "rotated_at"]
        read_only_fields = fields


def _check_values(values: dict) -> dict:
    if not values or len(values) > 20:
        raise serializers.ValidationError("Give between 1 and 20 fields.")
    for key, value in values.items():
        if not IDENT.match(key):
            raise serializers.ValidationError(f'Field "{key}" must be snake_case.')
        if not isinstance(value, str) or not value or len(value) > 2000:
            raise serializers.ValidationError(f'Field "{key}" needs a text value.')
    return values


class SecretCreateSerializer(serializers.Serializer):
    name = serializers.RegexField(IDENT, max_length=64)
    values = serializers.DictField(
        child=serializers.CharField(trim_whitespace=False), write_only=True
    )

    def validate_values(self, values: dict) -> dict:
        return _check_values(values)


class SecretRotateSerializer(serializers.Serializer):
    values = serializers.DictField(
        child=serializers.CharField(trim_whitespace=False), write_only=True
    )

    def validate_values(self, values: dict) -> dict:
        return _check_values(values)
