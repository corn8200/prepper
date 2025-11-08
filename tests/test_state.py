from pathlib import Path

from scripts.state import AlertKey, StateStore


def test_state_cooldown(tmp_path: Path):
    store = StateStore.load(tmp_path / "state.json")
    key = AlertKey(location_id="home", provider="nws", external_id="abc", category="nws")
    assert not store.is_seen(key)
    store.mark_seen(key)
    assert store.is_seen(key)
    bucket = "home:nws:1"
    store.start_cooldown(bucket, 1)
    assert store.in_cooldown(bucket)


def test_state_metadata_roundtrip(tmp_path: Path):
    path = tmp_path / "state_meta.json"
    store = StateStore.load(path)
    store.set_metadata("newsapi_last_run", "2024-01-01T00:00:00+00:00")
    store.save()
    reloaded = StateStore.load(path)
    assert reloaded.get_metadata("newsapi_last_run") == "2024-01-01T00:00:00+00:00"
