from django.conf import settings
from django.core.management.base import BaseCommand

from common.storage import S3Storage


class Command(BaseCommand):
    help = "Create the object storage bucket if missing and allow browser uploads (CORS)."

    def handle(self, *args, **options) -> None:
        S3Storage().ensure_bucket(settings.S3_UPLOAD_CORS_ORIGINS)
        self.stdout.write(
            self.style.SUCCESS(
                f"Bucket {settings.S3_BUCKET} ready; uploads allowed from "
                f"{', '.join(settings.S3_UPLOAD_CORS_ORIGINS)}"
            )
        )
