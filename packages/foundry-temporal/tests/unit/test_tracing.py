# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.tracing module"""

import os
from unittest.mock import MagicMock, patch

import pytest
from foundry_temporal.tracing import (
    OTEL_AVAILABLE,
    FoundryTracing,
    get_otel_resource,
    get_tracing_interceptor,
)


class TestGetOtelResource:
    def test_default_service_name(self):
        with patch.dict(os.environ, {}, clear=True):
            resource = get_otel_resource()

        assert resource.attributes["service.name"] == "foundry-temporal"

    def test_otel_service_name_env_var_overrides_default(self):
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "my-custom-worker"}):
            resource = get_otel_resource()

        assert resource.attributes["service.name"] == "my-custom-worker"

    def test_service_version_present(self):
        resource = get_otel_resource()

        assert resource.attributes["service.version"]
        assert resource.attributes["telemetry.sdk.name"] == "opentelemetry"
        assert resource.attributes["telemetry.sdk.language"] == "python"

    def test_empty_service_name_rejected(self):
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "   "}):
            with pytest.raises(ValueError, match="must not be empty"):
                get_otel_resource()

    def test_oversized_service_name_rejected(self):
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "x" * 256}):
            with pytest.raises(ValueError, match="exceeds 255 characters"):
                get_otel_resource()

    def test_max_length_service_name_accepted(self):
        name = "x" * 255
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": name}):
            resource = get_otel_resource()

        assert resource.attributes["service.name"] == name

    def test_control_character_service_name_rejected(self):
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "worker\nname"}):
            with pytest.raises(ValueError, match="control characters"):
                get_otel_resource()

    def test_default_parameter_bypassing_env_var_still_validated(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="control characters"):
                get_otel_resource(service_name="bad\x00name")


class TestFoundryTracing:
    def test_tracer_provider_constructed_without_explicit_sampler(self):
        tracing = FoundryTracing()

        # No explicit sampler was passed to SDKTracerProvider - resolution is left
        # to OTel's own OTEL_TRACES_SAMPLER/OTEL_TRACES_SAMPLER_ARG env-var handling.
        assert tracing.tracer_provider is not None
        assert "AlwaysOnSampler" in tracing.tracer_provider.sampler.get_description()

    def test_get_interceptor_returns_tracing_interceptor(self):
        from temporalio.contrib.opentelemetry import TracingInterceptor

        tracing = FoundryTracing()
        interceptor = tracing.get_interceptor()

        assert isinstance(interceptor, TracingInterceptor)

    def test_accepts_pre_built_tracer_provider(self):
        from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

        provider = SDKTracerProvider(resource=get_otel_resource())
        tracing = FoundryTracing(tracer_provider=provider)

        assert tracing.tracer_provider is provider

    def test_setup_console_exporter_is_chainable(self):
        tracing = FoundryTracing().setup_console_exporter()

        assert isinstance(tracing, FoundryTracing)

    def test_setup_otlp_exporter_is_chainable(self):
        tracing = FoundryTracing().setup_otlp_exporter()

        assert isinstance(tracing, FoundryTracing)

    def test_setup_otlp_exporter_does_not_raise_on_failure(self):
        tracing = FoundryTracing()

        with patch.object(
            tracing.tracer_provider, "add_span_processor", side_effect=Exception("collector unreachable")
        ):
            result = tracing.setup_otlp_exporter()

        assert result is tracing

    def test_setup_console_exporter_does_not_raise_on_failure(self):
        tracing = FoundryTracing()

        with patch.object(tracing.tracer_provider, "add_span_processor", side_effect=Exception("boom")):
            result = tracing.setup_console_exporter()

        assert result is tracing

    @patch("foundry_temporal.tracing.OTEL_AVAILABLE", False)
    def test_otel_unavailable_disables_tracer_provider(self):
        tracing = FoundryTracing()

        assert tracing.tracer_provider is None

    @patch("foundry_temporal.tracing.OTEL_AVAILABLE", False)
    def test_otel_unavailable_preserves_caller_supplied_tracer_provider(self):
        """A caller-supplied argument must never be silently discarded, even on this
        defensive branch (unreachable in practice: a real SDKTracerProvider instance
        implies OTEL_AVAILABLE is already True)."""
        sentinel = MagicMock()

        tracing = FoundryTracing(tracer_provider=sentinel)

        assert tracing.tracer_provider is sentinel

    @patch("foundry_temporal.tracing.OTEL_AVAILABLE", False)
    def test_get_interceptor_returns_none_when_otel_unavailable(self):
        tracing = FoundryTracing()

        assert tracing.get_interceptor() is None

    @patch("foundry_temporal.tracing.OTEL_AVAILABLE", False)
    def test_setup_exporters_are_noop_when_otel_unavailable(self):
        tracing = FoundryTracing()

        result = tracing.setup_console_exporter().setup_otlp_exporter()

        assert result is tracing


class TestGetTracingInterceptor:
    def setup_method(self):
        import foundry_temporal.tracing as tracing_module

        tracing_module._tracing_instance = None

    def teardown_method(self):
        import foundry_temporal.tracing as tracing_module

        tracing_module._tracing_instance = None

    def test_returns_tracing_interceptor(self):
        from temporalio.contrib.opentelemetry import TracingInterceptor

        interceptor = get_tracing_interceptor()

        assert isinstance(interceptor, TracingInterceptor)

    def test_reuses_singleton_across_calls(self):
        import foundry_temporal.tracing as tracing_module

        get_tracing_interceptor()
        first_instance = tracing_module._tracing_instance
        get_tracing_interceptor()
        second_instance = tracing_module._tracing_instance

        assert first_instance is second_instance

    def test_only_initializes_foundry_tracing_once(self):
        with patch("foundry_temporal.tracing.FoundryTracing") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.setup_otlp_exporter.return_value = mock_instance
            mock_cls.return_value = mock_instance

            get_tracing_interceptor()
            get_tracing_interceptor()

            mock_cls.assert_called_once()


class TestOtelAvailableFlag:
    def test_otel_available_is_bool(self):
        assert isinstance(OTEL_AVAILABLE, bool)

    @pytest.mark.skipif(not OTEL_AVAILABLE, reason="requires opentelemetry packages installed")
    def test_otel_available_true_in_this_environment(self):
        assert OTEL_AVAILABLE is True
