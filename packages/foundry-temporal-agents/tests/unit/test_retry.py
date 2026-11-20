# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal_agents.retry module"""

import pytest
from foundry_temporal_agents.exceptions import AgentNotFoundError, AgentRequestError
from foundry_temporal_agents.retry import is_non_retryable_http_status, is_retryable_strands_error


class TestIsNonRetryableHttpStatus:
    @pytest.mark.parametrize("status", [400, 404, 422, 499])
    def test_4xx_is_non_retryable(self, status):
        assert is_non_retryable_http_status(status) is True

    @pytest.mark.parametrize("status", [408, 429])
    def test_transient_4xx_is_retryable(self, status):
        assert is_non_retryable_http_status(status) is False

    @pytest.mark.parametrize("status", [500, 502, 503, 599])
    def test_5xx_is_retryable(self, status):
        assert is_non_retryable_http_status(status) is False


class TestIsRetryableStrandsError:
    def test_agent_not_found_404_is_not_retryable(self):
        assert is_retryable_strands_error(AgentNotFoundError("http://agent.example.com", status=404)) is False

    @pytest.mark.parametrize("status", [None, 408, 429, 503])
    def test_agent_not_found_without_404_is_retryable(self, status):
        assert is_retryable_strands_error(AgentNotFoundError("http://agent.example.com", status=status)) is True

    @pytest.mark.parametrize("status", [400, 422])
    def test_agent_request_error_is_not_retryable(self, status):
        assert is_retryable_strands_error(AgentRequestError("http://agent.example.com", status)) is False
