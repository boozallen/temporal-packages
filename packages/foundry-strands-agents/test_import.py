#!/usr/bin/env python3
# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
import os
import sys

# Add src to path
src_path = os.path.join(os.path.dirname(__file__), "src")
sys.path.insert(0, src_path)

try:
    import foundry_strands_agents

    print("✅ foundry_strands_agents imported successfully")

    from foundry_strands_agents.protocols import A2AMessageBuilder

    print("✅ protocols module imported successfully")

    from foundry_strands_agents.exceptions import StrandsAgentError

    print("✅ exceptions module imported successfully")

    print("🎉 All imports working!")

except ImportError as e:
    print(f"❌ Import error: {e}")

    # Debug information
    print(f"Python path: {sys.path}")
    print(f"Source path: {src_path}")
    print("Directory contents:")

    try:
        import os

        for item in os.listdir(src_path):
            print(f"  - {item}")
            if os.path.isdir(os.path.join(src_path, item)):
                subdir = os.path.join(src_path, item)
                print(f"    Contents of {item}:")
                for subitem in os.listdir(subdir):
                    print(f"      - {subitem}")
    except Exception as debug_e:
        print(f"Error getting debug info: {debug_e}")
