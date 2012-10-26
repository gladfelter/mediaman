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
import shutil
import sys
import time
from ctypes import windll, wintypes


class GUID(ctypes.Structure):
    _fields_ = [
         ('Data1', wintypes.DWORD),
         ('Data2', wintypes.WORD),
         ('Data3', wintypes.WORD),
         ('Data4', wintypes.BYTE * 8)
    ]
    def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
        """Create a new GUID."""
        self.Data1 = l
        self.Data2 = w1
        self.Data3 = w2
        self.Data4[:] = (b1, b2, b3, b4, b5, b6, b7, b8)
 
    def __repr__(self):
        b1, b2, b3, b4, b5, b6, b7, b8 = self.Data4
        return 'GUID(%x-%x-%x-%x%x%x%x%x%x%x%x)' % (
                   self.Data1, self.Data2, self.Data3, b1, b2, b3,
                   b4, b5, b6, b7, b8)
 
FOLDERID_LocalAppData = GUID(0xF1B32785, 0x6FBA, 0x4FCF, 0x9D, 0x55, 0x7B,
                             0x8E, 0x7F, 0x15, 0x70, 0x91)
FOLDERID_Pictures = GUID(0x33E28130, 0x4E1E, 0x4676, 0x83, 0x5A, 0x98, 0x39,
                         0x5C, 0x3B, 0xC3, 0xBB)
CSIDL_LOCAL_APPDATA = 0x001c
CSIDL_MYPICTURES = 0x27


class CollectionStatus():
  
  LAST_COLLECTION = 'last_collection'

  def __init__(self, path):
    self.status = dict()
    if path is not None:
      try:
        self.status = pickle.load(open(path, 'r'))
      except pickle.UnpicklingError:
        logging.exception('An error occurred while trying to read last' +
                          ' collection status, continuing')
      
  def get_last_collection(self):
    return self.status.get(self.LAST_COLLECTION, 0)

  def set_last_collection(self, time):
    self.status[self.LAST_COLLECTION] = time

  def save(self, path):
    pickle.dump(self.status, open(path, 'w'))


def get_known_folder(csidl, folderid):
  get_folder_path = getattr(windll.shell32, 'SHGetKnownFolderPath', None)
 
  if get_folder_path is not None:
    ptr = ctypes.c_wchar_p()
    get_known = windll.shell32.SHGetKnownFolderPath
    result = get_known(ctypes.byref(folderid), 0, 0,
                       ctypes.byref(ptr))
    return (result == 0, ptr.value)
  else:
    app_data_directory = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    dll = ctypes.windll.shell32
    result = dll.SHGetFolderPathW(0, csidl, 0, 0, app_data_directory)
    return (result == 0, app_data_directory.value)


def get_local_appdata_directory():
  return get_known_folder(CSIDL_LOCAL_APPDATA, FOLDERID_LocalAppData)


def get_pictures_directory():
  return get_known_folder(CSIDL_MYPICTURES, FOLDERID_Pictures)


def configure_status_dir():
  status_dir = os.path.join(get_local_appdata_directory()[1],
                            u'gladfelter', u'media_collection')
  if not os.path.exists(status_dir):
    os.makedirs(status_dir)
  return status_dir


def read_collection_status():
  status_file = os.path.join(configure_status_dir(), u'status.txt')
  
  if os.path.exists(status_file):
    return CollectionStatus(status_file)
  else:
    return CollectionStatus(None)


def write_collection_status(status):
  status_file = os.path.join(configure_status_dir(), u'status.txt')
  status.save(status_file)


def find_new_photos(start_time, src_dir, ignore_extensions):
  paths = os.walk(src_dir)
  results = []
  for (dirpath, dirnames, filenames) in paths:
    for filename in filenames:
      filepath = os.path.join(dirpath, filename)
      prefix, suffix = os.path.splitext(filepath)
      mtime = os.path.getmtime(filepath)
      ctime = os.path.getctime(filepath)
      if (mtime > start_time or ctime > start_time) and (
         suffix not in ignore_extensions):
        logging.info('Found a new photo, %s, with a creation date of %s and ' +
                     'a modification date of %s', filepath,
                     time.asctime(time.localtime(ctime)),
                     time.asctime(time.localtime(mtime)))
        results.append(os.path.join(dirpath, filename))

  return results


def copy_files(files, dest_dir):
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
    status = read_collection_status()
    last_coll = status.get_last_collection()
    logging.info('Starting photo collection: src_dir = %s, ' + 
                 'staging_dir = %s, last_collection = %s',
                 src_dir, staging_dir, time.ctime(last_coll))
    new_photos = find_new_photos(last_coll, src_dir, ignore_extensions)
    copy_files(new_photos, staging_dir)
    # finally, since successful:
    status.set_last_collection(start_time)
    write_collection_status(status)
  except:
    logging.exception('An unexpected error occurred during photo collection')


def _configure_logging():
  """Configures logging to stderr, file."""
  root = logging.getLogger('')
  handler = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s' +
                                ':%(lineno)d %(levelname)s %(message)s')
  handler.setFormatter(formatter)
  root.addHandler(handler)
  log_dir = configure_status_dir()
  file_handler = logging.FileHandler(os.path.join(log_dir, 'photocoll.log'))
  file_handler.setFormatter(formatter)
  root.addHandler(file_handler)
  root.setLevel(logging.INFO)


gflags.DEFINE_string('src_dir', get_pictures_directory()[1],
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
  _configure_logging()
  collect_photos(FLAGS.src_dir, FLAGS.staging_dir, set(FLAGS.ignore_extensions))
  pass


if __name__ == '__main__':
  _main(sys.argv)
