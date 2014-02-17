#! /c/Python27/python.exe
#
"""Photo collection utility
"""

import ctypes
import gflags
import logging
import os
import os.path
import pickle
import media_common
import shutil
import sys
import time
from ctypes import windll, wintypes


class CollectionStatus():
  
  LAST_COLLECTION = 'last_collection'

  def __init__(self, path, src_dir):
    self.status = dict()
    self.src_dir = os.path.realpath(src_dir)
    if path is not None:
      try:
        self.status = pickle.load(open(path, 'r'))
      except pickle.UnpicklingError:
        logging.exception('An error occurred while trying to read last' +
                          ' collection status, continuing')
      
  def get_last_collection(self):
    if self.LAST_COLLECTION in self.status:
      return self.status[self.LAST_COLLECTION].get(self.src_dir, 0)
    else:
      return 0

  def set_last_collection(self, time):
    collections = self.status.get(self.LAST_COLLECTION, dict())
    collections[self.src_dir] = time
    self.status[self.LAST_COLLECTION] = collections

  def save(self, path):
    pickle.dump(self.status, open(path, 'w'))


def get_repository():
  repository = media_common.CollectionRepository()
  repository.open(media_common.configure_status_dir())
  return repository


def read_collection_status(src_dir):
  status_file = os.path.join(media_common.configure_status_dir(), u'status.txt')
  
  if os.path.exists(status_file):
    return CollectionStatus(status_file, src_dir)
  else:
    return CollectionStatus(None, src_dir)


def write_collection_status(status):
  status_file = os.path.join(media_common.configure_status_dir(), u'status.txt')
  status.save(status_file)


def find_new_photos(rep, start_time, src_dir, ignore_extensions):
  paths = os.walk(src_dir)
  results = []
  for (dirpath, dirnames, filenames) in paths:
    mtime = os.path.getmtime(dirpath)
    ctime = os.path.getctime(dirpath)
    if (mtime > start_time or ctime > start_time):
      logging.info('Found a directory that has been modified ' +
                   'since the last collection, %s', dirpath)
      for filename in filenames:
        filepath = os.path.join(dirpath, filename)
        prefix, suffix = os.path.splitext(filepath)
        if suffix not in ignore_extensions:
          if True:
            results.append(os.path.join(dirpath, filename))
          else:
            photo = rep.lookup_filepath(filepath)
            if photo is None:
              results.append(filepath)
            elif (os.path.getmtime(filepath) != photo.modified
                  and photo.md5 != media_common.Photo(filepath).get_hash()):
              results.append(filepath)    

  return results


def copy_files(rep, files, dest_dir):
  for filepath in files:
    dirname, filename = os.path.split(filepath)
    prefix, suffix = os.path.splitext(filename)
    counter = 1
    destpath = os.path.join(dest_dir, filename)
    while os.path.exists(destpath): 
      destpath = os.path.join(dest_dir, prefix + '_' + str(counter) + suffix)
      counter += 1
    if counter != 1:
      logging.info('file %s had to be renamed to %s to avoid a conflict.',
                   filepath, destpath)
    shutil.copy2(filepath, destpath)


def collect_photos(src_dir, staging_dir, ignore_extensions):
  status = None
  start_time = time.time()
  try:
    status = read_collection_status(src_dir)
    last_coll = status.get_last_collection()
    logging.info('Starting photo collection: src_dir = %s, ' + 
                 'staging_dir = %s, last_collection = %s',
                 src_dir, staging_dir, time.ctime(last_coll))
    rep = get_repository()
    new_photos = find_new_photos(rep, last_coll, src_dir, ignore_extensions)
    logging.info('Found %d new photos', len(new_photos))
    copy_files(rep, new_photos, staging_dir)
    # finally, since successful:
    status.set_last_collection(start_time)
    write_collection_status(status)
  except:
    logging.exception('An unexpected error occurred during photo collection')


gflags.DEFINE_string('src_dir', media_common.get_pictures_directory()[1],
                     'Directory to scan for photos')
gflags.DEFINE_string('staging_dir', None, 'Directory for media staging')
gflags.DEFINE_list('ignore_extensions', [ '.ini', '.db' ],
                   'File extensions to ignore')
gflags.MarkFlagAsRequired('staging_dir')
FLAGS = gflags.FLAGS


def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  media_common.configure_logging('photocoll.log')
  collect_photos(FLAGS.src_dir, FLAGS.staging_dir, set(FLAGS.ignore_extensions))
  pass


if __name__ == '__main__':
  _main(sys.argv)
