#! c:\\Python27\\python.exe
#

import unittest
import photocoll
import os
import media_common
import os.path
from mock import *
import pickle


class PhotoCollectionTests(unittest.TestCase):

  def setUp(self):
    pass

  @patch('photocoll.find_new_photos')
  @patch('photocoll.get_repository')
  def test_collection(self, get_repository, find_photos):
    find_photos.return_value = []
    photocoll.collect_photos(None, None, set())

  @patch('os.path.exists')
  @patch('photocoll.CollectionStatus')
  @patch('media_common.configure_status_dir')
  def test_read_collection_status(self, configure_status_dir,
                                  stat, exists):
    configure_status_dir.return_value = 'c:\\foo'
    exists.return_value = True
    status = photocoll.read_collection_status('c:\\photos')
    stat.assert_called_with('c:\\foo\\status.txt', 'c:\\photos') 


  @patch('os.path.exists')
  @patch('photocoll.CollectionStatus')
  @patch('media_common.configure_status_dir')
  def test_read_collection_status_missing(self, configure_status_dir,
                                          stat, exists):
    configure_status_dir.return_value = '\\foo'
    exists.return_value = False
    status = photocoll.read_collection_status('c:\\photos')
    stat.assert_called_with(None, 'c:\\photos') 

  @patch('media_common.configure_status_dir')
  def test_write_collection_status(self, configure_status_dir):
    status = MagicMock()
    configure_status_dir.return_value = 'c:\\foo'
    photocoll.write_collection_status(status)
    status.save.assert_called_with('c:\\foo\status.txt')

  @patch('os.path.getmtime')
  @patch('os.path.getctime')
  @patch('os.walk')
  def test_find_new_photos(self, walk, ctime, mtime): 
    walk.return_value = [ ( 'c:\\foo', [ 'bar', 'bax' ],
                            [ 'baz', 'quz.txt' ] ),
                          ( 'c:\\foo\\bar', [ ], [ 'qux', 'quy.txt' ] ),
                          ( 'c:\\foo\\bax', [ ], [ 'bay', 'baw' ] ) ]
    mtimes = { 'c:\\foo' : 42,
               'c:\\foo\\bar' : 55,
               'c:\\foo\\bax' : 47,
               }
    ctimes = { 'c:\\foo' : 30,
               'c:\\foo\\bar' : 40,
               'c:\\foo\\bax' : 61,
             }
    mtime.side_effect = lambda filename : mtimes[filename]
    ctime.side_effect = lambda filename : ctimes[filename]
    rep = Mock()
    results = photocoll.find_new_photos(rep, 50, 'c:\\foo', set(['.txt']))
    self.assertEquals([ 'c:\\foo\\bar\\qux',
                        'c:\\foo\\bax\\bay',
                        'c:\\foo\\bax\\baw', ], results)


  @patch('os.path.exists')
  @patch('shutil.copy2')
  def test_copy_files(self, copy2, exists):
    existing = { 'c:\\foo\\bar.txt', 
                 'c:\\foo\\bar_1.txt', 'c:\\foo\\bar_3.txt' }
    exists.side_effect = lambda filename : filename in existing
    photocoll.copy_files([ 'c:\\baz\\bar.txt' ], 'c:\\foo')
    copy2.assert_called_with('c:\\baz\\bar.txt', 'c:\\foo\\bar_2.txt')
    self.assertEquals(1, copy2.call_count)


class CollectionStatusTests(unittest.TestCase):

  def setUp(self):
    pass

  @patch('pickle.dump')
  @patch('__builtin__.open')
  def test_save(self, open_fn, dump):
    open_fn.return_value = 1
    status = photocoll.CollectionStatus(None, 'c:\\photos')
    status.status['bar'] = 'baz'
    status.save('foo')
    open_fn.assert_called_with('foo', 'w')
    dump.assert_called_with({ 'bar' : 'baz' }, open_fn.return_value)

  def test_get_last_collection(self):
    status = photocoll.CollectionStatus(None, 'c:\\photos')
    status.status[photocoll.CollectionStatus.LAST_COLLECTION] = { 
        'c:\\photos' : 42 }
    self.assertEqual(42, status.get_last_collection())

  def test_set_last_collection(self):
    status = photocoll.CollectionStatus(None, 'c:\\photos')
    status.set_last_collection(42)
    self.assertEqual({ 'c:\\photos' : 42 },
                     status.status[photocoll.CollectionStatus.LAST_COLLECTION])

  @patch('pickle.load')
  @patch('__builtin__.open')
  def test_init(self, open_fn, load):
    open_fn.return_value = 1
    load.return_value = { photocoll.CollectionStatus.LAST_COLLECTION : 42 }
    status = photocoll.CollectionStatus('foo', 'c:\\photos')
    self.assertEquals(42, status.status[status.LAST_COLLECTION])
    

if __name__ == '__main__':
  unittest.main()
