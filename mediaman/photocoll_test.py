#!/usr/bin/env python3
"""Windows-only photo collection tests. Skipped on Linux."""
import os
import unittest
from unittest.mock import *

# This entire module is Windows-only
if os.name != 'nt':
    raise unittest.SkipTest('photocoll tests are Windows-only')

import photocoll
import pickle


class PhotoCollectionTests(unittest.TestCase):

    def setUp(self):
        pass

    @patch('photocoll.find_new_photos')
    def test_collection(self, find_photos):
        find_photos.return_value = []
        photocoll.collect_photos(None, None, set())

    @patch('os.path.exists')
    @patch('photocoll.CollectionStatus')
    @patch('photocoll.configure_status_dir')
    def test_read_collection_status(self, configure_status_dir,
                                    stat, exists):
        configure_status_dir.return_value = 'c:\\foo'
        exists.return_value = True
        status = photocoll.read_collection_status('c:\\photos')
        stat.assert_called_with('c:\\foo\\status.txt', 'c:\\photos')

    @patch('os.path.exists')
    @patch('photocoll.CollectionStatus')
    @patch('photocoll.configure_status_dir')
    def test_read_collection_status_missing(self, configure_status_dir,
                                            stat, exists):
        configure_status_dir.return_value = '\\foo'
        exists.return_value = False
        status = photocoll.read_collection_status('c:\\photos')
        stat.assert_called_with(None, 'c:\\photos')

    @patch('photocoll.configure_status_dir')
    def test_write_collection_status(self, configure_status_dir):
        status = MagicMock()
        configure_status_dir.return_value = 'c:\\foo'
        photocoll.write_collection_status(status)
        status.save.assert_called_with('c:\\foo\\status.txt')

    @patch('os.path.getmtime')
    @patch('os.path.getctime')
    @patch('os.walk')
    def test_find_new_photos(self, walk, ctime, mtime):
        walk.return_value = [('c:\\foo', ['bar'],
                             ['baz', 'qux', 'quy', 'quz.txt']),
                             ('c:\\foo\\bar', [], [])]
        mtimes = {'c:\\foo\\baz': 42,
                  'c:\\foo\\qux': 55,
                  'c:\\foo\\quy': 35}
        ctimes = {'c:\\foo\\baz': 10,
                  'c:\\foo\\qux': 60,
                  'c:\\foo\\quy': 36}
        mtime.side_effect = lambda p: mtimes[p]
        ctime.side_effect = lambda p: ctimes[p]
        result = photocoll.find_new_photos(30, 'c:\\foo', {'.txt'})
        self.assertEqual(['c:\\foo\\qux', 'c:\\foo\\quy'], result)


if __name__ == '__main__':
    unittest.main()
