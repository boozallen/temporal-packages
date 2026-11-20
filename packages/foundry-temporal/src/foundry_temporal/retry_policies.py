# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Retry Policy Configurations for Temporal Activities

Standard retry policies for different types of operations based on
foundry-temporal architecture specifications.
"""

from datetime import timedelta

from temporalio.common import RetryPolicy

# File I/O: Fewer retries (usually succeeds or fails fast)
FILE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)

# Light processing: Minimal retries
PROCESSING_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)

# DynamoDB operations: Quick retries for transient errors
DYNAMODB_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)

# HTTP operations: Moderate retries for network issues
HTTP_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=15),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)


def get_retry_policy_for_activity(activity_type: str) -> RetryPolicy:
    """
    Get appropriate retry policy based on activity type

    Args:
        activity_type: Type of activity ('file', 'processing', 'dynamodb', 'http')

    Returns:
        RetryPolicy: Appropriate retry policy for the activity type

    Raises:
        ValueError: If activity_type is not recognized

    Note:
        Agent retry policies are handled by foundry_strands_agent package
    """
    policies = {
        "file": FILE_RETRY_POLICY,
        "processing": PROCESSING_RETRY_POLICY,
        "dynamodb": DYNAMODB_RETRY_POLICY,
        "http": HTTP_RETRY_POLICY,
    }

    if activity_type not in policies:
        raise ValueError(f"Unknown activity type: {activity_type}. Supported types: {list(policies.keys())}")

    return policies[activity_type]
