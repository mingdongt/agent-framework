# Copyright (c) Microsoft. All rights reserved.

def test_package_imports() -> None:
    import af_fix
    assert af_fix.__version__ == "0.1.0"


def test_exception_hierarchy() -> None:
    from af_fix.exceptions import (
        AFFixError,
        ConfigError,
        GitHubAPIError,
        OpenHandsError,
        SandboxViolation,
    )
    assert issubclass(SandboxViolation, AFFixError)
    assert issubclass(ConfigError, AFFixError)
    assert issubclass(GitHubAPIError, AFFixError)
    assert issubclass(OpenHandsError, AFFixError)
