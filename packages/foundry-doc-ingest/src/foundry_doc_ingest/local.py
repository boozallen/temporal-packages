# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import shutil
import uuid

from temporalio import activity


@activity.defn
def store_file(
    source_path: str,
    target_dir: str = "/tmp",
) -> str:
    """Copy a file to a local storage directory, returning the stored path.

    Generates a unique filename to avoid collisions. Creates the target
    directory (including parents) if it does not exist.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")

    os.makedirs(target_dir, exist_ok=True)

    basename = os.path.basename(source_path)
    name, ext = os.path.splitext(basename)
    unique_name = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = os.path.join(target_dir, unique_name)

    shutil.copy2(source_path, dest_path)
    return os.path.abspath(dest_path)
