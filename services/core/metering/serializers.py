from rest_framework import serializers


class WorkflowSavingsSerializer(serializers.Serializer):
    workflow_id = serializers.CharField()
    name = serializers.CharField()
    runs = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    manual_duration_sec = serializers.IntegerField(allow_null=True)
    hours_saved = serializers.FloatField()


class DailyRunsSerializer(serializers.Serializer):
    date = serializers.DateField()
    runs = serializers.IntegerField()
    succeeded = serializers.IntegerField()


class AnalyticsSummarySerializer(serializers.Serializer):
    range_days = serializers.IntegerField()
    since = serializers.DateTimeField()
    runs = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    success_rate = serializers.FloatField(allow_null=True, help_text="Succeeded / finished runs.")
    hours_saved = serializers.FloatField(
        help_text="Each workflow's manual_duration_sec × its successful runs."
    )
    workflows_without_duration = serializers.IntegerField(
        help_text="Workflows with successful runs but no manual time set (not counted)."
    )
    heals = serializers.IntegerField()
    heals_approved = serializers.IntegerField()
    heals_pending = serializers.IntegerField()
    llm_spend_usd = serializers.DecimalField(max_digits=12, decimal_places=4)
    workflows = WorkflowSavingsSerializer(many=True)
    daily = DailyRunsSerializer(many=True)
