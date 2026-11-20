# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.activities module"""

import asyncio
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from foundry_temporal.activities import (
    ActivityConfig,
    BaseActivity,
    BatchActivity,
    HeartbeatActivity,
    _is_retryable_error,
    create_heartbeat_activity,
    create_simple_activity,
    foundry_activity,
    long_running_activity,
)
from foundry_temporal.errors import NonRetryableError, RetryableError, WorkflowError
from temporalio.exceptions import ApplicationError

# -- ActivityConfig ----------------------------------------------------------


class TestActivityConfig:
    def test_default_values(self):
        """Test ActivityConfig defaults"""
        config = ActivityConfig()

        assert config.retry_policy is None
        assert config.start_to_close_timeout is None
        assert config.schedule_to_close_timeout is None
        assert config.schedule_to_start_timeout is None
        assert config.heartbeat_timeout is None
        assert config.enable_observability is True
        assert config.enable_error_wrapping is True
        assert config.log_inputs is False
        assert config.log_outputs is False

    def test_custom_values(self):
        """Test ActivityConfig with custom values"""
        from temporalio.common import RetryPolicy

        retry = RetryPolicy(maximum_attempts=5)
        config = ActivityConfig(
            retry_policy=retry,
            start_to_close_timeout=timedelta(minutes=5),
            schedule_to_close_timeout=timedelta(minutes=10),
            schedule_to_start_timeout=timedelta(seconds=30),
            heartbeat_timeout=timedelta(seconds=15),
            enable_observability=False,
            enable_error_wrapping=False,
            log_inputs=True,
            log_outputs=True,
        )

        assert config.retry_policy is retry
        assert config.start_to_close_timeout == timedelta(minutes=5)
        assert config.schedule_to_close_timeout == timedelta(minutes=10)
        assert config.schedule_to_start_timeout == timedelta(seconds=30)
        assert config.heartbeat_timeout == timedelta(seconds=15)
        assert config.enable_observability is False
        assert config.enable_error_wrapping is False
        assert config.log_inputs is True
        assert config.log_outputs is True


# -- _is_retryable_error (module-level helper) ------------------------------


class TestIsRetryableErrorHelper:
    def test_timeout_error_retryable(self):
        """Errors with 'timeout' in the type name are retryable"""

        class TimeoutError(Exception):
            pass

        assert _is_retryable_error(TimeoutError("boom")) is True

    def test_connection_error_retryable(self):
        """Errors with 'connection' in the type name are retryable"""

        class ConnectionFailure(Exception):
            pass

        assert _is_retryable_error(ConnectionFailure("boom")) is True

    def test_network_error_retryable(self):
        """Errors with 'network' in the type name are retryable"""

        class NetworkError(Exception):
            pass

        assert _is_retryable_error(NetworkError("boom")) is True

    def test_unavailable_error_retryable(self):
        """Errors with 'unavailable' in the type name are retryable"""

        class ServiceUnavailableError(Exception):
            pass

        assert _is_retryable_error(ServiceUnavailableError("boom")) is True

    def test_throttle_error_retryable(self):
        """Errors with 'throttle' in the type name are retryable"""

        class ThrottleException(Exception):
            pass

        assert _is_retryable_error(ThrottleException("boom")) is True

    def test_rate_limit_error_retryable(self):
        """Errors with 'rate_limit' in the type name are retryable"""

        class Rate_LimitError(Exception):
            pass

        assert _is_retryable_error(Rate_LimitError("boom")) is True

    def test_generic_error_not_retryable(self):
        """Generic errors without retryable patterns are not retryable"""
        assert _is_retryable_error(ValueError("bad value")) is False
        assert _is_retryable_error(TypeError("wrong type")) is False
        assert _is_retryable_error(RuntimeError("runtime failure")) is False


# -- BaseActivity ------------------------------------------------------------


class ConcreteActivity(BaseActivity):
    """Concrete implementation of BaseActivity for testing"""

    def __init__(self, config=None, side_effect=None):
        super().__init__(config)
        self._side_effect = side_effect

    async def execute(self, *args, **kwargs):
        if self._side_effect:
            raise self._side_effect
        return {"result": "ok", "args": args}


class TestBaseActivity:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful activity execution"""
        act = ConcreteActivity()
        result = await act("hello")

        assert result == {"result": "ok", "args": ("hello",)}

    @pytest.mark.asyncio
    async def test_execute_with_observability_logging(self):
        """Test that observability logs are emitted on success"""
        config = ActivityConfig(enable_observability=True)
        act = ConcreteActivity(config=config)
        act.logger = MagicMock()

        await act("data")

        assert act.logger.info.call_count == 2  # starting + completed

    @pytest.mark.asyncio
    async def test_execute_with_observability_disabled(self):
        """Test that no observability logs are emitted when disabled"""
        config = ActivityConfig(enable_observability=False)
        act = ConcreteActivity(config=config)
        act.logger = MagicMock()

        await act("data")

        act.logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_logs_inputs_when_enabled(self):
        """Test that inputs are included in logs when log_inputs is True"""
        config = ActivityConfig(enable_observability=True, log_inputs=True)
        act = ConcreteActivity(config=config)
        act.logger = MagicMock()

        await act("secret-data")

        start_call = act.logger.info.call_args_list[0]
        assert start_call[1]["extra"]["inputs"] == ("secret-data",)

    @pytest.mark.asyncio
    async def test_execute_hides_inputs_by_default(self):
        """Test that inputs are NOT included in logs by default"""
        config = ActivityConfig(enable_observability=True, log_inputs=False)
        act = ConcreteActivity(config=config)
        act.logger = MagicMock()

        await act("secret-data")

        start_call = act.logger.info.call_args_list[0]
        assert start_call[1]["extra"]["inputs"] is None

    @pytest.mark.asyncio
    async def test_execute_logs_outputs_when_enabled(self):
        """Test that outputs are included in logs when log_outputs is True"""
        config = ActivityConfig(enable_observability=True, log_outputs=True)
        act = ConcreteActivity(config=config)
        act.logger = MagicMock()

        await act("data")

        completed_call = act.logger.info.call_args_list[1]
        assert completed_call[1]["extra"]["outputs"] == {"result": "ok", "args": ("data",)}

    @pytest.mark.asyncio
    async def test_error_wrapping_retryable(self):
        """Test that retryable errors are wrapped correctly"""

        class TemporaryConnectionError(Exception):
            pass

        act = ConcreteActivity(side_effect=TemporaryConnectionError("transient"))

        with pytest.raises(RetryableError, match="Retryable error in ConcreteActivity"):
            await act()

    @pytest.mark.asyncio
    async def test_error_wrapping_non_retryable(self):
        """Test that non-retryable errors are wrapped correctly"""
        act = ConcreteActivity(side_effect=ValueError("bad input"))

        with pytest.raises(NonRetryableError, match="Non-retryable error in ConcreteActivity"):
            await act()

    @pytest.mark.asyncio
    async def test_workflow_error_not_wrapped(self):
        """Test that WorkflowError passes through without wrapping"""
        original = WorkflowError("already wrapped")
        act = ConcreteActivity(side_effect=original)

        with pytest.raises(WorkflowError, match="already wrapped"):
            await act()

    @pytest.mark.asyncio
    async def test_application_error_not_wrapped(self):
        """Test that ApplicationError passes through without wrapping"""
        original = ApplicationError("temporal error")
        act = ConcreteActivity(side_effect=original)

        with pytest.raises(ApplicationError, match="temporal error"):
            await act()

    @pytest.mark.asyncio
    async def test_error_wrapping_disabled(self):
        """Test that errors pass through when error wrapping is disabled"""
        config = ActivityConfig(enable_error_wrapping=False)
        act = ConcreteActivity(config=config, side_effect=ValueError("raw"))

        with pytest.raises(ValueError, match="raw"):
            await act()

    @pytest.mark.asyncio
    async def test_error_logs_when_observability_enabled(self):
        """Test that errors are logged when observability is enabled"""
        config = ActivityConfig(enable_observability=True, enable_error_wrapping=False)
        act = ConcreteActivity(config=config, side_effect=ValueError("oops"))
        act.logger = MagicMock()

        with pytest.raises(ValueError):
            await act()

        act.logger.error.assert_called_once()

    def test_default_config_applied(self):
        """Test that default config is applied when None"""
        act = ConcreteActivity(config=None)
        assert act.config.enable_observability is True
        assert act.config.enable_error_wrapping is True


# -- @foundry_activity decorator ---------------------------------------------


class TestFoundryActivityDecorator:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test that decorated function executes normally"""

        @foundry_activity()
        async def greet(name: str) -> str:
            return f"hello {name}"

        result = await greet("world")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_custom_name(self):
        """Test that custom activity name is applied"""

        @foundry_activity(name="custom_greet")
        async def greet(name: str) -> str:
            return f"hello {name}"

        # The wrapper function retains the temporal activity name
        defn = getattr(greet, "__temporal_activity_definition")
        assert defn.name == "custom_greet"

    @pytest.mark.asyncio
    async def test_default_name_from_function(self):
        """Test that function name is used when no name is provided"""

        @foundry_activity()
        async def my_cool_activity(x: int) -> int:
            return x * 2

        result = await my_cool_activity(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_observability_logging(self):
        """Test that observability logs are emitted"""
        config = ActivityConfig(enable_observability=True)

        @foundry_activity(config=config)
        async def logged_activity() -> str:
            return "done"

        with patch("foundry_temporal.activities.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await logged_activity()

            assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_observability_disabled(self):
        """Test that no logs when observability is disabled"""
        config = ActivityConfig(enable_observability=False)

        @foundry_activity(config=config)
        async def quiet_activity() -> str:
            return "done"

        with patch("foundry_temporal.activities.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await quiet_activity()

            mock_logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_wrapping_retryable(self):
        """Test retryable error wrapping in decorator"""

        class TemporaryConnectionError(Exception):
            pass

        @foundry_activity()
        async def failing_activity():
            raise TemporaryConnectionError("transient")

        with pytest.raises(RetryableError, match="Retryable error"):
            await failing_activity()

    @pytest.mark.asyncio
    async def test_error_wrapping_non_retryable(self):
        """Test non-retryable error wrapping in decorator"""

        @foundry_activity()
        async def failing_activity():
            raise ValueError("bad input")

        with pytest.raises(NonRetryableError, match="Non-retryable error"):
            await failing_activity()

    @pytest.mark.asyncio
    async def test_workflow_error_passes_through(self):
        """Test WorkflowError is re-raised without wrapping"""

        @foundry_activity()
        async def failing_activity():
            raise WorkflowError("workflow issue")

        with pytest.raises(WorkflowError, match="workflow issue"):
            await failing_activity()

    @pytest.mark.asyncio
    async def test_application_error_passes_through(self):
        """Test ApplicationError is re-raised without wrapping"""

        @foundry_activity()
        async def failing_activity():
            raise ApplicationError("temporal issue")

        with pytest.raises(ApplicationError, match="temporal issue"):
            await failing_activity()

    @pytest.mark.asyncio
    async def test_error_wrapping_disabled(self):
        """Test raw errors when wrapping is disabled"""
        config = ActivityConfig(enable_error_wrapping=False)

        @foundry_activity(config=config)
        async def failing_activity():
            raise ValueError("raw error")

        with pytest.raises(ValueError, match="raw error"):
            await failing_activity()


# -- HeartbeatActivity -------------------------------------------------------


class ConcreteHeartbeatActivity(HeartbeatActivity):
    """Concrete implementation for testing"""

    def __init__(self, config=None, heartbeat_interval=timedelta(seconds=1), side_effect=None, duration=0):
        super().__init__(config, heartbeat_interval)
        self._side_effect = side_effect
        self._duration = duration

    async def execute(self, *args, **kwargs):
        if self._duration:
            await asyncio.sleep(self._duration)
        if self._side_effect:
            raise self._side_effect
        return {"heartbeat_result": "ok"}


class TestHeartbeatActivity:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful heartbeat activity execution"""
        act = ConcreteHeartbeatActivity()
        result = await act()

        assert result == {"heartbeat_result": "ok"}

    @pytest.mark.asyncio
    async def test_heartbeat_task_starts_and_stops(self):
        """Test that heartbeat loop is started and cancelled"""
        act = ConcreteHeartbeatActivity(heartbeat_interval=timedelta(seconds=0.05), duration=0.15)

        with patch("foundry_temporal.activities.activity") as mock_activity:
            result = await act()

            assert result == {"heartbeat_result": "ok"}
            # Heartbeat should have been called at least once
            assert mock_activity.heartbeat.call_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_task_cancelled_on_error(self):
        """Test heartbeat task is cancelled even when activity fails"""
        act = ConcreteHeartbeatActivity(
            side_effect=ValueError("fail"),
            config=ActivityConfig(enable_error_wrapping=False),
        )

        with pytest.raises(ValueError, match="fail"):
            await act()

    @pytest.mark.asyncio
    async def test_error_wrapping(self):
        """Test that HeartbeatActivity wraps errors like BaseActivity"""
        act = ConcreteHeartbeatActivity(side_effect=ValueError("bad"))

        with pytest.raises(NonRetryableError):
            await act()

    @pytest.mark.asyncio
    async def test_custom_heartbeat_interval(self):
        """Test custom heartbeat interval is stored"""
        act = ConcreteHeartbeatActivity(heartbeat_interval=timedelta(seconds=60))
        assert act.heartbeat_interval == timedelta(seconds=60)

    @pytest.mark.asyncio
    async def test_observability_logging(self):
        """Test observability logs for heartbeat activity"""
        config = ActivityConfig(enable_observability=True)
        act = ConcreteHeartbeatActivity(config=config)
        act.logger = MagicMock()

        with patch("foundry_temporal.activities.activity"):
            await act()

        assert act.logger.info.call_count == 2  # starting + completed


# -- @long_running_activity decorator ----------------------------------------


class TestLongRunningActivityDecorator:
    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test that decorated function executes normally"""

        @long_running_activity(heartbeat_interval=timedelta(seconds=1))
        async def process_data(items: list) -> int:
            return len(items)

        result = await process_data([1, 2, 3])
        assert result == 3

    @pytest.mark.asyncio
    async def test_heartbeat_fires_during_execution(self):
        """Test heartbeats are sent during long execution"""

        @long_running_activity(heartbeat_interval=timedelta(seconds=0.05))
        async def slow_task() -> str:
            await asyncio.sleep(0.15)
            return "done"

        with patch("foundry_temporal.activities.activity") as mock_activity:
            result = await slow_task()

            assert result == "done"
            assert mock_activity.heartbeat.call_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_cancelled_after_completion(self):
        """Test heartbeat task is properly cancelled after completion"""

        @long_running_activity(heartbeat_interval=timedelta(seconds=60))
        async def quick_task() -> str:
            return "done"

        with patch("foundry_temporal.activities.activity"):
            result = await quick_task()
            assert result == "done"

    @pytest.mark.asyncio
    async def test_error_wrapping(self):
        """Test error wrapping in long-running activity"""

        @long_running_activity()
        async def failing_task():
            raise ValueError("bad")

        with pytest.raises(NonRetryableError, match="Non-retryable error"):
            await failing_task()

    @pytest.mark.asyncio
    async def test_heartbeat_cancelled_on_error(self):
        """Test heartbeat task is cancelled when activity errors"""

        @long_running_activity(heartbeat_interval=timedelta(seconds=0.05))
        async def failing_task():
            await asyncio.sleep(0.1)
            raise ValueError("fail")

        with patch("foundry_temporal.activities.activity"):
            with pytest.raises(NonRetryableError):
                await failing_task()

    @pytest.mark.asyncio
    async def test_custom_name(self):
        """Test custom activity name"""

        @long_running_activity(name="my_long_task")
        async def task():
            return "ok"

        defn = getattr(task, "__temporal_activity_definition")
        assert defn.name == "my_long_task"

    @pytest.mark.asyncio
    async def test_observability_logging(self):
        """Test observability logs in long-running activity"""
        config = ActivityConfig(enable_observability=True)

        @long_running_activity(config=config)
        async def task():
            return "ok"

        with patch("foundry_temporal.activities.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            with patch("foundry_temporal.activities.activity"):
                await task()

            assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_observability_disabled(self):
        """Test no logs when observability disabled"""
        config = ActivityConfig(enable_observability=False)

        @long_running_activity(config=config)
        async def task():
            return "ok"

        with patch("foundry_temporal.activities.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            with patch("foundry_temporal.activities.activity"):
                await task()

            mock_logger.info.assert_not_called()


# -- BatchActivity -----------------------------------------------------------


class ConcreteBatchActivity(BatchActivity):
    """Concrete implementation for testing"""

    def __init__(self, config=None, batch_size=2, fail_on_batch=None):
        super().__init__(config, batch_size)
        self._fail_on_batch = fail_on_batch

    async def process_batch(self, batch: list):
        if self._fail_on_batch is not None and batch == self._fail_on_batch:
            raise ValueError("batch failed")
        return [item * 2 for item in batch]


class TestBatchActivity:
    @pytest.mark.asyncio
    async def test_process_all_items(self):
        """Test that all items are processed in batches"""
        act = ConcreteBatchActivity(batch_size=2)

        with patch("foundry_temporal.activities.activity"):
            result = await act([1, 2, 3, 4, 5])

        assert result == [2, 4, 6, 8, 10]

    @pytest.mark.asyncio
    async def test_single_batch(self):
        """Test when all items fit in one batch"""
        act = ConcreteBatchActivity(batch_size=10)

        with patch("foundry_temporal.activities.activity"):
            result = await act([1, 2, 3])

        assert result == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_empty_items(self):
        """Test with empty item list"""
        act = ConcreteBatchActivity(batch_size=2)

        with patch("foundry_temporal.activities.activity"):
            result = await act([])

        assert result == []

    @pytest.mark.asyncio
    async def test_heartbeat_progress(self):
        """Test heartbeat is called with progress after each batch"""
        act = ConcreteBatchActivity(batch_size=2)

        with patch("foundry_temporal.activities.activity") as mock_activity:
            await act([1, 2, 3, 4])

            # 2 batches -> 2 heartbeat calls
            assert mock_activity.heartbeat.call_count == 2
            mock_activity.heartbeat.assert_any_call("Processed 2/4 items")
            mock_activity.heartbeat.assert_any_call("Processed 4/4 items")

    @pytest.mark.asyncio
    async def test_batch_failure_propagates(self):
        """Test that batch failure raises and stops processing"""
        config = ActivityConfig(enable_error_wrapping=False)
        act = ConcreteBatchActivity(config=config, batch_size=2, fail_on_batch=[3, 4])

        with patch("foundry_temporal.activities.activity"):
            with pytest.raises(ValueError, match="batch failed"):
                await act([1, 2, 3, 4])

    @pytest.mark.asyncio
    async def test_custom_batch_size(self):
        """Test custom batch size"""
        act = ConcreteBatchActivity(batch_size=3)
        assert act.batch_size == 3

    @pytest.mark.asyncio
    async def test_non_list_batch_result_wrapped(self):
        """Test that non-list batch results are wrapped in a list"""

        class ScalarBatch(BatchActivity):
            async def process_batch(self, batch):
                return sum(batch)  # Returns int, not list

        act = ScalarBatch(batch_size=2)

        with patch("foundry_temporal.activities.activity"):
            result = await act([1, 2, 3, 4])

        assert result == [3, 7]  # sum([1,2])=3, sum([3,4])=7


# -- Convenience functions ---------------------------------------------------


class TestCreateSimpleActivity:
    @pytest.mark.asyncio
    async def test_creates_working_activity(self):
        """Test create_simple_activity produces a callable activity"""

        async def my_func(x: int) -> int:
            return x + 1

        activity_fn = create_simple_activity(my_func)
        result = await activity_fn(10)

        assert result == 11

    @pytest.mark.asyncio
    async def test_with_custom_config(self):
        """Test create_simple_activity with custom config"""
        config = ActivityConfig(enable_observability=False)

        async def my_func() -> str:
            return "ok"

        activity_fn = create_simple_activity(my_func, config=config)
        result = await activity_fn()

        assert result == "ok"


class TestCreateHeartbeatActivity:
    @pytest.mark.asyncio
    async def test_creates_working_activity(self):
        """Test create_heartbeat_activity produces a callable activity"""

        async def my_func() -> str:
            return "heartbeat-ok"

        # Decorator must be applied before mocking so @activity.defn runs for real
        activity_fn = create_heartbeat_activity(my_func)

        with patch("foundry_temporal.activities.activity.heartbeat"):
            result = await activity_fn()

        assert result == "heartbeat-ok"

    @pytest.mark.asyncio
    async def test_with_custom_interval(self):
        """Test create_heartbeat_activity with custom interval"""

        async def my_func() -> str:
            return "ok"

        activity_fn = create_heartbeat_activity(my_func, heartbeat_interval=timedelta(seconds=10))

        with patch("foundry_temporal.activities.activity.heartbeat"):
            result = await activity_fn()

        assert result == "ok"


# -- auto_heartbeat -----------------------------------------------------------


class TestAutoHeartbeat:
    @pytest.mark.asyncio
    async def test_noop_when_no_heartbeat_timeout(self):
        """No heartbeat task is started when the activity sets no heartbeat_timeout"""
        from foundry_temporal.activities import auto_heartbeat

        @auto_heartbeat
        async def my_activity(x: int) -> int:
            return x + 1

        with patch("foundry_temporal.activities.activity") as mock_activity:
            mock_activity.info.return_value = MagicMock(heartbeat_timeout=None)
            result = await my_activity(1)

        assert result == 2
        mock_activity.heartbeat.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeats_while_wrapped_call_runs(self):
        """Heartbeat fires periodically, at half the heartbeat_timeout, while fn runs"""
        from foundry_temporal.activities import auto_heartbeat

        @auto_heartbeat
        async def slow_activity() -> str:
            await asyncio.sleep(0.15)
            return "done"

        with patch("foundry_temporal.activities.activity") as mock_activity:
            mock_activity.info.return_value = MagicMock(heartbeat_timeout=timedelta(seconds=0.05))
            result = await slow_activity()

        assert result == "done"
        assert mock_activity.heartbeat.call_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_task_cancelled_on_error(self):
        """The heartbeat task is cancelled (not left running) when fn raises"""
        from foundry_temporal.activities import auto_heartbeat

        @auto_heartbeat
        async def failing_activity() -> None:
            raise ValueError("boom")

        with patch("foundry_temporal.activities.activity") as mock_activity:
            mock_activity.info.return_value = MagicMock(heartbeat_timeout=timedelta(seconds=1))
            with pytest.raises(ValueError, match="boom"):
                await failing_activity()

    @pytest.mark.asyncio
    async def test_preserves_function_arguments(self):
        """Positional and keyword arguments pass through to the wrapped function"""
        from foundry_temporal.activities import auto_heartbeat

        @auto_heartbeat
        async def add(a: int, b: int = 0) -> int:
            return a + b

        with patch("foundry_temporal.activities.activity") as mock_activity:
            mock_activity.info.return_value = MagicMock(heartbeat_timeout=None)
            result = await add(2, b=3)

        assert result == 5


# -- Public API (package-level imports) --------------------------------------


class TestPackageLevelImports:
    def test_activity_config_importable(self):
        """Test ActivityConfig is importable from foundry_temporal"""
        from foundry_temporal import ActivityConfig

        assert ActivityConfig is not None

    def test_base_activity_importable(self):
        """Test BaseActivity is importable from foundry_temporal"""
        from foundry_temporal import BaseActivity

        assert BaseActivity is not None

    def test_heartbeat_activity_importable(self):
        """Test HeartbeatActivity is importable from foundry_temporal"""
        from foundry_temporal import HeartbeatActivity

        assert HeartbeatActivity is not None

    def test_batch_activity_importable(self):
        """Test BatchActivity is importable from foundry_temporal"""
        from foundry_temporal import BatchActivity

        assert BatchActivity is not None

    def test_foundry_activity_importable(self):
        """Test foundry_activity is importable from foundry_temporal"""
        from foundry_temporal import foundry_activity

        assert foundry_activity is not None

    def test_long_running_activity_importable(self):
        """Test long_running_activity is importable from foundry_temporal"""
        from foundry_temporal import long_running_activity

        assert long_running_activity is not None

    def test_create_simple_activity_importable(self):
        """Test create_simple_activity is importable from foundry_temporal"""
        from foundry_temporal import create_simple_activity

        assert create_simple_activity is not None

    def test_create_heartbeat_activity_importable(self):
        """Test create_heartbeat_activity is importable from foundry_temporal"""
        from foundry_temporal import create_heartbeat_activity

        assert create_heartbeat_activity is not None
