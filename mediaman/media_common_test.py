#! /usr/bin/python

import datetime
import logging
import os
import os.path
import media_common
import pyexiv2
import sqlite3
import time
import unittest
from mock import *


class TestRepository(unittest.TestCase):

  def setUp(self):
    self.rep = media_common.Repository()
    pass

  @patch('sqlite3.dbapi2.connect')
  @patch('os.access')
  @patch('media_common.Repository._tree_setup')
  def test_open(self, tree_setup, access, connect):
    access.return_value = True
    conn_mock = Mock()
    cur_mock = Mock()
    conn_mock.cursor.return_value = cur_mock()
    connect.return_value = conn_mock
    self.rep.open('/tmp/bar')
    db_name = '/tmp/bar/media.db'
    if os.name == 'nt':
      db_name = '/tmp/bar\\media.db'
    access.assert_called_with(db_name, ANY)
    connect.assert_called_with(db_name)
    self.assertFalse(conn_mock.cursor.called,
                    'expect cursor not needed for existing database')
    self.assertTrue(tree_setup.called,
                     'expect tree_setup always called')

  @patch('sqlite3.dbapi2.connect')
  @patch('os.access')
  @patch('media_common.Repository._tree_setup')
  def test_create(self, tree_setup, access, connect):
    access.return_value = False
    conn_mock = Mock(name="connection_mock", spec_set=['cursor'])
    cur_mock = Mock(name="cursor_mock", spec_set=['execute'])
    conn_mock.cursor.return_value = cur_mock
    connect.return_value = conn_mock
    self.rep.open('/tmp/bar')
    db_name = '/tmp/bar/media.db'
    if os.name == 'nt':
      db_name = '/tmp/bar\\media.db'
    access.assert_called_with(db_name, ANY)
    connect.assert_called_with(db_name)
    self.assertTrue(conn_mock.cursor.called,
                    'expect cursor needed for new database')
    self.assertTrue(cur_mock.execute.called,
                    'expect insert table called for new database')
    self.assertTrue(tree_setup.called,
                     'expect tree_setup always called')

  @patch('os.mkdir')
  def test_tree_setup(self, mkdir):
    media_common.Repository()._tree_setup('/tmp/foo')
    self.assertEquals(2, mkdir.call_count)

  def _execute_tester(self, method):
    rep = media_common.Repository()
    rep.con = MagicMock()
    rep.con.cursor.return_value.execute.return_value = [1, 4]
    self.assertEquals(rep.con.cursor.return_value, method(rep))
    self.assertTrue(rep.con.cursor.return_value.execute.called)

  def test_iter_all_photos(self):
    rep = media_common.Repository()
    rep.con = MagicMock()
    rep.con.cursor.return_value.execute.return_value = [1, 4]
    self.assertEquals(rep.con.cursor.return_value, rep.iter_all_photos())
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
    self.assertEquals(None, rep.con, 'expect connection removed')
    self.assertEquals(call.commit(), connection.mock_calls[0])
    self.assertEquals(call.close(), connection.mock_calls[1])
  
  def test_add_or_update(self):
    rep = media_common.Repository()
    photo = Mock()
    rep.con = Mock()
    rep.con.cursor.return_value.lastrowid = 42
    self.assertEquals(42, rep.add_or_update(photo))
    self.assertTrue(rep.con.cursor.called)
    self.assertTrue(rep.con.cursor.return_value.execute.called)
    self.assertTrue(rep.con.commit.called)

  def test_lookup_hash(self):
    rep = media_common.Repository()
    rep.con = MagicMock()
    fetch_mock = rep.con.cursor.return_value.execute.return_value.fetchone
    fetch_mock.return_value = (42, '/tmp/foo')
    self.assertEquals('/tmp/foo', rep.lookup_hash('bar')[1])

  def test_lookup_hash_not_found(self):
    rep = media_common.Repository()
    rep.con = MagicMock()
    fetch_mock = rep.con.cursor.return_value.execute.return_value.fetchone
    fetch_mock.return_value = None
    self.assertEquals(None, rep.lookup_hash('bar'))

  def test_get_db_name(self):
    rep = media_common.Repository()
    self.assertEquals('media.db', rep._get_db_name())

  def test_init_db(self):
    rep = media_common.Repository()
    cur = Mock()
    rep._init_db(cur)
    self.assertTrue(cur.execute.called)


class TestCollectionRepository(unittest.TestCase):
  
  def test_add_or_update(self):
    rep = media_common.CollectionRepository()
    photo = Mock()
    rep.con = Mock()
    rep.con.cursor.return_value.lastrowid = 42
    self.assertEquals(42, rep.add_or_update(photo))
    self.assertTrue(rep.con.cursor.called)
    self.assertTrue(rep.con.cursor.return_value.execute.called)
    self.assertTrue(rep.con.commit.called)

  def test_get_db_name(self):
    rep = media_common.CollectionRepository()
    self.assertEquals('local_media.db', rep._get_db_name())

  def test_init_db(self):
    rep = media_common.CollectionRepository()
    cur = Mock()
    rep._init_db(cur)
    self.assertTrue(cur.execute.called)


class TestPhoto(unittest.TestCase):

  def setUp(self):
    self.photo = media_common.Photo('/tmp/foo.jpg')
    self.time_struct = time.strptime('2012-08-19 15:14:04', '%Y-%m-%d %H:%M:%S')
    self.timestamp = time.mktime(self.time_struct)
    self.datetime_obj = datetime.datetime.fromtimestamp(self.timestamp)
    pass

  @patch('pyexiv2.ImageMetadata')
  def test_get_path_parts(self, image):
    self.photo.metadata_read = True
    self.photo.timestamp = self.timestamp
    self.assertEquals((2012, 8, 'foo.jpg'), self.photo.get_path_parts())

  @patch('pyexiv2.ImageMetadata')
  def test_get_path_parts_uninitialized(self, image):
    self.photo.metadata_read = False
    with patch.object(self.photo, 'load_metadata') as ts:
      self.photo.timestamp = self.timestamp
      self.assertEquals((2012, 8, 'foo.jpg'), self.photo.get_path_parts())
      self.assertTrue(self.photo.load_metadata.called)

  @patch('pyexiv2.ImageMetadata')
  def test_load_metadata(self, image):
    instance = image.return_value
    with patch.object(self.photo, '_load_exif_timestamp') as ts:
      with patch.object(self.photo, '_load_camera_make') as cmake:
        with patch.object(self.photo, '_load_camera_model') as cmodel:
          with patch.object(self.photo, '_load_file_size') as fs:
            with patch.object(self.photo,
                              '_load_filesystem_timestamp') as fts:
              with patch.object(self.photo, 'get_hash') as gh:
                self.photo.load_metadata()
                self.assertTrue(ts.called)
                self.assertTrue(self.photo._load_camera_make.called)
                self.assertTrue(self.photo._load_camera_model.called)
                self.assertTrue(self.photo._load_file_size.called)

  def test_load_exif_timestamp(self):
    m = MagicMock(spec_set=['__getitem__'])
    image_keys = ['Exif.Image.DateTimeOriginal']
    m.__getitem__.return_value.value = self.datetime_obj
    self.photo._load_exif_timestamp(m, image_keys)
    self.assertEquals(self.timestamp, self.photo.timestamp)

  @patch('os.path.getmtime')
  def test_load_filesystem_timestamp(self, getmtime):
    getmtime.return_value = self.timestamp
    self.photo._load_filesystem_timestamp()
    self.assertEquals(self.timestamp, self.photo.timestamp)

  def test_load_camera_make(self):
    m = MagicMock(spec_set=['__getitem__'])
    image_keys = ['Exif.Image.Make']
    m.__getitem__.return_value.value = 'Foo'
    self.photo._load_camera_make(m, image_keys)
    self.assertEquals('Foo', self.photo.camera_make)

  def test_load_camera_model(self):
    m = MagicMock(spec_set=['__getitem__'])
    image_keys = ['Exif.Image.Model']
    m.__getitem__.return_value.value = 'Bar'
    self.photo._load_camera_model(m, image_keys)
    self.assertEquals('Bar', self.photo.camera_model)


if os.name != 'nt':
  class TestUtilityFunctions(unittest.TestCase):

    @patch('grp.getgrnam')
    def test_get_group_id(self, getgrnam):
      getgrnam.return_value = [None, None, 42]
      self.assertEquals(42, media_common.get_group_id('foo'))
      self.assertEquals(-1, media_common.get_group_id(None))


if __name__ == '__main__':
  unittest.main()
