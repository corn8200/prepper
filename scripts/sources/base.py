"""Shared base classes for threat sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceResult:
    provider: str
    location_id: str
    items: List[Dict[str, Any]] = field(default_factory=list)
    ok: bool = True
    error: Optional[str] = None
    latency_ms: Optional[int] = None


class SourceError(RuntimeError):
    pass


class BaseSource:
    provider: str = "base"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        raise NotImplementedError
