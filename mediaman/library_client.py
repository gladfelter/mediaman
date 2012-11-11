#! /c/Python27/python.exe
#
"""Photo collection utility
"""

import logging
import xmlrpclib
import gflags

gflags.DEFINE_string('server_address', None, 'IP Address or hostname of ' +
                     'media library server')

gflags.MarkFlagAsRequired('server_address')

FLAGS = gflags.FLAGS

def file_is_in_library(filepath):
  server_path = query_hash_exists(FLAGS.server_address,
                                  get_md5_hash(filepath))
  return server_path is not None

def get_md5_hash(filepath)
  photo = open(self.source_path, 'r')
  metadata = hashlib.md5()
  stuff = photo.read(8192)
  while len(stuff) > 0:
    metadata.update(stuff)
    stuff = photo.read(8192)
  photo.close()
  return (metadata.hexdigest())


def query_hash_exists(server_address, hashcode):
  proxy = xmlrpclib.ServerProxy('http://' + server_address + '9333')
  return proxy.check_file_hash(hashcode)
