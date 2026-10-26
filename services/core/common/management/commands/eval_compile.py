from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "E1: compile every golden recording, score it and replay it (writes evals/reports/)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("ids", nargs="*", help="Only these goldens (folder names).")
        parser.add_argument("--no-replay", action="store_true", help="Score the compile only.")
        parser.add_argument("--keep", action="store_true", help="Keep the eval workspace.")

    def handle(self, *args, ids: list[str], no_replay: bool, keep: bool, **options) -> None:
        from engine.evals.compile_eval import run_compile_eval

        summary, results, path = run_compile_eval(ids, run_replay=not no_replay, keep=keep)
        self.stdout.write(f"report: {path}")
        for key, value in summary.items():
            self.stdout.write(f"  {key}: {value}")
        if summary["checkpoint_recall"] not in (None, 1.0):
            raise SystemExit("checkpoint recall below 100%")
