# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Agent discovery and capability checking helpers
"""

import logging
from typing import Any

from .client import StrandsAgentClient
from .exceptions import AgentCapabilityError, AgentNotFoundError

logger = logging.getLogger(__name__)


class AgentCapabilityChecker:
    """Helper for checking agent capabilities"""

    def __init__(self, agent_url: str):
        self.agent_url = agent_url
        self._capabilities_cache: dict[str, Any] | None = None

    async def get_capabilities(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        Get agent capabilities (cached)

        Args:
            force_refresh: Force refresh of cached capabilities

        Returns:
            Agent capability information
        """
        if self._capabilities_cache is None or force_refresh:
            async with StrandsAgentClient(self.agent_url) as client:
                self._capabilities_cache = await client.discover_capabilities()

        return self._capabilities_cache

    async def supports_capability(self, capability: str) -> bool:
        """
        Check if agent supports a specific capability

        Args:
            capability: Capability name to check

        Returns:
            True if agent supports the capability
        """
        try:
            capabilities = await self.get_capabilities()

            # Check in various capability fields
            supported_capabilities = (
                capabilities.get("capabilities", []) + capabilities.get("tools", []) + capabilities.get("features", [])
            )

            return capability in supported_capabilities

        except Exception as e:
            logger.warning(f"Failed to check capability '{capability}': {e}")
            return False

    async def requires_capability(self, capability: str) -> None:
        """
        Assert that agent supports a required capability

        Args:
            capability: Required capability name

        Raises:
            AgentCapabilityError: If agent doesn't support the capability
        """
        if not await self.supports_capability(capability):
            capabilities = await self.get_capabilities()
            agent_name = capabilities.get("name", "unknown")

            # Get available capabilities for better error message
            available_capabilities = (
                capabilities.get("capabilities", []) + capabilities.get("tools", []) + capabilities.get("features", [])
            )

            raise AgentCapabilityError(agent_name, capability, available_capabilities)

    async def get_agent_info(self) -> dict[str, str]:
        """
        Get basic agent information

        Returns:
            Dictionary with agent name, description, version
        """
        capabilities = await self.get_capabilities()

        return {
            "name": capabilities.get("name", "Unknown Agent"),
            "description": capabilities.get("description", "No description"),
            "version": capabilities.get("version", "unknown"),
            "url": self.agent_url,
        }


class AgentRegistry:
    """Registry for managing multiple agents"""

    def __init__(self):
        self._agents: dict[str, str] = {}  # name -> url mapping
        self._capability_checkers: dict[str, AgentCapabilityChecker] = {}

    def register_agent(self, name: str, url: str) -> None:
        """
        Register an agent in the registry

        Args:
            name: Agent name
            url: Agent URL
        """
        self._agents[name] = url
        self._capability_checkers[name] = AgentCapabilityChecker(url)
        logger.info(f"Registered agent '{name}' at {url}")

    def get_agent_url(self, name: str) -> str:
        """
        Get agent URL by name

        Args:
            name: Agent name

        Returns:
            Agent URL

        Raises:
            AgentNotFoundError: If agent not found in registry
        """
        if name not in self._agents:
            raise AgentNotFoundError(f"registry://{name}")
        return self._agents[name]

    async def find_agents_with_capability(self, capability: str) -> list[str]:
        """
        Find all agents that support a specific capability

        Args:
            capability: Capability to search for

        Returns:
            List of agent names that support the capability
        """
        matching_agents = []

        for name, checker in self._capability_checkers.items():
            try:
                if await checker.supports_capability(capability):
                    matching_agents.append(name)
            except Exception as e:
                logger.warning(f"Failed to check capability for agent '{name}': {e}")

        return matching_agents

    async def get_agent_capabilities(self, name: str) -> dict[str, Any]:
        """
        Get capabilities for a specific agent

        Args:
            name: Agent name

        Returns:
            Agent capabilities
        """
        if name not in self._capability_checkers:
            raise AgentNotFoundError(f"registry://{name}")

        return await self._capability_checkers[name].get_capabilities()

    def list_agents(self) -> dict[str, str]:
        """
        List all registered agents

        Returns:
            Dictionary mapping agent names to URLs
        """
        return self._agents.copy()


# Global agent registry instance
agent_registry = AgentRegistry()
