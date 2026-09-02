from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, field_validator


class DatasetStatus(StrEnum):
    LOADING = "LOADING"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"


class IngestionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class DatasetEntry(BaseModel):
    logical_table: str
    raw_table: str
    schema_file: str
    data_file: str
    schema_sha256: str
    data_sha256: str
    schema_sheet: str
    data_sheet: str
    expected_rows: int
    expected_columns: int
    source_key_fields: list[str]

    @field_validator("schema_sha256", "data_sha256")
    @classmethod
    def sha256_must_be_lowercase_hex(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            msg = "SHA-256 must be 64 lowercase hex characters"
            raise ValueError(msg)
        return normalized


class SourceManifest(BaseModel):
    dataset_version: str
    validation_date: str
    source_data_dir_hint: str
    datasets: list[DatasetEntry]
    expected_total_rows: int

    @property
    def total_expected_rows(self) -> int:
        return sum(entry.expected_rows for entry in self.datasets)


def load_manifest(path: Path) -> SourceManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SourceManifest.model_validate(raw)


def compute_manifest_hash(manifest: SourceManifest) -> str:
    """manifest 내용 기준 해시 — dataset_version 변경 시 새 버전"""
    payload = manifest.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
