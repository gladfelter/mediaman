import glob
import logging
import os
import os.path
import photoman
import media_common
import shutil
import tempfile
import unittest
from mock import *


class PhotoManFunctionalTests(unittest.TestCase):

  def setUp(self):
    root = logging.getLogger('')
    # prevent log messages from cluttering unit test output
    root.setLevel(logging.CRITICAL)

  @patch('grp.getgrnam', new=lambda x: [None, None, -1])
  @patch('os.chown', new=lambda x, y, z : None)
  def testNewDatabase(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, False, 'foo')
      files = [
          os.path.join(tmpdir, 'dest/media/media.db'),
          os.path.join(tmpdir,
                       'dest/media/photos/2012/07_July/gnexus 160.jpg'),
          os.path.join(tmpdir, 'dest/media/photos/2002/'
                       + '10_October/105-0555_IMG.JPG'),
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
          os.path.join(tmpdir, 'src/foo/gnexus 160.jpg')]
      for filepath in files:
        self.assertTrue(os.path.isfile(filepath), 'Expect %s exists'
                        % filepath)
    finally:
      shutil.rmtree(tmpdir)

  @patch('grp.getgrnam', new=lambda x: [None, None, -1])
  @patch('os.chown', new=lambda x, y, z : None)
  def testNewDatabaseDeleteSource(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True, 'foo')
      files = [
          os.path.join(tmpdir, 'src/DSC09012.JPG'),
          os.path.join(tmpdir, 'src/IMG_1427.JPG'),
          os.path.join(tmpdir, 'src/594-9436_IMG.JPG'),
          os.path.join(tmpdir, 'src/105-0555_IMG.JPG'),
          os.path.join(tmpdir, 'src/gnexus 160.jpg')]
      for filepath in files:
        self.assertFalse(os.path.isfile(filepath), 'Expect %s is deleted' %
                         filepath)
    finally:
      shutil.rmtree(tmpdir)

  @patch('grp.getgrnam', new=lambda x: [None, None, -1])
  @patch('os.chown', new=lambda x, y, z : None)
  def testRefreshDatabaseWithDeleteSource(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True, 'foo')
      # Re-run and delete source, this should not cause any
      # library files to be deleted
      photoman._find_and_archive_photos(srcdir, mediadir, True, 'foo')
      files = [
          os.path.join(tmpdir,
                       'dest/media/photos/2012/07_July/gnexus 160.jpg'),
          os.path.join(tmpdir, 'dest/media/photos/2002/'
                       + '10_October/105-0555_IMG.JPG'),
          os.path.join(tmpdir,
                       'dest/media/photos/2003/03_March/594-9436_IMG.JPG'),
          os.path.join(tmpdir,
                       'dest/media/photos/2006/03_March/IMG_1427.JPG'),
          os.path.join(tmpdir,
                       'dest/media/photos/2006/06_June/DSC09012.JPG')]
      for filepath in files:
        self.assertTrue(os.path.isfile(filepath), 'Expect %s wasnt deleted'
                        % filepath)
    finally:
      shutil.rmtree(tmpdir)

  @patch('grp.getgrnam', new=lambda x: [None, None, -1])
  @patch('os.chown', new=lambda x, y, z : None)
  def testDuplicateFiles(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True, 'foo')
      self._copy_test_images(srcdir, 'dup_')
      photoman._find_and_archive_photos(srcdir, mediadir, False, 'foo')
      #print 'testDuplicatefiles Result'
      #self._print_tree(tmpdir)
    finally:
      shutil.rmtree(tmpdir)

  @patch('grp.getgrnam', new=lambda x: [None, None, -1])
  @patch('os.chown', new=lambda x, y, z : None)
  def test_query_all(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      photoman._find_and_archive_photos(srcdir, mediadir, True, 'foo')
      rep = media_common.Repository()
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

  @patch('grp.getgrnam', new=lambda x: [None, None, -1])
  @patch('os.chown', new=lambda x, y, z : None)
  def test_scan_missing(self):
    (srcdir, mediadir, tmpdir) = self._setup_test_data()
    try:
      rows = 0
      photoman._find_and_archive_photos(srcdir, mediadir, True, 'foo')
      rep = media_common.Repository()
      rep.open(os.path.join(mediadir))
      rows = self._get_row_count(rep)
      rep.close()
      os.remove(os.path.join(mediadir,
                             'photos/2012/07_July/gnexus 160.jpg'))
      photoman._scan_missing_photos(mediadir)
      rep = media_common.Repository()
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

  def _copy_test_images(self, destdir, prefix):
    scriptdir = os.path.dirname(os.path.realpath(__file__))
    test_data_dir = os.path.join(scriptdir, 'test')
    test_files = glob.glob(os.path.join(test_data_dir, '*.jpg'))
    test_files += glob.glob(os.path.join(test_data_dir, '*.JPG'))
    test_files = sorted(test_files)
    self.assertEquals(5, len(test_files))
    if not os.path.exists(os.path.join(destdir, 'foo')):
      os.mkdir(os.path.join(destdir, 'foo'))
    for test_file in test_files[:-1]:
      dup_file = os.path.join(destdir, prefix + os.path.basename(test_file))
      shutil.copy(test_file, dup_file)
    for test_file in test_files[-1:]:
      dup_file = os.path.join(destdir, 'foo',
                              prefix + os.path.basename(test_file))
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
