from django.core.management.base import BaseCommand, CommandError

from accounts.models import ApiToken, Membership, Organization, User
from audit.service import record


class Command(BaseCommand):
    help = (
        "Issue a personal access token (pat_…) for an existing account, e.g. to connect the "
        "recorder extension before the dashboard's token page exists. Creates a workspace for "
        "accounts that have none. The token is printed once."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("email")
        parser.add_argument("--name", default="Chrome extension")
        parser.add_argument("--org-name", default="My workspace")

    def handle(self, *args, email: str, name: str, org_name: str, **options) -> None:
        user = User.objects.filter(email=email.strip().lower()).first()
        if user is None:
            raise CommandError(f"No account with email {email}.")
        membership = Membership.objects.filter(user=user).order_by("created_at").first()
        if membership is None:
            org = Organization.objects.create(name=org_name)
            membership = Membership.objects.create(org=org, user=user, role=Membership.Role.OWNER)
            self.stdout.write(f"Created workspace {org.name!r} ({org.id})")
        token, raw = ApiToken.issue(org=membership.org, user=user, name=name)
        record(
            "token.created",
            org=membership.org,
            actor="system:issue_token",
            entity=token,
            metadata={"name": name},
        )
        self.stdout.write(f"Workspace: {membership.org.name}")
        self.stdout.write(self.style.SUCCESS(raw))
