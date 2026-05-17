# Copyright (c) Microsoft. All rights reserved.


class AFWatchError(Exception):
    """Base for all af-watch errors."""


class ConfigError(AFWatchError):
    """Configuration loading or validation failure."""


class CorpusError(AFWatchError):
    """Corpus file missing, malformed, or stale."""


class FeedError(AFWatchError):
    """GitHub / HTTP fetch failure during feed gathering."""


class ReasoningError(AFWatchError):
    """LLM call or output parsing failure during reasoning."""


class ReportError(AFWatchError):
    """Briefing or deep-dive render failure."""
