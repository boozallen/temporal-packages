# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
import os
import tempfile
from pathlib import Path

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
    path = os.path.join(tmp_dir, "sample.txt")
    with open(path, "w") as f:
        f.write("hello world")
    return path


@pytest.fixture
def empty_file(tmp_dir):
    path = os.path.join(tmp_dir, "empty.txt")
    Path(path).touch()
    return path


@pytest.fixture
def tmp_db(tmp_dir):
    return os.path.join(tmp_dir, "test_provenance.db")
