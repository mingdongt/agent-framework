from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Provider name fragments — case-insensitive; matched against filename + path
_PROVIDER_PATTERNS = {
    "anthropic": ["anthropic", "claude"],
    "openai": ["openai", "gpt"],
    "google": ["google", "gemini", "vertex"],
    "azure": ["azure"],
    "mistral": ["mistral"],
    "cohere": ["cohere"],
    "bedrock": ["bedrock"],
    "litellm": ["litellm"],
}

_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    "dist", "build", ".pytest_cache", ".ruff_cache", "target",
    ".tox", ".mypy_cache", "site-packages",
}

_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cs"}
_TEST_PATTERNS = ("test_", "_test.", "/tests/", "\\tests\\", ".spec.")


@dataclass
class FileInventory:
    repo_root: Path
    source_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    provider_files: dict[str, list[str]] = field(default_factory=dict)
    readme_excerpt: str = ""
    pyproject_present: bool = False
    package_json_present: bool = False


def _is_test_file(rel_path: str) -> bool:
    p = rel_path.lower()
    return any(t in p for t in _TEST_PATTERNS)


def _classify_provider(rel_path: str) -> str | None:
    p = rel_path.lower()
    for provider, patterns in _PROVIDER_PATTERNS.items():
        if any(pat in p for pat in patterns):
            return provider
    return None


def scan_repo_locally(
    repo_root: Path,
    *,
    max_source_files: int = 300,
    max_test_files: int = 100,
    readme_chars: int = 2000,
) -> FileInventory:
    """Scan a local repo clone and produce a structured inventory.

    Walks the tree, excluding well-known build/cache dirs. Caps result lists so
    the inventory stays small enough for a single LLM call later.
    """
    inv = FileInventory(repo_root=repo_root)

    if not repo_root.is_dir():
        log.warning("scan_repo_locally: %s is not a directory", repo_root)
        return inv

    readme_path = None
    for name in ("README.md", "Readme.md", "readme.md", "README.rst", "README.txt"):
        candidate = repo_root / name
        if candidate.is_file():
            readme_path = candidate
            break
    if readme_path is not None:
        try:
            inv.readme_excerpt = readme_path.read_text(encoding="utf-8", errors="replace")[
                :readme_chars
            ]
        except Exception as e:
            log.warning("Failed to read README %s: %s", readme_path, e)

    inv.pyproject_present = (repo_root / "pyproject.toml").is_file()
    inv.package_json_present = (repo_root / "package.json").is_file()

    source_buf: list[str] = []
    test_buf: list[str] = []
    provider_buf: dict[str, list[str]] = {}

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded dirs anywhere in the path
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix not in _SOURCE_EXTS:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if _is_test_file(rel):
            test_buf.append(rel)
        else:
            source_buf.append(rel)
            provider = _classify_provider(rel)
            if provider:
                provider_buf.setdefault(provider, []).append(rel)

    # Stable sort + cap
    inv.source_files = sorted(source_buf)[:max_source_files]
    inv.test_files = sorted(test_buf)[:max_test_files]
    inv.provider_files = {p: sorted(files) for p, files in sorted(provider_buf.items())}

    log.info(
        "scanned %s: %d source files, %d test files, %d providers",
        repo_root.name, len(inv.source_files), len(inv.test_files), len(inv.provider_files),
    )

    return inv
