# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
import os

import pytest
from foundry_doc_ingest.local import store_file


def test_store_to_default_dir(activity_environment, sample_file):
    stored = activity_environment.run(store_file, sample_file)
    try:
        assert os.path.exists(stored)
        assert stored.startswith(os.path.abspath("/tmp"))
        with open(stored) as f:
            assert f.read() == "hello world"
    finally:
        os.unlink(stored)


def test_store_to_custom_dir(activity_environment, sample_file, tmp_dir):
    target = os.path.join(tmp_dir, "custom_storage")
    stored = activity_environment.run(store_file, sample_file, target_dir=target)
    assert os.path.exists(stored)
    assert target in stored


def test_auto_create_directory(activity_environment, sample_file, tmp_dir):
    target = os.path.join(tmp_dir, "nested", "dir")
    stored = activity_environment.run(store_file, sample_file, target_dir=target)
    assert os.path.isdir(target)
    assert os.path.exists(stored)


def test_missing_source(activity_environment):
    with pytest.raises(FileNotFoundError, match="Source file not found"):
        activity_environment.run(store_file, "/nonexistent/file.txt")


def test_name_collision_avoidance(activity_environment, sample_file, tmp_dir):
    stored1 = activity_environment.run(store_file, sample_file, target_dir=tmp_dir)
    stored2 = activity_environment.run(store_file, sample_file, target_dir=tmp_dir)
    assert stored1 != stored2
    assert os.path.exists(stored1)
    assert os.path.exists(stored2)
