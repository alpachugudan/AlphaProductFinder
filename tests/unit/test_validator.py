from __future__ import annotations

from pathlib import Path

import pytest
from app.config.settings import PROJECT_ROOT
from app.data.manifest import load_manifest
from app.data.validator import ValidationFailedError, validate_or_raise, validate_source_files


@pytest.fixture
def manifest_path() -> Path:
    return PROJECT_ROOT / "data/manifests/source_manifest.json"


@pytest.fixture
def source_dir() -> Path:
    return (PROJECT_ROOT / "../데이터셋").resolve()


def test_validate_real_dataset_hashes(manifest_path: Path, source_dir: Path) -> None:
    result = validate_or_raise(manifest_path, source_dir, verify_hashes=True)
    assert result.ok
    assert sum(result.row_counts.values()) == 53375


def test_tampered_hash_fails(manifest_path: Path, source_dir: Path, tmp_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    tampered = manifest.model_copy(deep=True)
    tampered.datasets[0].data_sha256 = "0" * 64
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text(tampered.model_dump_json(indent=2), encoding="utf-8")

    result = validate_source_files(tampered, source_dir, verify_hashes=True)
    assert not result.ok
    assert any("hash mismatch" in err for err in result.errors)


def test_missing_file_fails(manifest_path: Path, tmp_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    result = validate_source_files(manifest, tmp_path, verify_hashes=False)
    assert not result.ok
    with pytest.raises(ValidationFailedError):
        validate_or_raise(manifest_path, tmp_path, verify_hashes=False)
