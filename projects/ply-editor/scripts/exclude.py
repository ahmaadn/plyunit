"""Folder-exclude patterns: glob parsing, matching, and layered merging.

Project scanning is driven by a list of *exclude* patterns. Without
them, an ``assets_root`` defaulting to ``"."`` makes the editor traverse
the entire project folder — including ``.venv/``, ``.dist/``, and
``node_modules/`` — before a single frame is shown.

Pattern semantics
-----------------

A pattern is a glob that always uses posix separators. There are two
forms:

* **Without ``/``** (e.g. ``node_modules``, ``*.egg-info``) — matched
  against the folder *name* at any depth.
* **With ``/``** (e.g. ``build/out``) — matched against the path
  relative to the project root.

``*`` and ``?`` do not cross ``/``; ``**`` does. Matching is
case-insensitive so behavior is consistent on Windows.

Layered merging
---------------

The global list applies to all projects. When a project enables
*override*, the project list **replaces** the global list entirely;
otherwise both are merged. On top of the result,
:data:`~scripts.constants.ALWAYS_EXCLUDED` is always appended — it
cannot be disabled — so the editor scaffold and git metadata are never
scanned.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts import constants as const

logger = logging.getLogger(__name__)


def normalize_pattern(raw: Any) -> str:
    """Clean up a single exclude pattern.

    Strips whitespace, converts ``\\`` to ``/``, and removes a leading
    ``./`` and trailing ``/`` so ``build/`` and ``build`` are treated
    the same.

    Args:
        raw: Raw pattern from a config file or user input.

    Returns:
        The normalized pattern; an empty string when unusable.
    """
    if not isinstance(raw, str):
        return ""
    text = raw.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = text.strip("/")
    if text in ("", ".", ".."):
        return ""
    return text


def normalize_patterns(raw: Any) -> tuple[str, ...]:
    """Clean up a list of patterns, dropping duplicates, keeping order.

    Args:
        raw: Iterable of patterns; non-string values are skipped.

    Returns:
        Tuple of unique, normalized patterns.
    """
    if isinstance(raw, str) or not isinstance(raw, (list, tuple, set, frozenset)):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        pattern = normalize_pattern(item)
        if pattern and pattern not in seen:
            seen.add(pattern)
            out.append(pattern)
    return tuple(out)


def _translate(pattern: str) -> str:
    """Translate a glob pattern into a regex source.

    Written by hand instead of :func:`fnmatch.translate` because
    ``fnmatch`` treats ``*`` as "anything including ``/``", making
    ``*`` and ``**`` indistinguishable.
    """
    out: list[str] = []
    i = 0
    length = len(pattern)
    while i < length:
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**", i):
                i += 2
                if pattern.startswith("/", i):
                    i += 1
                    # "**/" may match zero folders.
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
            else:
                i += 1
                out.append("[^/]*")
            continue
        if char == "?":
            i += 1
            out.append("[^/]")
            continue
        if char == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                i += 1
                out.append(re.escape("["))
                continue
            body = pattern[i + 1 : end]
            i = end + 1
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append(f"[{body}]")
            continue
        i += 1
        out.append(re.escape(char))
    return "".join(out)


def _compile(pattern: str) -> re.Pattern[str] | None:
    """Compile one pattern to a regex, logging and skipping on error."""
    try:
        return re.compile(f"^{_translate(pattern)}$", re.IGNORECASE)
    except re.error:
        logger.warning("Pola exclude '%s' tidak valid, dilewati", pattern)
        return None


@dataclass(frozen=True, slots=True)
class ExcludeRules:
    """A compiled set of exclude patterns.

    Immutable and hashable so instances can be compared to detect
    settings changes (and trigger a re-scan) without storing a separate
    copy.

    Attributes:
        patterns: Normalized source patterns, for display in the UI.
    """

    patterns: tuple[str, ...] = ()
    _name_res: tuple[re.Pattern[str], ...] = field(
        default=(), repr=False, compare=False, hash=False
    )
    _path_res: tuple[re.Pattern[str], ...] = field(
        default=(), repr=False, compare=False, hash=False
    )

    @classmethod
    def build(cls, patterns: Any) -> ExcludeRules:
        """Compile a list of patterns into ready-to-use rules.

        Patterns are split into two groups: *name*-based patterns
        (without ``/``) that match at any depth, and *path*-based
        patterns that are matched from the project root.

        Args:
            patterns: Iterable of raw patterns.

        Returns:
            A new :class:`ExcludeRules`.
        """
        cleaned = normalize_patterns(patterns)
        names: list[re.Pattern[str]] = []
        paths: list[re.Pattern[str]] = []
        for pattern in cleaned:
            compiled = _compile(pattern)
            if compiled is None:
                continue
            if "/" in pattern:
                paths.append(compiled)
            else:
                names.append(compiled)
        return cls(
            patterns=cleaned,
            _name_res=tuple(names),
            _path_res=tuple(paths),
        )

    @property
    def is_empty(self) -> bool:
        """True when no pattern compiled successfully."""
        return not self._name_res and not self._path_res

    def is_excluded_dir(self, name: str, relative_path: str) -> bool:
        """Return whether a folder should be skipped.

        Args:
            name: The folder's own name.
            relative_path: Folder path relative to the project root.

        Returns:
            True when the folder matches one of the patterns.
        """
        if any(regex.match(name) for regex in self._name_res):
            return True
        candidate = normalize_pattern(relative_path)
        if not candidate:
            return False
        return any(regex.match(candidate) for regex in self._path_res)

    def is_excluded_relative(self, relative_path: str) -> bool:
        """Return whether a relative path or one of its parents is excluded.

        Args:
            relative_path: Path relative to the project root, posix
                separators.

        Returns:
            True when the path is excluded.
        """
        candidate = normalize_pattern(relative_path)
        if not candidate:
            return False
        parts = candidate.split("/")
        for i in range(len(parts)):
            if self.is_excluded_dir(parts[i], "/".join(parts[: i + 1])):
                return True
        return False

    def is_excluded_path(self, path: Path, root: Path) -> bool:
        """Return whether ``path`` sits inside something excluded.

        Paths outside ``root`` are considered not excluded: these rules
        only talk about the project's contents.

        Args:
            path: Absolute path to check.
            root: Project root.
        """
        try:
            relative = Path(path).relative_to(root).as_posix()
        except ValueError:
            return False
        return self.is_excluded_relative(relative)


def resolve_excludes(
    global_patterns: Any,
    project_patterns: Any = None,
    *,
    override: bool = True,
) -> ExcludeRules:
    """Merge the global and project lists into one rule set.

    Args:
        global_patterns: Patterns from the global config.
        project_patterns: Patterns from ``project.json``.
        override: When True (default), a non-empty project list
            **replaces** the global list. When False, both are merged.

    Returns:
        Merged :class:`ExcludeRules`; always includes
        :data:`~scripts.constants.ALWAYS_EXCLUDED`.
    """
    globals_ = normalize_patterns(global_patterns)
    project = normalize_patterns(project_patterns)

    if project and override:
        base: tuple[str, ...] = project
    else:
        base = (*globals_, *project)
    return ExcludeRules.build((*base, *const.ALWAYS_EXCLUDED))
