from __future__ import annotations

from app.evidence.models import EvidenceBundle, EvidenceField, compute_evidence_hash


def test_compute_evidence_hash_is_stable() -> None:
    bundles = [
        EvidenceBundle(
            product_uid="ETF_KR:001",
            product_name="A",
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
    ]
    first = compute_evidence_hash(bundles)
    second = compute_evidence_hash(list(reversed(bundles)))
    assert first == second
    assert len(first) == 64
