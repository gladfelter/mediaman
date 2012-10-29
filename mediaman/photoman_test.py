#! /usr/bin/python

import datetime
import glob
import logging
import os
import photoman
import pyexiv2
import shutil
import sqlite3
import tempfile
import time
import unittest
from mock import *


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
    access.assert_called_with('/tmp/bar/media.db', ANY)
    connect.assert_called_with('/tmp/bar/media.db')
    self.assertFalse(conn_mock.cursor.called,
                    'expect cursor not needed for existing database')
    self.assertTrue(tree_setup.called,
                     'expect tree_setup always called')

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
    photoman.Repository()._tree_setup('/tmp/foo')
    self.assertEquals(2, mkdir.call_count)

  def _execute_tester(self, method):
    rep = photoman.Repository()
    rep.con = MagicMock()
    rep.con.cursor.return_value.execute.return_value = [1, 4]
    self.assertEquals(rep.con.cursor.return_value, method(rep))
    self.assertTrue(rep.con.cursor.return_value.execute.called)

  def test_iter_all_photos(self):
    rep = photoman.Repository()
    rep.con = MagicMock()
    rep.con.cursor.return_value.execute.return_value = [1, 4]
    self.assertEquals(rep.con.cursor.return_value, rep.iter_all_photos())
    self.assertTrue(rep.con.cursor.return_value.execute.called)

  def test_remove_photos(self):
    rep = photoman.Repository()
    rep.con = MagicMock()
    execute = rep.con.cursor.return_value.execute
    rep.remove_photos([1, 4])
    execute.assert_called_with(ANY, [1, 4])

  def test_remove(self):
    rep = photoman.Repository()
    rep.con = MagicMock()
    execute = rep.con.cursor.return_value.execute
    photo = MagicMock()
    photo.md5 = 42
    rep.remove(photo)
    execute.assert_called_with(ANY, [42])

  def test_close(self):
    rep = photoman.Repository()
    connection = MagicMock()
    rep.con = connection
    rep.close()
    self.assertEquals(None, rep.con, 'expect connection removed')
    self.assertEquals(call.commit(), connection.mock_calls[0])
    self.assertEquals(call.close(), connection.mock_calls[1])
  
  def test_add_or_update(self):
    rep = photoman.Repository()
    photo = Mock()
    rep.con = Mock()
    rep.con.cursor.return_value.lastrowid = 42
    self.assertEquals(42, rep.add_or_update(photo))
    self.assertTrue(rep.con.cursor.called)
    self.assertTrue(rep.con.cursor.return_value.execute.called)
    self.assertTrue(rep.con.commit.called)

  def test_lookup_hash(self):
    rep = photoman.Repository()
    rep.con = MagicMock()
    fetch_mock = rep.con.cursor.return_value.execute.return_value.fetchone
    fetch_mock.return_value = (42, '/tmp/foo')
    self.assertEquals('/tmp/foo', rep.lookup_hash('bar')[1])

  def test_lookup_hash_not_found(self):
    rep = photoman.Repository()
    rep.con = MagicMock()
    fetch_mock = rep.con.cursor.return_value.execute.return_value.fetchone
    fetch_mock.return_value = None
    self.assertEquals(None, rep.lookup_hash('bar'))


class TestPhoto(unittest.TestCase):

  def setUp(self):
    self.photo = photoman.Photo('/tmp/foo.jpg')
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
              with patch.object(self.photo, '_get_hash') as gh:
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

class PhotoManFunctionalTests(unittest.TestCase):

  def setUp(self):
    root = logging.getLogger('')
    # prevent log messages from cluttering unit test output
    root.setLevel(logging.CRITICAL)

  def testNewDatabase(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, False)
      files = [
          os.path.join(tmpdir, 'dest/media/media.db'),
          os.path.join(tmpdir,
                       'dest/media/photos/2012/07_July/gnexus 160.jpg'),
          os.path.join(tmpdir,
                       'dest/media/photos/2002/10_October/105-0555_IMG.JPG'),
          os.path.join(tmpdir,
                       'dest/media/photos/2003/03_March/594-9436_IMG.JPG'),
          os.path.join(tmpdir,
                       'dest/media/photos/2006/03_March/IMG_1427.JPG'),
          os.path.join(tmpdir,
                       'dest/media/photos/2006/06_June/DSC09012.JPG'),
          os.path.join(tmpdir, 'src/DSC09012.JPG'),
          os.path.join(tmpdir, 'src/IMG_1427.JPG'),
          os.path.join(tmpdir, 'src/594-9436_IMG.JPG'),
          os.path.join(tmpdir, 'src/105-0555_IMG.JPG'),
          os.path.join(tmpdir, 'src/gnexus 160.jpg')]
      for filepath in files:
        self.assertTrue(os.path.isfile(filepath))
    finally:
      shutil.rmtree(tmpdir)

  def testNewDatabaseDeleteSource(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True)
      files = [
          os.path.join(tmpdir, 'src/DSC09012.JPG'),
          os.path.join(tmpdir, 'src/IMG_1427.JPG'),
          os.path.join(tmpdir, 'src/594-9436_IMG.JPG'),
          os.path.join(tmpdir, 'src/105-0555_IMG.JPG'),
          os.path.join(tmpdir, 'src/gnexus 160.jpg')]
      for filepath in files:
        self.assertFalse(os.path.isfile(filepath))
    finally:
      shutil.rmtree(tmpdir)

  def testDuplicateFiles(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True)
      self._copy_test_images(srcdir, 'dup_')
      photoman._find_and_archive_photos(srcdir, mediadir, False)
      #print 'testDuplicatefiles Result'
      #self._print_tree(tmpdir)
    finally:
      shutil.rmtree(tmpdir)

  def test_query_all(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True)
      rep = photoman.Repository()
      rep.open(mediadir)
      cur = rep.con.cursor()
      cur.execute('''
        select id, archive_path FROM photos''')
      rows = 0
      for row in cur:
        rows += 1
      self.assertEquals(5, rows)
      cur = rep.con.cursor()
      ids = [1, 5]
      cur.execute(' DELETE from photos where id in (' +
                  ','.join('?'*len(ids)) + ')', ids)
      cur.execute('''
        select id, archive_path FROM photos''')
      rows = 0
      for row in cur:
        rows += 1
      self.assertEquals(3, rows)
      rep.close()
    finally:
      shutil.rmtree(tmpdir)

  def test_scan_missing(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      rows = 0
      photoman._find_and_archive_photos(srcdir, mediadir, True)
      rep = photoman.Repository()
      rep.open(os.path.join(mediadir))
      rows = self._get_row_count(rep)
      rep.close()
      os.remove(os.path.join(mediadir,
                             'photos/2012/07_July/gnexus 160.jpg'))
      photoman._scan_missing_photos(mediadir)
      rep = photoman.Repository()
      rep.open(os.path.join(mediadir))
      self.assertEquals(rows - 1, self._get_row_count(rep))
      cur = rep.con.cursor()
      filepath = os.path.join(mediadir,
                          'photos/2012/07_July/gnexus 160.jpg')
      rows = cur.execute('''
        select id FROM photos WHERE archive_path = ?''', [filepath])
      self.assertEquals(None, rows.fetchone())
      rep.close()
    finally:
      shutil.rmtree(tmpdir)

  def _get_row_count(self, repository):
    cur = repository.con.cursor()
    cur.execute(''' select id, archive_path FROM photos''')
    rows = 0
    for row in cur:
      rows += 1
    return rows

  def _setup_test_data(self):
    tmpdir = tempfile.mkdtemp()
    srcdir = os.path.join(tmpdir, 'src')
    destdir = os.path.join(tmpdir, 'dest')
    mediadir = os.path.join(destdir, 'media')
    os.mkdir(srcdir)
    os.mkdir(destdir)
    self._copy_test_images(srcdir, '')
    return (srcdir, mediadir, tmpdir)

  def _copy_test_images(self, srcdir, prefix):
    scriptdir = os.path.dirname(os.path.realpath(__file__))
    test_data_dir = os.path.join(scriptdir, 'test')
    test_files = glob.glob(os.path.join(test_data_dir, '*.jpg'))
    test_files += glob.glob(os.path.join(test_data_dir, '*.JPG'))
    for test_file in test_files:
      dup_file = os.path.join(srcdir, prefix + os.path.basename(test_file))
      shutil.copy(test_file, dup_file)
    
  def _print_tree(self, basedir):
    print basedir + '/'
    dirs = []
    for obj in os.listdir(basedir):
      full_path = os.path.join(basedir, obj)
      if os.path.isfile(full_path):
        print os.path.join(basedir, full_path)
      elif os.path.isdir(full_path):
        dirs.append(full_path)
    for dirname in dirs:
      self._print_tree(dirname)

  @patch('shutil.copy2')
  @patch('os.path.exists')
  def test_copy_file(self, exists, copy2):
    exists.side_effect = [True, False]
    photoman._copy_file('/tmp/foo.txt', '/tmp/blah')
    copy2.assert_called_with('/tmp/foo.txt', '/tmp/blah/foo_1.txt')
      

if __name__ == '__main__':
  unittest.main()
