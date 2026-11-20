# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from temporalio.testing import ActivityEnvironment


@pytest.fixture
def activity_environment():
    return ActivityEnvironment()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_file(tmp_dir):
    path = os.path.join(tmp_dir, "document.pdf")
    with open(path, "wb") as f:
        f.write(b"fake pdf content")
    return path


@pytest.fixture
def mock_s3_client():
    client = MagicMock()
    client.put_object = MagicMock(return_value={})
    return client


@pytest.fixture
def mock_bedrock_client():
    return MagicMock()
