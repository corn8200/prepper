"""Fusion helpers for surge detection, hysterias, and decision reasoning."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict


@dataclass
class SurgeResult:
    location_id: str
    count: int
    baseline: float
    factor: float
    distinct_domains: int
    tripped: bool


class RollingBaseline:
    """Maintains a rolling sample of counts for surge math."""

    def __init__(self, window: int = 12):
        self.window = window
        self.samples: Deque[int] = deque(maxlen=window)

    def observe(self, value: int) -> float:
        baseline = self.median()
        if value > 0:
            self.samples.append(value)
        return baseline

    def median(self) -> float:
        if not self.samples:
            return 0.0
        data = sorted(self.samples)
        mid = len(data) // 2
        if len(data) % 2 == 1:
            return float(data[mid])
        return (data[mid - 1] + data[mid]) / 2.0


class SignalsEngine:
    def __init__(self, news_min_mentions: int, news_spike_factor: float, require_domains: int, hysteria_sources: int):
        self.news_min_mentions = news_min_mentions
        self.news_spike_factor = news_spike_factor
        self.require_domains = require_domains
        self.hysteria_sources = hysteria_sources
        self.baselines: Dict[str, RollingBaseline] = defaultdict(RollingBaseline)
        self.confirmations: Dict[str, set[str]] = defaultdict(set)

    def record_news(self, location_id: str, count: int, distinct_domains: int) -> SurgeResult:
        baseline = self.baselines[location_id].observe(count)
        factor = float(count) if baseline == 0 else count / baseline
        tripped = (
            count >= self.news_min_mentions
            and (baseline == 0 or count >= baseline * self.news_spike_factor)
            and distinct_domains >= self.require_domains
        )
        if tripped:
            self.confirmations[location_id].add("news")
        return SurgeResult(
            location_id=location_id,
            count=count,
            baseline=baseline,
            factor=factor,
            distinct_domains=distinct_domains,
            tripped=tripped,
        )

    def record_confirmation(self, location_id: str, source_name: str) -> None:
        self.confirmations[location_id].add(source_name)

    def hysteria_active(self, location_id: str) -> bool:
        return len(self.confirmations[location_id]) >= self.hysteria_sources

    def reset_run_state(self) -> None:
        self.confirmations.clear()
