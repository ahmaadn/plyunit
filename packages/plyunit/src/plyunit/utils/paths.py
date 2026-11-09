"""Safe path resolution inside a base directory.

Pure functions over :class:`pathlib.Path` that ensure file operations stay
within trusted boundaries and resolve relative file references safely.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ("resolve_config_resource", "resolve_inside")


def resolve_inside(base_dir: Path, target_path: str | Path) -> Path:
    """Resolve ``target_path`` against ``base_dir`` and reject anything outside it.

    Symlinks and ``..`` segments are resolved *before* the containment check,
    so neither can be used to escape ``base_dir``.

    Args:
        base_dir: Trusted base directory, resolved before checking containment.
        target_path: Path relative to ``base_dir``. An absolute path is accepted
            as long as it ends up inside ``base_dir``.

    Returns:
        The resolved absolute path. It is not required to exist.

    Raises:
        ValueError: If the resolved path is outside ``base_dir``.

    Example:
        >>> base = Path("/app/data").resolve()
        >>> resolve_inside(base, "docs/file.txt")
        PosixPath('/app/data/docs/file.txt')
        >>> resolve_inside(base, "../secret.txt")
        Traceback (most recent call last):
            ...
        ValueError: Path escapes base directory: ../secret.txt
    """
    base_dir = base_dir.resolve()
    candidate = (base_dir / target_path).resolve()
    if not candidate.is_relative_to(base_dir):
        raise ValueError(f"Path escapes base directory: {target_path}")
    return candidate


def resolve_config_resource(
    base_dir: Path, resource_path: str | Path, context_path: Path
) -> Path:
    """Resolve a resource file referenced by a configuration or manifest file.

    The asset-root path takes priority if it exists. Otherwise, the complete
    resource path is resolved relative to the configuration's directory.
    Neither resolution discards path components, and both the configuration
    and the resource must remain inside the trusted base directory.

    Args:
        base_dir: Trusted base directory, resolved before checking containment.
        resource_path: The file path read from the config or manifest file.
        context_path: Path of the configuration file containing ``resource_path``.

    Returns:
        The resolved sidecar path if it exists and the root-relative file does
        not; otherwise the root-relative path.

    Raises:
        ValueError: If the resolved candidate escapes ``base_dir``.
    """
    base_dir = base_dir.resolve()
    context_path = resolve_inside(base_dir, context_path)
    root_candidate = resolve_inside(base_dir, resource_path)
    if root_candidate.is_file():
        return root_candidate

    sidecar = resolve_inside(base_dir, context_path.parent / resource_path)
    return sidecar if sidecar.is_file() else root_candidate
