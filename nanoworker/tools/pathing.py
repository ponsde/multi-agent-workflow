"""Workspace path resolution for tools."""

from __future__ import annotations

from pathlib import Path


class PathPolicyError(ValueError):
    """Raised when a requested path is outside the worker workspace."""


WRITE_DENY_PREFIXES = (
    ".git/",
    ".worktrees/",
    "node_modules/",
)
WRITE_DENY_NAMES = {
    ".env",
}
TEST_WRITE_DIR_NAMES = {
    "__tests__",
    "e2e",
    "spec",
    "specs",
    "test",
    "tests",
}
TEST_WRITE_SUFFIXES = (
    ".spec.js",
    ".spec.jsx",
    ".spec.mjs",
    ".spec.ts",
    ".spec.tsx",
    ".test.js",
    ".test.jsx",
    ".test.mjs",
    ".test.ts",
    ".test.tsx",
    "_spec.py",
    "_test.py",
)
TEST_WRITE_PREFIXES = (
    "test_",
    "spec_",
)


def resolve_workspace_path(workspace: str | Path, raw_path: str) -> Path:
    """Resolve a relative or absolute path and keep it inside workspace."""
    root = Path(workspace).resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)

    if not _is_relative_to(resolved, root):
        raise PathPolicyError(f"path escapes workspace: {raw_path}")

    return resolved


def relative_workspace_path(workspace: str | Path, path: Path) -> str:
    """Return a POSIX-style path relative to workspace."""
    root = Path(workspace).resolve()
    try:
        return path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def assert_write_allowed(workspace: str | Path, path: Path, policy: str = "default") -> None:
    """Apply a small default write denylist."""
    rel = relative_workspace_path(workspace, path)
    name = Path(rel).name
    if name in WRITE_DENY_NAMES:
        raise PathPolicyError(f"writes to {name} are blocked by tool policy")
    for prefix in WRITE_DENY_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            raise PathPolicyError(f"writes under {prefix.rstrip('/')} are blocked by tool policy")
    if policy == "tests" and not _looks_like_test_path(Path(rel)):
        raise PathPolicyError("test-write-only policy only allows writes to test/spec paths")


def _looks_like_test_path(path: Path) -> bool:
    parts = set(path.parts[:-1])
    if parts.intersection(TEST_WRITE_DIR_NAMES):
        return True
    name = path.name.lower()
    return name.startswith(TEST_WRITE_PREFIXES) or name.endswith(TEST_WRITE_SUFFIXES)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
