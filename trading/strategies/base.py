from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategyInfo:
    key: str
    name: str
    blurb: str
    lesson: str


_REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    _REGISTRY[cls.key] = cls
    return cls


def get_strategy(key: str) -> Strategy:
    if key not in _REGISTRY:
        raise KeyError(f"Unknown strategy: {key}. Known: {list(_REGISTRY)}")
    return _REGISTRY[key]()


def list_strategies() -> list[StrategyInfo]:
    return [
        StrategyInfo(s.key, s.name, s.blurb, s.lesson)
        for s in sorted(_REGISTRY.values(), key=lambda c: c.name)
    ]


class Strategy(ABC):
    key: str = ""
    name: str = ""
    blurb: str = ""
    lesson: str = ""
    warmup: int = 30  # bars needed before signals are meaningful

    @abstractmethod
    def signal_at(self, closes: pd.Series, i: int) -> Signal:
        """Return BUY/SELL/HOLD for bar index i using closes[: i+1] history."""

    def signals(self, closes: pd.Series) -> list[Signal]:
        return [self.signal_at(closes, i) for i in range(len(closes))]
