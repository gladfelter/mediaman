#! /usr/bin/python
#
"""Photo organization utility.

Organizes source photos by date and updates a sqlite database with
metadata about the photos. Detects duplicates and ignores them.
"""
import calendar
import gflags
import hashlib
import logging
import os
import os.path
import pyexiv2
import shutil
import sys
import time
from sqlite3 import dbapi2 as sqlite

gflags.DEFINE_string('src_dir', None, 'Directory to scan for photos')
gflags.DEFINE_string('media_dir', None, 'Directory of media library')
gflags.DEFINE_boolean('del_src', False, 'Delete the source image if' +
                      ' succesfully archived')
gflags.MarkFlagAsRequired('src_dir')
gflags.MarkFlagAsRequired('media_dir')

FLAGS = gflags.FLAGS

class Repository():
  """Represents a repository of media items, such as photos"""

  def __init__(self):
    self.con = None

  def open(self, lib_base_dir):  # opens, returns biggest ID or -1 on error
    """Opens or creates the repository and media library"""
    # create data store if it doesn't exist
    if not os.access(lib_base_dir, os.R_OK|os.W_OK|os.X_OK):
      logging.warning("can't open %s, will attempt to create it", 
                      lib_base_dir)
      self._tree_setup(lib_base_dir)
      # initialize the database
      self.con = sqlite.connect(lib_base_dir + "/media.db")
      cur = self.con.cursor()
      cur.execute('''create table photos
        (id integer primary key,
        flags text,
        md5 varchar(16),
        size integer,
        description text,
        source_info text,
        source_path text,
        timestamp integer,
        camera_make text,
        camera_model text,
        unique (md5) on conflict replace);
        ''')
    else:  
      self.con = sqlite.connect(lib_base_dir + "/media.db")
    if self.con <= 0:
      raise RuntimeError("Could not open the media database" +
                         "for an unknown reason")

  def close(self):
    """Closes the repository."""
    self.con.close()
  
  def add(self, photo):
    """Adds a photo to the repository."""
    cur = self.con.cursor()
    cur.execute('''
        insert into photos (flags, md5, size, description, source_info,
        camera_make, camera_model, source_path, timestamp)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (photo.flags, photo.md5, photo.size, photo.description,
        photo.source_info, photo.camera_make, photo.camera_model,
        photo.dest_path, photo.timestamp)
    )
    self.con.commit()
    return cur.lastrowid

  def is_hash_present(self, md5):
    """Returns true a photo already has the specified hash"""
    cur = self.con.cursor()
    rows = cur.execute('''
        from photos select id where md5=?''', md5)
    return len(rows) > 0

  @staticmethod
  def _tree_setup(lib_base_dir):
    """Creates the media library directories"""
    os.mkdir(lib_base_dir, 0755)
    os.mkdir(lib_base_dir + '/photos', 0755)


class Photo():

  """Represents a a file containing a photo"""
  
  def __init__(self, source_path):
    self.db_id = self.flags = self.md5 = None
    self.size = self.description = None
    self.timestamp = self.dest_path = None
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
    self.md5 = self._get_hash()
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
        except ValueError:
          pass

  def _load_filesystem_timestamp(self):
    """Gets the last modified timestamp for the photo."""
    if self.timestamp is None:
      try:
        self.timestamp = os.path.getmtime(self.source_path)
      except os.error:
        logging.warning('Could not access image''s timestamp' +
                        ' by any means, setting it to the epoch start.')
        self.timestamp = 0
      
  def _get_hash(self):
    """Computes the md5 hash."""
    photo = open(self.source_path, 'r')
    metadata = hashlib.md5()
    stuff = photo.read(8192)
    while len(stuff) > 0:
      metadata.update(stuff)
      stuff = photo.read(8192)
    photo.close()
    return (metadata.hexdigest())


def _read_photos(search_dir, lib_base_dir):
  """Sets up or opens a media library and adds new photos
  to the library and its database."""
  rep = Repository()
  rep.open(lib_base_dir)
  photos = os.listdir(search_dir)
  logging.info('Found these photo files: %s', photos)
  for path in photos:
    path = os.path.join(search_dir, path)
    if os.path.isfile(path):
      photo = Photo(path)
      photo.load_metadata()
      _copy_photo(photo, lib_base_dir)
      photo.db_id = rep.add(photo)
      if photo.db_id > 0 and os.path.isfile(photo.dest_path):
        dest_photo = Photo(photo.dest_path)
        dest_photo.load_metadata()
        if dest_photo.md5 is not None and dest_photo.md5 == photo.md5:
          logging.info('%s was successfully copied to destination %s', 
                       photo.source_path, photo.dest_path)
          if FLAGS.del_src:
            logging.info('deleting the source file %s.',
                         photo.source_path)
            os.remove(photo.source_path)
        else:
          logging.warning('Destination photo file %s didn''t match ' +
                          'the hash of or wasn''t properly transferred ' +
                          'from %s', photo.dest_path, photo.source_path)
      else:
        logging.warning('%s was not copied to %s or it failed to be ' +
                        'inserted into the database, skipping deletion ' +
                        'of the original',
                        photo.source_path, photo.dest_path)
    else:
      logging.warning('Found a non-file when looking for photos: %s, ' +
                      'it will not be modified', path)

  rep.close()

def _copy_photo(photo, lib_base_dir):
  """Copies a photo file to its destination, computing the destionation
  from the file's metadata"""
  parts = photo.get_path_parts()
  relative_path = "%04d/%s/%s" % (parts[0], _get_month_name(parts[1]),
                                  parts[2])
  dest_path = os.path.join(lib_base_dir, 'photos', relative_path)
  photo.dest_path = dest_path
  dest_dir = os.path.dirname(photo.dest_path)
  if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)
  shutil.copy(photo.source_path, photo.dest_path)


def _get_month_name(month):
  """Returns a month identifier for a given decimal month"""
  return "%02d_%s" % (month, calendar.month_name[month])


def _configure_logging():
  """Configures logging to stderr, file."""
  root = logging.getLogger('')
  handler = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s' +
                                ':%(lineno)d %(levelname)s %(message)s')
  handler.setFormatter(formatter)
  root.addHandler(handler)
  file_handler = logging.FileHandler('/var/tmp/photoman.log')
  file_handler.setFormatter(formatter)
  root.addHandler(file_handler)
  root.setLevel(logging.WARNING)


def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  _configure_logging()
  _read_photos(FLAGS.src_dir, FLAGS.media_dir)

if __name__ == '__main__':
  _main(sys.argv)
