"""Result types for expected failures (Lab1-style, no exceptions for control flow)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Success(Generic[T]):
    value: T


@dataclass(frozen=True)
class Failure:
    error: str


Result = Success[T] | Failure


def success(value: T) -> Success[T]:
    return Success(value)


def failure(error: str) -> Failure:
    if not error or not error.strip():
        raise ValueError("Error message must be provided")
    return Failure(error)


def is_success(result: Result[T]) -> bool:
    return isinstance(result, Success)


def is_failure(result: Result[T]) -> bool:
    return isinstance(result, Failure)


def unwrap(result: Result[T]) -> T:
    if isinstance(result, Failure):
        raise ValueError(result.error)
    return result.value
