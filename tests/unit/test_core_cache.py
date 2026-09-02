from __future__ import annotations

from app.core.cache import (
    BoundedVersionedCache,
    queryspec_cache_key,
    retrieval_cache_key,
)


def test_queryspec_cache_uses_normalized_question_without_storing_plaintext() -> None:
    first = queryspec_cache_key("  미국   ETF ", prompt_version="v1", schema_version="1.0")
    second = queryspec_cache_key("미국 ETF", prompt_version="v1", schema_version="1.0")

    assert first == second
    assert "미국" not in first.key_hash


def test_retrieval_cache_key_invalidates_on_dataset_or_external_version() -> None:
    payload = {"intent": "FILTER", "families": ["ETF_KR"]}
    baseline = retrieval_cache_key(
        payload, dataset_version="dataset-a", external_version="external-a"
    )
    changed_dataset = retrieval_cache_key(
        payload, dataset_version="dataset-b", external_version="external-a"
    )
    changed_external = retrieval_cache_key(
        payload, dataset_version="dataset-a", external_version="external-b"
    )
    cache = BoundedVersionedCache[str](max_entries=1)
    cache.put(baseline, "cached")

    assert cache.get(baseline) == "cached"
    assert cache.get(changed_dataset) is None
    assert cache.get(changed_external) is None


def test_bounded_cache_evicts_least_recently_used_item() -> None:
    first = queryspec_cache_key("첫 질문", prompt_version="v1", schema_version="1.0")
    second = queryspec_cache_key("둘 질문", prompt_version="v1", schema_version="1.0")
    cache = BoundedVersionedCache[str](max_entries=1)
    cache.put(first, "first")
    cache.put(second, "second")

    assert cache.get(first) is None
    assert cache.get(second) == "second"
