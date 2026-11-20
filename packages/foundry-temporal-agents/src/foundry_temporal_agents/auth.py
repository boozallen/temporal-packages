# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Shared bearer-credential helper for the A2A and query activity paths."""

import logging
import os

logger = logging.getLogger(__name__)

# Bearer credential the agent's auth middleware validates, shared by the
# A2A and query activity paths. See FOUNDRY_TLS_MODE in tls.py for the
# equivalent env-var-driven pattern.
_BEARER_TOKEN_ENV_VAR = "FOUNDRY_AGENT_BEARER_TOKEN"

# Back-compat alias: the original query-only variable name. Checked when
# the primary variable above is unset, so existing query-only deployments
# don't need a config change. Deprecated: using it logs a warning, and a
# future major version will remove it.
_BEARER_TOKEN_ENV_VAR_ALIAS = "FOUNDRY_AGENT_QUERY_BEARER_TOKEN"


def build_agent_auth_headers(agent_url: str) -> dict[str, str]:
    """
    Build the Authorization header for a request to a Strands agent.

    Reads the bearer credential from FOUNDRY_AGENT_BEARER_TOKEN, falling
    back to FOUNDRY_AGENT_QUERY_BEARER_TOKEN for backward compatibility.
    Used by both the A2A and query activity paths so there is exactly one
    place that builds auth headers.

    Args:
        agent_url: URL of the Strands agent endpoint, included in the
            warning logged when no credential is configured.

    Returns:
        `{"Authorization": "Bearer <token>"}` when a credential is
        configured, or `{}` when neither variable is set.
    """
    if bearer_token := os.getenv(_BEARER_TOKEN_ENV_VAR):
        return {"Authorization": f"Bearer {bearer_token}"}

    if bearer_token := os.getenv(_BEARER_TOKEN_ENV_VAR_ALIAS):
        logger.warning(
            "%s is deprecated and will be removed in a future major version; set %s instead.",
            _BEARER_TOKEN_ENV_VAR_ALIAS,
            _BEARER_TOKEN_ENV_VAR,
        )
        return {"Authorization": f"Bearer {bearer_token}"}

    logger.warning(
        "Neither %s nor %s is set; sending unauthenticated request to %s. "
        "This will become a hard failure in an upcoming release - "
        "set the credential now to avoid disruption.",
        _BEARER_TOKEN_ENV_VAR,
        _BEARER_TOKEN_ENV_VAR_ALIAS,
        agent_url,
    )
    return {}
