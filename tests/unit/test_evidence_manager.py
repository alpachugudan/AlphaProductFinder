from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.evidence.manager import EvidenceIntegrityError, EvidenceManager
from app.evidence.models import EvidenceBundle, EvidenceField, EvidenceValidationAction


def test_evidence_manager_drops_candidate_on_row_missing() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    manager = EvidenceManager()
    bundle = EvidenceBundle(
        product_uid="ETF_KR:001",
        product_name="Test",
        source_table="PREF01N001",
        source_key="1",
        used_fields=[
            EvidenceField(
                logical_field="expense_ratio",
                source_field="cu_charge_rt",
                value="0.20",
                unit="%",
                as_of_date="2026-08-22",
                derivation="SOURCE",
            )
        ],
    )
    result = manager.validate(session, dataset_version_id=1, bundles=[bundle])
    assert result.outcomes[0].action == EvidenceValidationAction.DROP_CANDIDATE
    assert result.bundles == []


def test_evidence_manager_passes_matching_row() -> None:
    row = SimpleNamespace(product_name="Test", cu_charge_rt=Decimal("0.20"))
    session = MagicMock()
    session.scalar.side_effect = [row, None]
    manager = EvidenceManager()
    bundle = EvidenceBundle(
        product_uid="ETF_KR:001",
        product_name="Test",
        source_table="PREF01N001",
        source_key="1",
        used_fields=[
            EvidenceField(
                logical_field="expense_ratio",
                source_field="cu_charge_rt",
                value="0.20",
                unit="%",
                as_of_date="2026-08-22",
                derivation="SOURCE",
            )
        ],
    )
    result = manager.validate(session, dataset_version_id=1, bundles=[bundle])
    assert result.bundles == [bundle]
    assert result.evidence_hash


def test_evidence_integrity_error_is_product_finder_error() -> None:
    error = EvidenceIntegrityError("mismatch")
    assert error.code == "EVIDENCE_INTEGRITY_ERROR"
