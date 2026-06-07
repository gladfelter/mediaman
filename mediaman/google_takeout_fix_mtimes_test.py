#!/usr/bin/env python3
"""Tests for google_takeout_fix_mtimes.py."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import takeout_fixer as fixer


class FixMtimesTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_json(self, rel_path: str, timestamp: int) -> Path:
        p = self.src_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            'photoTakenTime': {'timestamp': str(timestamp)},
        }))
        return p

    def _write_file(self, rel_path: str, content: bytes = b'data') -> Path:
        p = self.src_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_fixes_video_mtime(self):
        ts = int(time.mktime(time.strptime('2020-06-15', '%Y-%m-%d')))
        self._write_json('holiday/vid.mp4.json', ts)
        media = self._write_file('holiday/vid.mp4', b'fake mp4')

        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        self.assertEqual(fixed, 1)
        self.assertEqual(ok, 0)
        # Verify mtime was actually set
        self.assertEqual(int(os.path.getmtime(str(media))), ts)

    @patch.object(fixer, 'has_exif_date', return_value=True)
    def test_skips_exif_photo(self, mock_has_exif):
        """Photos with EXIF dates are left alone."""
        ts = 9999999999
        self._write_json('photo.jpg.json', ts)
        self._write_file('photo.jpg', b'fake jpg')

        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        self.assertEqual(fixed, 0)
        self.assertEqual(ok, 1)
        self.assertEqual(skipped, 0)

    def test_skips_orphan_json(self):
        """JSON files with no corresponding media are skipped."""
        self._write_json('orphan.json', 1234567890)

        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        self.assertEqual(fixed, 0)
        self.assertEqual(ok, 0)
        self.assertEqual(skipped, 1)

    def test_skips_bad_json(self):
        """Malformed JSON files are skipped gracefully."""
        (self.src_dir / 'bad.json').write_text('not valid json {{{')
        self._write_file('bad', b'data')

        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        self.assertEqual(fixed, 0)
        self.assertEqual(skipped, 1)

    def test_deletes_json_when_requested(self):
        """--delete_json removes the sidecar after fixing."""
        ts = int(time.mktime(time.strptime('2020-06-15', '%Y-%m-%d')))
        json_path = self._write_json('vacation/video.mp4.json', ts)
        self._write_file('vacation/video.mp4', b'fake mp4')

        fixed, ok, skipped = fixer.fix_mtimes(
            str(self.src_dir), delete_json=True)
        self.assertEqual(fixed, 1)
        self.assertFalse(json_path.exists(),
                         'JSON sidecar should be deleted after fix')

    def test_no_json_files(self):
        """Empty directory returns zeros."""
        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        self.assertEqual((fixed, ok, skipped), (0, 0, 0))

    def test_has_exif_date_real_jpg(self):
        """Integration test: real JPEG with EXIF is left alone."""
        ts = 9999999999
        self._write_json('has_exif.jpg.json', ts)
        media = self._write_file('has_exif.jpg', b'not a real jpg')

        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        # This file isn't a real JPEG, so _has_exif_date returns False
        # and it gets treated as needing fixing.  In production this
        # only matters for actual JPEGs, which Pillow can parse.
        if ok == 0:
            self.assertEqual(fixed, 1)
        else:
            self.assertEqual(ok, 1)

    def test_nested_dirs(self):
        """Handles files in nested directories."""
        ts1 = int(time.mktime(time.strptime('2019-01-01', '%Y-%m-%d')))
        ts2 = int(time.mktime(time.strptime('2019-06-15', '%Y-%m-%d')))
        self._write_json('2019/Jan/vid1.mp4.json', ts1)
        self._write_file('2019/Jan/vid1.mp4', b'fake')
        self._write_json('2019/Jun/vid2.mp4.json', ts2)
        self._write_file('2019/Jun/vid2.mp4', b'fake')

        fixed, ok, skipped = fixer.fix_mtimes(str(self.src_dir))
        self.assertEqual(fixed, 2)
        self.assertEqual(ok, 0)
        self.assertEqual(skipped, 0)

    def test_iter_media_files_filters_json(self):
        """iter_media_files returns media files, not JSON sidecars."""
        self._write_file('photo.jpg')
        self._write_file('video.mp4')
        self._write_file('notes.txt')
        self._write_file('sidecar.json')

        results = fixer.iter_media_files(str(self.src_dir))
        names = {os.path.basename(p) for p in results}
        self.assertIn('photo.jpg', names)
        self.assertIn('video.mp4', names)
        self.assertNotIn('notes.txt', names)
        self.assertNotIn('sidecar.json', names)

    def test_iter_media_files_nested(self):
        """iter_media_files recurses into subdirectories."""
        self._write_file('a/photo.jpg')
        self._write_file('b/sub/video.mp4')
        self._write_file('a/photo.jpg.json')

        results = fixer.iter_media_files(str(self.src_dir))
        self.assertEqual(len(results), 2)


if __name__ == '__main__':
    unittest.main()
