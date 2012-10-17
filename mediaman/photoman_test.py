#! /usr/bin/python
import unittest
from mock import *
import sqlite3
import os
import time
import photoman
import pyexiv2
import tempfile
import glob
import shutil


class TestRepository(unittest.TestCase):

  def setUp(self):
    self.rep = photoman.Repository()
    pass

  @patch('sqlite3.dbapi2.connect')
  @patch('os.access')
  @patch('photoman.Repository._tree_setup')
  def test_open(self, tree_setup, access, connect):
    access.return_value = True
    conn_mock = Mock()
    cur_mock = Mock()
    conn_mock.cursor.return_value = cur_mock()
    connect.return_value = conn_mock
    self.rep.open('/tmp/bar')
    access.assert_called_with('/tmp/bar', ANY)
    connect.assert_called_with('/tmp/bar/media.db')
    self.assertFalse(conn_mock.cursor.called,
                    'expect cursor not needed for existing database')
    self.assertFalse(tree_setup.called,
                     'expect tree_setup not needed for existing database')

  @patch('sqlite3.dbapi2.connect')
  @patch('os.access')
  @patch('photoman.Repository._tree_setup')
  def test_create(self, tree_setup, access, connect):
    access.return_value = False
    conn_mock = Mock(name="connection_mock", spec_set=['cursor'])
    cur_mock = Mock(name="cursor_mock", spec_set=['execute'])
    conn_mock.cursor.return_value = cur_mock
    connect.return_value = conn_mock
    self.rep.open('/tmp/bar')
    access.assert_called_with('/tmp/bar', ANY)
    connect.assert_called_with('/tmp/bar/media.db')
    self.assertTrue(conn_mock.cursor.called,
                    'expect cursor needed for new database')
    self.assertTrue(cur_mock.execute.called,
                    'expect insert table called for new database')
    self.assertTrue(tree_setup.called,
                     'expect tree_setup needed for new database')

  @patch('os.mkdir')
  def test_tree_setup(self, mkdir):
    photoman.Repository()._tree_setup('/tmp/foo')
    self.assertEquals(2, mkdir.call_count)

  
  def test_add(self):
    rep = photoman.Repository()
    photo = Mock()
    rep.con = Mock()
    rep.con.cursor.return_value.lastrowid = 42
    self.assertEquals(42, rep.add(photo))
    self.assertTrue(rep.con.cursor.called)
    self.assertTrue(rep.con.cursor.return_value.execute.called)
    self.assertTrue(rep.con.commit.called)


class TestPhoto(unittest.TestCase):

  def setUp(self):
    self.photo = photoman.Photo('/tmp/foo.jpg')
    self.time_struct = time.strptime('2012-08-19 15:14:04', '%Y-%m-%d %H:%M:%S')
    self.timestamp = time.mktime(self.time_struct)
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
            with patch.object(self.photo, '_load_filesystem_timestamp') as fts:
              with patch.object(self.photo, 'get_hash') as fts:
                self.photo.load_metadata()
                self.assertTrue(ts.called)
                self.assertTrue(self.photo._load_camera_make.called)
                self.assertTrue(self.photo._load_camera_model.called)
                self.assertTrue(self.photo._load_file_size.called)

  def test_load_exif_timestamp(self):
    m = MagicMock(spec_set=['__getitem__'])
    image_keys = ['Exif.Image.DateTimeOriginal']
    m.__getitem__.return_value.value = '2012-08-19 15:14:04'
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

class PhotoManFunctionalTests(unittest.TestCase):

  def testNewDatabase(self):
    scriptdir = os.path.dirname(os.path.realpath(__file__))
    test_data_dir = os.path.join(scriptdir, 'test')
    tmpdir = tempfile.mkdtemp()
    try:
      srcdir = os.path.join(tmpdir, 'src')
      destdir = os.path.join(tmpdir, 'dest')
      mediadir = os.path.join(destdir, 'media')
      os.mkdir(srcdir)
      os.mkdir(destdir)
      test_files = glob.glob(os.path.join(test_data_dir, '*.jpg'))
      test_files += glob.glob(os.path.join(test_data_dir, '*.JPG'))
      for test_file in test_files:
        shutil.copy(test_file, srcdir)
      photoman.read_photos(srcdir, mediadir)
      self._printTree(tmpdir)
    finally:
      shutil.rmtree(tmpdir)

  def _printTree(self, basedir):
    print basedir + '/'
    dirs = []
    for obj in os.listdir(basedir):
      full_path = os.path.join(basedir, obj)
      if os.path.isfile(full_path):
        print os.path.join(basedir, full_path)
      elif os.path.isdir(full_path):
        dirs.append(full_path)
    for dirname in dirs:
      self._printTree(dirname)


      

if __name__ == '__main__':
  unittest.main()
