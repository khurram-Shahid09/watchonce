from django.contrib import admin

from .models import LlmCall


@admin.register(LlmCall)
class LlmCallAdmin(admin.ModelAdmin):
    list_display = ("created_at", "org", "purpose", "provider", "model", "cost_usd", "stop_reason")
    list_filter = ("purpose", "provider")
    readonly_fields = [f.name for f in LlmCall._meta.fields]
