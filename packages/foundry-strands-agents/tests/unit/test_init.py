# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_strands_agents package initialization and imports"""


class TestPackageImports:
    def test_a2a_imports(self):
        """Test that A2A package imports work correctly"""
        from foundry_strands_agents import (
            StrandsAgentClient,
            call_strands_agent,
            call_strands_agent_dataclass,
            strands_agent_activity,
            strands_agent_dataclass_activity,
        )

        # Verify imports are not None
        assert StrandsAgentClient is not None
        assert strands_agent_activity is not None
        assert strands_agent_dataclass_activity is not None
        assert call_strands_agent is not None
        assert call_strands_agent_dataclass is not None

    def test_query_imports(self):
        """Test that Query API imports work correctly"""
        from foundry_strands_agents import (
            StrandsQueryClient,
            call_strands_query,
            call_strands_query_dataclass,
            strands_query_activity,
            strands_query_dataclass_activity,
        )

        # Verify imports are not None
        assert StrandsQueryClient is not None
        assert strands_query_activity is not None
        assert strands_query_dataclass_activity is not None
        assert call_strands_query is not None
        assert call_strands_query_dataclass is not None

    def test_model_imports(self):
        """Test that model imports work correctly"""
        from foundry_strands_agents import (
            StrandsAgentTaskInput,
            StrandsQueryTaskInput,
        )

        # Verify imports are not None
        assert StrandsAgentTaskInput is not None
        assert StrandsQueryTaskInput is not None

    def test_exception_imports(self):
        """Test that exception imports work correctly"""
        from foundry_strands_agents import (
            A2AProtocolError,
            AgentCapabilityError,
            AgentNotFoundError,
            AgentTimeoutError,
            QueryProcessingError,
            StrandsAgentError,
        )

        # Verify exceptions are Exception subclasses
        assert issubclass(StrandsAgentError, Exception)
        assert issubclass(AgentNotFoundError, StrandsAgentError)
        assert issubclass(AgentTimeoutError, StrandsAgentError)
        assert issubclass(A2AProtocolError, StrandsAgentError)
        assert issubclass(AgentCapabilityError, StrandsAgentError)
        assert issubclass(QueryProcessingError, StrandsAgentError)

    def test_discovery_imports(self):
        """Test that discovery imports work correctly"""
        from foundry_strands_agents import (
            AgentCapabilityChecker,
            AgentRegistry,
            agent_registry,
        )

        # Verify imports are not None
        assert AgentCapabilityChecker is not None
        assert AgentRegistry is not None
        assert agent_registry is not None

    def test_protocol_imports(self):
        """Test that protocol imports work correctly"""
        from foundry_strands_agents import (
            A2AMessageBuilder,
            extract_agent_response,
            validate_a2a_response,
        )

        # Verify imports are not None
        assert A2AMessageBuilder is not None
        assert extract_agent_response is not None
        assert validate_a2a_response is not None

    def test_all_exports(self):
        """Test __all__ exports are available"""
        import foundry_strands_agents

        expected_exports = [
            # A2A activities
            "call_strands_agent",
            "call_strands_agent_dataclass",
            # Query activities
            "call_strands_query",
            "call_strands_query_dataclass",
            # Decorators
            "strands_agent_activity",
            "strands_agent_dataclass_activity",
            "strands_query_activity",
            "strands_query_dataclass_activity",
            # Clients
            "StrandsAgentClient",
            "StrandsQueryClient",
            # Models
            "StrandsAgentTaskInput",
            "StrandsQueryTaskInput",
            # Discovery
            "AgentCapabilityChecker",
            "AgentRegistry",
            "agent_registry",
            # Exceptions
            "StrandsAgentError",
            "AgentNotFoundError",
            "AgentTimeoutError",
            "A2AProtocolError",
            "AgentCapabilityError",
            "QueryProcessingError",
            # Protocols
            "A2AMessageBuilder",
            "extract_agent_response",
            "validate_a2a_response",
        ]

        for export in expected_exports:
            assert hasattr(foundry_strands_agents, export), f"Missing export: {export}"

    def test_version_attribute(self):
        """Test package version matches installed package metadata"""
        from importlib.metadata import version

        import foundry_strands_agents

        assert hasattr(foundry_strands_agents, "__version__")
        assert isinstance(foundry_strands_agents.__version__, str)
        assert foundry_strands_agents.__version__ == version("foundry-strands-agents")

    def test_package_docstring(self):
        """Test package has proper docstring"""
        import foundry_strands_agents

        assert foundry_strands_agents.__doc__ is not None
        assert "Temporal integration for Strands agents" in foundry_strands_agents.__doc__
        assert "A2A" in foundry_strands_agents.__doc__
        assert "Query REST API" in foundry_strands_agents.__doc__

    def test_direct_module_imports(self):
        """Test that modules can be imported directly"""
        # These should not raise ImportError
        from foundry_strands_agents import (
            activities,
            client,
            discovery,
            exceptions,
            protocols,
            query_activities,
            query_client,
            query_models,
        )

        # Verify A2A modules have expected attributes
        assert hasattr(client, "StrandsAgentClient")
        assert hasattr(activities, "strands_agent_activity")
        assert hasattr(activities, "call_strands_agent")
        assert hasattr(activities, "call_strands_agent_dataclass")

        # Verify Query modules have expected attributes
        assert hasattr(query_client, "StrandsQueryClient")
        assert hasattr(query_activities, "strands_query_activity")
        assert hasattr(query_activities, "call_strands_query")
        assert hasattr(query_activities, "call_strands_query_dataclass")
        assert hasattr(query_models, "StrandsQueryTaskInput")

        # Verify common modules have expected attributes
        assert hasattr(exceptions, "StrandsAgentError")
        assert hasattr(exceptions, "QueryProcessingError")
        assert hasattr(protocols, "A2AMessageBuilder")
        assert hasattr(discovery, "AgentCapabilityChecker")
        assert hasattr(discovery, "AgentRegistry")

    def test_star_import_availability(self):
        """Test that all expected items are available for star import"""
        import foundry_strands_agents

        # Get items that would be imported with import *
        if hasattr(foundry_strands_agents, "__all__"):
            all_items = foundry_strands_agents.__all__
        else:
            # If no __all__, get public items (not starting with _)
            all_items = [name for name in dir(foundry_strands_agents) if not name.startswith("_")]

        expected_items = [
            # A2A activities
            "call_strands_agent",
            "call_strands_agent_dataclass",
            # Query activities
            "call_strands_query",
            "call_strands_query_dataclass",
            # Decorators
            "strands_agent_activity",
            "strands_agent_dataclass_activity",
            "strands_query_activity",
            "strands_query_dataclass_activity",
            # Clients
            "StrandsAgentClient",
            "StrandsQueryClient",
            # Models
            "StrandsAgentTaskInput",
            "StrandsQueryTaskInput",
            # Discovery
            "AgentCapabilityChecker",
            "AgentRegistry",
            "agent_registry",
            # Exceptions
            "StrandsAgentError",
            "AgentNotFoundError",
            "AgentTimeoutError",
            "A2AProtocolError",
            "AgentCapabilityError",
            "QueryProcessingError",
            # Protocols
            "A2AMessageBuilder",
            "extract_agent_response",
            "validate_a2a_response",
        ]

        # Verify all expected items are available in the module
        for item in expected_items:
            assert hasattr(foundry_strands_agents, item), f"Missing item for star import: {item}"

        # If __all__ exists, verify expected items are in __all__
        if hasattr(foundry_strands_agents, "__all__"):
            for item in expected_items:
                assert item in all_items, f"Item {item} not in __all__"

    def test_interface_separation(self):
        """Test that A2A and Query interfaces are properly separated"""
        from foundry_strands_agents import (
            StrandsAgentClient,
            StrandsQueryClient,
            call_strands_agent,
            call_strands_query,
        )

        # Verify they are different classes/functions
        assert StrandsAgentClient != StrandsQueryClient
        assert call_strands_agent != call_strands_query

        # Verify they are both callable
        assert callable(call_strands_agent)
        assert callable(call_strands_query)

    def test_dataclass_models_available(self):
        """Test that both input dataclass models are available"""
        from foundry_strands_agents import (
            StrandsAgentTaskInput,
            StrandsQueryTaskInput,
        )

        # Test basic instantiation
        a2a_input = StrandsAgentTaskInput(task="Test task", query_extra_data={"key": "value"})
        assert a2a_input.task == "Test task"

        query_input = StrandsQueryTaskInput(query="Test query", context={"key": "value"})
        assert query_input.query == "Test query"

    def test_decorator_functions_available(self):
        """Test that decorator functions are properly exported"""
        from foundry_strands_agents import (
            strands_agent_activity,
            strands_agent_dataclass_activity,
            strands_query_activity,
            strands_query_dataclass_activity,
        )

        # All decorators should be callable
        assert callable(strands_agent_activity)
        assert callable(strands_agent_dataclass_activity)
        assert callable(strands_query_activity)
        assert callable(strands_query_dataclass_activity)

    def test_comprehensive_import_from_root(self):
        """Test that all functionality can be imported from the root package"""
        # This should not raise any ImportError
        from foundry_strands_agents import (
            # Protocols
            QueryProcessingError,
            # A2A functionality
            StrandsAgentClient,
            # Exceptions
            StrandsAgentError,
            StrandsAgentTaskInput,
            # Query functionality
            StrandsQueryClient,
            StrandsQueryTaskInput,
            call_strands_agent,
            call_strands_query,
        )

        # Basic verification that imports succeeded
        assert StrandsAgentClient is not None
        assert StrandsQueryClient is not None
        assert call_strands_agent is not None
        assert call_strands_query is not None
        assert StrandsAgentTaskInput is not None
        assert StrandsQueryTaskInput is not None
        assert StrandsAgentError is not None
        assert QueryProcessingError is not None
