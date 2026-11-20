# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Activity Decorators and Base Classes for Temporal Workflows

Generic activity infrastructure that provides common patterns for workflow activities
based on foundry-temporal architecture specifications.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
from typing import Any

from temporalio import activity
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from .errors import NonRetryableError, RetryableError, WorkflowError
from .logging import get_logger

logger = logging.getLogger(__name__)

# Heartbeat twice as often as the timeout.
_AUTO_HEARTBEAT_TICKS_PER_TIMEOUT = 2


@dataclass
class ActivityConfig:
    """Configuration for foundry activities"""

    retry_policy: RetryPolicy | None = None
    start_to_close_timeout: timedelta | None = None
    schedule_to_close_timeout: timedelta | None = None
    schedule_to_start_timeout: timedelta | None = None
    heartbeat_timeout: timedelta | None = None
    enable_observability: bool = True
    enable_error_wrapping: bool = True
    log_inputs: bool = False
    log_outputs: bool = False


class BaseActivity(ABC):
    """
    Base class for foundry activities providing common functionality

    Provides:
    - Standardized logging
    - Error handling patterns
    - Observability integration
    - Configuration management
    """

    def __init__(self, config: ActivityConfig | None = None):
        self.config = config or ActivityConfig()
        self.logger = get_logger()

    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        """Execute the activity logic - must be implemented by subclasses"""
        pass

    async def __call__(self, *args, **kwargs) -> Any:
        """Wrapper that provides observability and error handling"""
        activity_name = self.__class__.__name__

        if self.config.enable_observability:
            self.logger.info(
                f"Activity {activity_name} starting", extra={"inputs": args if self.config.log_inputs else None}
            )

        try:
            result = await self.execute(*args, **kwargs)

            if self.config.enable_observability:
                self.logger.info(
                    f"Activity {activity_name} completed",
                    extra={"outputs": result if self.config.log_outputs else None},
                )

            return result

        except Exception as error:
            if self.config.enable_observability:
                self.logger.error(f"Activity {activity_name} failed: {error}", extra={"error": str(error)})

            if self.config.enable_error_wrapping:
                raise self._wrap_error(error) from error
            else:
                raise

    def _wrap_error(self, error: Exception) -> Exception:
        """Wrap errors in foundry-specific error types for better handling"""
        if isinstance(error, (WorkflowError, ApplicationError)):
            return error

        # Determine if error should be retryable
        if self._is_retryable_error(error):
            return RetryableError(f"Retryable error in {self.__class__.__name__}: {error}")
        else:
            return NonRetryableError(f"Non-retryable error in {self.__class__.__name__}: {error}")

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error should be retried - override in subclasses"""
        return _is_retryable_error(error)


def foundry_activity(config: ActivityConfig | None = None, name: str | None = None, **activity_kwargs):
    """
    Decorator for creating foundry activities with standard patterns

    Args:
        config: Activity configuration
        name: Activity name (defaults to function name)
        **activity_kwargs: Additional arguments for @activity decorator

    Usage:
        @foundry_activity(config=ActivityConfig(enable_observability=True))
        async def my_activity(param: str) -> str:
            return f"processed: {param}"
    """

    def decorator(func: Callable) -> Callable:
        activity_config = config or ActivityConfig()

        @activity.defn(name=name, **activity_kwargs)
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            activity_name = name or func.__name__

            activity_logger = get_logger()

            if activity_config.enable_observability:
                activity_logger.info(
                    f"Activity {activity_name} starting", extra={"inputs": args if activity_config.log_inputs else None}
                )

            try:
                result = await func(*args, **kwargs)

                if activity_config.enable_observability:
                    activity_logger.info(
                        f"Activity {activity_name} completed",
                        extra={"outputs": result if activity_config.log_outputs else None},
                    )

                return result

            except Exception as error:
                if activity_config.enable_observability:
                    activity_logger.error(f"Activity {activity_name} failed: {error}", extra={"error": str(error)})

                if activity_config.enable_error_wrapping:
                    # Wrap error for better handling
                    if isinstance(error, (WorkflowError, ApplicationError)):
                        raise
                    elif _is_retryable_error(error):
                        raise RetryableError(f"Retryable error in {activity_name}: {error}") from error
                    else:
                        raise NonRetryableError(f"Non-retryable error in {activity_name}: {error}") from error
                else:
                    raise

        return wrapper

    return decorator


def _is_retryable_error(error: Exception) -> bool:
    """Helper to determine if error should be retried"""
    error_str = str(type(error)).lower()
    retryable_patterns = [
        "timeout",
        "connection",
        "network",
        "temporary",
        "unavailable",
        "overload",
        "busy",
        "throttle",
        "rate_limit",
    ]

    return any(pattern in error_str for pattern in retryable_patterns)


class HeartbeatActivity(BaseActivity):
    """
    Base class for long-running activities that need heartbeating

    Provides automatic heartbeat functionality for activities that run longer
    than the heartbeat timeout.
    """

    def __init__(self, config: ActivityConfig | None = None, heartbeat_interval: timedelta = timedelta(seconds=30)):
        super().__init__(config)
        self.heartbeat_interval = heartbeat_interval
        self._heartbeat_task: asyncio.Task | None = None

    async def execute_with_heartbeat(self, *args, **kwargs) -> Any:
        """Execute activity logic with automatic heartbeating"""
        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            result = await self.execute(*args, **kwargs)
            return result
        finally:
            # Stop heartbeat
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval.total_seconds())
                activity.heartbeat()
        except asyncio.CancelledError:
            pass

    async def __call__(self, *args, **kwargs) -> Any:
        """Override to use heartbeat execution"""
        activity_name = self.__class__.__name__

        if self.config.enable_observability:
            self.logger.info(
                f"Activity {activity_name} starting", extra={"inputs": args if self.config.log_inputs else None}
            )

        try:
            result = await self.execute_with_heartbeat(*args, **kwargs)

            if self.config.enable_observability:
                self.logger.info(
                    f"Activity {activity_name} completed",
                    extra={"outputs": result if self.config.log_outputs else None},
                )

            return result

        except Exception as error:
            if self.config.enable_observability:
                self.logger.error(f"Activity {activity_name} failed: {error}", extra={"error": str(error)})

            if self.config.enable_error_wrapping:
                raise self._wrap_error(error) from error
            else:
                raise


def long_running_activity(
    heartbeat_interval: timedelta = timedelta(seconds=30),
    config: ActivityConfig | None = None,
    name: str | None = None,
    **activity_kwargs,
):
    """
    Decorator for long-running activities with automatic heartbeating

    Args:
        heartbeat_interval: How often to send heartbeats
        config: Activity configuration
        name: Activity name
        **activity_kwargs: Additional arguments for @activity decorator

    Usage:
        @long_running_activity(heartbeat_interval=timedelta(seconds=10))
        async def process_large_dataset(data: List[str]) -> Dict[str, int]:
            # Long processing logic here
            return results
    """

    def decorator(func: Callable) -> Callable:
        activity_config = config or ActivityConfig()

        @activity.defn(name=name, **activity_kwargs)
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            activity_name = name or func.__name__
            heartbeat_task: asyncio.Task | None = None

            activity_logger = get_logger()

            if activity_config.enable_observability:
                activity_logger.info(
                    f"Long-running activity {activity_name} starting",
                    extra={"inputs": args if activity_config.log_inputs else None},
                )

            # Start heartbeat loop
            async def heartbeat_loop():
                try:
                    while True:
                        await asyncio.sleep(heartbeat_interval.total_seconds())
                        activity.heartbeat()
                except asyncio.CancelledError:
                    pass

            heartbeat_task = asyncio.create_task(heartbeat_loop())

            try:
                result = await func(*args, **kwargs)

                if activity_config.enable_observability:
                    activity_logger.info(
                        f"Long-running activity {activity_name} completed",
                        extra={"outputs": result if activity_config.log_outputs else None},
                    )

                return result

            except Exception as error:
                if activity_config.enable_observability:
                    activity_logger.error(
                        f"Long-running activity {activity_name} failed: {error}", extra={"error": str(error)}
                    )

                if activity_config.enable_error_wrapping:
                    if isinstance(error, (WorkflowError, ApplicationError)):
                        raise
                    elif _is_retryable_error(error):
                        raise RetryableError(f"Retryable error in {activity_name}: {error}") from error
                    else:
                        raise NonRetryableError(f"Non-retryable error in {activity_name}: {error}") from error
                else:
                    raise

            finally:
                # Stop heartbeat
                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

        return wrapper

    return decorator


def auto_heartbeat[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Heartbeat while `fn` runs; no-op if the activity sets no `heartbeat_timeout`.

    Unlike `HeartbeatActivity`/`long_running_activity` above, which heartbeat at a
    caller-supplied fixed interval, this derives the interval from the activity's own
    `heartbeat_timeout` — so a wrapped activity's timeout is chosen for how fast a dead
    worker should be noticed, not for liveness.
    """

    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        heartbeat_timeout = activity.info().heartbeat_timeout
        heartbeat_task = None
        if heartbeat_timeout:
            interval = heartbeat_timeout.total_seconds() / _AUTO_HEARTBEAT_TICKS_PER_TIMEOUT
            heartbeat_task = asyncio.create_task(_auto_heartbeat_every(interval))
        try:
            return await fn(*args, **kwargs)
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                await asyncio.wait([heartbeat_task])

    return wrapper


async def _auto_heartbeat_every(interval_sec: float) -> None:
    """Call `activity.heartbeat()` every `interval_sec` seconds until cancelled."""
    while True:
        await asyncio.sleep(interval_sec)
        activity.heartbeat()


class BatchActivity(BaseActivity):
    """
    Base class for activities that process items in batches

    Provides patterns for:
    - Processing large datasets in chunks
    - Progress reporting
    - Partial failure handling
    """

    def __init__(self, config: ActivityConfig | None = None, batch_size: int = 100):
        super().__init__(config)
        self.batch_size = batch_size

    @abstractmethod
    async def process_batch(self, batch: list) -> Any:
        """Process a single batch - must be implemented by subclasses"""
        pass

    async def execute(self, items: list) -> list:
        """Execute batch processing"""
        results = []
        total_items = len(items)
        processed_count = 0

        for i in range(0, total_items, self.batch_size):
            batch = items[i : i + self.batch_size]

            try:
                batch_result = await self.process_batch(batch)
                results.extend(batch_result if isinstance(batch_result, list) else [batch_result])

                processed_count += len(batch)

                # Report progress via heartbeat
                activity.heartbeat(f"Processed {processed_count}/{total_items} items")

            except Exception as error:
                self.logger.error(f"Batch processing failed for items {i}-{i + len(batch)}: {error}")
                # Could implement partial failure handling here
                raise

        return results


# Convenience functions for common activity patterns


def create_simple_activity(func: Callable, config: ActivityConfig | None = None) -> Callable:
    """Create a simple activity from a function with foundry patterns"""
    return foundry_activity(config=config)(func)


def create_heartbeat_activity(func: Callable, heartbeat_interval: timedelta = timedelta(seconds=30)) -> Callable:
    """Create a long-running activity with heartbeating"""
    return long_running_activity(heartbeat_interval=heartbeat_interval)(func)
