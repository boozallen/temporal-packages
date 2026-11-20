# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Dataclass-based activity patterns for Temporal workflows.

This module provides decorators and utilities for creating activities with
dataclass inputs, following Temporal best practices for activity design:

- Single dataclass parameter instead of multiple parameters
- Easier interface evolution over time
- Better type safety and IDE support
- Standardized patterns across activities
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from temporalio import activity

from .activities import ActivityConfig, _is_retryable_error
from .errors import NonRetryableError, RetryableError, WorkflowError
from .logging import get_logger

logger = logging.getLogger(__name__)


def dataclass_activity(
    config: ActivityConfig | None = None,
    name: str | None = None,
    **activity_kwargs,
):
    """
    Decorator for creating Temporal activities with dataclass inputs.

    This decorator encourages the Temporal best practice of using a single
    dataclass parameter for all activity inputs, rather than multiple parameters.
    This makes it easier to evolve activity interfaces over time.

    Args:
        config: Activity configuration
        name: Activity name (defaults to function name)
        **activity_kwargs: Additional arguments for @activity decorator

    Returns:
        Decorated async function that accepts a dataclass input

    Example:
        @dataclass
        class MyTaskInput:
            query: str
            timeout: int = 30

        @dataclass_activity(name="my_activity")
        async def my_activity(input_data: MyTaskInput) -> dict[str, str]:
            result = await process_query(input_data.query)
            return {"result": result}
    """

    def decorator(func: Callable) -> Callable:
        activity_config = config or ActivityConfig()

        @activity.defn(name=name, **activity_kwargs)
        @wraps(func)
        async def wrapper(input_data: Any) -> Any:
            activity_name = name or func.__name__

            activity_logger = get_logger()

            if activity_config.enable_observability:
                activity_logger.info(
                    f"Activity {activity_name} starting",
                    extra={"input_type": type(input_data).__name__} if activity_config.log_inputs else None,
                )

            try:
                result = await func(input_data)

                if activity_config.enable_observability:
                    activity_logger.info(
                        f"Activity {activity_name} completed",
                        extra={"output_type": type(result).__name__} if activity_config.log_outputs else None,
                    )

                return result

            except Exception as error:
                if activity_config.enable_observability:
                    activity_logger.error(f"Activity {activity_name} failed: {error}", extra={"error": str(error)})

                if activity_config.enable_error_wrapping:
                    if isinstance(error, (WorkflowError)):
                        raise
                    elif _is_retryable_error(error):
                        raise RetryableError(f"Retryable error in {activity_name}: {error}") from error
                    else:
                        raise NonRetryableError(f"Non-retryable error in {activity_name}: {error}") from error
                else:
                    raise

        return wrapper

    return decorator


# Common input patterns for activities


@dataclass
class BasicTaskInput:
    """
    Simple input dataclass for basic activities.

    Use this for straightforward activities that need minimal input.
    """

    query: str
    """The main input or query for the activity"""

    timeout: int = 30
    """Timeout in seconds for the activity"""

    metadata: dict[str, Any] | None = None
    """Optional metadata about the task"""


@dataclass
class FileProcessingInput:
    """
    Input dataclass for file processing activities.

    Use this when your activity processes files.
    """

    file_path: str
    """Path to the file to process"""

    operation: str
    """Operation to perform on the file"""

    options: dict[str, Any] | None = None
    """Processing options"""

    output_format: str = "json"
    """Output format for the results"""


@dataclass
class BatchProcessingInput:
    """
    Input dataclass for batch processing activities.

    Use this when your activity processes multiple items in batches.
    """

    items: list[Any]
    """Items to process"""

    batch_size: int = 100
    """Size of each batch"""

    concurrent: bool = False
    """Whether to process batches concurrently"""

    options: dict[str, Any] | None = None
    """Processing options"""


@dataclass
class APICallInput:
    """
    Input dataclass for API call activities.

    Use this when your activity makes external API calls.
    """

    endpoint: str
    """API endpoint URL"""

    method: str = "GET"
    """HTTP method (GET, POST, PUT, DELETE, etc.)"""

    headers: dict[str, str] | None = None
    """HTTP headers"""

    body: dict[str, Any] | None = None
    """Request body for POST/PUT requests"""

    timeout: int = 30
    """Request timeout in seconds"""

    retries: int = 3
    """Number of retries on failure"""


# Utility functions for working with dataclass activities


def validate_dataclass_input(input_data: Any, expected_type: type) -> None:
    """
    Validate that input is of the expected dataclass type.

    Args:
        input_data: Input to validate
        expected_type: Expected dataclass type

    Raises:
        TypeError: If input is not of the expected type
    """
    if not isinstance(input_data, expected_type):
        raise TypeError(f"Expected {expected_type.__name__}, got {type(input_data).__name__}")


def dataclass_to_dict(dataclass_obj: Any) -> dict[str, Any]:
    """
    Convert a dataclass to a dictionary.

    Args:
        dataclass_obj: Dataclass instance to convert

    Returns:
        Dictionary representation of the dataclass
    """
    from dataclasses import asdict

    return asdict(dataclass_obj)


def dict_to_dataclass(data: dict[str, Any], dataclass_type: type) -> Any:
    """
    Convert a dictionary to a dataclass instance.

    Args:
        data: Dictionary to convert
        dataclass_type: Target dataclass type

    Returns:
        Dataclass instance created from the dictionary

    Raises:
        TypeError: If dataclass_type is not a dataclass
    """
    from dataclasses import fields, is_dataclass

    if not is_dataclass(dataclass_type):
        raise TypeError(f"{dataclass_type.__name__} is not a dataclass")

    # Filter to only valid fields
    valid_fields = {f.name for f in fields(dataclass_type)}
    filtered_data = {k: v for k, v in data.items() if k in valid_fields}

    return dataclass_type(**filtered_data)
