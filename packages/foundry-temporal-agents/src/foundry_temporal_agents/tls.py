# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""TLS context factory for Strands agent client connections."""

import os
import ssl


def create_agent_tls_context() -> ssl.SSLContext | None:
    """Build an SSL context based on FOUNDRY_TLS_MODE and related env vars.

    Modes:
        platform (default) — return None (TLS terminated by platform/mesh)
        off  — alias for platform
        tls  — server verification with optional custom CA and client cert
        mtls — require client cert + key with optional custom CA

    Defaults to 'platform' when FOUNDRY_TLS_MODE is unset.
    """
    mode = (os.getenv("FOUNDRY_TLS_MODE") or "platform").strip().lower()

    if mode in ("platform", "off"):
        return None

    if mode not in ("tls", "mtls"):
        raise ValueError(f"Invalid FOUNDRY_TLS_MODE '{mode}'. Expected 'platform', 'off', 'tls', or 'mtls'.")

    cert_file = os.getenv("FOUNDRY_TLS_CLIENT_CERTFILE")
    key_file = os.getenv("FOUNDRY_TLS_CLIENT_KEYFILE")
    ca_file = os.getenv("FOUNDRY_TLS_CA_CERTFILE")

    if mode == "mtls":
        if not cert_file or not key_file:
            raise ValueError(
                "FOUNDRY_TLS_MODE=mtls requires both FOUNDRY_TLS_CLIENT_CERTFILE and FOUNDRY_TLS_CLIENT_KEYFILE."
            )

    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    try:
        if ca_file:
            ctx.load_verify_locations(ca_file)

        if cert_file and key_file:
            ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
    except (FileNotFoundError, ssl.SSLError) as exc:
        raise ValueError(f"TLS file load failed: {exc}") from exc

    return ctx
