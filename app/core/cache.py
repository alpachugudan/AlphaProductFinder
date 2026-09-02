from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


def normalized_question_hash(question: str) -> str:
    """원문을 저장하지 않는, 공백 정규화 질문 해시."""

    normalized = " ".join(question.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def stable_payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheKey:
    namespace: str
    key_hash: str
    versions: tuple[str, ...]


def queryspec_cache_key(question: str, *, prompt_version: str, schema_version: str) -> CacheKey:
    return CacheKey(
        namespace="queryspec",
        key_hash=normalized_question_hash(question),
        versions=(prompt_version, schema_version),
    )


def retrieval_cache_key(
    queryspec_payload: object,
    *,
    dataset_version: str,
    external_version: str,
) -> CacheKey:
    return CacheKey(
        namespace="retrieval",
        key_hash=stable_payload_hash(queryspec_payload),
        versions=(dataset_version, external_version),
    )


class BoundedVersionedCache(Generic[T]):
    """단일 VM용 LRU cache. 버전은 key 일부라 변경 즉시 cache miss가 된다."""

    def __init__(self, max_entries: int = 128) -> None:
        if max_entries < 1:
            msg = "max_entries must be positive"
            raise ValueError(msg)
        self._max_entries = max_entries
        self._items: OrderedDict[CacheKey, T] = OrderedDict()

    def get(self, key: CacheKey) -> T | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def put(self, key: CacheKey, value: T) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
