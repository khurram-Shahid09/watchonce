from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "E2: replay the Acme workflows against portal mutations M1–M8 (writes evals/reports/)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workflow", action="append", help="Only this golden (repeatable).")
        parser.add_argument("--variant", action="append", help='Only this variant, e.g. "m3".')
        parser.add_argument("--keep", action="store_true", help="Keep the eval workspace.")

    def handle(self, *args, workflow, variant, keep: bool, **options) -> None:
        from engine.evals.heal_eval import run_heal_eval

        summary, _, path = run_heal_eval(workflow, variant, keep=keep)
        self.stdout.write(f"report: {path}")
        for key, value in summary.items():
            self.stdout.write(f"  {key}: {value}")
        if summary["wrong_element_heals"] or summary["injection_picks"]:
            raise SystemExit("wrong-element heals or injection picks found")
