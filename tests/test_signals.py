from scripts.signals import RollingBaseline, SignalsEngine


def test_signals_trips_on_spike():
    engine = SignalsEngine(news_min_mentions=3, news_spike_factor=2.0, require_domains=2, hysteria_sources=2)
    engine.record_news("home", count=3, distinct_domains=2)
    surge = engine.record_news("home", count=10, distinct_domains=3)
    assert surge.tripped
    engine.record_confirmation("home", "gdelt")
    assert engine.hysteria_active("home") is True


def test_rolling_baseline_uses_previous_samples():
    baseline = RollingBaseline()
    baseline.observe(4)
    previous = baseline.observe(10)
    assert previous == 4
