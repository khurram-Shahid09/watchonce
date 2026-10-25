"""CSV batch runs: parse and validate the file, then build the results file
(docs/08 "Batch runs", docs/10 "POST /workflows/{id}/batches")."""

import csv
import io
import re
from typing import Any

from .service import clean_inputs

MAX_ROWS = 500
MAX_BYTES = 2 * 1024 * 1024
RESULT_COLUMNS = ("status", "error", "run_id")


class BatchFileError(ValueError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def parse_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise BatchFileError("The file is larger than 2 MB.")
    try:
        text = data.decode("utf-8-sig")  # Excel adds a byte-order mark
    except UnicodeDecodeError:
        raise BatchFileError("Save the CSV as UTF-8.") from None
    reader = csv.DictReader(io.StringIO(text))
    columns = [c.strip() for c in (reader.fieldnames or []) if c and c.strip()]
    if not columns:
        raise BatchFileError("The file has no header row.")
    rows = []
    for raw in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
        if any(row.values()):  # skip blank lines
            rows.append(row)
    if not rows:
        raise BatchFileError("The file has no data rows.")
    if len(rows) > MAX_ROWS:
        raise BatchFileError(
            f"A batch can have at most {MAX_ROWS} rows (this file has {len(rows)})."
        )
    return columns, rows


def default_column_map(spec: dict[str, Any], columns: list[str]) -> dict[str, str]:
    """Input name -> CSV column, matching "Vendor Name" to vendor_name and so on."""
    by_key = {_key(c): c for c in columns}
    return {i["name"]: by_key[i["name"]] for i in spec.get("inputs", []) if i["name"] in by_key}


def row_inputs(row: dict[str, str], column_map: dict[str, str]) -> dict[str, Any]:
    return {name: row.get(column, "") for name, column in column_map.items()}


def validate_rows(
    spec: dict[str, Any], rows: list[dict[str, str]], column_map: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(typed inputs per row, errors). Errors are keyed "row N" (1-based data rows) plus
    "columns" for required inputs with no column at all."""
    errors: dict[str, Any] = {}
    unmapped = [
        i["name"]
        for i in spec.get("inputs", [])
        if i.get("required", True) and i["name"] not in column_map
    ]
    if unmapped:
        errors["columns"] = f"No column for: {', '.join(unmapped)}."
    cleaned = []
    for n, row in enumerate(rows, start=1):
        values, row_errors = clean_inputs(spec, row_inputs(row, column_map))
        if row_errors and not unmapped:
            errors[f"row {n}"] = row_errors
        cleaned.append(values)
    return cleaned, errors


def results_csv(batch, runs: list) -> str:
    out = io.StringIO()
    output_names = sorted({k for r in runs for k in (r.outputs or {})})
    writer = csv.writer(out)
    writer.writerow([*batch.columns, *RESULT_COLUMNS, *output_names])
    by_row = {r.row_index: r for r in runs}
    for n, row in enumerate(batch.rows, start=1):
        run = by_row.get(n)
        status = run.status if run else "not run"
        error = run.error_message if run else ""
        outputs = (run.outputs or {}) if run else {}
        writer.writerow(
            [row.get(c, "") for c in batch.columns]
            + [status, error, run.id if run else ""]
            + [outputs.get(name, "") for name in output_names]
        )
    return out.getvalue()
