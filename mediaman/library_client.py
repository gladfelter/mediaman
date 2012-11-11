#! /c/Python27/python.exe
#
"""Photo collection utility
"""

import ctypes
import gflags
import logging
import os
import os.path
import sys
from ctypes import windll, wintypes
import xmlrpclib

FLAGS = gflags.FLAGS


def connect_to_server():
  proxy = xmlrpclib.ServerProxy('http://192.168.1.27:9333')
  print proxy.check_file_hash('9469d77d43ea667ea0eac61d3795a123')


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


def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  _configure_logging()
  connect_to_server()


if __name__ == '__main__':
  _main(sys.argv)
