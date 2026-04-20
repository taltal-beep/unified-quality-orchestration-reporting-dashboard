"""Tests for integration façade functions (mock HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.integrations import test_prometheus_pushgateway


def test_test_prometheus_pushgateway_ok() -> None:
    with patch("engine.integrations.requests.get") as get:
        get.return_value = MagicMock(status_code=200, text="ok")
        ok, _msg = test_prometheus_pushgateway(pushgateway_url="http://localhost:9091")
        assert ok is True


def test_test_prometheus_pushgateway_empty_url() -> None:
    ok, msg = test_prometheus_pushgateway(pushgateway_url=None)
    assert ok is False and "PROMETHEUS" in msg

