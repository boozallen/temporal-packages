# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and configuration for foundry_temporal tests"""

import os

import pytest

TEST_ENCRYPTION_KEY_HEX = os.urandom(32).hex()


@pytest.fixture(autouse=True)
def isolate_tests():
    """Automatically isolate tests to prevent side effects"""
    # This fixture runs automatically for all tests
    # Add any cleanup or isolation logic here
    yield
    # Cleanup after each test if needed


@pytest.fixture(autouse=True)
def _temporal_encryption_key_env(monkeypatch):
    """Ensure FOUNDRY_TEMPORAL_ENCRYPTION_KEY is set for storage tests."""
    monkeypatch.setenv("FOUNDRY_TEMPORAL_ENCRYPTION_KEY", TEST_ENCRYPTION_KEY_HEX)


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically

    The unit/integration tier is decided by directory (tests/unit vs
    tests/integration), not by a marker, so nothing is auto-marked for it here.
    Only the cross-cutting `slow` trait, which no directory expresses, is
    inferred from the test name.
    """
    for item in items:
        # Mark slow tests based on name patterns
        if any(pattern in item.name for pattern in ["slow", "large", "performance"]):
            item.add_marker(pytest.mark.slow)
