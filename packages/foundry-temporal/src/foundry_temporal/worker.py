# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Worker Bootstrap and Configuration Utilities

Standard worker setup based on foundry-temporal architecture specifications.
"""

import asyncio
import logging
import os
from collections.abc import Callable, Sequence
from typing import Any

from temporalio.client import Client, Plugin
from temporalio.converter import DataConverter
from temporalio.service import TLSConfig
from temporalio.worker import Interceptor, Worker


class WorkerConfig:
    """
    Worker configuration management

    Environment variables:
    - TEMPORAL_HOST: Temporal frontend address
    - TEMPORAL_NAMESPACE: Temporal namespace
    - TASK_QUEUE: Worker task queue name
    - MAX_CONCURRENT_ACTIVITIES: Max concurrent activities (replaces WORKER_CONCURRENCY)
    - MAX_CONCURRENT_WORKFLOW_TASKS: Max concurrent workflow tasks
    - MAX_CONCURRENT_LOCAL_ACTIVITIES: Max concurrent local activities
    - MAX_CONCURRENT_NEXUS_TASKS: Max concurrent nexus tasks
    - LOG_LEVEL: Logging level

    Legacy support:
    - WORKER_CONCURRENCY: Legacy alias for MAX_CONCURRENT_ACTIVITIES
    """

    def __init__(
        self,
        temporal_address: str = "localhost:7233",
        namespace: str = "default",
        task_queue: str = "foundry-workflows",
        identity: str | None = None,
        max_concurrent_activities: int = 100,
        max_concurrent_workflow_tasks: int = 50,
        max_concurrent_local_activities: int = 200,
        max_concurrent_nexus_tasks: int = 10,
        log_level: str = "INFO",
        metrics_port: int = 9090,
        health_port: int = 9091,
        temporal_tls_cert: str | None = None,
        temporal_tls_key: str | None = None,
        temporal_tls_ca: str | None = None,
        tls_mode: str | None = None,
        tracing_enabled: bool = False,
    ):
        self.temporal_host = temporal_address
        self.temporal_namespace = namespace
        self.task_queue = task_queue
        self.worker_identity = identity or f"foundry-worker-{os.getpid()}"
        self.max_concurrent_activities = max_concurrent_activities
        self.max_concurrent_workflow_tasks = max_concurrent_workflow_tasks
        self.max_concurrent_local_activities = max_concurrent_local_activities
        self.max_concurrent_nexus_tasks = max_concurrent_nexus_tasks
        self.log_level = log_level
        self.metrics_port = metrics_port
        self.health_port = health_port
        self.temporal_tls_cert = temporal_tls_cert
        self.temporal_tls_key = temporal_tls_key
        self.temporal_tls_ca = temporal_tls_ca
        # STIG V-222596: explicit TLS posture (platform | off | tls | mtls), where
        # off is an alias for platform. No default —
        # create_temporal_client() fails closed when unset.
        self.tls_mode = tls_mode
        # OpenTelemetry tracing toggle. OTLP endpoint/headers/service name are left
        # to OTel's own standard env vars, not surfaced here — see foundry_temporal.tracing.
        self.tracing_enabled = tracing_enabled

    @classmethod
    def from_env(cls) -> WorkerConfig:
        """Create WorkerConfig from environment variables"""
        # Legacy support - warn if WORKER_CONCURRENCY is used
        if os.getenv("WORKER_CONCURRENCY") and not os.getenv("MAX_CONCURRENT_ACTIVITIES"):
            logging.getLogger(__name__).warning(
                "WORKER_CONCURRENCY is deprecated, use MAX_CONCURRENT_ACTIVITIES instead"
            )

        return cls(
            temporal_address=os.getenv("TEMPORAL_HOST", "localhost:7233"),
            namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            task_queue=os.getenv("TASK_QUEUE", "foundry-workflows"),
            identity=os.getenv("WORKER_IDENTITY", f"foundry-worker-{os.getpid()}"),
            max_concurrent_activities=int(
                os.getenv(
                    "MAX_CONCURRENT_ACTIVITIES",
                    os.getenv("WORKER_CONCURRENCY", "100"),  # Legacy fallback
                )
            ),
            max_concurrent_workflow_tasks=int(os.getenv("MAX_CONCURRENT_WORKFLOW_TASKS", "50")),
            max_concurrent_local_activities=int(os.getenv("MAX_CONCURRENT_LOCAL_ACTIVITIES", "200")),
            max_concurrent_nexus_tasks=int(os.getenv("MAX_CONCURRENT_NEXUS_TASKS", "10")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            metrics_port=int(os.getenv("METRICS_PORT", "9090")),
            health_port=int(os.getenv("HEALTH_PORT", "9091")),
            temporal_tls_cert=os.getenv("TEMPORAL_TLS_CERT"),
            temporal_tls_key=os.getenv("TEMPORAL_TLS_KEY"),
            temporal_tls_ca=os.getenv("TEMPORAL_TLS_CA"),
            tls_mode=os.getenv("TEMPORAL_TLS_MODE"),
            tracing_enabled=os.getenv("TRACING_ENABLED", "false").lower() == "true",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for logging"""
        return {
            "temporal_host": self.temporal_host,
            "temporal_namespace": self.temporal_namespace,
            "task_queue": self.task_queue,
            "worker_identity": self.worker_identity,
            "max_concurrent_activities": self.max_concurrent_activities,
            "max_concurrent_workflow_tasks": self.max_concurrent_workflow_tasks,
            "max_concurrent_local_activities": self.max_concurrent_local_activities,
            "max_concurrent_nexus_tasks": self.max_concurrent_nexus_tasks,
            "log_level": self.log_level,
            "metrics_port": self.metrics_port,
            "health_port": self.health_port,
            "tls_mode": self.tls_mode,
            "tracing_enabled": self.tracing_enabled,
        }


# Utility functions for common worker patterns
def _read_pem(path: str | None) -> bytes | None:
    """Read a PEM file path to bytes, or return None if path is None."""
    if path is None:
        return None
    with open(path, "rb") as f:
        return f.read()


async def create_temporal_client(
    config: WorkerConfig | None = None,
    data_converter: DataConverter | None = None,
    plugins: Sequence[Plugin] | None = None,
    interceptors: Sequence[Any] | None = None,
) -> Client:
    """Create a Temporal client with standard configuration.

    Plugins passed here are automatically inherited by any Worker created from the
    returned client — do not re-pass them to create_worker_with_defaults().
    """
    config = config or WorkerConfig()

    client_interceptors = list(interceptors or [])
    if config.tracing_enabled:
        from .tracing import get_tracing_interceptor

        tracing_interceptor = get_tracing_interceptor()
        if tracing_interceptor is not None:
            client_interceptors.append(tracing_interceptor)

    client_kwargs: dict[str, Any] = {
        "target_host": config.temporal_host,
        "namespace": config.temporal_namespace,
        "plugins": plugins or [],
        "interceptors": client_interceptors,
    }

    # Add data converter if provided
    if data_converter:
        client_kwargs["data_converter"] = data_converter

    # STIG V-222596: require an explicit TLS posture; fail closed when unset/invalid
    # so the transport is never silently plaintext. See docs/tls-posture.md.
    mode = (config.tls_mode or "").strip().lower()
    if not mode:
        raise ValueError(
            "TEMPORAL_TLS_MODE is not set. Set an explicit TLS posture: 'platform' "
            "(TLS terminated by the platform/service mesh), 'off' (alias for "
            "'platform'), 'tls' (application one-way TLS), or 'mtls' (application "
            "mutual TLS). See docs/tls-posture.md."
        )
    if mode in ("platform", "off"):
        # TLS is terminated by the deployment platform / service mesh; the client
        # connects without application-managed TLS. Conscious, documented decision.
        # "off" is an alias for "platform"; the logged posture keeps the name given.
        pass
    elif mode == "tls":
        if config.temporal_tls_cert or config.temporal_tls_ca:
            client_kwargs["tls"] = TLSConfig(
                client_cert=_read_pem(config.temporal_tls_cert),
                client_private_key=_read_pem(config.temporal_tls_key),
                server_root_ca_cert=_read_pem(config.temporal_tls_ca),
            )
        else:
            # Enable transport TLS using system root CAs.
            client_kwargs["tls"] = True
    elif mode == "mtls":
        if not (config.temporal_tls_cert and config.temporal_tls_key):
            raise ValueError("TEMPORAL_TLS_MODE=mtls requires TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY.")
        client_kwargs["tls"] = TLSConfig(
            client_cert=_read_pem(config.temporal_tls_cert),
            client_private_key=_read_pem(config.temporal_tls_key),
            server_root_ca_cert=_read_pem(config.temporal_tls_ca),
        )
    else:
        raise ValueError(
            f"Invalid TEMPORAL_TLS_MODE '{config.tls_mode}'. Expected 'platform', 'off', 'tls', or 'mtls'."
        )

    logging.getLogger(__name__).info("Temporal client TLS posture: %s", mode)

    # If service account auth is configured, fetch token and schedule refresh
    token_url = os.getenv("TEMPORAL_AUTH_TOKEN_URL")
    expires_in = 300
    if token_url:
        import httpx

        client_id = os.getenv("TEMPORAL_AUTH_CLIENT_ID")
        if not client_id:
            raise ValueError("TEMPORAL_AUTH_TOKEN_URL is set but TEMPORAL_AUTH_CLIENT_ID is required")
        token_data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "scope": os.getenv("TEMPORAL_AUTH_SCOPES", "openid"),
        }
        client_secret = os.getenv("TEMPORAL_AUTH_CLIENT_SECRET")
        if client_secret:
            token_data["client_secret"] = client_secret

        async def _fetch_token() -> tuple[str, int]:
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.post(token_url, data=token_data)
                resp.raise_for_status()
            data = resp.json()
            return data["access_token"], data.get("expires_in", 300)

        token, expires_in = await _fetch_token()
        client_kwargs["rpc_metadata"] = {"authorization": f"Bearer {token}"}

    client = await Client.connect(**client_kwargs)

    if token_url:

        async def _refresh_loop() -> None:
            sleep_duration = max(expires_in - 60, 30)
            while True:
                await asyncio.sleep(sleep_duration)
                try:
                    new_token, new_expires_in = await _fetch_token()
                    sleep_duration = max(new_expires_in - 60, 30)
                    client.rpc_metadata = {"authorization": f"Bearer {new_token}"}
                    logging.getLogger(__name__).info("Refreshed Temporal service account token")
                except Exception as e:
                    logging.getLogger(__name__).error(f"Failed to refresh Temporal token: {e}")

        # Stashed on the client so close_temporal_client() can cancel it when a
        # caller is done with this client (e.g. evicting it from a cache after
        # a connection failure) - otherwise the loop runs forever.
        client._foundry_refresh_task = asyncio.create_task(_refresh_loop())  # type: ignore[attr-defined]

    return client


def close_temporal_client(client: Client) -> None:
    """Cancel the background token-refresh task started by create_temporal_client.

    No-op if the client was created without service account auth (no task was
    scheduled) or has already been closed. Safe to call from sync code - it
    only requests cancellation, it does not await the task's shutdown.
    """
    task = getattr(client, "_foundry_refresh_task", None)
    if task is not None:
        task.cancel()


def create_worker_with_defaults(
    client: Client,
    workflows: list[type],
    activities: list[Callable],
    config: WorkerConfig | None = None,
    interceptors: Sequence[Interceptor] | None = None,
) -> Worker:
    """Create a worker with foundry defaults"""
    config = config or WorkerConfig()

    worker_interceptors = list(interceptors or [])
    if config.tracing_enabled:
        from .tracing import get_tracing_interceptor

        tracing_interceptor = get_tracing_interceptor()
        if tracing_interceptor is not None:
            worker_interceptors.append(tracing_interceptor)

    return Worker(
        client,
        task_queue=config.task_queue,
        workflows=workflows,
        activities=activities,
        max_concurrent_activities=config.max_concurrent_activities,
        max_concurrent_workflow_tasks=config.max_concurrent_workflow_tasks,
        max_concurrent_local_activities=config.max_concurrent_local_activities,
        max_concurrent_nexus_tasks=config.max_concurrent_nexus_tasks,
        interceptors=worker_interceptors,
    )
