from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.data.excel_reader import (
    ExcelValidationError,
    iter_data_rows,
    read_data_headers,
    read_schema_columns,
)
from app.data.manifest import (
    SourceManifest,
    compute_file_sha256,
    load_manifest,
)
from app.data.source_key import SourceKeyError, build_source_key


class ValidationFailedError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


def validate_manifest_schema(manifest_path: Path) -> SourceManifest:
    return load_manifest(manifest_path)


def validate_source_files(
    manifest: SourceManifest,
    source_dir: Path,
    *,
    verify_hashes: bool = True,
    verify_row_counts: bool = True,
) -> ValidationResult:
    result = ValidationResult(ok=True)
    total_rows = 0

    for entry in manifest.datasets:
        schema_path = source_dir / entry.schema_file
        data_path = source_dir / entry.data_file

        if not schema_path.exists():
            result.errors.append(f"missing schema file: {schema_path}")
            continue
        if not data_path.exists():
            result.errors.append(f"missing data file: {data_path}")
            continue

        if verify_hashes:
            actual_schema_hash = compute_file_sha256(schema_path)
            actual_data_hash = compute_file_sha256(data_path)
            if actual_schema_hash != entry.schema_sha256:
                result.errors.append(
                    f"schema hash mismatch for {entry.schema_file}: "
                    f"expected {entry.schema_sha256}, got {actual_schema_hash}"
                )
            if actual_data_hash != entry.data_sha256:
                result.errors.append(
                    f"data hash mismatch for {entry.data_file}: "
                    f"expected {entry.data_sha256}, got {actual_data_hash}"
                )

        try:
            schema_columns = read_schema_columns(schema_path, entry.schema_sheet)
            data_headers = read_data_headers(data_path, entry.data_sheet)
        except ExcelValidationError as exc:
            result.errors.append(f"{entry.logical_table}: {exc}")
            continue

        if schema_columns != data_headers:
            result.errors.append(
                f"header order mismatch for {entry.logical_table}: "
                f"schema/data columns differ"
            )

        if len(data_headers) != entry.expected_columns:
            result.errors.append(
                f"column count mismatch for {entry.data_file}: "
                f"expected {entry.expected_columns}, got {len(data_headers)}"
            )

        missing_key_fields = [f for f in entry.source_key_fields if f not in data_headers]
        if missing_key_fields:
            result.errors.append(
                f"missing source key fields for {entry.logical_table}: {missing_key_fields}"
            )

        row_count = 0
        seen_keys: set[str] = set()
        seen_rows: set[str] = set()
        for parsed in iter_data_rows(data_path, entry, data_headers):
            row_count += 1
            row_fingerprint = hashlib.sha256(
                json.dumps(parsed.payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            if row_fingerprint in seen_rows:
                result.errors.append(
                    f"duplicate full row in {entry.data_file} at row {parsed.row_number}"
                )
                break
            seen_rows.add(row_fingerprint)
            try:
                source_key = build_source_key(entry.source_key_fields, parsed.payload)
            except SourceKeyError as exc:
                result.errors.append(
                    f"invalid source key at {entry.data_file}:{parsed.row_number}: {exc}"
                )
                continue
            if source_key in seen_keys:
                result.errors.append(
                    f"duplicate source key in {entry.data_file}: {source_key}"
                )
            seen_keys.add(source_key)

        result.row_counts[entry.raw_table] = row_count
        total_rows += row_count

        if verify_row_counts and row_count != entry.expected_rows:
            result.errors.append(
                f"row count mismatch for {entry.data_file}: "
                f"expected {entry.expected_rows}, got {row_count}"
            )

    if total_rows != manifest.expected_total_rows:
        result.errors.append(
            f"total row mismatch: expected {manifest.expected_total_rows}, got {total_rows}"
        )

    result.ok = len(result.errors) == 0
    return result


def validate_or_raise(
    manifest_path: Path,
    source_dir: Path,
    *,
    verify_hashes: bool = True,
) -> ValidationResult:
    manifest = validate_manifest_schema(manifest_path)
    result = validate_source_files(
        manifest,
        source_dir,
        verify_hashes=verify_hashes,
        verify_row_counts=True,
    )
    if not result.ok:
        raise ValidationFailedError(result.errors)
    return result
