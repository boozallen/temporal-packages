# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.retry_policies module"""

from datetime import timedelta

import pytest
from foundry_temporal.retry_policies import (
    DYNAMODB_RETRY_POLICY,
    FILE_RETRY_POLICY,
    HTTP_RETRY_POLICY,
    PROCESSING_RETRY_POLICY,
    get_retry_policy_for_activity,
)
from temporalio.common import RetryPolicy


class TestRetryPolicies:
    def test_file_retry_policy(self):
        """Test FILE_RETRY_POLICY configuration"""
        policy = FILE_RETRY_POLICY

        assert isinstance(policy, RetryPolicy)
        assert policy.initial_interval == timedelta(seconds=1)
        assert policy.maximum_interval == timedelta(seconds=5)
        assert policy.maximum_attempts == 3
        assert policy.backoff_coefficient == 2.0

    def test_processing_retry_policy(self):
        """Test PROCESSING_RETRY_POLICY configuration"""
        policy = PROCESSING_RETRY_POLICY

        assert isinstance(policy, RetryPolicy)
        assert policy.initial_interval == timedelta(seconds=1)
        assert policy.maximum_interval == timedelta(seconds=10)
        assert policy.maximum_attempts == 3
        assert policy.backoff_coefficient == 2.0

    def test_dynamodb_retry_policy(self):
        """Test DYNAMODB_RETRY_POLICY configuration"""
        policy = DYNAMODB_RETRY_POLICY

        assert isinstance(policy, RetryPolicy)
        assert policy.initial_interval == timedelta(seconds=1)
        assert policy.maximum_interval == timedelta(seconds=5)
        assert policy.maximum_attempts == 3
        assert policy.backoff_coefficient == 2.0

    def test_http_retry_policy(self):
        """Test HTTP_RETRY_POLICY configuration"""
        policy = HTTP_RETRY_POLICY

        assert isinstance(policy, RetryPolicy)
        assert policy.initial_interval == timedelta(seconds=1)
        assert policy.maximum_interval == timedelta(seconds=15)
        assert policy.maximum_attempts == 3
        assert policy.backoff_coefficient == 2.0

    def test_retry_policies_are_different_instances(self):
        """Test that retry policies are different instances"""
        policies = [FILE_RETRY_POLICY, PROCESSING_RETRY_POLICY, DYNAMODB_RETRY_POLICY, HTTP_RETRY_POLICY]

        # Each policy should be a unique instance
        for i, policy1 in enumerate(policies):
            for j, policy2 in enumerate(policies):
                if i != j:
                    assert policy1 is not policy2

    def test_retry_policies_configuration_differences(self):
        """Test that retry policies have appropriate configuration differences"""
        # File and DynamoDB should have same maximum_interval (5s) - fast operations
        assert FILE_RETRY_POLICY.maximum_interval == DYNAMODB_RETRY_POLICY.maximum_interval

        # HTTP should have longer maximum_interval (15s) - network operations
        assert HTTP_RETRY_POLICY.maximum_interval > FILE_RETRY_POLICY.maximum_interval
        assert HTTP_RETRY_POLICY.maximum_interval > DYNAMODB_RETRY_POLICY.maximum_interval

        # Processing should have moderate maximum_interval (10s)
        assert PROCESSING_RETRY_POLICY.maximum_interval > FILE_RETRY_POLICY.maximum_interval
        assert PROCESSING_RETRY_POLICY.maximum_interval < HTTP_RETRY_POLICY.maximum_interval

        # All should have same initial_interval, attempts, and backoff
        for policy in [FILE_RETRY_POLICY, PROCESSING_RETRY_POLICY, DYNAMODB_RETRY_POLICY, HTTP_RETRY_POLICY]:
            assert policy.initial_interval == timedelta(seconds=1)
            assert policy.maximum_attempts == 3
            assert policy.backoff_coefficient == 2.0


class TestGetRetryPolicyForActivity:
    def test_get_file_retry_policy(self):
        """Test getting file retry policy"""
        policy = get_retry_policy_for_activity("file")
        assert policy is FILE_RETRY_POLICY

    def test_get_processing_retry_policy(self):
        """Test getting processing retry policy"""
        policy = get_retry_policy_for_activity("processing")
        assert policy is PROCESSING_RETRY_POLICY

    def test_get_dynamodb_retry_policy(self):
        """Test getting DynamoDB retry policy"""
        policy = get_retry_policy_for_activity("dynamodb")
        assert policy is DYNAMODB_RETRY_POLICY

    def test_get_http_retry_policy(self):
        """Test getting HTTP retry policy"""
        policy = get_retry_policy_for_activity("http")
        assert policy is HTTP_RETRY_POLICY

    def test_get_retry_policy_case_sensitivity(self):
        """Test that activity type matching is case sensitive"""
        # Should work with exact case
        policy = get_retry_policy_for_activity("file")
        assert policy is FILE_RETRY_POLICY

        # Should fail with different case
        with pytest.raises(ValueError):
            get_retry_policy_for_activity("FILE")

        with pytest.raises(ValueError):
            get_retry_policy_for_activity("File")

    def test_get_retry_policy_unknown_type(self):
        """Test error handling for unknown activity type"""
        with pytest.raises(ValueError) as exc_info:
            get_retry_policy_for_activity("unknown")

        error_message = str(exc_info.value)
        assert "Unknown activity type: unknown" in error_message
        assert "Supported types:" in error_message

        # Should list all supported types
        assert "file" in error_message
        assert "processing" in error_message
        assert "dynamodb" in error_message
        assert "http" in error_message

    def test_get_retry_policy_empty_string(self):
        """Test error handling for empty string"""
        with pytest.raises(ValueError) as exc_info:
            get_retry_policy_for_activity("")

        assert "Unknown activity type:" in str(exc_info.value)

    def test_get_retry_policy_none(self):
        """Test error handling for None activity type"""
        with pytest.raises(ValueError):
            get_retry_policy_for_activity(None)

    def test_get_retry_policy_whitespace(self):
        """Test error handling for whitespace activity type"""
        with pytest.raises(ValueError):
            get_retry_policy_for_activity(" file ")

        with pytest.raises(ValueError):
            get_retry_policy_for_activity("  ")

    def test_supported_activity_types_completeness(self):
        """Test that all documented activity types are supported"""
        supported_types = ["file", "processing", "dynamodb", "http"]

        for activity_type in supported_types:
            # Should not raise exception
            policy = get_retry_policy_for_activity(activity_type)
            assert isinstance(policy, RetryPolicy)

    def test_retry_policy_function_returns_same_instance(self):
        """Test that function returns the same policy instance for same type"""
        policy1 = get_retry_policy_for_activity("file")
        policy2 = get_retry_policy_for_activity("file")

        assert policy1 is policy2
        assert policy1 is FILE_RETRY_POLICY

    def test_all_retry_policies_have_required_attributes(self):
        """Test that all retry policies have required RetryPolicy attributes"""
        activity_types = ["file", "processing", "dynamodb", "http"]

        for activity_type in activity_types:
            policy = get_retry_policy_for_activity(activity_type)

            # Check required attributes exist
            assert hasattr(policy, "initial_interval")
            assert hasattr(policy, "maximum_interval")
            assert hasattr(policy, "maximum_attempts")
            assert hasattr(policy, "backoff_coefficient")

            # Check types are correct
            assert isinstance(policy.initial_interval, timedelta)
            assert isinstance(policy.maximum_interval, timedelta)
            assert isinstance(policy.maximum_attempts, int)
            assert isinstance(policy.backoff_coefficient, (int, float))

            # Check values are positive
            assert policy.initial_interval.total_seconds() > 0
            assert policy.maximum_interval.total_seconds() > 0
            assert policy.maximum_attempts > 0
            assert policy.backoff_coefficient > 0

    def test_retry_policy_maximum_interval_greater_than_initial(self):
        """Test that maximum_interval >= initial_interval for all policies"""
        activity_types = ["file", "processing", "dynamodb", "http"]

        for activity_type in activity_types:
            policy = get_retry_policy_for_activity(activity_type)
            assert policy.maximum_interval >= policy.initial_interval

    def test_retry_policy_backoff_coefficient_reasonable(self):
        """Test that backoff coefficient is reasonable (typically 1.0 to 5.0)"""
        activity_types = ["file", "processing", "dynamodb", "http"]

        for activity_type in activity_types:
            policy = get_retry_policy_for_activity(activity_type)
            # Backoff coefficient should be >= 1.0 and reasonable upper bound
            assert 1.0 <= policy.backoff_coefficient <= 5.0
