# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Observability Integration (OpenTelemetry Tracing)

Native OpenTelemetry tracing setup for Temporal workers/clients, mirroring the
observability.py Prometheus metrics module's shape. Wraps temporalio's own
temporalio.contrib.opentelemetry.TracingInterceptor, which needs no special
wiring to a specific TracerProvider instance beyond the global
opentelemetry.trace.set_tracer_provider() call this module performs.
"""

from importlib.metadata import version
from typing import Any

from .logging import get_logger

# OpenTelemetry SDK (required dependency, see pyproject.toml). Defensive
# try/except mirrors observability.py's PROMETHEUS_AVAILABLE shape for
# consistency across this package's two observability modules.
try:
    import opentelemetry.trace as trace_api
    from opentelemetry import propagate
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from temporalio.contrib.opentelemetry import TracingInterceptor

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace_api = None  # type: ignore
    propagate = None  # type: ignore
    W3CBaggagePropagator = CompositePropagator = None  # type: ignore
    Resource = SDKTracerProvider = None  # type: ignore
    BatchSpanProcessor = ConsoleSpanExporter = SimpleSpanProcessor = None  # type: ignore
    TraceContextTextMapPropagator = None  # type: ignore
    TracingInterceptor = None  # type: ignore


_MAX_SERVICE_NAME_LEN = 255


def _validate_service_name(value: str) -> None:
    """Reject empty, oversized, or control-character service names (STIG V-222606).

    service.name is emitted as an OTel resource attribute on every span/metric this
    process produces, so an unvalidated env var here reaches whatever OTLP backend
    is configured. Bounds length and rejects control characters (including
    newlines) to prevent unbounded-size or log/metric-injection payloads; otherwise
    permissive, since OTel's own semantic conventions place no charset restriction
    on service.name.
    """
    if not value:
        raise ValueError("OTEL_SERVICE_NAME must not be empty")
    if len(value) > _MAX_SERVICE_NAME_LEN:
        raise ValueError(f"OTEL_SERVICE_NAME exceeds {_MAX_SERVICE_NAME_LEN} characters: {value!r}")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        raise ValueError(f"OTEL_SERVICE_NAME contains control characters: {value!r}")


def get_otel_resource(service_name: str = "foundry-temporal") -> Resource:  # type: ignore
    """Create a standard OpenTelemetry resource with service information.

    Args:
        service_name: Overridden by OTEL_SERVICE_NAME if that env var is set.

    Returns:
        Resource object with standard service information.

    Raises:
        ValueError: The resolved service name is empty, too long, or contains
            control characters (STIG V-222606).
    """
    import os

    resolved_name = os.getenv("OTEL_SERVICE_NAME", service_name).strip()
    _validate_service_name(resolved_name)

    return Resource.create(  # type: ignore
        {
            "service.name": resolved_name,
            "service.version": version("foundry-temporal"),
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.language": "python",
        }
    )


class FoundryTracing:
    """OpenTelemetry tracing configuration and setup for foundry-temporal workers/clients.

    Automatically initializes a tracer provider with text map propagators, without
    passing an explicit sampler — sampler resolution is left to the OpenTelemetry
    SDK's own OTEL_TRACES_SAMPLER/OTEL_TRACES_SAMPLER_ARG env-var handling (defaults
    to parentbased_always_on when unset).

    Trace exporters (console, OTLP) are set up individually via dedicated methods
    that support method chaining.

    Examples:
        >>> tracing = FoundryTracing().setup_otlp_exporter()
        >>> interceptor = tracing.get_interceptor()
    """

    def __init__(self, tracer_provider: SDKTracerProvider | None = None) -> None:  # type: ignore
        if not OTEL_AVAILABLE:
            get_logger().warning("otel_not_available", reason="opentelemetry packages not installed")
            # Preserve whatever was passed rather than discarding it - unreachable in
            # practice (opentelemetry-sdk is a hard dependency of this package, so a
            # real SDKTracerProvider instance implies OTEL_AVAILABLE is already True),
            # but a caller-supplied argument should never be silently dropped.
            self.tracer_provider = tracer_provider
            return

        self.resource = get_otel_resource()
        if tracer_provider:
            self.tracer_provider = tracer_provider
        else:
            self._initialize_tracer()

    def _initialize_tracer(self) -> None:
        """Initialize the OpenTelemetry tracer provider and propagators."""
        get_logger().info("initializing_tracer")

        self.tracer_provider = SDKTracerProvider(resource=self.resource)  # type: ignore
        trace_api.set_tracer_provider(self.tracer_provider)  # type: ignore

        propagate.set_global_textmap(  # type: ignore
            CompositePropagator(  # type: ignore
                [
                    W3CBaggagePropagator(),  # type: ignore
                    TraceContextTextMapPropagator(),  # type: ignore
                ]
            )
        )

    def setup_console_exporter(self, **kwargs: Any) -> FoundryTracing:
        """Set up a console span exporter for local development.

        Failures are logged, not raised, matching this method's OTLP counterpart.
        """
        if not OTEL_AVAILABLE or not self.tracer_provider:
            return self
        try:
            self.tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(**kwargs)))  # type: ignore
            get_logger().info("console_exporter_enabled")
        except Exception as e:
            get_logger().warning("console_exporter_setup_failed", error=str(e))
        return self

    def setup_otlp_exporter(self, **kwargs: Any) -> FoundryTracing:
        """Set up an OTLP span exporter (reads OTEL_EXPORTER_OTLP_ENDPOINT/HEADERS if unset).

        Failures are logged, not raised, so a missing/unreachable collector never
        prevents worker/client startup.
        """
        if not OTEL_AVAILABLE or not self.tracer_provider:
            return self
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            self.tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**kwargs)))  # type: ignore
            get_logger().info("otlp_exporter_enabled")
        except Exception as e:
            get_logger().warning("otlp_exporter_setup_failed", error=str(e))
        return self

    def get_interceptor(self) -> TracingInterceptor | None:  # type: ignore
        """Return a ready-to-use TracingInterceptor for this tracer provider.

        TracingInterceptor.__init__ falls back to opentelemetry.trace.get_tracer()
        when no tracer is passed, which resolves against whatever tracer provider
        this instance already made global via _initialize_tracer() — no explicit
        tracer wiring is needed here.
        """
        if not OTEL_AVAILABLE:
            get_logger().warning("otel_not_available", reason="cannot create TracingInterceptor")
            return None
        return TracingInterceptor()  # type: ignore


# Module-level singleton: a Temporal worker process typically calls
# create_temporal_client() and create_worker_with_defaults() in the same process.
# opentelemetry.trace.set_tracer_provider() silently refuses a second call (logs a
# warning, keeps the first provider global) - constructing a second FoundryTracing
# independently would waste its own setup_otlp_exporter() call, since the resulting
# TracingInterceptor always resolves against whichever provider is actually global.
# Lazily initializing exactly one instance, shared by both call sites, avoids that
# double-init trap entirely.
_tracing_instance: FoundryTracing | None = None


def get_tracing_interceptor() -> TracingInterceptor | None:  # type: ignore
    """Return a TracingInterceptor backed by a process-wide FoundryTracing instance.

    Initializes that instance (tracer provider + OTLP exporter) on first call;
    subsequent calls reuse it. Safe to call from both create_temporal_client() and
    create_worker_with_defaults() in the same process.
    """
    global _tracing_instance
    if _tracing_instance is None:
        _tracing_instance = FoundryTracing().setup_otlp_exporter()
    return _tracing_instance.get_interceptor()
