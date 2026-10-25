"""Generate engine/spec/models.py (Pydantic v2) from packages/spec/workflow.schema.json.

Run from services/core:  uv run python scripts/gen_spec_models.py
CI runs it with --check and fails if the committed file is stale.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
SCHEMA = CORE.parents[1] / "packages" / "spec" / "workflow.schema.json"
TARGET = CORE / "engine" / "spec" / "models.py"
HEADER = "# GENERATED from packages/spec/workflow.schema.json by scripts/gen_spec_models.py. Do not edit."


def generate(out: Path) -> None:
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(SCHEMA),
            "--input-file-type",
            "jsonschema",
            "--output",
            str(out),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.12",
            "--use-annotated",
            "--field-constraints",
            "--use-standard-collections",
            "--use-union-operator",
            "--collapse-root-models",
            "--enum-field-as-literal",
            "all",
            "--use-double-quotes",
            "--disable-timestamp",
            "--extra-fields",
            "forbid",
            "--use-title-as-name",
            "--formatters",
            "ruff-format",
            "--custom-file-header",
            HEADER,
        ],
        check=True,
    )
    # Format with fixed settings so output doesn't depend on where it was written.
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--isolated",
            "--line-length",
            "100",
            "--config",
            "format.skip-magic-trailing-comma = true",
            str(out),
        ],  # fmt: skip
        check=True,
        capture_output=True,
    )


def main() -> int:
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "models.py"
            generate(fresh)
            if fresh.read_text(encoding="utf8") != TARGET.read_text(encoding="utf8"):
                print(f"{TARGET} is stale; run scripts/gen_spec_models.py", file=sys.stderr)
                return 1
        return 0
    generate(TARGET)
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
