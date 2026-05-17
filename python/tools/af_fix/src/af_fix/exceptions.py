# Copyright (c) Microsoft. All rights reserved.


class AFFixError(Exception):
    """Base exception for af-fix."""


class SandboxViolation(AFFixError):
    """Raised when tools attempt to access paths outside the sandboxed workspace."""


class ConfigError(AFFixError):
    """Raised when configuration is missing or invalid."""


class GitHubAPIError(AFFixError):
    """Raised when GitHub API calls fail in a way that should abort the run."""


class OpenHandsError(AFFixError):
    """Raised when OpenHands invocation fails or returns malformed state."""


class ClaudeAgentError(AFFixError):
    """Raised when claude-agent-sdk invocation fails or returns malformed state."""
