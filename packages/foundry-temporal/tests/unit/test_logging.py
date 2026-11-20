# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.logging module

Dedicated test module for logging utilities including StandardLoggerWrapper,
WorkflowEventLogger, structured logging setup, and the activity logging decorator.
"""

from unittest.mock import MagicMock, patch

import pytest
from foundry_temporal.logging import (
    StandardLoggerWrapper,
    WorkflowEventLogger,
    get_logger,
    log_activity_execution,
    setup_structured_logging,
)


class TestStandardLoggerWrapper:
    def test_init_basic(self):
        """Test basic StandardLoggerWrapper initialization"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger)

        assert wrapper._logger is mock_logger
        assert wrapper._context == {}

    def test_init_with_context(self):
        """Test StandardLoggerWrapper initialization with context"""
        mock_logger = MagicMock()
        context = {"workflow_id": "test-123", "phase": "planning"}
        wrapper = StandardLoggerWrapper(mock_logger, context)

        assert wrapper._logger is mock_logger
        assert wrapper._context == context

    def test_bind(self):
        """Test bind method creates new wrapper with additional context"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger, {"existing": "value"})

        new_wrapper = wrapper.bind(new_key="new_value", another="another_value")

        # Should be a new instance
        assert new_wrapper is not wrapper
        assert isinstance(new_wrapper, StandardLoggerWrapper)

        # Should have combined context
        expected_context = {"existing": "value", "new_key": "new_value", "another": "another_value"}
        assert new_wrapper._context == expected_context

        # Original wrapper should be unchanged
        assert wrapper._context == {"existing": "value"}

    def test_info_logging(self):
        """Test info logging method"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger, {"workflow_id": "test"})

        wrapper.info("Test message", extra_param="extra_value")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        message = call_args[0]

        assert "Test message" in message
        assert "workflow_id=test" in message
        assert "extra_param=extra_value" in message

    def test_warning_logging(self):
        """Test warning logging method"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger)

        wrapper.warning("Warning message")

        mock_logger.warning.assert_called_once_with("Warning message")

    def test_error_logging(self):
        """Test error logging method"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger, {"context": "test"})

        wrapper.error("Error occurred", error_code=500)

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0]
        message = call_args[0]

        assert "Error occurred" in message
        assert "context=test" in message
        assert "error_code=500" in message

    def test_debug_logging(self):
        """Test debug logging method"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger, {"component": "worker"})

        wrapper.debug("Debug details", step=3)

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args[0]
        message = call_args[0]

        assert "Debug details" in message
        assert "component=worker" in message
        assert "step=3" in message

    def test_format_message_no_context(self):
        """Test _format_message with no context or kwargs"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger)

        formatted = wrapper._format_message("Simple message", {})
        assert formatted == "Simple message"

    def test_format_message_with_context_and_kwargs(self):
        """Test _format_message with both context and kwargs"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger, {"ctx": "value"})

        formatted = wrapper._format_message("Message", {"kwarg": "kwarg_value"})

        assert "Message" in formatted
        assert "ctx=value" in formatted
        assert "kwarg=kwarg_value" in formatted

    def test_kwargs_override_context(self):
        """Test that kwargs override context values with same keys"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger, {"key": "context_value"})

        wrapper.info("Test", key="kwarg_value")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        message = call_args[0]

        # kwargs should override context
        assert "key=kwarg_value" in message
        assert "key=context_value" not in message

    def test_bind_chaining(self):
        """Test that bind can be chained multiple times"""
        mock_logger = MagicMock()
        wrapper = StandardLoggerWrapper(mock_logger)

        chained = wrapper.bind(a="1").bind(b="2").bind(c="3")

        assert chained._context == {"a": "1", "b": "2", "c": "3"}
        # Original unchanged
        assert wrapper._context == {}


class TestSetupStructuredLogging:
    @patch("foundry_temporal.logging._get_structlog")
    def test_setup_with_structlog_available(self, mock_get_structlog):
        """Test setup when structlog is available"""
        mock_structlog = MagicMock()
        mock_get_structlog.return_value = (mock_structlog, True)

        logger = setup_structured_logging("DEBUG")

        # Should configure structlog
        mock_structlog.configure.assert_called_once()
        mock_structlog.get_logger.assert_called_once()

        # Should return structlog logger
        assert logger == mock_structlog.get_logger.return_value

    @patch("foundry_temporal.logging._get_structlog")
    @patch("foundry_temporal.logging.logging")
    def test_setup_with_structlog_unavailable(self, mock_logging, mock_get_structlog):
        """Test setup when structlog is unavailable"""
        mock_get_structlog.return_value = (mock_logging, False)

        mock_stdlib_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_stdlib_logger

        logger = setup_structured_logging("INFO")

        # Should configure standard logging
        mock_logging.basicConfig.assert_called_once()
        mock_logging.getLogger.assert_called_once_with("foundry_temporal.logging")

        # Should return wrapped logger
        assert isinstance(logger, StandardLoggerWrapper)
        assert logger._logger is mock_stdlib_logger

    @patch("foundry_temporal.logging._get_structlog")
    @patch("foundry_temporal.logging.logging")
    def test_setup_log_level_handling(self, mock_logging, mock_get_structlog):
        """Test log level is properly handled"""
        mock_get_structlog.return_value = (mock_logging, False)
        mock_logging.getLogger.return_value = MagicMock()

        setup_structured_logging("WARNING")

        # Should call basicConfig with correct log level
        call_kwargs = mock_logging.basicConfig.call_args[1]
        assert call_kwargs["level"] == mock_logging.WARNING


class TestGetLogger:
    @patch("foundry_temporal.logging.setup_structured_logging")
    def test_get_logger_initialization(self, mock_setup):
        """Test get_logger initializes logger on first call"""
        mock_logger = MagicMock()
        mock_setup.return_value = mock_logger

        # Reset global logger state
        import foundry_temporal.logging

        foundry_temporal.logging.logger = None

        logger = get_logger()

        assert logger is mock_logger
        mock_setup.assert_called_once_with()

    def test_get_logger_caching(self):
        """Test get_logger returns cached logger on subsequent calls"""
        # Set up a mock logger in the global state
        import foundry_temporal.logging

        mock_logger = MagicMock()
        foundry_temporal.logging.logger = mock_logger

        logger1 = get_logger()
        logger2 = get_logger()

        assert logger1 is mock_logger
        assert logger2 is mock_logger
        assert logger1 is logger2


class TestWorkflowEventLogger:
    @patch("foundry_temporal.logging.get_logger")
    def test_init(self, mock_get_logger):
        """Test WorkflowEventLogger initialization"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow-123")

        assert event_logger.workflow_id == "test-workflow-123"
        assert event_logger.logger is mock_bound_logger
        mock_logger.bind.assert_called_once_with(workflow_id="test-workflow-123")

    @patch("foundry_temporal.logging.get_logger")
    @patch("foundry_temporal.observability.research_workflows_started_total")
    def test_workflow_started(self, mock_metric, mock_get_logger):
        """Test workflow_started logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.workflow_started("AI Research Topic", extra_param="value")

        # Should increment metric
        mock_metric.inc.assert_called_once()

        # Should log event
        mock_bound_logger.info.assert_called_once_with(
            "workflow_started", topic="AI Research Topic", extra_param="value"
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_plan_generated(self, mock_get_logger):
        """Test plan_generated logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.plan_generated(1, "plan-doc-key", extra="data")

        mock_bound_logger.info.assert_called_once_with(
            "plan_generated", version=1, document_key="plan-doc-key", extra="data"
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_plan_feedback_received(self, mock_get_logger):
        """Test plan_feedback_received logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.plan_feedback_received(2, "Please add more detail")

        mock_bound_logger.info.assert_called_once_with(
            "plan_feedback_received", iteration=2, feedback_length=len("Please add more detail")
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_plan_approved(self, mock_get_logger):
        """Test plan_approved logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.plan_approved(3, "plan-doc-key-v3")

        mock_bound_logger.info.assert_called_once_with("plan_approved", iteration=3, document_key="plan-doc-key-v3")

    @patch("foundry_temporal.logging.get_logger")
    def test_research_complete(self, mock_get_logger):
        """Test research_complete logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.research_complete("research-doc-key", duration_seconds=45.2)

        mock_bound_logger.info.assert_called_once_with(
            "research_complete", document_key="research-doc-key", duration_seconds=45.2
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_research_complete_without_duration(self, mock_get_logger):
        """Test research_complete logging without duration"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.research_complete("research-doc-key")

        mock_bound_logger.info.assert_called_once_with(
            "research_complete", document_key="research-doc-key", duration_seconds=None
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_document_feedback_received(self, mock_get_logger):
        """Test document_feedback_received logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.document_feedback_received(1, "Needs more citations")

        mock_bound_logger.info.assert_called_once_with(
            "document_feedback_received", iteration=1, feedback_length=len("Needs more citations")
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_document_approved(self, mock_get_logger):
        """Test document_approved logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.document_approved(2, "final-doc-key-v2")

        mock_bound_logger.info.assert_called_once_with(
            "document_approved", iteration=2, final_document_key="final-doc-key-v2"
        )

    @patch("foundry_temporal.logging.get_logger")
    def test_agent_call_retry(self, mock_get_logger):
        """Test agent_call_retry logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        error = ValueError("Test error")
        event_logger.agent_call_retry(2, error, "test_activity")

        mock_bound_logger.warning.assert_called_once_with(
            "agent_call_retry", attempt=2, error="Test error", activity_name="test_activity"
        )

    @patch("foundry_temporal.logging.get_logger")
    @patch("foundry_temporal.observability.research_workflows_completed_total")
    @patch("foundry_temporal.observability.research_iterations")
    def test_workflow_completed(self, mock_iterations_metric, mock_completed_metric, mock_get_logger):
        """Test workflow_completed logging"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.workflow_completed("completed", 3, 120.5)

        # Should update metrics
        mock_completed_metric.labels.assert_called_once_with(status="completed")
        mock_completed_metric.labels.return_value.inc.assert_called_once()
        mock_iterations_metric.observe.assert_called_once_with(3)

        # Should log event
        mock_bound_logger.info.assert_called_once_with(
            "workflow_completed", status="completed", iterations=3, duration_seconds=120.5
        )

    @patch("foundry_temporal.logging.get_logger")
    @patch("foundry_temporal.observability.research_workflows_completed_total")
    @patch("foundry_temporal.observability.research_iterations")
    def test_workflow_completed_without_duration(self, mock_iterations_metric, mock_completed_metric, mock_get_logger):
        """Test workflow_completed logging without duration"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        event_logger.workflow_completed("timeout", 5)

        mock_completed_metric.labels.assert_called_once_with(status="timeout")
        mock_iterations_metric.observe.assert_called_once_with(5)

        mock_bound_logger.info.assert_called_once_with(
            "workflow_completed", status="timeout", iterations=5, duration_seconds=None
        )

    @patch("foundry_temporal.logging.get_logger")
    @patch("foundry_temporal.observability.agent_call_errors_total")
    def test_agent_call_retry_increments_error_metric(self, mock_error_metric, mock_get_logger):
        """Test that agent_call_retry increments the error counter metric"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        event_logger = WorkflowEventLogger("test-workflow")
        error = ConnectionError("Connection lost")
        event_logger.agent_call_retry(1, error, "agent_activity")

        mock_error_metric.labels.assert_called_once_with(error_type="ConnectionError")
        mock_error_metric.labels.return_value.inc.assert_called_once()


class TestLogActivityExecution:
    @patch("foundry_temporal.logging.get_logger")
    @patch("time.time")
    def test_log_activity_execution_success(self, mock_time, mock_get_logger):
        """Test log_activity_execution decorator for successful activity"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        mock_time.side_effect = [1000.0, 1005.5]

        @log_activity_execution("test_activity")
        async def test_activity():
            return "success"

        async def run_test():
            result = await test_activity()
            assert result == "success"

        import asyncio

        asyncio.run(run_test())

        # Should log start and completion
        assert mock_bound_logger.info.call_count == 2
        start_call, completion_call = mock_bound_logger.info.call_args_list

        assert start_call[0] == ("activity_started",)
        assert completion_call[0] == ("activity_completed",)
        assert completion_call[1]["duration_seconds"] == 5.5

    @patch("foundry_temporal.logging.get_logger")
    @patch("time.time")
    def test_log_activity_execution_failure(self, mock_time, mock_get_logger):
        """Test log_activity_execution decorator for failed activity"""
        mock_logger = MagicMock()
        mock_bound_logger = MagicMock()
        mock_logger.bind.return_value = mock_bound_logger
        mock_get_logger.return_value = mock_logger

        mock_time.side_effect = [1000.0, 1003.2]

        @log_activity_execution("failing_activity")
        async def failing_activity():
            raise ValueError("Activity failed")

        async def run_test():
            with pytest.raises(ValueError):
                await failing_activity()

        import asyncio

        asyncio.run(run_test())

        # Should log start and error
        assert mock_bound_logger.info.call_count == 1  # Only start
        assert mock_bound_logger.error.call_count == 1  # Error

        error_call = mock_bound_logger.error.call_args
        assert error_call[0] == ("activity_failed",)
        assert error_call[1]["duration_seconds"] == pytest.approx(3.2)
        assert error_call[1]["error"] == "Activity failed"
        assert error_call[1]["error_type"] == "ValueError"

    @patch("foundry_temporal.logging.get_logger")
    @patch("time.time")
    def test_log_activity_execution_preserves_function_name(self, mock_time, mock_get_logger):
        """Test that the decorator preserves the original function name"""
        mock_logger = MagicMock()
        mock_logger.bind.return_value = MagicMock()
        mock_get_logger.return_value = mock_logger

        @log_activity_execution("my_activity")
        async def original_function():
            pass

        assert original_function.__name__ == "original_function"
