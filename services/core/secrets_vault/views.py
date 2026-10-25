"""Workspace secrets (docs/10-api-spec.md "Secrets"). Owners manage them; members can see
which exist (names and field names) so they know whether a workflow can run."""

from typing import cast

from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.models import User
from accounts.views_base import OrgScopedViewMixin
from audit.service import record
from common.exceptions import ApiError

from .models import Secret
from .serializers import SecretCreateSerializer, SecretRotateSerializer, SecretSerializer


class SecretListView(OrgScopedViewMixin, generics.ListCreateAPIView):
    queryset = Secret.objects.all()
    serializer_class = SecretSerializer
    owner_methods = frozenset({"POST"})
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().order_by("name")

    @extend_schema(request=SecretCreateSerializer, responses={201: SecretSerializer})
    def post(self, request: Request, *args, **kwargs) -> Response:
        data = SecretCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        secret = Secret(
            org=self.org, name=data.validated_data["name"], created_by=cast(User, request.user)
        )
        secret.set_values(data.validated_data["values"])
        try:
            with transaction.atomic():
                secret.save()
        except IntegrityError:
            raise ApiError(
                "secret_exists", "A secret with this name already exists.", status_code=409
            ) from None
        record(
            "secret.created",
            org=self.org,
            request=request,
            entity=secret,
            metadata={"name": secret.name, "fields": secret.fields},
        )
        return Response(SecretSerializer(secret).data, status=status.HTTP_201_CREATED)


class SecretDetailView(OrgScopedViewMixin, generics.RetrieveDestroyAPIView):
    queryset = Secret.objects.all()
    serializer_class = SecretSerializer
    lookup_url_kwarg = "secret_id"
    owner_methods = frozenset({"PUT", "DELETE"})

    @extend_schema(request=SecretRotateSerializer, responses={200: SecretSerializer})
    def put(self, request: Request, *args, **kwargs) -> Response:
        """Replace the values (rotation)."""
        secret = self.get_object()
        data = SecretRotateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        secret.set_values(data.validated_data["values"])
        secret.rotated_at = timezone.now()
        secret.save()
        record(
            "secret.rotated",
            org=self.org,
            request=request,
            entity=secret,
            metadata={"name": secret.name, "fields": secret.fields},
        )
        return Response(SecretSerializer(secret).data)

    def perform_destroy(self, instance: Secret) -> None:
        record(
            "secret.deleted",
            org=self.org,
            request=self.request,
            entity=instance,
            metadata={"name": instance.name},
        )
        instance.delete()
