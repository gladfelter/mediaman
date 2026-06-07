#!/usr/bin/env python3
"""Tests for photocoll.py — cross-platform, uses temp dirs for all I/O."""
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import photocoll


# ---------------------------------------------------------------------------
# Phase 1: Unit tests
# ---------------------------------------------------------------------------

class FindNewPhotosTests(unittest.TestCase):
    """Tests for find_new_photos()."""

    @patch('os.walk')
    @patch('os.path.getmtime')
    def test_find_new_photos_none(self, mock_getmtime, mock_walk):
        """Returns empty list when no files are newer than last collection."""
        mock_walk.return_value = [
            (str(Path('/pics')), [], ['old.jpg']),
        ]
        mock_getmtime.return_value = 100  # older than 200
        result = photocoll.find_new_photos(
            Path('/pics'), last_collection=200, ignore_extensions=set()
        )
        self.assertEqual(result, [])

    @patch('os.walk')
    @patch('os.path.getmtime')
    def test_find_new_photos_some(self, mock_getmtime, mock_walk):
        """Returns only files modified after last collection."""
        mock_walk.return_value = [
            (str(Path('/pics')), [], ['old.jpg', 'new.jpg', 'newer.png']),
        ]
        mtimes = {
            str(Path('/pics/old.jpg')): 100,
            str(Path('/pics/new.jpg')): 300,
            str(Path('/pics/newer.png')): 250,
        }
        mock_getmtime.side_effect = lambda p: mtimes[p]
        result = photocoll.find_new_photos(
            Path('/pics'), last_collection=200, ignore_extensions=set()
        )
        expected = sorted([Path('/pics/new.jpg'), Path('/pics/newer.png')])
        self.assertEqual(sorted(result), expected)

    @patch('os.walk')
    @patch('os.path.getmtime')
    def test_find_new_photos_ignores_extensions(self, mock_getmtime, mock_walk):
        """Filters out files with ignored extensions."""
        mock_walk.return_value = [
            (str(Path('/pics')), [], ['photo.jpg', 'notes.txt', 'thumbs.db']),
        ]
        mock_getmtime.return_value = 999  # all newer
        result = photocoll.find_new_photos(
            Path('/pics'), last_collection=200,
            ignore_extensions={'.txt', '.db'}
        )
        self.assertEqual(result, [Path('/pics/photo.jpg')])

    @patch('os.walk')
    @patch('os.path.getmtime')
    def test_find_new_photos_handles_mtime_none(self, mock_getmtime, mock_walk):
        """Gracefully handles files with unreadable mtime."""
        mock_walk.return_value = [
            (str(Path('/pics')), [], ['bad.jpg', 'good.jpg']),
        ]

        def mtime_side_effect(path):
            if 'bad' in path:
                raise OSError('permission denied')
            return 999

        mock_getmtime.side_effect = mtime_side_effect
        result = photocoll.find_new_photos(
            Path('/pics'), last_collection=200, ignore_extensions=set()
        )
        # Only good.jpg should be returned; bad.jpg skipped gracefully
        self.assertEqual(result, [Path('/pics/good.jpg')])


class CollectionStateTests(unittest.TestCase):
    """Tests for CollectionState class."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / 'state.json'
        self.src_dir = Path('/home/user/Pictures')

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_collection_state_new(self):
        """Creates fresh state when no file exists."""
        cs = photocoll.CollectionState(self.state_path)
        self.assertEqual(cs.get_last_collection(self.src_dir), 0.0)
        # Nothing written to disk yet
        self.assertFalse(self.state_path.exists())

    def test_collection_state_load_existing(self):
        """Loads existing state from disk."""
        existing = {str(self.src_dir): 1712345678.9}
        self.state_path.write_text(json.dumps(existing))
        cs = photocoll.CollectionState(self.state_path)
        self.assertEqual(cs.get_last_collection(self.src_dir), 1712345678.9)

    def test_collection_state_update_in_memory(self):
        """Updates timestamp in memory without writing to disk."""
        cs = photocoll.CollectionState(self.state_path)
        cs.set_last_collection(self.src_dir, 1712345678.9)
        self.assertEqual(cs.get_last_collection(self.src_dir), 1712345678.9)
        self.assertFalse(self.state_path.exists())

    def test_collection_state_save(self):
        """Writes state to disk on save()."""
        cs = photocoll.CollectionState(self.state_path)
        cs.set_last_collection(self.src_dir, 1712345678.9)
        cs.save()
        self.assertTrue(self.state_path.exists())
        loaded = json.loads(self.state_path.read_text())
        self.assertEqual(loaded[str(self.src_dir)], 1712345678.9)

    def test_collection_state_preserves_on_copy_failure(self):
        """State is not updated if copies fail (save never called)."""
        cs = photocoll.CollectionState(self.state_path)
        cs.set_last_collection(self.src_dir, 50.0)
        cs.save()

        # Simulate a failed run: we update in memory but never save
        cs2 = photocoll.CollectionState(self.state_path)
        cs2.set_last_collection(self.src_dir, 100.0)
        # Don't call save — simulates failure

        # Reload: should still see the old value
        cs3 = photocoll.CollectionState(self.state_path)
        self.assertEqual(cs3.get_last_collection(self.src_dir), 50.0)

    def test_collection_state_multiple_dirs(self):
        """Tracks collection times per source directory."""
        cs = photocoll.CollectionState(self.state_path)
        pics = Path('/home/user/Pictures')
        downloads = Path('/home/user/Downloads')
        cs.set_last_collection(pics, 100.0)
        cs.set_last_collection(downloads, 200.0)
        cs.save()

        loaded = photocoll.CollectionState(self.state_path)
        self.assertEqual(loaded.get_last_collection(pics), 100.0)
        self.assertEqual(loaded.get_last_collection(downloads), 200.0)

    def test_collection_state_unknown_dir_returns_zero(self):
        """Returns 0.0 for directories never collected."""
        cs = photocoll.CollectionState(self.state_path)
        self.assertEqual(cs.get_last_collection(Path('/unknown')), 0.0)


class CopyFileTests(unittest.TestCase):
    """Tests for copy_files()."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src_dir = Path(self.tmpdir.name) / 'src'
        self.dest_dir = Path(self.tmpdir.name) / 'dest'
        self.src_dir.mkdir()
        self.dest_dir.mkdir()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_file(self, dir_path, name, content=b'hello'):
        p = dir_path / name
        p.write_bytes(content)
        return p

    def test_copy_file_no_collision(self):
        """Copies directly when no name conflict."""
        src = self._create_file(self.src_dir, 'photo.jpg', b'pic1')
        result = photocoll.copy_files([src], self.dest_dir)
        dest = self.dest_dir / 'photo.jpg'
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), b'pic1')
        self.assertEqual(result, [dest])

    def test_copy_file_renames_on_collision(self):
        """Appends _1, _2 when destination name exists."""
        # Pre-create a file at dest with the same name
        (self.dest_dir / 'photo.jpg').write_bytes(b'existing')
        src = self._create_file(self.src_dir, 'photo.jpg', b'different')

        result = photocoll.copy_files([src], self.dest_dir)
        dest = self.dest_dir / 'photo_1.jpg'
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), b'different')

    def test_copy_file_multiple_collisions(self):
        """Handles multiple collisions (_1, _2, _3...)."""
        (self.dest_dir / 'photo.jpg').write_bytes(b'orig')
        (self.dest_dir / 'photo_1.jpg').write_bytes(b'first')
        src = self._create_file(self.src_dir, 'photo.jpg', b'new')

        result = photocoll.copy_files([src], self.dest_dir)
        dest = self.dest_dir / 'photo_2.jpg'
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), b'new')

    def test_copy_file_preserves_metadata(self):
        """shutil.copy2 preserves timestamps."""
        src = self._create_file(self.src_dir, 'photo.jpg')
        result = photocoll.copy_files([src], self.dest_dir)
        dest = self.dest_dir / 'photo.jpg'
        self.assertEqual(dest.stat().st_mtime, src.stat().st_mtime)

    def test_copy_file_creates_dest_subdirs(self):
        """Creates subdirectories when dest_dir has nested structure."""
        subdir = self.dest_dir / 'nested' / 'path'
        src = self._create_file(self.src_dir, 'photo.jpg', b'data')
        result = photocoll.copy_files([src], subdir)
        self.assertTrue(subdir.exists())
        self.assertTrue((subdir / 'photo.jpg').exists())

    def test_copy_file_empty_list(self):
        """Returns empty list for empty input."""
        result = photocoll.copy_files([], self.dest_dir)
        self.assertEqual(result, [])

    def test_copy_file_multiple_files(self):
        """Copies multiple files correctly."""
        src1 = self._create_file(self.src_dir, 'a.jpg', b'aaa')
        src2 = self._create_file(self.src_dir, 'b.jpg', b'bbb')
        result = photocoll.copy_files([src1, src2], self.dest_dir)
        self.assertTrue((self.dest_dir / 'a.jpg').exists())
        self.assertTrue((self.dest_dir / 'b.jpg').exists())
        self.assertEqual(sorted(result), sorted([
            self.dest_dir / 'a.jpg',
            self.dest_dir / 'b.jpg',
        ]))


# ---------------------------------------------------------------------------
# Phase 2: Integration tests
# ---------------------------------------------------------------------------

class IntegrationTests(unittest.TestCase):
    """Integration tests using real temp directories."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src_dir = Path(self.tmpdir.name) / 'Pictures'
        self.staging_dir = Path(self.tmpdir.name) / 'staging'
        self.state_path = Path(self.tmpdir.name) / 'state.json'
        self.src_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_file(self, dir_path, name, content=b'photo data'):
        p = dir_path / name
        p.write_bytes(content)
        return p

    def test_full_pipeline_no_prior_state(self):
        """First run: all photos copied, state created."""
        self._create_file(self.src_dir, 'photo1.jpg', b'pic1')
        self._create_file(self.src_dir, 'photo2.jpg', b'pic2')
        # Add a subdirectory
        sub = self.src_dir / 'holiday'
        sub.mkdir()
        self._create_file(sub, 'photo3.jpg', b'pic3')

        result = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions=set(),
            state_path=self.state_path,
        )

        self.assertEqual(len(result), 3)
        self.assertTrue((self.staging_dir / 'photo1.jpg').exists())
        self.assertTrue((self.staging_dir / 'photo2.jpg').exists())
        self.assertTrue((self.staging_dir / 'photo3.jpg').exists())
        self.assertTrue(self.state_path.exists())

    def test_full_pipeline_incremental(self):
        """Second run: only new photos copied."""
        # First collection
        self._create_file(self.src_dir, 'old.jpg', b'old')
        photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions=set(),
            state_path=self.state_path,
        )

        # Add a new file after a short delay (to ensure mtime difference)
        time.sleep(0.01)
        self._create_file(self.src_dir, 'new.jpg', b'new')

        result = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions=set(),
            state_path=self.state_path,
        )

        # Only new.jpg should be in result
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'new.jpg')

    def test_full_pipeline_collision(self):
        """File exists in staging, same-name file in source → renamed copy."""
        # Pre-populate staging with a file
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        (self.staging_dir / 'photo.jpg').write_bytes(b'original')

        self._create_file(self.src_dir, 'photo.jpg', b'different')

        result = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions=set(),
            state_path=self.state_path,
        )

        # Should have created photo_1.jpg
        renamed = self.staging_dir / 'photo_1.jpg'
        self.assertTrue(renamed.exists())
        self.assertEqual(renamed.read_bytes(), b'different')

    def test_full_pipeline_ignores_extensions(self):
        """Only non-ignored extensions are copied."""
        self._create_file(self.src_dir, 'photo.jpg', b'pic')
        self._create_file(self.src_dir, 'notes.txt', b'text')
        self._create_file(self.src_dir, 'thumbs.db', b'db')

        result = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions={'.txt', '.db'},
            state_path=self.state_path,
        )

        self.assertEqual(len(result), 1)
        self.assertTrue((self.staging_dir / 'photo.jpg').exists())
        self.assertFalse((self.staging_dir / 'notes.txt').exists())
        self.assertFalse((self.staging_dir / 'thumbs.db').exists())

    def test_full_pipeline_idempotent(self):
        """Re-run copies nothing if no new photos."""
        self._create_file(self.src_dir, 'photo.jpg', b'pic')

        # First run
        r1 = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions=set(),
            state_path=self.state_path,
        )
        self.assertEqual(len(r1), 1)

        # Second run — should copy nothing
        r2 = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions=set(),
            state_path=self.state_path,
        )
        self.assertEqual(len(r2), 0)


# ---------------------------------------------------------------------------
# Phase 3: E2E test
# ---------------------------------------------------------------------------

class EndToEndTest(unittest.TestCase):
    """Full pipeline E2E test with temp dirs."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src_dir = Path(self.tmpdir.name) / 'Pictures'
        self.staging_dir = Path(self.tmpdir.name) / 'staging'
        self.state_path = Path(self.tmpdir.name) / 'state.json'
        self.src_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_file(self, dir_path, name, content=b'photo data'):
        p = dir_path / name
        p.write_bytes(content)
        return p

    def test_end_to_end_with_tempdirs(self):
        """Full pipeline: scan → filter → copy → state update → verify."""
        # Scenario: Multiple files, some in subdirs, some to be ignored
        self._create_file(self.src_dir, 'IMG_0001.jpg', b'photo1')
        self._create_file(self.src_dir, 'IMG_0002.jpg', b'photo2')
        self._create_file(self.src_dir, 'notes.txt', b'ignore me')
        sub = self.src_dir / 'vacation'
        sub.mkdir()
        self._create_file(sub, 'vacation1.jpg', b'vacation photo')

        # First collection
        result1 = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions={'.txt', '.db', '.ini'},
            state_path=self.state_path,
        )
        self.assertEqual(len(result1), 3)
        # Verify all expected files in staging
        stagings = {p.name for p in self.staging_dir.iterdir()}
        self.assertIn('IMG_0001.jpg', stagings)
        self.assertIn('IMG_0002.jpg', stagings)
        self.assertIn('vacation1.jpg', stagings)
        self.assertNotIn('notes.txt', stagings)

        # State file exists and has a timestamp
        self.assertTrue(self.state_path.exists())

        # Idempotent re-run
        result2 = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions={'.txt', '.db', '.ini'},
            state_path=self.state_path,
        )
        self.assertEqual(len(result2), 0)

        # Add new files
        time.sleep(0.01)
        self._create_file(self.src_dir, 'IMG_0003.jpg', b'new photo')
        sub2 = self.src_dir / 'birthday'
        sub2.mkdir()
        self._create_file(sub2, 'birthday1.jpg', b'birthday photo')

        # Incremental collection — only new files
        result3 = photocoll.collect_photos(
            self.src_dir, self.staging_dir,
            ignore_extensions={'.txt', '.db', '.ini'},
            state_path=self.state_path,
        )
        self.assertEqual(len(result3), 2)
        stagings = {p.name for p in self.staging_dir.iterdir()}
        self.assertIn('IMG_0003.jpg', stagings)
        self.assertIn('birthday1.jpg', stagings)


# ---------------------------------------------------------------------------
# CLI / main tests
# ---------------------------------------------------------------------------

class MainTests(unittest.TestCase):
    """Tests for the argparse entry point."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    @patch('photocoll.collect_photos')
    def test_main_required_staging_dir(self, mock_collect):
        """--staging_dir is required."""
        with self.assertRaises(SystemExit):
            photocoll.main(['--src_dir', str(self.tmpdir.name)])

    @patch('photocoll.collect_photos')
    def test_main_default_src_dir(self, mock_collect):
        """--src_dir defaults to ~/Pictures."""
        staging = str(Path(self.tmpdir.name) / 'staging')
        photocoll.main(['--staging_dir', staging])
        default_src = Path.home() / 'Pictures'
        kwargs = mock_collect.call_args.kwargs
        self.assertEqual(kwargs['src_dir'], default_src)

    @patch('photocoll.collect_photos')
    def test_main_custom_src_dir(self, mock_collect):
        """--src_dir overrides the default."""
        staging = str(Path(self.tmpdir.name) / 'staging')
        src = str(Path(self.tmpdir.name) / 'custom_pics')
        photocoll.main([
            '--src_dir', src,
            '--staging_dir', staging,
        ])
        kwargs = mock_collect.call_args.kwargs
        self.assertEqual(kwargs['src_dir'], Path(src))

    @patch('photocoll.collect_photos')
    def test_main_ignore_extensions(self, mock_collect):
        """--ignore_extensions accepts a comma-separated list."""
        staging = str(Path(self.tmpdir.name) / 'staging')
        photocoll.main([
            '--staging_dir', staging,
            '--ignore_extensions', '.txt,.db,.ini',
        ])
        _, kwargs = mock_collect.call_args
        self.assertEqual(kwargs['ignore_extensions'], {'.txt', '.db', '.ini'})

    @patch('photocoll.collect_photos')
    def test_main_state_path(self, mock_collect):
        """--state_path overrides default."""
        staging = str(Path(self.tmpdir.name) / 'staging')
        state = str(Path(self.tmpdir.name) / 'my_state.json')
        photocoll.main([
            '--staging_dir', staging,
            '--state_path', state,
        ])
        _, kwargs = mock_collect.call_args
        self.assertEqual(kwargs['state_path'], Path(state))

    @patch('photocoll.collect_photos')
    def test_main_log_file(self, mock_collect):
        """--log_file configures file logging."""
        staging = str(Path(self.tmpdir.name) / 'staging')
        log = str(Path(self.tmpdir.name) / 'photocoll.log')
        photocoll.main([
            '--staging_dir', staging,
            '--log_file', log,
        ])
        _, kwargs = mock_collect.call_args
        self.assertEqual(kwargs['log_file'], Path(log))


if __name__ == '__main__':
    unittest.main()
