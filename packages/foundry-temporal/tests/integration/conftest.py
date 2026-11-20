# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Put tests/integration on sys.path so the workflow sandbox can import test workflows by name."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
