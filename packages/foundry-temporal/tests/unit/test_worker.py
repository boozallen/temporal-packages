# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.worker module"""

import logging
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from foundry_temporal.worker import (
    WorkerConfig,
    close_temporal_client,
    create_temporal_client,
    create_worker_with_defaults,
)
from temporalio.service import TLSConfig


class TestWorkerConfig:
    def test_init_default_values(self):
        """Test WorkerConfig initialization with default values"""
        with patch("foundry_temporal.worker.os.getpid", return_value=12345):
            config = WorkerConfig()

        assert config.temporal_host == "localhost:7233"
        assert config.temporal_namespace == "default"
        assert config.task_queue == "foundry-workflows"
        assert config.worker_identity == "foundry-worker-12345"
        assert config.max_concurrent_activities == 100
        assert config.max_concurrent_workflow_tasks == 50
        assert config.max_concurrent_local_activities == 200
        assert config.max_concurrent_nexus_tasks == 10
        assert config.log_level == "INFO"
        assert config.metrics_port == 9090
        assert config.health_port == 9091
        assert config.temporal_tls_cert is None
        assert config.temporal_tls_key is None
        assert config.temporal_tls_ca is None

    def test_init_custom_values(self):
        """Test WorkerConfig initialization with custom values"""
        config = WorkerConfig(
            temporal_address="custom-host:7234",
            namespace="custom-namespace",
            task_queue="custom-queue",
            identity="custom-worker",
            max_concurrent_activities=150,
            max_concurrent_workflow_tasks=75,
            max_concurrent_local_activities=300,
            max_concurrent_nexus_tasks=20,
            log_level="DEBUG",
            metrics_port=9999,
            health_port=8888,
            temporal_tls_cert="/path/to/cert.pem",
            temporal_tls_key="/path/to/key.pem",
            temporal_tls_ca="/path/to/ca.pem",
        )

        assert config.temporal_host == "custom-host:7234"
        assert config.temporal_namespace == "custom-namespace"
        assert config.task_queue == "custom-queue"
        assert config.worker_identity == "custom-worker"
        assert config.max_concurrent_activities == 150
        assert config.max_concurrent_workflow_tasks == 75
        assert config.max_concurrent_local_activities == 300
        assert config.max_concurrent_nexus_tasks == 20
        assert config.log_level == "DEBUG"
        assert config.metrics_port == 9999
        assert config.health_port == 8888
        assert config.temporal_tls_cert == "/path/to/cert.pem"
        assert config.temporal_tls_key == "/path/to/key.pem"
        assert config.temporal_tls_ca == "/path/to/ca.pem"

    def test_init_tracing_enabled_default_false(self):
        """Test tracing_enabled defaults to False"""
        config = WorkerConfig()

        assert config.tracing_enabled is False

    def test_init_tracing_enabled_settable_via_constructor(self):
        """Test tracing_enabled can be set via constructor"""
        config = WorkerConfig(tracing_enabled=True)

        assert config.tracing_enabled is True

    def test_init_identity_fallback(self):
        """Test that identity falls back to PID-based name when None"""
        with patch("foundry_temporal.worker.os.getpid", return_value=54321):
            config = WorkerConfig(identity=None)

        assert config.worker_identity == "foundry-worker-54321"

    @patch.dict(os.environ, {}, clear=True)
    def test_from_env_default_values(self):
        """Test from_env with no environment variables set"""
        with patch("foundry_temporal.worker.os.getpid", return_value=12345):
            config = WorkerConfig.from_env()

        assert config.temporal_host == "localhost:7233"
        assert config.temporal_namespace == "default"
        assert config.task_queue == "foundry-workflows"
        assert config.worker_identity == "foundry-worker-12345"
        assert config.max_concurrent_activities == 100
        assert config.max_concurrent_workflow_tasks == 50
        assert config.max_concurrent_local_activities == 200
        assert config.max_concurrent_nexus_tasks == 10
        assert config.log_level == "INFO"
        assert config.metrics_port == 9090
        assert config.health_port == 9091
        assert config.tracing_enabled is False

    @patch.dict(os.environ, {"TRACING_ENABLED": "true"}, clear=True)
    def test_from_env_tracing_enabled_true(self):
        """Test from_env with TRACING_ENABLED=true"""
        config = WorkerConfig.from_env()

        assert config.tracing_enabled is True

    @patch.dict(os.environ, {"TRACING_ENABLED": "false"}, clear=True)
    def test_from_env_tracing_enabled_false(self):
        """Test from_env with TRACING_ENABLED=false"""
        config = WorkerConfig.from_env()

        assert config.tracing_enabled is False

    @patch.dict(
        os.environ,
        {
            "TEMPORAL_HOST": "env-host:7234",
            "TEMPORAL_NAMESPACE": "env-namespace",
            "TASK_QUEUE": "env-queue",
            "WORKER_IDENTITY": "env-worker",
            "MAX_CONCURRENT_ACTIVITIES": "200",
            "MAX_CONCURRENT_WORKFLOW_TASKS": "100",
            "MAX_CONCURRENT_LOCAL_ACTIVITIES": "400",
            "MAX_CONCURRENT_NEXUS_TASKS": "30",
            "LOG_LEVEL": "DEBUG",
            "METRICS_PORT": "8080",
            "HEALTH_PORT": "8081",
            "TEMPORAL_TLS_CERT": "/env/cert.pem",
            "TEMPORAL_TLS_KEY": "/env/key.pem",
            "TEMPORAL_TLS_CA": "/env/ca.pem",
        },
        clear=True,
    )
    def test_from_env_with_environment_variables(self):
        """Test from_env with all environment variables set"""
        config = WorkerConfig.from_env()

        assert config.temporal_host == "env-host:7234"
        assert config.temporal_namespace == "env-namespace"
        assert config.task_queue == "env-queue"
        assert config.worker_identity == "env-worker"
        assert config.max_concurrent_activities == 200
        assert config.max_concurrent_workflow_tasks == 100
        assert config.max_concurrent_local_activities == 400
        assert config.max_concurrent_nexus_tasks == 30
        assert config.log_level == "DEBUG"
        assert config.metrics_port == 8080
        assert config.health_port == 8081
        assert config.temporal_tls_cert == "/env/cert.pem"
        assert config.temporal_tls_key == "/env/key.pem"
        assert config.temporal_tls_ca == "/env/ca.pem"

    @patch.dict(os.environ, {"WORKER_CONCURRENCY": "150"}, clear=True)
    @patch("foundry_temporal.worker.logging")
    def test_from_env_legacy_worker_concurrency(self, mock_logging):
        """Test from_env with legacy WORKER_CONCURRENCY environment variable"""
        mock_logger = Mock()
        mock_logging.getLogger.return_value = mock_logger

        config = WorkerConfig.from_env()

        # Should use legacy value
        assert config.max_concurrent_activities == 150

        # Should log deprecation warning
        mock_logging.getLogger.assert_called_once_with("foundry_temporal.worker")
        mock_logger.warning.assert_called_once_with(
            "WORKER_CONCURRENCY is deprecated, use MAX_CONCURRENT_ACTIVITIES instead"
        )

    @patch.dict(os.environ, {"WORKER_CONCURRENCY": "150", "MAX_CONCURRENT_ACTIVITIES": "200"}, clear=True)
    @patch("foundry_temporal.worker.logging")
    def test_from_env_new_overrides_legacy(self, mock_logging):
        """Test that MAX_CONCURRENT_ACTIVITIES overrides WORKER_CONCURRENCY"""
        mock_logger = Mock()
        mock_logging.getLogger.return_value = mock_logger

        config = WorkerConfig.from_env()

        # Should use new value, not legacy
        assert config.max_concurrent_activities == 200

        # Should not log warning when new variable is present
        mock_logger.warning.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "MAX_CONCURRENT_ACTIVITIES": "invalid",
        },
        clear=True,
    )
    def test_from_env_invalid_int_values(self):
        """Test from_env with invalid integer values"""
        with pytest.raises(ValueError):
            WorkerConfig.from_env()

    @patch.dict(os.environ, {"METRICS_PORT": "0", "HEALTH_PORT": "65536"}, clear=True)
    def test_from_env_edge_case_port_values(self):
        """Test from_env with edge case port values"""
        config = WorkerConfig.from_env()

        assert config.metrics_port == 0
        assert config.health_port == 65536

    def test_to_dict_complete(self):
        """Test to_dict method with all values"""
        config = WorkerConfig(
            temporal_address="test-host:7233",
            namespace="test-namespace",
            task_queue="test-queue",
            identity="test-worker",
            max_concurrent_activities=123,
            max_concurrent_workflow_tasks=45,
            max_concurrent_local_activities=67,
            max_concurrent_nexus_tasks=8,
            log_level="DEBUG",
            metrics_port=1234,
            health_port=5678,
            tls_mode="platform",
        )

        result = config.to_dict()

        expected = {
            "temporal_host": "test-host:7233",
            "temporal_namespace": "test-namespace",
            "task_queue": "test-queue",
            "worker_identity": "test-worker",
            "max_concurrent_activities": 123,
            "max_concurrent_workflow_tasks": 45,
            "max_concurrent_local_activities": 67,
            "max_concurrent_nexus_tasks": 8,
            "log_level": "DEBUG",
            "metrics_port": 1234,
            "health_port": 5678,
            "tls_mode": "platform",
            "tracing_enabled": False,
        }

        assert result == expected

    def test_to_dict_includes_tracing_enabled(self):
        """Test that to_dict surfaces tracing_enabled"""
        config = WorkerConfig(tracing_enabled=True)

        result = config.to_dict()

        assert result["tracing_enabled"] is True

    def test_to_dict_excludes_tls_config(self):
        """Test that to_dict excludes TLS configuration for security"""
        config = WorkerConfig(
            temporal_tls_cert="/path/to/cert.pem",
            temporal_tls_key="/path/to/key.pem",
            temporal_tls_ca="/path/to/ca.pem",
        )

        result = config.to_dict()

        # TLS configuration should not be in the dictionary
        assert "temporal_tls_cert" not in result
        assert "temporal_tls_key" not in result
        assert "temporal_tls_ca" not in result

    def test_to_dict_immutable(self):
        """Test that to_dict returns a copy that doesn't affect original config"""
        config = WorkerConfig(temporal_address="original-host")

        result = config.to_dict()
        result["temporal_host"] = "modified-host"

        # Original config should be unchanged
        assert config.temporal_host == "original-host"

    def test_config_attributes_types(self):
        """Test that config attributes have correct types"""
        config = WorkerConfig()

        assert isinstance(config.temporal_host, str)
        assert isinstance(config.temporal_namespace, str)
        assert isinstance(config.task_queue, str)
        assert isinstance(config.worker_identity, str)
        assert isinstance(config.max_concurrent_activities, int)
        assert isinstance(config.max_concurrent_workflow_tasks, int)
        assert isinstance(config.max_concurrent_local_activities, int)
        assert isinstance(config.max_concurrent_nexus_tasks, int)
        assert isinstance(config.log_level, str)
        assert isinstance(config.metrics_port, int)
        assert isinstance(config.health_port, int)

    def test_config_concurrency_limits_positive(self):
        """Test that concurrency limits are positive"""
        config = WorkerConfig()

        assert config.max_concurrent_activities > 0
        assert config.max_concurrent_workflow_tasks > 0
        assert config.max_concurrent_local_activities > 0
        assert config.max_concurrent_nexus_tasks > 0

    def test_config_ports_valid_range(self):
        """Test that default port values are in valid range"""
        config = WorkerConfig()

        assert 1 <= config.metrics_port <= 65535
        assert 1 <= config.health_port <= 65535


class TestCreateTemporalClient:
    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_default_config(self, mock_client_class):
        """Test creating client with default configuration"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        result = await create_temporal_client(WorkerConfig(tls_mode="platform"))

        assert result is mock_client
        mock_client_class.connect.assert_called_once_with(
            target_host="localhost:7233",
            namespace="default",
            plugins=[],
            interceptors=[],
        )

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_custom_config(self, mock_client_class):
        """Test creating client with custom configuration"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        config = WorkerConfig(temporal_address="custom-host:9999", namespace="custom-namespace", tls_mode="platform")

        result = await create_temporal_client(config)

        assert result is mock_client
        mock_client_class.connect.assert_called_once_with(
            target_host="custom-host:9999", namespace="custom-namespace", plugins=[], interceptors=[]
        )

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_with_mtls_cert_key_ca(self, mock_client_class, tmp_path):
        """Test that mTLS cert/key/CA paths are read and passed as a TLSConfig"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        cert = tmp_path / "client.pem"
        key = tmp_path / "client.key"
        ca = tmp_path / "ca.pem"
        cert.write_bytes(b"CLIENT-CERT")
        key.write_bytes(b"CLIENT-KEY")
        ca.write_bytes(b"CA-CERT")

        config = WorkerConfig(
            temporal_address="secure-host:7233",
            temporal_tls_cert=str(cert),
            temporal_tls_key=str(key),
            temporal_tls_ca=str(ca),
            tls_mode="mtls",
        )

        result = await create_temporal_client(config)

        assert result is mock_client
        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["target_host"] == "secure-host:7233"
        # Regression guard: previously only tls=True was passed - cert/key/CA silently dropped
        tls = call_kwargs["tls"]
        assert isinstance(tls, TLSConfig)
        assert tls.client_cert == b"CLIENT-CERT"
        assert tls.client_private_key == b"CLIENT-KEY"
        assert tls.server_root_ca_cert == b"CA-CERT"

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_with_tls_cert_only(self, mock_client_class, tmp_path):
        """Test creating client with cert only - key and CA stay None"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        cert = tmp_path / "client.pem"
        cert.write_bytes(b"CLIENT-CERT")

        config = WorkerConfig(
            temporal_address="secure-host:7233",
            temporal_tls_cert=str(cert),
            tls_mode="tls",
        )

        result = await create_temporal_client(config)

        assert result is mock_client
        tls = mock_client_class.connect.call_args[1]["tls"]
        assert isinstance(tls, TLSConfig)
        assert tls.client_cert == b"CLIENT-CERT"
        assert tls.client_private_key is None
        assert tls.server_root_ca_cert is None

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_with_ca_only(self, mock_client_class, tmp_path):
        """Test CA-only deployment (custom server CA, no client cert) activates TLS"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        ca = tmp_path / "ca.pem"
        ca.write_bytes(b"CA-CERT")

        config = WorkerConfig(
            temporal_address="secure-host:7233",
            temporal_tls_ca=str(ca),
            tls_mode="tls",
        )

        result = await create_temporal_client(config)

        assert result is mock_client
        tls = mock_client_class.connect.call_args[1]["tls"]
        assert isinstance(tls, TLSConfig)
        assert tls.server_root_ca_cert == b"CA-CERT"
        assert tls.client_cert is None
        assert tls.client_private_key is None

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_platform_mode_omits_tls(self, mock_client_class):
        """Test that platform posture connects without an application tls kwarg"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        config = WorkerConfig(tls_mode="platform")

        await create_temporal_client(config)

        # Verify TLS was not set (platform / mesh terminates TLS)
        call_kwargs = mock_client_class.connect.call_args[1]
        assert "tls" not in call_kwargs

    @pytest.mark.parametrize("tls_mode", ["off", "OFF", " off "])
    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_off_mode_is_platform_alias(self, mock_client_class, tls_mode, caplog):
        """'off' is an alias for 'platform': no application tls kwarg, and the given name is logged"""
        mock_client_class.connect = AsyncMock(return_value=Mock())

        with caplog.at_level(logging.INFO, logger="foundry_temporal.worker"):
            await create_temporal_client(WorkerConfig(tls_mode=tls_mode))

        call_kwargs = mock_client_class.connect.call_args[1]
        assert "tls" not in call_kwargs
        assert "Temporal client TLS posture: off" in caplog.text

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_invalid_tls_mode_fails_closed(self, mock_client_class):
        """An unrecognized TLS posture raises and does not connect (STIG V-222596)"""
        mock_client_class.connect = AsyncMock()

        config = WorkerConfig(tls_mode="bogus")

        with pytest.raises(ValueError, match="Invalid TEMPORAL_TLS_MODE"):
            await create_temporal_client(config)

        mock_client_class.connect.assert_not_called()

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_mtls_requires_cert_and_key(self, mock_client_class, tmp_path):
        """mtls posture without a client key fails closed (STIG V-222596)"""
        mock_client_class.connect = AsyncMock()

        cert = tmp_path / "client.pem"
        cert.write_bytes(b"CLIENT-CERT")

        config = WorkerConfig(tls_mode="mtls", temporal_tls_cert=str(cert))  # key missing

        with pytest.raises(ValueError, match="mtls requires TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY"):
            await create_temporal_client(config)

        mock_client_class.connect.assert_not_called()

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_tls_mode_no_certs_enables_default_tls(self, mock_client_class):
        """tls posture with no cert/CA enables transport TLS with system roots (STIG V-222596)"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        config = WorkerConfig(tls_mode="tls")

        await create_temporal_client(config)

        assert mock_client_class.connect.call_args[1]["tls"] is True

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_with_plugins(self, mock_client_class):
        """Test that plugins are passed to Client.connect()"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)
        mock_plugin = Mock()

        result = await create_temporal_client(WorkerConfig(tls_mode="platform"), plugins=[mock_plugin])

        assert result is mock_client
        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["plugins"] == [mock_plugin]

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_plugins_none_passes_empty_list(self, mock_client_class):
        """Test that plugins=None results in empty list passed to Client.connect()"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        await create_temporal_client(WorkerConfig(tls_mode="platform"), plugins=None)

        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["plugins"] == []

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_plugins_empty_list_passes_empty_list(self, mock_client_class):
        """Test that plugins=[] results in empty list passed to Client.connect()"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        await create_temporal_client(WorkerConfig(tls_mode="platform"), plugins=[])

        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["plugins"] == []

    @patch("foundry_temporal.tracing.get_tracing_interceptor")
    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_tracing_disabled_no_interceptor_added(self, mock_client_class, mock_get_interceptor):
        """Test that tracing_enabled=False leaves the interceptor list untouched"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        await create_temporal_client(WorkerConfig(tls_mode="platform", tracing_enabled=False))

        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["interceptors"] == []
        mock_get_interceptor.assert_not_called()

    @patch("foundry_temporal.tracing.get_tracing_interceptor")
    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_tracing_enabled_no_caller_interceptors(self, mock_client_class, mock_get_interceptor):
        """Test that tracing_enabled=True with no caller interceptors yields exactly the TracingInterceptor"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)
        mock_tracing_interceptor = Mock()
        mock_get_interceptor.return_value = mock_tracing_interceptor

        await create_temporal_client(WorkerConfig(tls_mode="platform", tracing_enabled=True))

        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["interceptors"] == [mock_tracing_interceptor]

    @patch("foundry_temporal.tracing.get_tracing_interceptor")
    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_tracing_enabled_appends_to_caller_interceptors(
        self, mock_client_class, mock_get_interceptor
    ):
        """Test that tracing_enabled=True appends to, never replaces, caller-supplied interceptors"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)
        mock_tracing_interceptor = Mock()
        mock_get_interceptor.return_value = mock_tracing_interceptor
        mock_caller_interceptor = Mock()

        await create_temporal_client(
            WorkerConfig(tls_mode="platform", tracing_enabled=True), interceptors=[mock_caller_interceptor]
        )

        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["interceptors"] == [mock_caller_interceptor, mock_tracing_interceptor]

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_connection_error(self, mock_client_class):
        """Test handling connection errors when creating client"""
        mock_client_class.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception) as exc_info:
            await create_temporal_client(WorkerConfig(tls_mode="platform"))

        assert "Connection failed" in str(exc_info.value)

    @patch("foundry_temporal.worker.Client")
    @pytest.mark.asyncio
    async def test_create_client_none_config_fails_closed(self, mock_client_class):
        """None config uses WorkerConfig() defaults, which has no TLS posture - fail closed (STIG V-222596)"""
        mock_client_class.connect = AsyncMock()

        with pytest.raises(ValueError, match="TEMPORAL_TLS_MODE is not set"):
            await create_temporal_client(None)

        mock_client_class.connect.assert_not_called()


class TestCreateTemporalClientAuth:
    """Tests for service account authentication in create_temporal_client"""

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
            "TEMPORAL_AUTH_CLIENT_ID": "my-client",
            "TEMPORAL_AUTH_CLIENT_SECRET": "my-secret",
            "TEMPORAL_AUTH_SCOPES": "openid profile",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_auth_fetches_token_and_sets_rpc_metadata(self, mock_client_class):
        """Test that auth env vars trigger token fetch and set rpc_metadata"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "test-jwt-token", "expires_in": 300}
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.create_task"):
                await create_temporal_client(WorkerConfig(tls_mode="platform"))

        # Verify rpc_metadata was set in client_kwargs
        call_kwargs = mock_client_class.connect.call_args[1]
        assert call_kwargs["rpc_metadata"] == {"authorization": "Bearer test-jwt-token"}

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
            "TEMPORAL_AUTH_CLIENT_ID": "my-client",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_auth_without_client_secret(self, mock_client_class):
        """Test that auth works without client_secret (public client)"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "public-token", "expires_in": 300}
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.create_task"):
                await create_temporal_client(WorkerConfig(tls_mode="platform"))

        # Verify token_data did not include client_secret
        post_call = mock_http_client.post.call_args
        assert "client_secret" not in post_call[1]["data"]

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_auth_missing_client_id_raises(self, mock_client_class):
        """Test that missing TEMPORAL_AUTH_CLIENT_ID raises ValueError"""
        with pytest.raises(ValueError, match="TEMPORAL_AUTH_CLIENT_ID is required"):
            await create_temporal_client(WorkerConfig(tls_mode="platform"))

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
            "TEMPORAL_AUTH_CLIENT_ID": "my-client",
            "TEMPORAL_AUTH_CLIENT_SECRET": "my-secret",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_auth_schedules_refresh_task(self, mock_client_class):
        """Test that a background refresh task is created"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "token", "expires_in": 300}
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.create_task") as mock_create_task:
                await create_temporal_client(WorkerConfig(tls_mode="platform"))

        mock_create_task.assert_called_once()

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
            "TEMPORAL_AUTH_CLIENT_ID": "my-client",
            "TEMPORAL_AUTH_CLIENT_SECRET": "my-secret",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_auth_stores_refresh_task_on_client(self, mock_client_class):
        """Test that the refresh task is stashed on the client for later cancellation"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "token", "expires_in": 300}
        mock_response.raise_for_status = Mock()

        mock_task = Mock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.create_task", return_value=mock_task):
                result = await create_temporal_client(WorkerConfig(tls_mode="platform"))

        assert result._foundry_refresh_task is mock_task

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
            "TEMPORAL_AUTH_CLIENT_ID": "my-client",
            "TEMPORAL_AUTH_CLIENT_SECRET": "my-secret",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_auth_default_scope(self, mock_client_class):
        """Test that default scope is 'openid' when not set"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "token", "expires_in": 300}
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.create_task"):
                await create_temporal_client(WorkerConfig(tls_mode="platform"))

        post_call = mock_http_client.post.call_args
        assert post_call[1]["data"]["scope"] == "openid"

    @patch("foundry_temporal.worker.Client")
    @patch.dict(os.environ, {}, clear=True)
    @pytest.mark.asyncio
    async def test_no_auth_when_env_vars_absent(self, mock_client_class):
        """Test that no auth is attempted when TEMPORAL_AUTH_TOKEN_URL is not set"""
        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        result = await create_temporal_client(WorkerConfig(tls_mode="platform"))

        assert result is mock_client
        call_kwargs = mock_client_class.connect.call_args[1]
        assert "rpc_metadata" not in call_kwargs

    @patch("foundry_temporal.worker.Client")
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_AUTH_TOKEN_URL": "https://keycloak.example.com/token",
            "TEMPORAL_AUTH_CLIENT_ID": "my-client",
            "TEMPORAL_AUTH_CLIENT_SECRET": "my-secret",
        },
        clear=True,
    )
    @pytest.mark.asyncio
    async def test_refresh_loop_updates_rpc_metadata(self, mock_client_class):
        """Test that the refresh loop updates client.rpc_metadata with a new token"""
        import asyncio

        mock_client = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        initial_response = Mock()
        initial_response.json.return_value = {"access_token": "initial-token", "expires_in": 90}
        initial_response.raise_for_status = Mock()

        refreshed_response = Mock()
        refreshed_response.json.return_value = {"access_token": "refreshed-token", "expires_in": 90}
        refreshed_response.raise_for_status = Mock()

        captured_coro = None

        def capture_task(coro):
            nonlocal captured_coro
            captured_coro = coro
            return Mock()

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(side_effect=[initial_response, refreshed_response])
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("asyncio.create_task", side_effect=capture_task):
                await create_temporal_client(WorkerConfig(tls_mode="platform"))

            # Run the captured refresh loop - let first sleep pass (so refresh fires),
            # then cancel on second sleep to exit the while True loop
            assert captured_coro is not None
            sleep_calls = 0

            async def controlled_sleep(seconds):
                nonlocal sleep_calls
                sleep_calls += 1
                if sleep_calls > 1:
                    raise asyncio.CancelledError()

            with patch("asyncio.sleep", new=controlled_sleep):
                try:
                    await captured_coro
                except asyncio.CancelledError:
                    pass

        assert mock_client.rpc_metadata == {"authorization": "Bearer refreshed-token"}


class TestCloseTemporalClient:
    def test_cancels_stored_refresh_task(self):
        """Test that close_temporal_client cancels the task stashed by create_temporal_client"""
        mock_client = Mock()
        mock_task = Mock()
        mock_client._foundry_refresh_task = mock_task

        close_temporal_client(mock_client)

        mock_task.cancel.assert_called_once()

    def test_noop_when_no_refresh_task(self):
        """Test that close_temporal_client is a no-op for a client without service account auth"""
        mock_client = Mock(spec=[])

        close_temporal_client(mock_client)  # Should not raise

    @pytest.mark.asyncio
    async def test_cancels_real_asyncio_task(self):
        """Integration check: a real asyncio task is actually cancelled, not just mocked"""
        import asyncio

        async def _loop_forever():
            while True:
                await asyncio.sleep(3600)

        mock_client = Mock()
        mock_client._foundry_refresh_task = asyncio.create_task(_loop_forever())
        # Let the task actually start running before cancelling it.
        await asyncio.sleep(0)

        close_temporal_client(mock_client)

        with pytest.raises(asyncio.CancelledError):
            await mock_client._foundry_refresh_task


class TestCreateWorkerWithDefaults:
    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_default_config(self, mock_worker_class):
        """Test creating worker with default configuration"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        workflows = [Mock()]
        activities = [Mock()]

        result = create_worker_with_defaults(client=mock_client, workflows=workflows, activities=activities)

        assert result is mock_worker

        mock_worker_class.assert_called_once_with(
            mock_client,
            task_queue="foundry-workflows",
            workflows=workflows,
            activities=activities,
            max_concurrent_activities=100,
            max_concurrent_workflow_tasks=50,
            max_concurrent_local_activities=200,
            max_concurrent_nexus_tasks=10,
            interceptors=[],
        )

    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_custom_config(self, mock_worker_class):
        """Test creating worker with custom configuration"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        config = WorkerConfig(
            task_queue="custom-queue",
            max_concurrent_activities=150,
            max_concurrent_workflow_tasks=75,
            max_concurrent_local_activities=300,
            max_concurrent_nexus_tasks=25,
        )

        workflows = [Mock()]
        activities = [Mock()]

        result = create_worker_with_defaults(
            client=mock_client, workflows=workflows, activities=activities, config=config
        )

        assert result is mock_worker

        mock_worker_class.assert_called_once_with(
            mock_client,
            task_queue="custom-queue",
            workflows=workflows,
            activities=activities,
            max_concurrent_activities=150,
            max_concurrent_workflow_tasks=75,
            max_concurrent_local_activities=300,
            max_concurrent_nexus_tasks=25,
            interceptors=[],
        )

    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_empty_workflows_and_activities(self, mock_worker_class):
        """Test creating worker with empty workflows and activities lists"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        result = create_worker_with_defaults(client=mock_client, workflows=[], activities=[])

        assert result is mock_worker

        mock_worker_class.assert_called_once_with(
            mock_client,
            task_queue="foundry-workflows",
            workflows=[],
            activities=[],
            max_concurrent_activities=100,
            max_concurrent_workflow_tasks=50,
            max_concurrent_local_activities=200,
            max_concurrent_nexus_tasks=10,
            interceptors=[],
        )

    @patch("foundry_temporal.tracing.get_tracing_interceptor")
    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_tracing_disabled_no_interceptor_added(self, mock_worker_class, mock_get_interceptor):
        """Test that tracing_enabled=False leaves the interceptor list untouched"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        create_worker_with_defaults(
            client=mock_client,
            workflows=[Mock()],
            activities=[Mock()],
            config=WorkerConfig(tracing_enabled=False),
        )

        call_kwargs = mock_worker_class.call_args[1]
        assert call_kwargs["interceptors"] == []
        mock_get_interceptor.assert_not_called()

    @patch("foundry_temporal.tracing.get_tracing_interceptor")
    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_tracing_enabled_no_caller_interceptors(self, mock_worker_class, mock_get_interceptor):
        """Test that tracing_enabled=True with no caller interceptors yields exactly the TracingInterceptor"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        mock_tracing_interceptor = Mock()
        mock_get_interceptor.return_value = mock_tracing_interceptor

        create_worker_with_defaults(
            client=mock_client,
            workflows=[Mock()],
            activities=[Mock()],
            config=WorkerConfig(tracing_enabled=True),
        )

        call_kwargs = mock_worker_class.call_args[1]
        assert call_kwargs["interceptors"] == [mock_tracing_interceptor]

    @patch("foundry_temporal.tracing.get_tracing_interceptor")
    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_tracing_enabled_appends_to_caller_interceptors(
        self, mock_worker_class, mock_get_interceptor
    ):
        """Test that tracing_enabled=True appends to, never replaces, caller-supplied interceptors"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker
        mock_tracing_interceptor = Mock()
        mock_get_interceptor.return_value = mock_tracing_interceptor
        mock_caller_interceptor = Mock()

        create_worker_with_defaults(
            client=mock_client,
            workflows=[Mock()],
            activities=[Mock()],
            config=WorkerConfig(tracing_enabled=True),
            interceptors=[mock_caller_interceptor],
        )

        call_kwargs = mock_worker_class.call_args[1]
        assert call_kwargs["interceptors"] == [mock_caller_interceptor, mock_tracing_interceptor]

    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_none_config(self, mock_worker_class):
        """Test creating worker with None config (should use defaults)"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        workflows = [Mock()]
        activities = [Mock()]

        result = create_worker_with_defaults(
            client=mock_client, workflows=workflows, activities=activities, config=None
        )

        assert result is mock_worker

        # Verify defaults were used
        call_kwargs = mock_worker_class.call_args[1]
        assert call_kwargs["task_queue"] == "foundry-workflows"
        assert call_kwargs["max_concurrent_activities"] == 100

    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_client_parameter_position(self, mock_worker_class):
        """Test that client is passed as first positional argument"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        create_worker_with_defaults(client=mock_client, workflows=[], activities=[])

        # Verify client was passed as first positional argument
        call_args = mock_worker_class.call_args[0]
        assert len(call_args) == 1
        assert call_args[0] is mock_client

    @patch("foundry_temporal.worker.Worker")
    def test_create_worker_parameter_types(self, mock_worker_class):
        """Test that worker parameters have correct types"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_worker_class.return_value = mock_worker

        create_worker_with_defaults(client=mock_client, workflows=[Mock()], activities=[Mock()])

        call_kwargs = mock_worker_class.call_args[1]

        assert isinstance(call_kwargs["task_queue"], str)
        assert isinstance(call_kwargs["workflows"], list)
        assert isinstance(call_kwargs["activities"], list)
        assert isinstance(call_kwargs["max_concurrent_activities"], int)
        assert isinstance(call_kwargs["max_concurrent_workflow_tasks"], int)
        assert isinstance(call_kwargs["max_concurrent_local_activities"], int)
        assert isinstance(call_kwargs["max_concurrent_nexus_tasks"], int)


class TestIntegration:
    """Integration tests for worker utilities"""

    @patch("foundry_temporal.worker.Client")
    @patch("foundry_temporal.worker.Worker")
    @pytest.mark.asyncio
    async def test_full_worker_setup_flow(self, mock_worker_class, mock_client_class):
        """Test complete worker setup flow"""
        mock_client = Mock()
        mock_worker = Mock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)
        mock_worker_class.return_value = mock_worker

        # Create config from environment
        with patch.dict(
            os.environ,
            {
                "TASK_QUEUE": "integration-test-queue",
                "MAX_CONCURRENT_ACTIVITIES": "50",
                "TEMPORAL_TLS_MODE": "platform",
            },
            clear=True,
        ):
            config = WorkerConfig.from_env()

        # Create client
        client = await create_temporal_client(config)

        # Create worker
        workflows = [Mock()]
        activities = [Mock()]
        worker = create_worker_with_defaults(client=client, workflows=workflows, activities=activities, config=config)

        # Verify complete flow
        assert client is mock_client
        assert worker is mock_worker

        # Verify client creation
        mock_client_class.connect.assert_called_once_with(
            target_host="localhost:7233",
            namespace="default",
            plugins=[],
            interceptors=[],
        )

        # Verify worker creation
        worker_call_kwargs = mock_worker_class.call_args[1]
        assert worker_call_kwargs["task_queue"] == "integration-test-queue"
        assert worker_call_kwargs["max_concurrent_activities"] == 50

    def test_config_serialization_for_logging(self):
        """Test that config can be safely serialized for logging"""
        import json

        config = WorkerConfig(
            temporal_address="test-host:7233",
            namespace="test-namespace",
            temporal_tls_cert="/secret/path",  # Should not appear in serialization
        )

        config_dict = config.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(config_dict)
        assert isinstance(json_str, str)

        # Should not contain sensitive information
        assert "temporal_tls_cert" not in json_str
        assert "/secret/path" not in json_str

        # Should contain expected configuration
        assert "test-host:7233" in json_str
        assert "test-namespace" in json_str

    def test_environment_variable_precedence(self):
        """Test environment variable precedence and fallbacks"""
        test_cases = [
            # (env_vars, expected_activities, should_warn)
            ({}, 100, False),  # Default
            ({"MAX_CONCURRENT_ACTIVITIES": "150"}, 150, False),  # New variable
            ({"WORKER_CONCURRENCY": "200"}, 200, True),  # Legacy only
            ({"MAX_CONCURRENT_ACTIVITIES": "150", "WORKER_CONCURRENCY": "200"}, 150, False),  # New overrides legacy
        ]

        for env_vars, expected_activities, should_warn in test_cases:
            with patch.dict(os.environ, env_vars, clear=True):
                with patch("foundry_temporal.worker.logging") as mock_logging:
                    mock_logger = Mock()
                    mock_logging.getLogger.return_value = mock_logger

                    config = WorkerConfig.from_env()

                    assert config.max_concurrent_activities == expected_activities

                    if should_warn:
                        mock_logger.warning.assert_called_once()
                    else:
                        mock_logger.warning.assert_not_called()

    def test_config_validation_edge_cases(self):
        """Test configuration validation with edge cases"""
        # Test zero concurrency (should be allowed)
        config = WorkerConfig(
            max_concurrent_activities=0,
            max_concurrent_workflow_tasks=0,
            max_concurrent_local_activities=0,
            max_concurrent_nexus_tasks=0,
        )

        assert config.max_concurrent_activities == 0
        assert config.max_concurrent_workflow_tasks == 0
        assert config.max_concurrent_local_activities == 0
        assert config.max_concurrent_nexus_tasks == 0

        # Should be serializable
        config_dict = config.to_dict()
        assert config_dict["max_concurrent_activities"] == 0

    @patch("foundry_temporal.worker.os.getpid")
    def test_identity_generation_consistency(self, mock_getpid):
        """Test that worker identity generation is consistent"""
        mock_getpid.return_value = 42

        config1 = WorkerConfig()
        config2 = WorkerConfig()

        # Should generate same identity for same PID
        assert config1.worker_identity == config2.worker_identity
        assert config1.worker_identity == "foundry-worker-42"

        # Explicit identity should override
        config3 = WorkerConfig(identity="custom-worker")
        assert config3.worker_identity == "custom-worker"
