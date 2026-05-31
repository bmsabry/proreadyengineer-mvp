"""Bandwidth panel: capacity-advisor pure logic. asyncio_mode=auto."""
from app.services import capacity_advisor as CA


def test_parse_series_sums_across_series_and_sorts():
    payload = [
        {"labels": [{"field": "instance", "value": "a"}],
         "values": [{"timestamp": "2026-01-01T00:02:00Z", "value": 1.0, "unit": "n"},
                    {"timestamp": "2026-01-01T00:01:00Z", "value": 2.0, "unit": "n"}]},
        {"labels": [{"field": "instance", "value": "b"}],
         "values": [{"timestamp": "2026-01-01T00:01:00Z", "value": 3.0, "unit": "n"}]},
    ]
    pts = CA.parse_series(payload)
    assert pts == [("2026-01-01T00:01:00Z", 5.0), ("2026-01-01T00:02:00Z", 1.0)]


def test_parse_series_handles_garbage():
    assert CA.parse_series(None) == []
    assert CA.parse_series([{"nope": 1}, "x", {"values": [{"timestamp": "t"}]}]) == []


def test_summarize_basic_stats():
    pts = [(str(i), float(i)) for i in range(1, 101)]  # 1..100
    s = CA.summarize(pts)
    assert s["peak"] == 100 and s["latest"] == 100 and s["count"] == 100
    assert s["avg"] == 50.5
    assert 94 <= s["p95"] <= 96
    assert len(s["spark"]) <= 40


def test_trend_detects_growth():
    rising = [(str(i), float(i)) for i in range(10)]   # 0..9 climbing
    assert CA.trend_pct(rising) > 50
    flat = [(str(i), 5.0) for i in range(10)]
    assert CA.trend_pct(flat) == 0.0
    assert CA.trend_pct([("a", 1.0)]) is None  # too few points


def test_next_plan_walks_up_the_ladder():
    assert CA.next_plan("starter")["plan"] == "standard"
    assert CA.next_plan("standard")["plan"] == "pro"
    assert CA.next_plan("pro ultra") is None  # top of ladder


def test_recommend_scale_now_at_high_utilization():
    rec = CA.recommend(cpu_pct=90, mem_pct=60, cpu_trend=10, current_plan="starter")
    assert rec["status"] == "scale_now"
    assert rec["suggested_plan"]["plan"] == "standard"


def test_recommend_watch_and_healthy():
    assert CA.recommend(72, 40, 5, "starter")["status"] == "watch"
    assert CA.recommend(55, 30, 40, "starter")["status"] == "watch"   # rising pushes to watch
    assert CA.recommend(40, 30, 5, "starter")["status"] == "healthy"


def test_recommend_unknown_when_no_data():
    rec = CA.recommend(None, None, None, "starter")
    assert rec["status"] == "unknown" and rec["suggested_plan"] is None
