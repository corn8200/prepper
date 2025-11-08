from pathlib import Path

from scripts.config_models import LocationsConfig, SettingsConfig, KeywordsConfig
from scripts.validate import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def test_locations_config_valid():
    payload = load_yaml(ROOT / "config" / "locations.yaml")
    cfg = LocationsConfig.model_validate(payload)
    assert cfg.locations, "should have default locations"


def test_settings_config_valid():
    payload = load_yaml(ROOT / "config" / "settings.yaml")
    cfg = SettingsConfig.model_validate(payload)
    assert cfg.global_.schedule_minutes == 10


def test_keywords_placeholder():
    payload = load_yaml(ROOT / "config" / "keywords.yaml")
    cfg = KeywordsConfig.model_validate(payload)
    assert "union" in cfg.model_dump()
