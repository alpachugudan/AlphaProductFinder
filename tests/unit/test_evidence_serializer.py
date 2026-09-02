from __future__ import annotations

from app.evidence.models import EvidenceBundle, EvidenceField
from app.evidence.serializer import serialize_retrieved_context


def _sample_bundle(uid: str = "ETF_KR:001", name: str = "Test|ETF") -> EvidenceBundle:
    return EvidenceBundle(
        product_uid=uid,
        product_name=name,
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
        selection_reasons=["expense_ratio_low"],
    )


def test_retrieved_context_is_byte_deterministic() -> None:
    bundles = [_sample_bundle("ETF_KR:A"), _sample_bundle("ETF_KR:B", "Beta ETF")]
    first = serialize_retrieved_context(bundles)
    second = serialize_retrieved_context(list(reversed(bundles)))
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_retrieved_context_escapes_special_characters() -> None:
    text = serialize_retrieved_context([_sample_bundle(name="A|B\nC;D")])
    assert "name=A\\|B\\nC\\;D" in text


def test_retrieved_context_truncates_by_candidate_unit() -> None:
    bundles = [_sample_bundle(f"ETF_KR:{index:03d}", f"Name {index}") for index in range(20)]
    text = serialize_retrieved_context(bundles, char_budget=400)
    assert "meta=truncated" in text
    assert "original_count=20" in text
    assert "ETF_KR:019" not in text
