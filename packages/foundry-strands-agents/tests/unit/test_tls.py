# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for TLS context factory."""

import ssl
from unittest.mock import patch

import pytest
from foundry_strands_agents.tls import create_agent_tls_context


class TestCreateAgentTlsContext:
    def test_unset_mode_defaults_to_platform(self):
        """Unset FOUNDRY_TLS_MODE defaults to platform (returns None)."""
        with patch.dict("os.environ", {}, clear=True):
            assert create_agent_tls_context() is None

    @pytest.mark.parametrize("mode", ["off", "OFF", " off "])
    def test_off_mode_is_platform_alias(self, mode):
        """'off' is an alias for platform (returns None)."""
        with patch.dict("os.environ", {"FOUNDRY_TLS_MODE": mode}, clear=True):
            assert create_agent_tls_context() is None

    def test_invalid_mode_raises(self):
        """Invalid mode value raises ValueError."""
        with patch.dict("os.environ", {"FOUNDRY_TLS_MODE": "bogus"}, clear=True):
            with pytest.raises(ValueError, match="Invalid FOUNDRY_TLS_MODE"):
                create_agent_tls_context()

    def test_tls_mode_returns_context(self):
        """Mode 'tls' returns an SSLContext with TLS 1.2 minimum."""
        with patch.dict("os.environ", {"FOUNDRY_TLS_MODE": "tls"}, clear=True):
            ctx = create_agent_tls_context()
            assert isinstance(ctx, ssl.SSLContext)
            assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_tls_mode_with_ca(self, tmp_path):
        """Mode 'tls' loads custom CA when provided."""
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text("FAKE")

        with (
            patch.dict(
                "os.environ",
                {"FOUNDRY_TLS_MODE": "tls", "FOUNDRY_TLS_CA_CERTFILE": str(ca_file)},
                clear=True,
            ),
            patch("ssl.SSLContext.load_verify_locations") as mock_load,
        ):
            ctx = create_agent_tls_context()
            assert isinstance(ctx, ssl.SSLContext)
            mock_load.assert_any_call(str(ca_file))

    def test_mtls_mode_with_cert_and_key(self, tmp_path):
        """Mode 'mtls' loads client cert chain."""
        cert_file = tmp_path / "client.pem"
        key_file = tmp_path / "client.key"
        cert_file.write_bytes(b"CERT")
        key_file.write_bytes(b"KEY")

        with (
            patch.dict(
                "os.environ",
                {
                    "FOUNDRY_TLS_MODE": "mtls",
                    "FOUNDRY_TLS_CLIENT_CERTFILE": str(cert_file),
                    "FOUNDRY_TLS_CLIENT_KEYFILE": str(key_file),
                },
                clear=True,
            ),
            patch("ssl.SSLContext.load_cert_chain") as mock_load,
        ):
            ctx = create_agent_tls_context()
            assert isinstance(ctx, ssl.SSLContext)
            mock_load.assert_called_once_with(certfile=str(cert_file), keyfile=str(key_file))

    def test_mtls_mode_missing_key_raises(self):
        """Mode 'mtls' without key raises ValueError."""
        with patch.dict(
            "os.environ",
            {
                "FOUNDRY_TLS_MODE": "mtls",
                "FOUNDRY_TLS_CLIENT_CERTFILE": "/path/to/cert.pem",
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="FOUNDRY_TLS_CLIENT_KEYFILE"):
                create_agent_tls_context()

    def test_mtls_mode_missing_cert_raises(self):
        """Mode 'mtls' without cert raises ValueError."""
        with patch.dict(
            "os.environ",
            {
                "FOUNDRY_TLS_MODE": "mtls",
                "FOUNDRY_TLS_CLIENT_KEYFILE": "/path/to/key.pem",
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="FOUNDRY_TLS_CLIENT_CERTFILE"):
                create_agent_tls_context()
