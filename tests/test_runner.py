import json

import scripts.prepper_alerts as pa


class _BoomSource:
    provider = "boom"

    def fetch(self, location, keywords=None):
        raise RuntimeError("boom")


class _OkSource:
    provider = "ok"

    def fetch(self, location, keywords=None):
        return pa.SourceResult(provider=self.provider, location_id=location["id"], items=[], ok=True, latency_ms=1)


def test_runner_records_failed_source(monkeypatch, tmp_path):
    pa.DATA_DIR = tmp_path
    pa.LATEST_RUN_PATH = tmp_path / "latest_run.json"
    pa.STATE_PATH = tmp_path / "alerts_state.json"

    def fake_sources(self, news_stack, allow_domains):
        return {"boom": _BoomSource(), "ok": _OkSource()}

    monkeypatch.setattr(pa.PrepperAlertsRunner, "_build_sources", fake_sources)

    runner = pa.PrepperAlertsRunner(dry_run=True)
    runner.run()

    payload = json.loads(pa.LATEST_RUN_PATH.read_text())
    boom_meta = payload["locations"]["home"]["sources"]["boom"]
    assert boom_meta["ok"] is False
    assert "boom" in boom_meta["error"]
