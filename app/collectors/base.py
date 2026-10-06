from __future__ import annotations

from typing import Protocol, TypeVar


T = TypeVar("T", covariant=True)


class Collector(Protocol[T]):
    def collect(self) -> list[T]: ...
