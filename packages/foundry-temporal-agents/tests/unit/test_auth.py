# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared agent auth header helper."""

from foundry_temporal_agents.auth import build_agent_auth_headers


class TestBuildAgentAuthHeaders:
    def test_primary_var_set(self, monkeypatch):
        """Primary variable set -> Authorization header built from it."""
        monkeypatch.setenv("FOUNDRY_AGENT_BEARER_TOKEN", "primary-token")
        monkeypatch.delenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", raising=False)

        headers = build_agent_auth_headers("http://test-agent:8000")

        assert headers == {"Authorization": "Bearer primary-token"}

    def test_only_alias_var_set(self, monkeypatch, caplog):
        """Only the back-compat alias set -> builds the header and warns that the alias is deprecated."""
        monkeypatch.delenv("FOUNDRY_AGENT_BEARER_TOKEN", raising=False)
        monkeypatch.setenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", "alias-token")

        headers = build_agent_auth_headers("http://test-agent:8000")

        assert headers == {"Authorization": "Bearer alias-token"}
        assert "FOUNDRY_AGENT_QUERY_BEARER_TOKEN is deprecated" in caplog.text
        assert "unauthenticated" not in caplog.text

    def test_primary_var_set_does_not_warn(self, monkeypatch, caplog):
        """Primary variable set -> no deprecation or missing-credential warning."""
        monkeypatch.setenv("FOUNDRY_AGENT_BEARER_TOKEN", "primary-token")
        monkeypatch.setenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", "alias-token")

        build_agent_auth_headers("http://test-agent:8000")

        assert caplog.text == ""

    def test_both_set_primary_wins(self, monkeypatch):
        """Both variables set -> the primary variable's value is used."""
        monkeypatch.setenv("FOUNDRY_AGENT_BEARER_TOKEN", "primary-token")
        monkeypatch.setenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", "alias-token")

        headers = build_agent_auth_headers("http://test-agent:8000")

        assert headers == {"Authorization": "Bearer primary-token"}

    def test_neither_set_warns_and_returns_empty(self, monkeypatch, caplog):
        """Neither variable set -> empty headers and a warning, not an error."""
        monkeypatch.delenv("FOUNDRY_AGENT_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", raising=False)

        headers = build_agent_auth_headers("http://test-agent:8000")

        assert headers == {}
        assert "FOUNDRY_AGENT_BEARER_TOKEN" in caplog.text
        assert "FOUNDRY_AGENT_QUERY_BEARER_TOKEN" in caplog.text
        assert "deprecated" not in caplog.text
