# Copyright (c) Microsoft. All rights reserved.

def test_package_imports() -> None:
    import af_watch
    assert af_watch.__version__ == "0.1.0"


def test_exception_hierarchy() -> None:
    from af_watch.exceptions import (
        AFWatchError,
        ConfigError,
        CorpusError,
        FeedError,
        ReasoningError,
        ReportError,
    )
    assert issubclass(ConfigError, AFWatchError)
    assert issubclass(CorpusError, AFWatchError)
    assert issubclass(FeedError, AFWatchError)
    assert issubclass(ReasoningError, AFWatchError)
    assert issubclass(ReportError, AFWatchError)
