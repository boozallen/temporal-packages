# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_strands_agents.discovery module"""

from unittest.mock import AsyncMock, patch

import pytest
from foundry_strands_agents.discovery import AgentCapabilityChecker, AgentRegistry
from foundry_strands_agents.exceptions import AgentCapabilityError, AgentNotFoundError


class TestAgentCapabilityChecker:
    @pytest.fixture
    def checker(self):
        """Create a test capability checker"""
        return AgentCapabilityChecker("http://test-agent.com")

    @pytest.fixture
    def mock_capabilities(self):
        """Mock agent capabilities"""
        return {
            "name": "test-agent",
            "description": "A test agent",
            "version": "1.0.0",
            "capabilities": ["text_processing", "data_analysis"],
            "tools": ["file_reader", "web_search"],
            "features": ["streaming", "async_processing"],
        }

    @pytest.mark.asyncio
    async def test_init(self, checker):
        """Test capability checker initialization"""
        assert checker.agent_url == "http://test-agent.com"
        assert checker._capabilities_cache is None

    @pytest.mark.asyncio
    async def test_get_capabilities_first_call(self, checker, mock_capabilities):
        """Test get_capabilities fetches from agent on first call"""
        with patch("foundry_strands_agents.discovery.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.discover_capabilities.return_value = mock_capabilities
            mock_client_class.return_value.__aenter__.return_value = mock_client

            capabilities = await checker.get_capabilities()

            assert capabilities == mock_capabilities
            assert checker._capabilities_cache == mock_capabilities
            mock_client.discover_capabilities.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_capabilities_cached(self, checker, mock_capabilities):
        """Test get_capabilities uses cache on subsequent calls"""
        checker._capabilities_cache = mock_capabilities

        with patch("foundry_strands_agents.discovery.StrandsAgentClient") as mock_client_class:
            capabilities = await checker.get_capabilities()

            assert capabilities == mock_capabilities
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_capabilities_force_refresh(self, checker, mock_capabilities):
        """Test get_capabilities with force refresh"""
        checker._capabilities_cache = {"old": "data"}

        with patch("foundry_strands_agents.discovery.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.discover_capabilities.return_value = mock_capabilities
            mock_client_class.return_value.__aenter__.return_value = mock_client

            capabilities = await checker.get_capabilities(force_refresh=True)

            assert capabilities == mock_capabilities
            assert checker._capabilities_cache == mock_capabilities
            mock_client.discover_capabilities.assert_called_once()

    @pytest.mark.asyncio
    async def test_supports_capability_in_capabilities(self, checker, mock_capabilities):
        """Test supports_capability when capability is in capabilities list"""
        checker._capabilities_cache = mock_capabilities

        supports = await checker.supports_capability("text_processing")
        assert supports is True

    @pytest.mark.asyncio
    async def test_supports_capability_in_tools(self, checker, mock_capabilities):
        """Test supports_capability when capability is in tools list"""
        checker._capabilities_cache = mock_capabilities

        supports = await checker.supports_capability("web_search")
        assert supports is True

    @pytest.mark.asyncio
    async def test_supports_capability_in_features(self, checker, mock_capabilities):
        """Test supports_capability when capability is in features list"""
        checker._capabilities_cache = mock_capabilities

        supports = await checker.supports_capability("streaming")
        assert supports is True

    @pytest.mark.asyncio
    async def test_supports_capability_not_found(self, checker, mock_capabilities):
        """Test supports_capability when capability is not found"""
        checker._capabilities_cache = mock_capabilities

        supports = await checker.supports_capability("nonexistent_capability")
        assert supports is False

    @pytest.mark.asyncio
    async def test_supports_capability_exception_handling(self, checker):
        """Test supports_capability handles exceptions gracefully"""
        with patch.object(checker, "get_capabilities", side_effect=Exception("Network error")):
            supports = await checker.supports_capability("any_capability")
            assert supports is False

    @pytest.mark.asyncio
    async def test_requires_capability_success(self, checker, mock_capabilities):
        """Test requires_capability when capability is supported"""
        checker._capabilities_cache = mock_capabilities

        # Should not raise exception
        await checker.requires_capability("text_processing")

    @pytest.mark.asyncio
    async def test_requires_capability_failure(self, checker, mock_capabilities):
        """Test requires_capability when capability is not supported"""
        checker._capabilities_cache = mock_capabilities

        with pytest.raises(AgentCapabilityError) as exc_info:
            await checker.requires_capability("nonexistent_capability")

        error = exc_info.value
        assert error.agent_name == "test-agent"
        assert error.capability == "nonexistent_capability"
        assert "text_processing" in error.available_capabilities
        assert "web_search" in error.available_capabilities
        assert "streaming" in error.available_capabilities

    @pytest.mark.asyncio
    async def test_get_agent_info_basic(self, checker, mock_capabilities):
        """Test get_agent_info with complete capabilities"""
        checker._capabilities_cache = mock_capabilities

        info = await checker.get_agent_info()

        assert info["name"] == "test-agent"
        assert info["description"] == "A test agent"
        assert info["version"] == "1.0.0"
        assert info["url"] == "http://test-agent.com"

    @pytest.mark.asyncio
    async def test_get_agent_info_missing_fields(self, checker):
        """Test get_agent_info with missing capability fields"""
        incomplete_capabilities = {"some_field": "value"}
        checker._capabilities_cache = incomplete_capabilities

        info = await checker.get_agent_info()

        assert info["name"] == "Unknown Agent"
        assert info["description"] == "No description"
        assert info["version"] == "unknown"
        assert info["url"] == "http://test-agent.com"


class TestAgentRegistry:
    @pytest.fixture
    def registry(self):
        """Create a test agent registry"""
        return AgentRegistry()

    def test_init(self, registry):
        """Test registry initialization"""
        assert len(registry._agents) == 0
        assert len(registry._capability_checkers) == 0

    def test_register_agent(self, registry):
        """Test registering an agent"""
        registry.register_agent("test-agent", "http://test-agent.com")

        assert "test-agent" in registry._agents
        assert registry._agents["test-agent"] == "http://test-agent.com"
        assert "test-agent" in registry._capability_checkers
        assert isinstance(registry._capability_checkers["test-agent"], AgentCapabilityChecker)

    def test_get_agent_url_success(self, registry):
        """Test getting agent URL for registered agent"""
        registry.register_agent("test-agent", "http://test-agent.com")

        url = registry.get_agent_url("test-agent")
        assert url == "http://test-agent.com"

    def test_get_agent_url_not_found(self, registry):
        """Test getting agent URL for non-existent agent"""
        with pytest.raises(AgentNotFoundError) as exc_info:
            registry.get_agent_url("nonexistent-agent")

        assert "registry://nonexistent-agent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_find_agents_with_capability(self, registry):
        """Test finding agents with specific capability"""
        # Register test agents
        registry.register_agent("agent1", "http://agent1.com")
        registry.register_agent("agent2", "http://agent2.com")

        # Mock capability checkers
        mock_checker1 = AsyncMock()
        mock_checker1.supports_capability.return_value = True
        registry._capability_checkers["agent1"] = mock_checker1

        mock_checker2 = AsyncMock()
        mock_checker2.supports_capability.return_value = False
        registry._capability_checkers["agent2"] = mock_checker2

        matching_agents = await registry.find_agents_with_capability("text_processing")

        assert matching_agents == ["agent1"]
        mock_checker1.supports_capability.assert_called_once_with("text_processing")
        mock_checker2.supports_capability.assert_called_once_with("text_processing")

    @pytest.mark.asyncio
    async def test_find_agents_with_capability_exception_handling(self, registry):
        """Test find_agents_with_capability handles exceptions gracefully"""
        registry.register_agent("agent1", "http://agent1.com")

        # Mock capability checker that raises exception
        mock_checker = AsyncMock()
        mock_checker.supports_capability.side_effect = Exception("Network error")
        registry._capability_checkers["agent1"] = mock_checker

        matching_agents = await registry.find_agents_with_capability("text_processing")

        assert matching_agents == []  # Should return empty list, not crash

    @pytest.mark.asyncio
    async def test_get_agent_capabilities_success(self, registry):
        """Test getting capabilities for registered agent"""
        registry.register_agent("test-agent", "http://test-agent.com")

        mock_capabilities = {"name": "test-agent", "capabilities": ["text_processing"]}
        mock_checker = AsyncMock()
        mock_checker.get_capabilities.return_value = mock_capabilities
        registry._capability_checkers["test-agent"] = mock_checker

        capabilities = await registry.get_agent_capabilities("test-agent")

        assert capabilities == mock_capabilities
        mock_checker.get_capabilities.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_agent_capabilities_not_found(self, registry):
        """Test getting capabilities for non-existent agent"""
        with pytest.raises(AgentNotFoundError) as exc_info:
            await registry.get_agent_capabilities("nonexistent-agent")

        assert "registry://nonexistent-agent" in str(exc_info.value)

    def test_list_agents_empty(self, registry):
        """Test listing agents when registry is empty"""
        agents = registry.list_agents()
        assert agents == {}

    def test_list_agents_with_agents(self, registry):
        """Test listing agents when registry has agents"""
        registry.register_agent("agent1", "http://agent1.com")
        registry.register_agent("agent2", "http://agent2.com")

        agents = registry.list_agents()

        expected = {"agent1": "http://agent1.com", "agent2": "http://agent2.com"}
        assert agents == expected

    def test_list_agents_returns_copy(self, registry):
        """Test that list_agents returns a copy, not the original dict"""
        registry.register_agent("agent1", "http://agent1.com")

        agents = registry.list_agents()
        agents["malicious"] = "http://evil.com"

        # Original registry should not be modified
        assert "malicious" not in registry._agents


class TestGlobalAgentRegistry:
    def test_global_registry_exists(self):
        """Test that global agent registry is available"""
        from foundry_strands_agents.discovery import agent_registry

        assert isinstance(agent_registry, AgentRegistry)

    def test_global_registry_singleton_behavior(self):
        """Test that importing agent_registry gives the same instance"""
        from foundry_strands_agents.discovery import agent_registry as registry1
        from foundry_strands_agents.discovery import agent_registry as registry2

        assert registry1 is registry2
