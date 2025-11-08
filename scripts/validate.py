"""Config validation entrypoint used by CI and dashboard write-back."""

from __future__ import annotations

from pathlib import Path
import yaml
from pydantic import BaseModel, ValidationError

from .config_models import (
    KeywordsConfig,
    LocationsConfig,
    SettingsConfig,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def validate_file(model: type[BaseModel], path: Path) -> None:
    data = load_yaml(path)
    try:
        model.model_validate(data)
    except ValidationError as exc:
        raise SystemExit(f"Validation failed for {path}:\n{exc}") from exc


def main() -> None:
    validate_file(LocationsConfig, CONFIG_DIR / "locations.yaml")
    validate_file(SettingsConfig, CONFIG_DIR / "settings.yaml")
    validate_file(KeywordsConfig, CONFIG_DIR / "keywords.yaml")


if __name__ == "__main__":
    main()
