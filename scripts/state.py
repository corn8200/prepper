"""Persistence helpers for dedupe, cooldown, and delivery receipts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass
class AlertKey:
    location_id: str
    provider: str
    external_id: str
    category: str

    def composite(self) -> str:
        return "/".join([self.location_id, self.provider, self.external_id, self.category])


@dataclass
class StateStore:
    path: Path
    seen: Dict[str, str] = field(default_factory=dict)
    cooldowns: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "StateStore":
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            payload = {}
        return cls(
            path=path,
            seen=payload.get("seen", {}),
            cooldowns=payload.get("cooldowns", {}),
            metadata=payload.get("metadata", {}),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(
                {"seen": self.seen, "cooldowns": self.cooldowns, "metadata": self.metadata},
                handle,
                indent=2,
                sort_keys=True,
            )

    def mark_seen(self, key: AlertKey) -> None:
        self.seen[key.composite()] = utcnow().strftime(ISO_FORMAT)

    def is_seen(self, key: AlertKey) -> bool:
        return key.composite() in self.seen

    def start_cooldown(self, bucket: str, minutes: int) -> None:
        expiry = utcnow() + timedelta(minutes=minutes)
        self.cooldowns[bucket] = expiry.strftime(ISO_FORMAT)

    def in_cooldown(self, bucket: str) -> bool:
        expiry_str = self.cooldowns.get(bucket)
        if not expiry_str:
            return False
        expiry = datetime.strptime(expiry_str, ISO_FORMAT).replace(tzinfo=timezone.utc)
        if utcnow() >= expiry:
            self.cooldowns.pop(bucket, None)
            return False
        return True

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.metadata.get(key, default)

    def set_metadata(self, key: str, value: str) -> None:
        self.metadata[key] = value


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
