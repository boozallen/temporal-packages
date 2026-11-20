# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Structured Logging Setup (separated from observability to avoid sandbox issues)

Provides structured logging configuration with fallback to standard logging
when running in Temporal workflow sandbox environments.
"""

import logging
from typing import Any


def _get_structlog():
    """Check if we're in a workflow environment and avoid structlog if so"""
    try:
        # Check if we're in a Temporal workflow sandbox by looking for the restriction marker
        import sys

        if "temporalio.worker.workflow_sandbox._restrictions" in sys.modules:
            # We're in a workflow, use standard logging
            return logging, False
        else:
            # Not in workflow, try structlog
            import structlog  # type: ignore

            return structlog, True
    except ImportError:
        return logging, False


STRUCTLOG_AVAILABLE = None  # Will be determined on first use


# Simple logger wrapper to provide bind() method for standard logging
class StandardLoggerWrapper:
    """Wrapper to make standard logger compatible with structlog interface"""

    def __init__(self, logger: logging.Logger, context: dict[str, Any] | None = None):
        self._logger = logger
        self._context = context or {}

    def bind(self, **kwargs) -> StandardLoggerWrapper:
        """Return new logger with additional context"""
        new_context = {**self._context, **kwargs}
        return StandardLoggerWrapper(self._logger, new_context)

    def info(self, msg: str, **kwargs) -> None:
        self._logger.info(self._format_message(msg, kwargs))

    def warning(self, msg: str, **kwargs) -> None:
        self._logger.warning(self._format_message(msg, kwargs))

    def error(self, msg: str, **kwargs) -> None:
        self._logger.error(self._format_message(msg, kwargs))

    def debug(self, msg: str, **kwargs) -> None:
        self._logger.debug(self._format_message(msg, kwargs))

    def _format_message(self, msg: str, kwargs: dict[str, Any]) -> str:
        """Format message with context and kwargs"""
        all_context = {**self._context, **kwargs}
        if all_context:
            context_str = " ".join(f"{k}={v}" for k, v in all_context.items())
            return f"{msg} {context_str}"
        return msg


def setup_structured_logging(log_level: str = "INFO") -> Any:
    """
    Configure structured logging for workflow components

    Returns structlog logger or standard logger if structlog unavailable
    """
    global STRUCTLOG_AVAILABLE
    structlog_module, STRUCTLOG_AVAILABLE = _get_structlog()

    if STRUCTLOG_AVAILABLE:
        structlog_module.configure(
            processors=[
                structlog_module.stdlib.filter_by_level,
                structlog_module.stdlib.add_logger_name,
                structlog_module.stdlib.add_log_level,
                structlog_module.stdlib.PositionalArgumentsFormatter(),
                structlog_module.processors.TimeStamper(fmt="iso"),
                structlog_module.processors.StackInfoRenderer(),
                structlog_module.processors.format_exc_info,
                structlog_module.processors.UnicodeDecoder(),
                structlog_module.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog_module.stdlib.LoggerFactory(),
            wrapper_class=structlog_module.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        return structlog_module.get_logger()
    else:
        # Fallback to standard logging with wrapper for compatibility
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        return StandardLoggerWrapper(logging.getLogger(__name__))


# Logger instance (lazy initialization)
logger = None


def get_logger():
    """Get or initialize the logger"""
    global logger
    if logger is None:
        logger = setup_structured_logging()
    return logger


# Workflow Event Logger (from architecture specification)
class WorkflowEventLogger:
    """
    Standard workflow event logging

    Key Log Events from architecture:
    - workflow_started - Workflow initiated with topic and workflow_id
    - plan_generated - Research plan created (version number)
    - plan_feedback_received - User provided plan feedback
    - plan_approved - User approved research plan
    - research_complete - Research execution finished
    - document_feedback_received - User provided document feedback
    - document_approved - User approved final document
    - agent_call_retry - Activity retry with attempt number and error
    - workflow_completed - Final workflow result
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.logger = get_logger().bind(workflow_id=workflow_id)

    def workflow_started(self, topic: str, **kwargs):
        """Log workflow initiation"""
        # Import here to avoid circular imports
        from .observability import research_workflows_started_total

        research_workflows_started_total.inc()
        self.logger.info("workflow_started", topic=topic, **kwargs)

    def plan_generated(self, version: int, document_key: str, **kwargs):
        """Log research plan creation"""
        self.logger.info("plan_generated", version=version, document_key=document_key, **kwargs)

    def plan_feedback_received(self, iteration: int, comments: str, **kwargs):
        """Log plan feedback"""
        self.logger.info("plan_feedback_received", iteration=iteration, feedback_length=len(comments), **kwargs)

    def plan_approved(self, iteration: int, document_key: str, **kwargs):
        """Log plan approval"""
        self.logger.info("plan_approved", iteration=iteration, document_key=document_key, **kwargs)

    def research_complete(self, document_key: str, duration_seconds: float | None = None, **kwargs):
        """Log research execution completion"""
        self.logger.info("research_complete", document_key=document_key, duration_seconds=duration_seconds, **kwargs)

    def document_feedback_received(self, iteration: int, comments: str, **kwargs):
        """Log document feedback"""
        self.logger.info("document_feedback_received", iteration=iteration, feedback_length=len(comments), **kwargs)

    def document_approved(self, iteration: int, final_document_key: str, **kwargs):
        """Log document approval"""
        self.logger.info("document_approved", iteration=iteration, final_document_key=final_document_key, **kwargs)

    def agent_call_retry(self, attempt: int, error: str, activity_name: str, **kwargs):
        """Log activity retry"""
        from .observability import agent_call_errors_total

        agent_call_errors_total.labels(error_type=type(error).__name__).inc()
        self.logger.warning(
            "agent_call_retry", attempt=attempt, error=str(error), activity_name=activity_name, **kwargs
        )

    def workflow_completed(self, status: str, iterations: int, duration_seconds: float | None = None, **kwargs):
        """Log workflow completion"""
        from .observability import research_iterations, research_workflows_completed_total

        research_workflows_completed_total.labels(status=status).inc()
        research_iterations.observe(iterations)

        self.logger.info(
            "workflow_completed", status=status, iterations=iterations, duration_seconds=duration_seconds, **kwargs
        )


# Activity logging decorator
def log_activity_execution(activity_name: str):
    """
    Decorator to add logging to activity execution

    Usage:
        @log_activity_execution("my_activity")
        @activity.defn
        async def my_activity():
            pass
    """
    import time

    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            activity_logger = get_logger().bind(
                activity_name=activity_name, activity_id=f"{activity_name}-{int(start_time)}"
            )

            activity_logger.info("activity_started")

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                activity_logger.info("activity_completed", duration_seconds=duration)
                return result

            except Exception as e:
                duration = time.time() - start_time
                activity_logger.error(
                    "activity_failed", duration_seconds=duration, error=str(e), error_type=type(e).__name__
                )
                raise

        wrapper.__name__ = func.__name__
        return wrapper

    return decorator
