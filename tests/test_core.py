import os
import tempfile
import unittest
from pathlib import Path

from simple_directory_difference import (
    DirectoryDiff,
    FileChange,
    diff_directories,
    hash_file,
)


class DiffDirectoriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.old = self.root / "old"
        self.new = self.root / "new"
        self.old.mkdir()
        self.new.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, root: Path, relative: str, content: bytes) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_empty_directories_have_no_differences(self) -> None:
        result = diff_directories(self.old, self.new)
        self.assertIsInstance(result, DirectoryDiff)
        self.assertEqual(result.added, ())
        self.assertEqual(result.removed, ())
        self.assertEqual(result.modified, ())
        self.assertEqual(result.unchanged, ())
        self.assertFalse(result.has_differences)

    def test_added_file(self) -> None:
        self.write(self.new, "a.txt", b"hello")
        result = diff_directories(self.old, self.new)
        self.assertEqual(len(result.added), 1)
        change = result.added[0]
        self.assertIsInstance(change, FileChange)
        self.assertEqual(change.relative_path, "a.txt")
        self.assertEqual(change.change_type, "added")
        self.assertIsNone(change.old_hash)
        self.assertEqual(change.new_hash, hash_file(self.new / "a.txt"))
        self.assertEqual(result.removed, ())
        self.assertEqual(result.modified, ())
        self.assertTrue(result.has_differences)

    def test_removed_file(self) -> None:
        self.write(self.old, "a.txt", b"hello")
        result = diff_directories(self.old, self.new)
        self.assertEqual(len(result.removed), 1)
        change = result.removed[0]
        self.assertEqual(change.relative_path, "a.txt")
        self.assertEqual(change.change_type, "removed")
        self.assertEqual(change.old_hash, hash_file(self.old / "a.txt"))
        self.assertIsNone(change.new_hash)
        self.assertEqual(result.added, ())
        self.assertEqual(result.modified, ())

    def test_modified_file(self) -> None:
        self.write(self.old, "a.txt", b"hello")
        self.write(self.new, "a.txt", b"world")
        result = diff_directories(self.old, self.new)
        self.assertEqual(len(result.modified), 1)
        change = result.modified[0]
        self.assertEqual(change.relative_path, "a.txt")
        self.assertEqual(change.change_type, "modified")
        self.assertEqual(change.old_hash, hash_file(self.old / "a.txt"))
        self.assertEqual(change.new_hash, hash_file(self.new / "a.txt"))
        self.assertNotEqual(change.old_hash, change.new_hash)

    def test_unchanged_file(self) -> None:
        self.write(self.old, "a.txt", b"same")
        self.write(self.new, "a.txt", b"same")
        result = diff_directories(self.old, self.new)
        self.assertEqual(result.added, ())
        self.assertEqual(result.removed, ())
        self.assertEqual(result.modified, ())
        self.assertEqual(result.unchanged, ("a.txt",))
        self.assertFalse(result.has_differences)

    def test_nested_paths_use_forward_slashes(self) -> None:
        self.write(self.old, os.path.join("sub", "deep", "file.txt"), b"x")
        self.write(self.new, os.path.join("sub", "deep", "file.txt"), b"y")
        result = diff_directories(self.old, self.new)
        self.assertEqual(len(result.modified), 1)
        self.assertEqual(result.modified[0].relative_path, "sub/deep/file.txt")

    def test_sorted_output(self) -> None:
        for name in ("b.txt", "a.txt", "c.txt"):
            self.write(self.new, name, name.encode())
        result = diff_directories(self.old, self.new)
        self.assertEqual(
            [change.relative_path for change in result.added],
            ["a.txt", "b.txt", "c.txt"],
        )

    def test_all_changes_combined_and_sorted(self) -> None:
        self.write(self.old, "removed.txt", b"r")
        self.write(self.old, "modified.txt", b"old")
        self.write(self.new, "modified.txt", b"new")
        self.write(self.new, "added.txt", b"a")
        result = diff_directories(self.old, self.new)
        combined = result.all_changes()
        self.assertEqual(
            [change.relative_path for change in combined],
            ["added.txt", "modified.txt", "removed.txt"],
        )
        self.assertEqual(
            [change.change_type for change in combined],
            ["added", "modified", "removed"],
        )

    def test_has_differences_is_false_for_identical_trees(self) -> None:
        self.write(self.old, "one.txt", b"1")
        self.write(self.new, "one.txt", b"1")
        result = diff_directories(self.old, self.new)
        self.assertFalse(result.has_differences)

    def test_missing_directory_raises(self) -> None:
        with self.assertRaises(NotADirectoryError):
            diff_directories(self.old / "missing", self.new)

    def test_file_instead_of_directory_raises(self) -> None:
        file_path = self.root / "file.txt"
        file_path.write_bytes(b"not a dir")
        with self.assertRaises(NotADirectoryError):
            diff_directories(file_path, self.new)

    def test_hash_file_matches_known_sha256(self) -> None:
        path = self.root / "known.txt"
        path.write_bytes(b"abc")
        self.assertEqual(
            hash_file(path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_hash_file_large_content(self) -> None:
        # Force multi-chunk reading to exercise the chunking loop.
        content = b"x" * (2 * (1 << 20) + 123)
        path = self.root / "large.bin"
        path.write_bytes(content)
        self.assertEqual(
            hash_file(path),
            "cfc6db13bd7e4bcc69c1675e27a9b3f7a820f94430245510a736bb68c0129f16",
        )

    def test_unchanged_is_sorted(self) -> None:
        for name in ("c.txt", "a.txt", "b.txt"):
            self.write(self.old, name, name.encode())
            self.write(self.new, name, name.encode())
        result = diff_directories(self.old, self.new)
        self.assertEqual(result.unchanged, ("a.txt", "b.txt", "c.txt"))


if __name__ == "__main__":
    unittest.main()
