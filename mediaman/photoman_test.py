#! /usr/bin/python
import unittest
from mock import *
import sqlite3
import os
import photoman


class TestPhotoMan(unittest.TestCase):

  def setUp(self):
    pass

  @patch('sqlite3.dbapi2.connect')
  @patch('os.access')
  @patch('photoman.tree_setup')
  def test_store_open(self, tree_setup, access, connect):
    access.return_value = True
    conn_mock = Mock()
    cur_mock = Mock()
    conn_mock.cursor.return_value = cur_mock()
    connect.return_value = conn_mock
    photoman.store_open('/tmp/bar')
    access.assert_called_with('/tmp/bar', ANY)
    connect.assert_called_with('/tmp/bar/media.db')
    self.assertFalse(conn_mock.cursor.called,
                    'expect cursor not needed for existing database')
    self.assertFalse(tree_setup.called,
                     'expect tree_setup not needed for existing database')

  @patch('sqlite3.dbapi2.connect')
  @patch('os.access')
  @patch('photoman.tree_setup')
  def test_store_create(self, tree_setup, access, connect):
    access.return_value = False
    conn_mock = Mock(name="connection_mock", spec_set=['cursor'])
    cur_mock = Mock(name="cursor_mock", spec_set=['execute'])
    conn_mock.cursor.return_value = cur_mock
    connect.return_value = conn_mock
    photoman.store_open('/tmp/bar')
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
    photoman.tree_setup('/tmp/foo')
    self.assertEquals(2, mkdir.call_count)


if __name__ == '__main__':
  unittest.main()
