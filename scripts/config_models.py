"""Shared Pydantic models for project configuration files."""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator


class LocationDefaults(BaseModel):
    quake_min_mag_normal: float = Field(..., ge=0)
    quake_min_mag_emergency: float = Field(..., ge=0)
    aqi_emergency: int = Field(..., ge=0)

    @model_validator(mode="after")
    def check_order(self):
        if self.quake_min_mag_emergency < self.quake_min_mag_normal:
            raise ValueError("Emergency magnitude must be >= normal magnitude")
        return self


class Location(BaseModel):
    id: str
    label: str
    role: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(..., gt=0)
    roads: List[str] = Field(default_factory=list)


class LocationsConfig(BaseModel):
    locations: List[Location]
    defaults: LocationDefaults

    @field_validator("locations")
    def ensure_ids_unique(cls, locations: List[Location]):
        ids = [loc.id for loc in locations]
        if len(ids) != len(set(ids)):
            raise ValueError("Location IDs must be unique")
        return locations


class OutputsConfig(BaseModel):
    use_email: bool
    use_pushover: bool
    emergency_retry_sec: int = Field(..., gt=0)
    emergency_expire_sec: int = Field(..., gt=0)


class SafetyConfig(BaseModel):
    allowlist_domains: List[str]


class GlobalConfig(BaseModel):
    schedule_minutes: int = Field(..., gt=0)
    outputs: OutputsConfig
    safety: SafetyConfig


class ThresholdsConfig(BaseModel):
    nws_severity_emergency: List[str]
    news_spike_factor: float = Field(..., gt=0)
    news_min_mentions: int = Field(..., gt=0)
    wiki_spike_factor: float = Field(..., gt=0)


class HysteriaConfig(BaseModel):
    require_sources: int = Field(..., gt=0)
    window_minutes: int = Field(..., gt=0)
    cooldown_minutes: int = Field(..., gt=0)


class NewsStackQuotas(BaseModel):
    newsapi_cooldown_minutes: int = Field(..., gt=0)
    newsapi_burst_minutes: int = Field(..., gt=0)


class NewsStackSurge(BaseModel):
    require_distinct_domains: int = Field(..., gt=1)


class NewsStackConfig(BaseModel):
    rss_sources: List[str]
    google_news_queries_per_location: List[str]
    quotas: NewsStackQuotas
    surge: NewsStackSurge
    mode: Literal["auto", "always", "off"] = "auto"


class TestingConfig(BaseModel):
    dry_run: bool = False


class PerLocationOverrides(RootModel[Dict[str, Dict[str, float]]]):
    pass


class SettingsConfig(BaseModel):
    global_: GlobalConfig = Field(..., alias="global")
    thresholds: ThresholdsConfig
    hysteria: HysteriaConfig
    news_stack: NewsStackConfig
    per_location_overrides: PerLocationOverrides
    testing: TestingConfig


class KeywordEntry(BaseModel):
    geo_terms: List[str]
    wiki_pages: List[str]
    roads: List[str]
    metadata: Dict[str, str] = Field(default_factory=dict)


class KeywordsConfig(BaseModel):
    locations: Dict[str, KeywordEntry]
    union: KeywordEntry
