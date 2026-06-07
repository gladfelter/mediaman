#!/usr/bin/env python3

import logging
import os
import os.path
import media_common
import sqlite3
import time
import unittest
from unittest.mock import *


class TestRepository(unittest.TestCase):

    def setUp(self):
        self.rep = media_common.Repository()

    @patch('sqlite3.connect')
    @patch('os.access')
    @patch('media_common.Repository._tree_setup')
    def test_open(self, tree_setup, access, connect):
        access.return_value = True
        conn_mock = Mock()
        cur_mock = Mock()
        conn_mock.cursor.return_value = cur_mock
        connect.return_value = conn_mock
        self.rep.open('/tmp/bar')
        access.assert_called_with('/tmp/bar/media.db', ANY)
        connect.assert_called_with('/tmp/bar/media.db')
        self.assertFalse(conn_mock.cursor.called,
                         'expect cursor not needed for existing database')
        self.assertTrue(tree_setup.called,
                        'expect tree_setup always called')

    @patch('sqlite3.connect')
    @patch('os.access')
    @patch('media_common.Repository._tree_setup')
    def test_create(self, tree_setup, access, connect):
        access.return_value = False
        conn_mock = Mock(name="connection_mock", spec_set=['cursor'])
        cur_mock = Mock(name="cursor_mock", spec_set=['execute'])
        conn_mock.cursor.return_value = cur_mock
        connect.return_value = conn_mock
        self.rep.open('/tmp/bar')
        access.assert_called_with('/tmp/bar/media.db', ANY)
        connect.assert_called_with('/tmp/bar/media.db')
        self.assertTrue(conn_mock.cursor.called,
                        'expect cursor needed for new database')
        self.assertTrue(cur_mock.execute.called,
                        'expect insert table called for new database')
        self.assertTrue(tree_setup.called,
                        'expect tree_setup always called')

    @patch('os.mkdir')
    def test_tree_setup(self, mkdir):
        media_common.Repository()._tree_setup('/tmp/foo')
        self.assertEqual(2, mkdir.call_count)

    def test_iter_all_photos(self):
        rep = media_common.Repository()
        rep.con = MagicMock()
        rep.con.cursor.return_value.execute.return_value = [1, 4]
        self.assertEqual(rep.con.cursor.return_value, rep.iter_all_photos())
        self.assertTrue(rep.con.cursor.return_value.execute.called)

    def test_remove_photos(self):
        rep = media_common.Repository()
        rep.con = MagicMock()
        execute = rep.con.cursor.return_value.execute
        rep.remove_photos([1, 4])
        execute.assert_called_with(ANY, [1, 4])

    def test_remove(self):
        rep = media_common.Repository()
        rep.con = MagicMock()
        execute = rep.con.cursor.return_value.execute
        photo = MagicMock()
        photo.md5 = 42
        rep.remove(photo)
        execute.assert_called_with(ANY, [42])

    def test_close(self):
        rep = media_common.Repository()
        connection = MagicMock()
        rep.con = connection
        rep.close()
        self.assertIsNone(rep.con, 'expect connection removed')
        self.assertTrue(connection.commit.called)
        self.assertTrue(connection.close.called)

    def test_add_or_update(self):
        rep = media_common.Repository()
        photo = Mock()
        rep.con = Mock()
        rep.con.cursor.return_value.lastrowid = 42
        self.assertEqual(42, rep.add_or_update(photo))
        self.assertTrue(rep.con.cursor.called)
        self.assertTrue(rep.con.cursor.return_value.execute.called)
        self.assertTrue(rep.con.commit.called)

    def test_lookup_hash(self):
        rep = media_common.Repository()
        rep.con = MagicMock()
        fetch_mock = rep.con.cursor.return_value.execute.return_value.fetchone
        fetch_mock.return_value = (42, '/tmp/foo')
        self.assertEqual('/tmp/foo', rep.lookup_hash('bar')[1])

    def test_lookup_hash_not_found(self):
        rep = media_common.Repository()
        rep.con = MagicMock()
        fetch_mock = rep.con.cursor.return_value.execute.return_value.fetchone
        fetch_mock.return_value = None
        self.assertEqual(None, rep.lookup_hash('bar'))

    def test_lookup_hash_with_size(self):
        """lookup_hash with size parameter adds size to WHERE clause."""
        rep = media_common.Repository()
        rep.con = MagicMock()
        execute = rep.con.cursor.return_value.execute
        fetch_mock = execute.return_value.fetchone
        fetch_mock.return_value = (42, '/tmp/foo')
        result = rep.lookup_hash('abc', size=12345)
        self.assertEqual('/tmp/foo', result[1])
        # Verify the query includes both md5 and size
        call_args = execute.call_args[0]
        self.assertIn('size', call_args[0].lower())
        self.assertEqual({'md5': 'abc', 'size': 12345}, call_args[1])


class TestPhoto(unittest.TestCase):

    def setUp(self):
        self.photo = media_common.Photo('/tmp/foo.jpg')
        self.time_struct = time.strptime('2012-08-19 15:14:04',
                                         '%Y-%m-%d %H:%M:%S')
        self.timestamp = time.mktime(self.time_struct)

    def test_get_path_parts(self):
        self.photo.metadata_read = True
        self.photo.timestamp = self.timestamp
        self.assertEqual((2012, 8, 'foo.jpg'), self.photo.get_path_parts())

    def test_get_path_parts_uninitialized(self):
        self.photo.metadata_read = False
        with patch.object(self.photo, 'load_metadata') as lm:
            self.photo.timestamp = self.timestamp
            self.assertEqual((2012, 8, 'foo.jpg'),
                             self.photo.get_path_parts())
            self.assertTrue(lm.called)

    @patch.object(media_common.Photo, '_load_exif_metadata')
    @patch.object(media_common.Photo, '_load_file_size')
    @patch.object(media_common.Photo, '_load_filesystem_timestamp')
    @patch.object(media_common.Photo, '_get_hash')
    def test_load_metadata(self, gh, fts, fs, exif):
        self.photo.load_metadata()
        self.assertTrue(exif.called)
        self.assertTrue(fs.called)
        self.assertTrue(fts.called)
        self.assertTrue(gh.called)

    @patch('os.path.getmtime')
    def test_load_filesystem_timestamp(self, getmtime):
        getmtime.return_value = self.timestamp
        self.photo._load_filesystem_timestamp()
        self.assertEqual(self.timestamp, self.photo.timestamp)

    @patch('os.path.getmtime')
    def test_load_filesystem_timestamp_none(self, getmtime):
        self.photo.timestamp = None
        getmtime.return_value = self.timestamp
        self.photo._load_filesystem_timestamp()
        self.assertEqual(self.timestamp, self.photo.timestamp)


class TestUtilityFunctions(unittest.TestCase):

    @patch('grp.getgrnam')
    def test_get_group_id(self, getgrnam):
        getgrnam.return_value = [None, None, 42]
        self.assertEqual(42, media_common.get_group_id('foo'))
        self.assertEqual(-1, media_common.get_group_id(None))


if __name__ == '__main__':
    unittest.main()
