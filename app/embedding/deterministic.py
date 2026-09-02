from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable


class DeterministicEmbeddingProvider:
    """Step 10 전 테스트용 1024차원 결정적 embedding"""

    provider = "deterministic"
    model = "hash-v1"
    version = "1.0.0"
    dimensions = 1024

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        seed = int.from_bytes(digest[:8], "big")
        while len(values) < self.dimensions:
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            values.append((seed / 0x7FFFFFFF) * 2 - 1)
        norm = math.sqrt(sum(value * value for value in values))
        return [value / norm for value in values]

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]
