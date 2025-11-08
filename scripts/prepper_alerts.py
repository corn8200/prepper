"""Main orchestration loop invoked by CI and CLI."""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List
from uuid import uuid4

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from .alerting import AlertDispatcher, AlertPayload
    from .config_models import KeywordsConfig, LocationsConfig, SettingsConfig
    from .keywords_builder import normalize_ascii
    from .metrics import MetricsStore
    from .signals import SignalsEngine, SurgeResult
    from .sources.airnow import AirNowClient
    from .sources.base import SourceResult
    from .sources.eonet import EONETClient
    from .sources.news_rss import NewsRSSClient
    from .sources.nws import NWSClient
    from .sources.usgs import USGSClient
    from .state import AlertKey, StateStore, utcnow
    from .validate import load_yaml
    try:
        from .llm import classify_news_items  # optional
        from .fetch import enrich_items_with_fulltext  # optional
    except Exception:  # pragma: no cover
        classify_news_items = None  # type: ignore
        enrich_items_with_fulltext = None  # type: ignore
except ImportError:  # pragma: no cover - fallback for direct script execution
    from scripts.alerting import AlertDispatcher, AlertPayload
    from scripts.config_models import KeywordsConfig, LocationsConfig, SettingsConfig
    from scripts.keywords_builder import normalize_ascii
    from scripts.metrics import MetricsStore
    from scripts.signals import SignalsEngine, SurgeResult
    from scripts.sources.airnow import AirNowClient
    from scripts.sources.base import SourceResult
    from scripts.sources.eonet import EONETClient
    from scripts.sources.news_rss import NewsRSSClient
    from scripts.sources.nws import NWSClient
    from scripts.sources.usgs import USGSClient
    from scripts.state import AlertKey, StateStore, utcnow
    from scripts.validate import load_yaml
    try:
        from scripts.llm import classify_news_items  # type: ignore
        from scripts.fetch import enrich_items_with_fulltext  # type: ignore
    except Exception:  # pragma: no cover
        classify_news_items = None  # type: ignore
        enrich_items_with_fulltext = None  # type: ignore

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LATEST_RUN_PATH = DATA_DIR / "latest_run.json"
STATE_PATH = DATA_DIR / "alerts_state.json"


@dataclass
class AlertDecision:
    provider: str
    location_id: str
    title: str
    body: str
    priority: int
    url: str | None = None
    category: str = "general"
    reason: str = ""


@dataclass
class LocationSummary:
    sources: Dict[str, Dict[str, int | bool | str]] = field(default_factory=dict)
    alerts: List[Dict[str, str | int]] = field(default_factory=list)
    surges: List[Dict[str, int | float | bool]] = field(default_factory=list)


class RunSummary:
    def __init__(self) -> None:
        self.locations: Dict[str, LocationSummary] = {}
        self.run_id = str(uuid4())

    def record_source(self, result: SourceResult) -> None:
        entry = self.locations.setdefault(result.location_id, LocationSummary())
        entry.sources[result.provider] = {
            "ok": result.ok,
            "count": len(result.items),
            "error": result.error or "",
            "latency_ms": result.latency_ms or 0,
        }

    def record_alert(self, decision: AlertDecision, channels: Dict[str, bool]) -> None:
        entry = self.locations.setdefault(decision.location_id, LocationSummary())
        entry.alerts.append(
            {
                "provider": decision.provider,
                "title": decision.title,
                "priority": decision.priority,
                "reason": decision.reason,
                "channels": channels,
            }
        )

    def record_surge(self, surge: SurgeResult) -> None:
        entry = self.locations.setdefault(surge.location_id, LocationSummary())
        entry.surges.append(
            {
                "count": surge.count,
                "baseline": surge.baseline,
                "factor": surge.factor,
                "domains": surge.distinct_domains,
                "tripped": surge.tripped,
            }
        )

    def write(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"run_id": self.run_id, "locations": {loc: summary.__dict__ for loc, summary in self.locations.items()}}
        LATEST_RUN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class PrepperAlertsRunner:
    def __init__(self, dry_run: bool = False) -> None:
        self.locations_cfg = LocationsConfig.model_validate(load_yaml(ROOT / "config" / "locations.yaml"))
        self.settings_cfg = SettingsConfig.model_validate(load_yaml(ROOT / "config" / "settings.yaml"))
        self.keywords_cfg = KeywordsConfig.model_validate(load_yaml(ROOT / "config" / "keywords.yaml"))
        testing_override = self.settings_cfg.testing.dry_run
        self.dry_run = dry_run or testing_override
        self.state = StateStore.load(STATE_PATH)
        self.run_started_at = utcnow()
        thresholds = self.settings_cfg.thresholds
        hysteria = self.settings_cfg.hysteria
        news_stack = self.settings_cfg.news_stack
        self.severe_thresholds = set(thresholds.nws_severity_emergency)
        self.signals = SignalsEngine(
            news_min_mentions=thresholds.news_min_mentions,
            news_spike_factor=thresholds.news_spike_factor,
            require_domains=news_stack.surge.require_distinct_domains,
            hysteria_sources=hysteria.require_sources,
        )
        self.dispatcher = AlertDispatcher(config={"outputs": self.settings_cfg.global_.outputs.model_dump()}, dry_run=self.dry_run)
        self.summary = RunSummary()
        self.sources = self._build_sources(news_stack=news_stack, allow_domains=self.settings_cfg.global_.safety.allowlist_domains)
        self.metrics = MetricsStore(DATA_DIR / "metrics.db")
        self.metrics.record_run_start(self.summary.run_id, self.run_started_at, self.dry_run)
        # Optional LLM classification
        self.llm_enabled = bool(os.getenv("OPENAI_API_KEY")) and (os.getenv("LLM_CLASSIFY_NEWS", "").strip().lower() in {"1", "true", "yes", "on"})
        try:
            self.llm_max_items = int(os.getenv("LLM_MAX_ITEMS", "10"))
        except ValueError:
            self.llm_max_items = 10
        try:
            self.llm_max_chars = int(os.getenv("LLM_MAX_CHARS", "1000"))
        except ValueError:
            self.llm_max_chars = 1000
        self.llm_emit_alerts = os.getenv("LLM_EMIT_ALERTS", "").strip().lower() in {"1", "true", "yes", "on"}

    def _build_sources(self, news_stack, allow_domains: Iterable[str]):
        return {
            "nws": NWSClient(),
            "usgs": USGSClient(),
            "news_rss": NewsRSSClient(news_stack.rss_sources, allow_domains, news_stack.google_news_queries_per_location),
            "eonet": EONETClient(),
            "airnow": AirNowClient(),
        }

    def run(self) -> None:
        LOGGER.info("Starting run (dry_run=%s)", self.dry_run)
        for location in self.locations_cfg.locations:
            LOGGER.info("Processing %s", location.id)
            location_payload = location.model_dump()
            location_payload["label"] = location.label
            keywords_entry = self.keywords_cfg.locations.get(location.id)
            keywords = keywords_entry.model_dump() if keywords_entry else {}
            pending_nws: List[Dict[str, Any]] = []
            pending_usgs: List[Dict[str, Any]] = []
            news_surge_active = False
            official_severe = False
            rss_items: List[Dict[str, Any]] = []
            for name, source in self.sources.items():
                result = source.fetch(location_payload, keywords)
                self.summary.record_source(result)
                self.metrics.record_fetch(self.summary.run_id, result)
                if result.provider == "news_rss" and result.ok:
                    domains = {item.get("domain") for item in result.items if item.get("domain")}
                    surge = self.signals.record_news(location.id, len(result.items), len(domains))
                    self.metrics.record_surge(self.summary.run_id, surge)
                    self.summary.record_surge(surge)
                    news_surge_active = news_surge_active or surge.tripped
                    rss_items = result.items or []
                if result.provider == "nws" and result.items:
                    pending_nws.extend(result.items)
                    if any((item.get("severity") or "") in self.severe_thresholds for item in result.items):
                        official_severe = True
                if result.provider == "usgs" and result.items:
                    pending_usgs.extend(result.items)
            # Fetch full text and classify RSS items via LLM; treat accepted items as confirmation and optionally emit alerts
            if self.llm_enabled and classify_news_items and rss_items:
                enriched = rss_items
                if enrich_items_with_fulltext:
                    try:
                        enriched = enrich_items_with_fulltext(
                            rss_items,
                            allow_domains=self.settings_cfg.global_.safety.allowlist_domains,
                            max_items=self.llm_max_items,
                            max_chars=self.llm_max_chars,
                        )
                    except Exception:
                        enriched = rss_items[: self.llm_max_items]
                try:
                    filtered, meta = classify_news_items(
                        enriched,
                        location_id=location.id,
                        geo_terms=(keywords or {}).get("geo_terms", []),
                        max_items=self.llm_max_items,
                    )
                except Exception as err:  # pragma: no cover
                    filtered, meta = [], {"used": True, "error": str(err)}
                llm_result = SourceResult(
                    provider="llm_news",
                    location_id=location.id,
                    items=filtered,
                    ok=True,
                    error=None if filtered else "no_relevant_items",
                    latency_ms=None,
                )
                self.summary.record_source(llm_result)
                self.metrics.record_fetch(self.summary.run_id, llm_result)
                if filtered:
                    self.signals.record_confirmation(location.id, "llm_news")
                    if self.llm_emit_alerts:
                        for i in filtered:
                            sev = int(i.get("severity") or 1)
                            priority = 2 if sev >= 3 else 1
                            title = f"[{location.id.upper()}] {i.get('title','News item')}"
                            body = normalize_ascii(i.get("content") or i.get("summary") or i.get("title") or "")
                            reason = f"llm:{i.get('category','news')} sev={sev}; {i.get('reason','')}"
                            decision = AlertDecision(
                                provider="llm_news",
                                location_id=location.id,
                                title=title,
                                body=body[:5000],
                                priority=priority,
                                url=i.get("link"),
                                category="news",
                                reason=reason,
                            )
                            self._emit_if_needed(decision)
            hysteria_active = self.signals.hysteria_active(location.id)
            if hysteria_active:
                LOGGER.info("HYSTERIA active for %s", location.id)
            for item in pending_nws:
                decision = self._decision_from_nws(location_payload, keywords, item, hysteria_active)
                if decision:
                    self._emit_if_needed(decision)
            for item in pending_usgs:
                decision = self._decision_from_usgs(location.id, item)
                if decision:
                    self._emit_if_needed(decision)
        self.state.save()
        self.summary.write()
        ended_at = utcnow()
        self.metrics.record_run_end(self.summary.run_id, ended_at, (ended_at - self.run_started_at).total_seconds())
        self.metrics.close()
        self.signals.reset_run_state()

    def _decision_from_nws(
        self,
        location_payload: Dict[str, Any],
        keywords: Dict[str, Any],
        item: Dict[str, Any],
        hysteria_active: bool,
    ) -> AlertDecision | None:
        if not self._nws_impacts_location(location_payload, keywords, item):
            return None
        severity = (item.get("severity") or "").title()
        event = item.get("event") or "NWS Alert"
        is_watch = "watch" in event.lower() or severity.lower() in {"minor", "moderate"}
        if is_watch and not hysteria_active:
            return None
        if severity not in self.severe_thresholds and not hysteria_active:
            return None
        urgency = (item.get("urgency") or "").lower()
        priority = 2 if severity in self.severe_thresholds or urgency == "immediate" else 1
        reason_bits = [f"severity={severity}"]
        if hysteria_active:
            reason_bits.append("hysteria")
        title = f"[{location_payload['id'].upper()}] {event}"
        body = normalize_ascii(item.get("description") or item.get("headline") or "")
        return AlertDecision(
            provider="nws",
            location_id=location_payload["id"],
            title=title,
            body=body[:5000],
            priority=priority,
            url=item.get("uri"),
            category="nws",
            reason=";".join(reason_bits),
        )

    def _decision_from_usgs(self, location_id: str, item: Dict[str, str | float | None]) -> AlertDecision | None:
        mag = item.get("mag") or 0
        overrides = self.settings_cfg.per_location_overrides.root.get(location_id, {})
        normal = overrides.get("quake_min_mag_normal", self.locations_cfg.defaults.quake_min_mag_normal)
        emergency = overrides.get("quake_min_mag_emergency", self.locations_cfg.defaults.quake_min_mag_emergency)
        if mag < normal:
            return None
        priority = 2 if mag >= emergency else 1
        title = f"[{location_id.upper()}] M{mag} earthquake"
        body = normalize_ascii(item.get("place") or "USGS event")
        return AlertDecision(
            provider="usgs",
            location_id=location_id,
            title=title,
            body=body,
            priority=priority,
            url=item.get("url"),
            category="earthquake",
            reason=f"mag={mag}",
        )

    def _emit_if_needed(self, decision: AlertDecision) -> None:
        key = AlertKey(location_id=decision.location_id, provider=decision.provider, external_id=decision.title, category=decision.category)
        cooldown_bucket = f"{decision.location_id}:{decision.category}:{decision.priority}"
        if self.state.is_seen(key):
            LOGGER.info("Skipping duplicate alert %s", decision.title)
            return
        if self.state.in_cooldown(cooldown_bucket):
            LOGGER.info("Cooldown active for %s", cooldown_bucket)
            return
        payload = AlertPayload(
            title=decision.title,
            body=f"{decision.body}\nReason: {decision.reason}",
            priority=decision.priority,
            url=decision.url,
            location_id=decision.location_id,
        )
        channels = self.dispatcher.dispatch(payload)
        self.summary.record_alert(decision, channels)
        self.state.mark_seen(key)
        self.state.start_cooldown(cooldown_bucket, self.settings_cfg.hysteria.cooldown_minutes)
        alert_id = key.composite()
        self.metrics.record_alert(
            self.summary.run_id,
            alert_id,
            decision.location_id,
            decision.__dict__,
            channels,
            utcnow(),
        )

    def _nws_impacts_location(self, location_payload: Dict[str, Any], keywords: Dict[str, Any], item: Dict[str, Any]) -> bool:
        area_desc = normalize_ascii(item.get("area_desc") or "").lower()
        headline = normalize_ascii(item.get("headline") or "").lower()
        search_text = f"{area_desc} {headline}"
        if not search_text.strip():
            return True
        tokens = {
            normalize_ascii(location_payload.get("label", "")).lower(),
            location_payload["id"].lower(),
        }
        tokens.update(term.lower() for term in keywords.get("geo_terms", []))
        return any(token and token in search_text for token in tokens)

    # NewsAPI no longer used; LLM classification over RSS is the primary news path.


def run_once(dry_run: bool = False) -> None:
    logging.basicConfig(level=logging.INFO)
    runner = PrepperAlertsRunner(dry_run=dry_run)
    runner.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Prepper Alerts orchestrator once.")
    parser.add_argument("--dry-run", action="store_true", help="Prevent outbound notifications.")
    args = parser.parse_args()
    run_once(dry_run=args.dry_run)
