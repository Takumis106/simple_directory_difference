# simple_directory_difference

Compares two directories and reports added, removed, and modified files by
content hash.

```python
import os
import tempfile

from simple_directory_difference import diff_directories

with tempfile.TemporaryDirectory() as tmp:
    old_tree = os.path.join(tmp, "old")
    new_tree = os.path.join(tmp, "new")
    os.mkdir(old_tree)
    os.mkdir(new_tree)

    with open(os.path.join(old_tree, "kept.txt"), "w") as handle:
        handle.write("same")
    with open(os.path.join(new_tree, "kept.txt"), "w") as handle:
        handle.write("same")

    with open(os.path.join(old_tree, "gone.txt"), "w") as handle:
        handle.write("old")

    with open(os.path.join(new_tree, "fresh.txt"), "w") as handle:
        handle.write("new")

    result = diff_directories(old_tree, new_tree)

    for change in result.all_changes():
        print(change.change_type, change.relative_path)

    print("unchanged:", len(result.unchanged))
```

This prints:

```
fresh.txt added
gone.txt removed
unchanged: 1
```

## Why this exists

A plain recursive walk that compares file sizes or modification times gives
false positives after a copy or a checkout: content is identical but the
metadata moved. This library hashes file contents with SHA-256 and compares
those hashes, so only real content differences are reported. The trade-off is
speed: every file in both trees is read. That is acceptable for the intended
use of checking modest source trees, but it is not the right tool for
multi-terabyte archives.

## What counts as a file

Only regular files are compared. Symlinks that point at files are followed
and hashed; symlinks that point at directories are not followed, which avoids
infinite loops on self-referential trees. Broken symlinks are ignored because
they have no content to hash. Directories themselves are not reported, only
the files inside them.

## API

- `diff_directories(old_root, new_root) -> DirectoryDiff`
- `DirectoryDiff` with attributes `added`, `removed`, `modified`, `unchanged`
  (all tuples), a property `has_differences`, and a method `all_changes()`
  that returns every change sorted by path.
- `FileChange` with attributes `relative_path`, `change_type`, `old_hash`,
  `new_hash`.
- `hash_file(path) -> str` returns the SHA-256 hex digest of one file.

Paths in the result are relative to their root and always use `/` as the
separator, so a comparison made on Windows and one made on POSIX produce the
same strings.

## The awkward edge

Both roots must already exist and be directories. Passing a path that does not
exist, or a regular file, raises `NotADirectoryError`. There is no silent
empty result for a missing tree, because a typo in the path would otherwise
look like a tree full of removals.
