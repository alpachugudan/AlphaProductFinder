from __future__ import annotations

from app.config.settings import PROJECT_ROOT
from app.data.manifest import load_manifest


def test_manifest_loads() -> None:
    manifest = load_manifest(PROJECT_ROOT / "data/manifests/source_manifest.json")
    assert manifest.dataset_version == "2026-07-11-baseline"
    assert manifest.expected_total_rows == 53375
    assert len(manifest.datasets) == 4
    assert manifest.total_expected_rows == 53375


def test_manifest_row_expectations() -> None:
    manifest = load_manifest(PROJECT_ROOT / "data/manifests/source_manifest.json")
    by_table = {entry.raw_table: entry.expected_rows for entry in manifest.datasets}
    assert by_table == {
        "raw_bond_kr": 21882,
        "raw_etf_kr": 1780,
        "raw_etf_global": 6037,
        "raw_fund": 23676,
    }
