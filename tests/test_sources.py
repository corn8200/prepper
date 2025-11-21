import requests

from scripts.sources.eonet import EONETClient
from scripts.sources.nws import NWSClient
from scripts.sources.usgs import USGSClient


def _boom(*args, **kwargs):
    raise requests.RequestException("boom")


def test_nws_handles_request_error(monkeypatch):
    monkeypatch.setattr("scripts.sources.nws.requests.get", _boom)
    client = NWSClient()
    result = client.fetch({"id": "home", "lat": 0, "lon": 0})
    assert result.ok is False
    assert result.items == []
    assert "boom" in (result.error or "")


def test_usgs_handles_request_error(monkeypatch):
    monkeypatch.setattr("scripts.sources.usgs.requests.get", _boom)
    client = USGSClient()
    result = client.fetch({"id": "home", "lat": 0, "lon": 0, "radius_km": 10})
    assert result.ok is False
    assert result.items == []
    assert "boom" in (result.error or "")


def test_eonet_handles_request_error(monkeypatch):
    monkeypatch.setattr("scripts.sources.eonet.requests.get", _boom)
    client = EONETClient()
    result = client.fetch({"id": "home"})
    assert result.ok is False
    assert result.items == []
    assert "boom" in (result.error or "")
