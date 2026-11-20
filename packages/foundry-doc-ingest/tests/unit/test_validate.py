# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
import os

from foundry_doc_ingest.validate import DEFAULT_SUPPORTED_EXTENSIONS, validate_file


def test_valid_file(activity_environment, sample_file):
    result = activity_environment.run(validate_file, sample_file)
    assert result.valid is True
    assert result.file_path == sample_file
    assert result.error is None


def test_missing_file(activity_environment):
    result = activity_environment.run(validate_file, "/nonexistent/path/file.txt")
    assert result.valid is False
    assert result.error == "File not found"


def test_empty_file(activity_environment, empty_file):
    result = activity_environment.run(validate_file, empty_file)
    assert result.valid is False
    assert result.error == "File is empty"


def test_unsupported_extension(activity_environment, tmp_dir):
    path = os.path.join(tmp_dir, "file.xyz")
    with open(path, "w") as f:
        f.write("data")
    result = activity_environment.run(validate_file, path)
    assert result.valid is False
    assert "Unsupported extension" in result.error


def test_custom_extensions(activity_environment, tmp_dir):
    path = os.path.join(tmp_dir, "file.csv")
    with open(path, "w") as f:
        f.write("a,b,c")
    result = activity_environment.run(validate_file, path, supported_extensions=[".csv"])
    assert result.valid is True


def test_default_extensions():
    assert ".pdf" in DEFAULT_SUPPORTED_EXTENSIONS
    assert ".txt" in DEFAULT_SUPPORTED_EXTENSIONS
    assert ".docx" in DEFAULT_SUPPORTED_EXTENSIONS
    assert ".md" in DEFAULT_SUPPORTED_EXTENSIONS
    assert ".json" in DEFAULT_SUPPORTED_EXTENSIONS
