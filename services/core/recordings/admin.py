from django.contrib import admin

from .models import Recording


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = ("id", "description", "org", "status", "event_count", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "description")
    readonly_fields = [f.name for f in Recording._meta.fields]
