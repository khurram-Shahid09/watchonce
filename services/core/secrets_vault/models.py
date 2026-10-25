from django.conf import settings
from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel

from . import crypto


class Secret(OrgOwnedModel, TimeStampedModel):
    """A named set of credentials, e.g. ``acme_login`` with ``username`` and ``password``.
    A workflow's ``{{secrets.acme_login.password}}`` uses the workspace secret of that name."""

    id = PrefixedIdField(prefix="sec")
    name = models.CharField(max_length=64)
    fields = models.JSONField(default=list)
    ciphertext = models.BinaryField()
    data_key_ciphertext = models.BinaryField()
    key_version = models.PositiveSmallIntegerField(default=crypto.KEY_VERSION)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    rotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "secrets"
        constraints = [models.UniqueConstraint(fields=["org", "name"], name="uniq_secret_name")]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"  # never the values

    def set_values(self, values: dict[str, str]) -> None:
        self.fields = sorted(values)
        self.ciphertext, self.data_key_ciphertext, self.key_version = crypto.seal(self.id, values)

    def values(self) -> dict[str, str]:
        return crypto.unseal(self.id, self.ciphertext, self.data_key_ciphertext)
