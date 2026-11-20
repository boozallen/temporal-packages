# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
A2A protocol message builders and handlers
"""

import json
import time
import uuid
from collections.abc import Mapping


class A2AMessageBuilder:
    """Builder for A2A protocol JSON-RPC messages"""

    def __init__(self):
        self._request_id = 0

    def create_request(
        self, message: str, method: str = "message/send", session_id: str | None = None
    ) -> dict[str, object]:
        """
        Create a JSON-RPC 2.0 request for A2A protocol

        Args:
            message: The message content to send to the agent
            method: JSON-RPC method (default: "message/send")
            session_id: Optional session ID for conversation continuity

        Returns:
            JSON-RPC 2.0 request dictionary
        """
        self._request_id += 1
        message_id = f"foundry-{int(time.time())}-{uuid.uuid4().hex[:8]}"

        # Build base request
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {
                "message": {"role": "user", "parts": [{"kind": "text", "text": message}], "messageId": message_id}
            },
            "id": self._request_id,
        }

        # Include session ID if provided for conversation continuity
        if session_id:
            request["params"]["sessionId"] = session_id

        return request

    def create_task_message(
        self,
        task: str,
        query_extra_data: dict[str, object] | None = None,
        **kwargs: object,
    ) -> str:
        """
        Create a clean task message for Strands agents

        Args:
            task: The task description
            query_extra_data: Optional extra data that gets JSON-dumped into message text
            **kwargs: Additional parameters

        Returns:
            Clean message string
        """
        # Start with just the task
        message = task

        # Add extra data and parameters only if they're meaningful
        additional_info = []

        if query_extra_data:
            additional_info.append(f"Extra Data: {json.dumps(query_extra_data)}")

        if kwargs:
            additional_info.append(f"Parameters: {json.dumps(kwargs)}")

        # Only add extra info if it exists
        if additional_info:
            message += "\n\n" + "\n".join(additional_info)

        return message


def validate_a2a_response(response_data: dict[str, object]) -> bool:
    """
    Validate A2A protocol response structure

    Args:
        response_data: Response data to validate

    Returns:
        True if valid A2A response
    """
    if not isinstance(response_data, dict):
        return False

    # Check for JSON-RPC 2.0 structure
    if "jsonrpc" not in response_data or response_data["jsonrpc"] != "2.0":
        return False

    # Must have either result or error
    has_result = "result" in response_data
    has_error = "error" in response_data

    return has_result or has_error


def extract_agent_response(response_data: dict[str, object]) -> object:
    """
    Extract the agent's response from A2A protocol wrapper

    Args:
        response_data: A2A protocol response

    Returns:
        The actual agent response content
    """
    if "result" in response_data:
        return response_data["result"]
    elif "error" in response_data:
        error_obj = response_data["error"]
        error = error_obj if isinstance(error_obj, Mapping) else {}
        raise Exception(f"Agent error {error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}")
    else:
        raise Exception("Invalid A2A response: no result or error field")
