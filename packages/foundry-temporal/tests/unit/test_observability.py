# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.observability module

Tests for Prometheus metrics, timing context managers, metrics server, and health checks.
Logging-related tests are in test_logging.py.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from foundry_temporal.observability import (
    PROMETHEUS_AVAILABLE,
    get_health_status,
    start_metrics_server,
    time_agent_call,
    time_storage_operation,
)


class TestTimeAgentCall:
    @patch("foundry_temporal.observability.agent_call_duration_seconds")
    @patch("time.time")
    def test_time_agent_call_success(self, mock_time, mock_metric):
        """Test time_agent_call context manager for successful operation"""
        mock_time.side_effect = [100.0, 105.5]  # start, end times

        with time_agent_call():
            pass  # Simulate operation

        mock_metric.observe.assert_called_once_with(5.5)

    @patch("foundry_temporal.observability.agent_call_duration_seconds")
    @patch("time.time")
    def test_time_agent_call_with_exception(self, mock_time, mock_metric):
        """Test time_agent_call context manager when operation raises exception"""
        mock_time.side_effect = [100.0, 103.2]

        with pytest.raises(ValueError):
            with time_agent_call():
                raise ValueError("Test error")

        # Should still record timing even when exception occurs
        mock_metric.observe.assert_called_once_with(pytest.approx(3.2))


class TestTimeStorageOperation:
    @patch("foundry_temporal.observability.storage_operations_total")
    @patch("foundry_temporal.observability.storage_operation_duration_seconds")
    @patch("time.time")
    def test_time_storage_operation_success(self, mock_time, mock_duration_metric, mock_count_metric):
        """Test time_storage_operation for successful operation"""
        mock_time.side_effect = [100.0, 102.5]

        with time_storage_operation("store", "s3"):
            pass

        # Should record success metrics
        mock_count_metric.labels.assert_called_once_with(operation="store", backend="s3", status="success")
        mock_count_metric.labels.return_value.inc.assert_called_once()

        mock_duration_metric.labels.assert_called_once_with(operation="store", backend="s3")
        mock_duration_metric.labels.return_value.observe.assert_called_once_with(2.5)

    @patch("foundry_temporal.observability.storage_operations_total")
    @patch("foundry_temporal.observability.storage_operation_duration_seconds")
    @patch("time.time")
    def test_time_storage_operation_error(self, mock_time, mock_duration_metric, mock_count_metric):
        """Test time_storage_operation when operation fails"""
        mock_time.side_effect = [100.0, 101.8]

        with pytest.raises(RuntimeError):
            with time_storage_operation("retrieve", "dynamodb"):
                raise RuntimeError("Storage error")

        # Should record error metrics
        mock_count_metric.labels.assert_called_once_with(operation="retrieve", backend="dynamodb", status="error")
        mock_duration_metric.labels.return_value.observe.assert_called_once_with(pytest.approx(1.8))


class TestStartMetricsServer:
    @patch("foundry_temporal.observability.start_http_server")
    @patch("foundry_temporal.observability.get_logger")
    def test_start_metrics_server_prometheus_available(self, mock_get_logger, mock_start_server):
        """Test start_metrics_server when Prometheus is available"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        with patch("foundry_temporal.observability.PROMETHEUS_AVAILABLE", True):
            start_metrics_server(8080)

        mock_start_server.assert_called_once_with(8080)
        mock_logger.info.assert_called_once_with("metrics_server_started", port=8080)

    @patch("foundry_temporal.observability.get_logger")
    def test_start_metrics_server_prometheus_unavailable(self, mock_get_logger):
        """Test start_metrics_server when Prometheus is unavailable"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        with patch("foundry_temporal.observability.PROMETHEUS_AVAILABLE", False):
            start_metrics_server(9090)

        mock_logger.warning.assert_called_once_with(
            "metrics_server_not_started", reason="prometheus_client not available"
        )

    @patch("foundry_temporal.observability.start_http_server")
    @patch("foundry_temporal.observability.get_logger")
    def test_start_metrics_server_default_port(self, mock_get_logger, mock_start_server):
        """Test start_metrics_server with default port"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        with patch("foundry_temporal.observability.PROMETHEUS_AVAILABLE", True):
            start_metrics_server()

        mock_start_server.assert_called_once_with(9090)  # Default port


class TestGetHealthStatus:
    @patch("foundry_temporal.logging._get_structlog")
    def test_get_health_status(self, mock_get_structlog):
        """Test get_health_status returns proper health information"""
        mock_get_structlog.return_value = (None, True)

        with patch("foundry_temporal.observability.PROMETHEUS_AVAILABLE", True):
            with patch("foundry_temporal.logging.STRUCTLOG_AVAILABLE", True):
                status = get_health_status()

        assert status["status"] == "healthy"
        assert "timestamp" in status
        assert status["observability"]["prometheus_available"] is True
        assert status["observability"]["structlog_available"] is True
        assert status["components"]["logging"] == "active"
        assert status["components"]["metrics"] == "active"

    @patch("foundry_temporal.logging._get_structlog")
    def test_get_health_status_no_prometheus(self, mock_get_structlog):
        """Test get_health_status when Prometheus is unavailable"""
        mock_get_structlog.return_value = (None, False)

        with patch("foundry_temporal.observability.PROMETHEUS_AVAILABLE", False):
            with patch("foundry_temporal.logging.STRUCTLOG_AVAILABLE", False):
                status = get_health_status()

        assert status["observability"]["prometheus_available"] is False
        assert status["observability"]["structlog_available"] is False
        assert status["components"]["metrics"] == "disabled"

    def test_get_health_status_timestamp_format(self):
        """Test get_health_status timestamp is properly formatted"""
        with patch("foundry_temporal.logging._get_structlog") as mock_get_structlog:
            mock_get_structlog.return_value = (None, True)

            status = get_health_status()

            # Should be ISO format timestamp
            timestamp = status["timestamp"]
            assert isinstance(timestamp, str)
            # Should be parseable as datetime
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


class TestPrometheusIntegration:
    def test_prometheus_available_detection(self):
        """Test PROMETHEUS_AVAILABLE is properly detected"""
        # This test checks the actual import detection
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    @patch("foundry_temporal.observability.PROMETHEUS_AVAILABLE", False)
    def test_noop_metrics_when_prometheus_unavailable(self):
        """Test that NoOpMetric is used when Prometheus is unavailable"""
        import foundry_temporal.observability as obs

        assert hasattr(obs, "NoOpMetric")

        noop = obs.NoOpMetric()
        # Should not raise errors
        noop.inc()
        noop.observe(1.5)
        assert noop.labels() is noop
