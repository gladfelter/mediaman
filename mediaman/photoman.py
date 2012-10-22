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
gflags.DEFINE_boolean('scan_missing', False, 'Scan for deleted files in' +
                      ' the archive and remove them from the database')

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
        archive_path text,
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


def _find_and_archive_photos(search_dir,
                             lib_base_dir,
                             delete_source_on_success):
  """Sets up or opens a media library and adds new photos
  to the library and its database.
  
  The source image files will be deleted if --del_src is
  specified.
  """
  rep = Repository()
  rep.open(lib_base_dir)
  photos = os.listdir(search_dir)
  logging.info('Found these photo files: %s', photos)
  for path in photos:
    path = os.path.join(search_dir, path)
    if os.path.isfile(path):
      photo = Photo(path)
      photo.load_metadata()
      db_result = rep.lookup_hash(photo.md5)
      if (db_result is not None
          and os.path.isfile(db_result[1])
          and delete_source_on_success):
        # file is a duplicate and the original is still around
        logging.info('deleting the source file %s, which is a ' +
                     'duplicate of existing file %s',
                     photo.source_path, db_result[1])
        os.remove(photo.source_path)
      elif (db_result is not None
            and os.path.isfile(db_result[1])):
        # same as above, but client didn't request deletion
        logging.info('ignoring the source file %s, which is a ' +
                     'duplicate of existing file %s',
                     photo.source_path, db_result[1])
      elif db_result is not None:
        # file was deleted from archive, remove it from repository
        logging.info('Photo %s was deleted from the archive, replacing' +
                     ' it with the new one.', db_result[1])
        _archive_photo(photo, lib_base_dir, rep, delete_source_on_success)
      else:
        _archive_photo(photo, lib_base_dir, rep, delete_source_on_success)
    else:
      logging.warning('Found a non-file when looking for photos: %s, ' +
                      'it will not be modified', path)

  rep.close()


def _archive_photo(photo,
                   lib_base_dir,
                   repository,
                   delete_source_on_success):
  """Copies the photo to the archive and adds it to the repository.

  The source file will be deleted if it was successfully archived
  and the --del_src flag is specified.
  """
  _copy_photo(photo, lib_base_dir)
  photo.db_id = repository.add_or_update(photo)
  if photo.db_id > 0 and os.path.isfile(photo.archive_path):
    dest_photo = Photo(photo.archive_path)
    dest_photo.load_metadata()
    if dest_photo.md5 is not None and dest_photo.md5 == photo.md5:
      logging.info('%s was successfully copied to destination %s', 
                   photo.source_path, photo.archive_path)
      if delete_source_on_success:
        logging.info('deleting the source file %s.',
                     photo.source_path)
        os.remove(photo.source_path)
    else:
      logging.warning('Destination photo file %s didn''t match ' +
                      'the hash of or wasn''t properly transferred ' +
                      'from %s', photo.archive_path, photo.source_path)
  else:
    logging.warning('%s was not copied to %s or it failed to be ' +
                    'inserted into the database, skipping deletion ' +
                    'of the original',
                    photo.source_path, photo.archive_path)


def _copy_photo(photo, lib_base_dir):
  """Copies a photo file to its destination, computing the destination
  from the file's metadata"""
  parts = photo.get_path_parts()
  relative_path = "%04d/%s/%s" % (parts[0], _get_month_name(parts[1]),
                                  parts[2])
  archive_path = os.path.join(lib_base_dir, 'photos', relative_path)
  photo.archive_path = archive_path
  dest_dir = os.path.dirname(photo.archive_path)
  if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)
  if photo.source_path != photo.archive_path:
    shutil.copy(photo.source_path, photo.archive_path)


def _get_month_name(month):
  """Returns a month identifier for a given decimal month"""
  return "%02d_%s" % (month, calendar.month_name[month])


def _scan_missing_photos(lib_base_dir):
  """Removes photos from the repository that don't exist in the archive"""
  rep = Repository()
  try:
    rep.open(lib_base_dir)
    missing_files = []
    for (db_id, filepath) in rep.iter_all_photos():
      if not os.path.isfile(filepath):
        logging.warning('The photo %s was deleted from the ' +
                        'archive unexpectedly. It will be removed from ' +
                        'the database.', filepath)
        missing_files.append(db_id)
    rep.remove_photos(missing_files)
  finally:
    rep.close()


def _recursive_iter(current_dir, operation):
  """Perform an operation on all the files in the current and sub-folders.
  """ 
  results = []
  current_dir = os.path.abspath(current_dir)
  elements = os.listdir(current_dir)
  for element in elements:
    abs_path = os.path.join(current_dir, element)
    if os.path.isfile(curFile):
      results.append(operation(curFile))
    else:
      results += _recursive_iter(current_dir, operation)
  return results

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
  root.setLevel(logging.INFO)


def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  _configure_logging()
  _find_and_archive_photos(FLAGS.src_dir, FLAGS.media_dir, FLAGS.del_src)
  if FLAGS.scan_missing:
    _scan_missing_photos(FLAGS.media_dir)


if __name__ == '__main__':
  _main(sys.argv)
