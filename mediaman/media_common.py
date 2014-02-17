""" Common operations and types for media collection and management
"""

import ctypes
import logging
import os
import os.path
import sys
import xmlrpclib
import time
import hashlib
import pyexiv2
from sqlite3 import dbapi2 as sqlite

if os.name == 'nt':
  from ctypes import windll, wintypes
  DWORD = wintypes.DWORD
  WORD = wintypes.WORD
  BYTE = wintypes.BYTE
  class GUID(ctypes.Structure):
      _fields_ = [
           ('Data1', DWORD),
           ('Data2', WORD),
           ('Data3', WORD),
           ('Data4', BYTE * 8)
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
else:
  import grp


class Repository():

  """Represents a repository of media items, such as photos"""

  def __init__(self):
    self.con = None

  def open(self, lib_base_dir):  # opens, returns biggest ID or -1 on error
    """Opens or creates the repository and media library"""
    self._tree_setup(lib_base_dir)
    # create data store if it doesn't exist
    db_path = os.path.join(lib_base_dir, self._get_db_name())
    if not os.access(db_path, os.R_OK|os.W_OK):
      logging.warning("can't open %s, will attempt to create it", 
                      lib_base_dir)
      # initialize the database
      self.con = sqlite.connect(os.path.join(lib_base_dir,
          self._get_db_name()))
      cur = self.con.cursor()
      self._init_db(cur)
    else:  
      self.con = sqlite.connect(os.path.join(lib_base_dir,
          self._get_db_name()))
    if self.con <= 0:
      raise RuntimeError("Could not open the media database" +
                         "for an unknown reason")

  def close(self):
    """Closes the repository."""
    self.con.commit()
    self.con.close()
    self.con = None
  
  def add_or_update(self, photo):
    """Adds a photo to the repository."""
    cur = self.con.cursor()
    cur.execute('''
INSERT OR REPLACE INTO photos (id, flags, md5, size, description,
                               source_info, camera_make,
                               camera_model, archive_path,
                               timestamp)
SELECT old.id, old.flags, new.md5, new.size, old.description,
       old.source_info, new.camera_make, new.camera_model,
       new.archive_path, new.timestamp
FROM ( SELECT
     :md5             AS md5,
     :size            AS size,
     :camera_make     AS camera_make,
     :camera_model    AS camera_model,
     :archive_path     AS archive_path,
     :timestamp       AS timestamp
 ) AS new
LEFT JOIN (
           SELECT id, flags, description, source_info, md5
           FROM photos
) AS old ON new.md5 = old.md5;
                ''', photo.__dict__)
    self.con.commit()
    return cur.lastrowid

  def remove(self, photo):
    """Removes a photo from the repository."""
    cur = self.con.cursor()
    cur.execute('''
        DELETE FROM photos WHERE md5 = ?''',
        [photo.md5])

  def lookup_hash(self, md5):
    """Returns the filepath and id of the existing file with the
    provided hash, or None if no such file exists"""
    cur = self.con.cursor()
    logging.info('looking for hash %s', md5)
    rows = cur.execute('''
        SELECT id, archive_path FROM photos WHERE md5 = :md5 ''', locals())
    row = rows.fetchone()
    if row != None:
      logging.debug('Fond row object %s', row)
      return row

    return None

  def iter_all_photos(self):
    """Returns an iterator returning (id, filepath) for all photos"""
    cur = self.con.cursor()
    cur.execute('''
      select id, archive_path FROM photos''')
    return cur

  def remove_photos(self, photo_ids):
    cur = self.con.cursor()
    query = (' DELETE from photos where id in (' +
            ','.join('?'*len(photo_ids)) + ')')
    cur.execute(query, photo_ids)

  def _tree_setup(self, lib_base_dir):
    """Creates the media library directories"""
    if not os.path.exists(lib_base_dir):
      os.mkdir(lib_base_dir, 0755)
    photos_dir = os.path.join(lib_base_dir, 'photos')
    if not os.path.exists(photos_dir):
      os.mkdir(photos_dir, 0755)

  def _get_db_name(self):
    return 'media.db'

  def _init_db(self, db_cur):
      db_cur.execute('''create table photos
        (id integer primary key,
        flags text,
        md5 varchar(16),
        size integer,
        description text,
        source_info text,
        archive_path text,
        timestamp integer,
        camera_make text,
        camera_model text,
        unique (md5) on conflict replace);
        ''')


class CollectionRepository(Repository):

  def add_or_update(self, photo):
    """Adds a photo to the repository."""
    cur = self.con.cursor()
    cur.execute('''
INSERT OR REPLACE INTO photos (id, archive_path, md5, modified)
SELECT old.id, old.archive_path, new.md5, new.modified
FROM ( SELECT
     :md5             AS md5,
     :modified        AS modified
     :archive_path    AS archive_path
 ) AS new
LEFT JOIN (
           SELECT id, md5, modified, archive_path
           FROM photos
) AS old ON new.archive_path = old.archive_path;
                ''', photo.__dict__)
    self.con.commit()
    return cur.lastrowid

  def _get_db_name(self):
    return 'local_media.db'

  def _init_db(self, db_cur):
      db_cur.execute('''create table photos
        (id integer primary key,
        md5 varchar(16),
        archive_path text,
        modified integer,
        unique (archive_path) on conflict replace);
        ''')


  def lookup_filepath(self, filepath):
    """Returns the filepath and id of the existing file with the
    provided hash, or None if no such file exists"""
    cur = self.con.cursor()
    logging.info('looking for hash %s', md5)
    rows = cur.execute('''
        SELECT id, archive_path FROM photos WHERE md5 = :md5 ''', locals())
    row = rows.fetchone()
    if row != None:
      logging.debug('Fond row object %s', row)
      return row

    return None


class Photo():

  """Represents a a file containing a photo"""
  
  def __init__(self, source_path):
    self.db_id = self.flags = self.md5 = None
    self.modified = None
    self.size = self.description = None
    self.timestamp = self.archive_path = None
    self.camera_make = self.camera_model = None
    self.source_info = None
    self.source_path = source_path
    self.metadata_read = False

  def get_path_parts(self):
    """Gets the year/month/basename tuple for the file, based on its
    creation time metadata."""
    if not self.metadata_read:
      self.load_metadata()
    time_struct = time.localtime(self.timestamp)
    return time_struct[0:2] + (os.path.basename(self.source_path),)
 
  def load_metadata(self):
    """Loads relevant exif and filesystem metadata for the photo"""
    metadata = None
    try:
      metadata = pyexiv2.ImageMetadata(self.source_path)
      metadata.read()
    except IOError:
      metadata = None
      logging.warning("%s contains no EXIF data", self.source_path)
    except Exception:
      metadata = None
      logging.warning('An unexpected error occurred while reading '
                      + 'exif data from %s. Will attempt to recover',
                      self.source_path)

    if metadata is not None:
      image_keys = frozenset(metadata.exif_keys)
      self._load_exif_timestamp(metadata, image_keys)
      self._load_camera_make(metadata, image_keys)
      self._load_camera_model(metadata, image_keys)

    self._load_filesystem_timestamp()
    self._load_file_size()
    self.md5 = self.get_hash()
    self.metadata_read = True

  def _load_file_size(self):
    """ Gets the size in bytes of the photo from the filesystem"""
    try:
      self.size = os.path.getsize(self.source_path)
    except os.error:
      self.size = 0
      logging.warning('Could not read file size of %s', self.source_path)

  def _load_camera_model(self, metadata, image_keys):
    """Gets the camera's model for the photo from the exif data."""
    if 'Exif.Image.Model' in image_keys:
      self.camera_model = metadata['Exif.Image.Model'].value

  def _load_camera_make(self, metadata, image_keys):
    """Gets the camera's make for the photo from the exif data."""
    if 'Exif.Image.Make' in image_keys:
      self.camera_make = metadata['Exif.Image.Make'].value

  def _load_exif_timestamp(self, metadata, image_keys):
    """Gets the photo's creation time from the photo's exif data"""
    time_keys = ['Exif.Image.DateTimeOriginal', 'Exif.Photo.DateTime',
                 'Exif.Photo.DateTimeDigitized']
    for key in time_keys:
      if key in image_keys:
        try:
          time_struct = metadata[key].value.timetuple()
          self.timestamp = time.mktime(time_struct)
          break
        except (ValueError, AttributeError):
          logging.warning('There was a problem reading the exif '
                          + 'timestamp for %s.', self.source_path)

  def _load_filesystem_timestamp(self):
    """Gets the last modified timestamp for the photo."""
    if self.timestamp is None:
      try:
        self.timestamp = os.path.getmtime(self.source_path)
      except os.error:
        logging.warning('Could not access image''s timestamp' +
                        ' by any means, setting it to the epoch start.')
        self.timestamp = 0
      
  def get_hash(self):
    """Computes the md5 hash."""
    photo = open(self.source_path, 'r')
    metadata = hashlib.md5()
    stuff = photo.read(8192)
    while len(stuff) > 0:
      metadata.update(stuff)
      stuff = photo.read(8192)
    photo.close()
    return (metadata.hexdigest())


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
  if os.name == 'posix':
    return '/var/tmp'
  else:
    status_dir = os.path.join(get_local_appdata_directory()[1],
                              u'gladfelter', u'media_collection')
    if not os.path.exists(status_dir):
      os.makedirs(status_dir)
    return status_dir


def configure_logging(filename):
  """Configures logging to stderr, file."""
  root = logging.getLogger('')
  handler = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s' +
                                ':%(lineno)d %(levelname)s %(message)s')
  handler.setFormatter(formatter)
  root.addHandler(handler)
  log_dir = configure_status_dir()
  file_handler = logging.FileHandler(os.path.join(log_dir, filename))
  file_handler.setFormatter(formatter)
  root.addHandler(file_handler)
  root.setLevel(logging.INFO)


def get_group_id(group_name):
  """ Returns the group id for the given group name """
  if group_name is not None:
    return grp.getgrnam(group_name)[2]
  else:
    # means 'don't change group'
    return -1
