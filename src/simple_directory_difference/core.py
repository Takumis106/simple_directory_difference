"""Core logic for comparing two directories by file content hash.

This module intentionally has no third-party dependencies. The hash function
is fixed to SHA-256 so that comparisons are stable across runs and platforms.

Files are identified by their relative path (using forward slashes) so that
the same logical tree compares equal on Windows and POSIX systems.

Symlinks are followed when reading file contents, but the path recorded is
the path of the symlink itself. This matches the common expectation that a
symlinked file is compared by what it points at.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

_HASH_CHUNK_SIZE = 1 << 20  # 1 MiB


@dataclass(frozen=True)
class FileChange:
    """A single difference between two directory trees.

    Attributes:
        relative_path: The path relative to the root, using ``/`` separators.
        change_type: One of ``"added"``, ``"removed"``, or ``"modified"``.
        old_hash: The hash in the first directory, or ``None`` for added files.
        new_hash: The hash in the second directory, or ``None`` for removed files.
    """

    relative_path: str
    change_type: str
    old_hash: Optional[str]
    new_hash: Optional[str]


@dataclass(frozen=True)
class DirectoryDiff:
    """The complete result of comparing two directories.

    ``added``, ``removed``, and ``modified`` are tuples of ``FileChange``
    instances sorted by ``relative_path``. ``unchanged`` is a tuple of
    relative paths that exist with the same hash in both directories.
    """

    added: Tuple[FileChange, ...] = field(default_factory=tuple)
    removed: Tuple[FileChange, ...] = field(default_factory=tuple)
    modified: Tuple[FileChange, ...] = field(default_factory=tuple)
    unchanged: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_differences(self) -> bool:
        """Return True when any file was added, removed, or modified."""
        return bool(self.added or self.removed or self.modified)

    def all_changes(self) -> Tuple[FileChange, ...]:
        """Return every change in a single tuple, sorted by path."""
        combined: List[FileChange] = list(self.added) + list(self.removed) + list(self.modified)
        combined.sort(key=lambda change: change.relative_path)
        return tuple(combined)


def hash_file(path: os.PathLike[str] | str) -> str:
    """Return the SHA-256 hex digest of the file at *path*.

    The file is read in chunks so that hashing a large file does not load it
    entirely into memory. This is the only hash function used by the library;
    callers who need a different algorithm should hash themselves and compare.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterator[Tuple[str, Path]]:
    """Yield ``(relative_path, absolute_path)`` for every regular file under *root*.

    Directories are walked in sorted order for deterministic output. Symlinks
    to files are included; symlinks to directories are not followed to avoid
    cycles. Broken symlinks are skipped because they cannot be hashed.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        current = Path(dirpath)
        for name in filenames:
            full = current / name
            if full.is_symlink() and not full.exists():
                continue
            if not full.is_file():
                continue
            relative = full.relative_to(root).as_posix()
            yield relative, full


def _hash_tree(root: os.PathLike[str] | str) -> Dict[str, str]:
    """Return a mapping of relative path to SHA-256 hash for *root*."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(f"not a directory: {root_path}")
    result: Dict[str, str] = {}
    for relative, full in _iter_files(root_path):
        result[relative] = hash_file(full)
    return result


def diff_directories(
    old_root: os.PathLike[str] | str,
    new_root: os.PathLike[str] | str,
) -> DirectoryDiff:
    """Compare two directory trees by file content hash.

    Both roots must be existing directories. The result lists files that were
    added (present only in *new_root*), removed (present only in *old_root*),
    and modified (present in both but with different hashes). Files with the
    same relative path and hash are reported as unchanged.

    The comparison is purely content-based: file modification times and
    permissions are ignored. This is deliberate, because a directory copy
    that preserves content but changes timestamps should not be reported as
    different.
    """
    old_hashes = _hash_tree(old_root)
    new_hashes = _hash_tree(new_root)

    added: List[FileChange] = []
    removed: List[FileChange] = []
    modified: List[FileChange] = []
    unchanged: List[str] = []

    for relative in sorted(old_hashes):
        old_hash = old_hashes[relative]
        if relative not in new_hashes:
            removed.append(
                FileChange(
                    relative_path=relative,
                    change_type="removed",
                    old_hash=old_hash,
                    new_hash=None,
                )
            )
        else:
            new_hash = new_hashes[relative]
            if old_hash == new_hash:
                unchanged.append(relative)
            else:
                modified.append(
                    FileChange(
                        relative_path=relative,
                        change_type="modified",
                        old_hash=old_hash,
                        new_hash=new_hash,
                    )
                )

    for relative in sorted(new_hashes):
        if relative not in old_hashes:
            added.append(
                FileChange(
                    relative_path=relative,
                    change_type="added",
                    old_hash=None,
                    new_hash=new_hashes[relative],
                )
            )

    return DirectoryDiff(
        added=tuple(added),
        removed=tuple(removed),
        modified=tuple(modified),
        unchanged=tuple(unchanged),
    )
