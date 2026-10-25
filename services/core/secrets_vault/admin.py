from django.contrib import admin

from .models import Secret


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    list_display = ("name", "org", "fields", "created_at", "rotated_at")
    fields = ("id", "org", "name", "fields", "key_version", "created_at", "rotated_at")
    readonly_fields = fields  # values are never shown, not even to staff
