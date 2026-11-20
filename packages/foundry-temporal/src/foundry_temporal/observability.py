# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Observability Integration (Prometheus Metrics)

Metrics and workflow event logging based on foundry-temporal architecture specifications.
"""

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

# Import logging functionality from separate module to avoid sandbox issues
from .logging import get_logger

# Prometheus metrics (required dependency)
try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    PROMETHEUS_AVAILABLE = True
except ImportError:
    # Fallback for environments where prometheus_client is not available
    PROMETHEUS_AVAILABLE = False
    Counter = Histogram = Gauge = None  # type: ignore
    start_http_server: Callable[[int], Any] | None = None  # type: ignore


# No-op metrics class (always available for testing)
class NoOpMetric:
    def inc(self, *args, **kwargs):
        pass

    def observe(self, *args, **kwargs):
        pass

    def labels(self, *args, **kwargs):
        return self


# Workflow Metrics (from architecture specification)
if PROMETHEUS_AVAILABLE:
    research_workflows_started_total = Counter("research_workflows_started_total", "Total research workflows started")  # type: ignore

    research_workflows_completed_total = Counter(  # type: ignore
        "research_workflows_completed_total",
        "Total completed workflows by status",
        ["status"],  # completed/timeout/failed
    )

    research_iterations = Histogram("research_iterations", "Number of feedback iterations per workflow")  # type: ignore

    # Activity Metrics
    agent_call_duration_seconds = Histogram("agent_call_duration_seconds", "Duration of agent calls")  # type: ignore

    agent_call_errors_total = Counter("agent_call_errors_total", "Total agent call errors by type", ["error_type"])  # type: ignore

    # Storage Metrics
    storage_operations_total = Counter(  # type: ignore
        "storage_operations_total", "Total storage operations", ["operation", "backend", "status"]
    )

    storage_operation_duration_seconds = Histogram(  # type: ignore
        "storage_operation_duration_seconds", "Duration of storage operations", ["operation", "backend"]
    )
else:
    # No-op metrics when Prometheus is not available
    research_workflows_started_total = NoOpMetric()
    research_workflows_completed_total = NoOpMetric()
    research_iterations = NoOpMetric()
    agent_call_duration_seconds = NoOpMetric()
    agent_call_errors_total = NoOpMetric()
    storage_operations_total = NoOpMetric()
    storage_operation_duration_seconds = NoOpMetric()


# Context managers for timing operations
@contextmanager
def time_agent_call() -> Generator:
    """Context manager for timing agent calls"""
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        agent_call_duration_seconds.observe(duration)


@contextmanager
def time_storage_operation(operation: str, backend: str) -> Generator:
    """Context manager for timing storage operations"""
    start_time = time.time()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.time() - start_time
        storage_operations_total.labels(operation=operation, backend=backend, status=status).inc()
        storage_operation_duration_seconds.labels(operation=operation, backend=backend).observe(duration)


# Metrics server for Prometheus
def start_metrics_server(port: int = 9090):
    """
    Start Prometheus metrics HTTP server

    Args:
        port: Port to serve metrics on (default: 9090)
    """
    if PROMETHEUS_AVAILABLE and start_http_server:
        start_http_server(port)  # type: ignore
        get_logger().info("metrics_server_started", port=port)
    else:
        get_logger().warning("metrics_server_not_started", reason="prometheus_client not available")


# Health check utilities
def get_health_status() -> dict[str, Any]:
    """
    Get health status for workflow components

    Returns:
        Dictionary with health information
    """
    from .logging import STRUCTLOG_AVAILABLE

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "observability": {
            "prometheus_available": PROMETHEUS_AVAILABLE,
            "structlog_available": STRUCTLOG_AVAILABLE,
        },
        "components": {"logging": "active", "metrics": "active" if PROMETHEUS_AVAILABLE else "disabled"},
    }
