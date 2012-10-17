#! /usr/bin/python

import sys
import os
import os.path
import glob
import time
import shutil
import hashlib
import logging
import pyexiv2
import datetime
import gflags
from exceptions import IOError
from logging import StreamHandler
from sqlite3 import dbapi2 as sqlite

gflags.DEFINE_string('src_dir', None, 'Directory to scan for photos')
gflags.DEFINE_string('media_dir', None, 'Directory of media library')
gflags.MarkFlagAsRequired('src_dir')
gflags.MarkFlagAsRequired('media_dir')

FLAGS = gflags.FLAGS

class Repository():

  def __init__(this):
    con = None

  def open(self, lib_base_dir):  # opens, returns biggest ID or -1 on error
    # create data store if it doesn't exist
    if not os.access(lib_base_dir, os.R_OK|os.W_OK|os.X_OK):
      logging.warning("can't open %s, will attempt to create it" 
                      % lib_base_dir)
      self._tree_setup(lib_base_dir)
      # initialize the database
      self.con = sqlite.connect(lib_base_dir + "/media.db")
      cur = self.con.cursor()
      r = cur.execute('''create table photos
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
    self.con.close()
  
  def add(self, photo):
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

  def isHashPresent(self, md5):
    cur = self.con.cursor()
    rows = cur.execute('''
        select id where md5=?''', md5)
    return len(rows) > 0

  def _tree_setup(self, lib_base_dir):
    os.mkdir(lib_base_dir, 0755)
    os.mkdir(lib_base_dir + '/photos', 0755)


def openfl(path):       # open a file list, returns file object
  return open(path, 'r')


class Photo():
  
  def __init__(self, source_path):
    self.db_id = self.flags = self.md5 = None
    self.size = self.description = None
    self.timestamp = self.dest_path = None
    self.camera_make = self.camera_model = None
    self.source_info = None
    self.source_path = source_path
    self.metadata_read = False
    pass

  def get_path_parts(self):
    if not self.metadata_read:
      self.load_metadata()
    time_struct = time.localtime(self.timestamp)
    return time_struct[0:2] + (os.path.basename(self.source_path),)
 
  def load_metadata(self):
    m = None
    time_parts = None
    try:
      m = pyexiv2.ImageMetadata(self.source_path)
      m.read()
    except IOError:
      m = None
      logging.warning("%s contains no EXIF data" % self.source_path)
    except Exception:
      m = None
      logging.warning('An unexpected error occurred while reading '
                      + 'exif data from %s. Will attempt to recover')

    if m is not None:
      image_keys = frozenset(m.exif_keys)
      self._load_exif_timestamp(m, image_keys)
      self._load_camera_make(m, image_keys)
      self._load_camera_model(m, image_keys)

    self._load_filesystem_timestamp()
    self._load_file_size()
    self.md5 = self.get_hash()
    self.metadata_read = True

  def _load_file_size(self):
    try:
      self.size = os.path.getsize(self.source_path)
    except os.error:
      self.size = 0
      logging.warning('Could not read file size of %s' % self.source_path)

  def _load_camera_model(self, metadata, image_keys):
    if 'Exif.Image.Model' in image_keys:
      self.camera_model = metadata['Exif.Image.Model'].value

  def _load_camera_make(self, metadata, image_keys):
    if 'Exif.Image.Make' in image_keys:
      self.camera_make = metadata['Exif.Image.Make'].value

  def _load_exif_timestamp(self, metadata, image_keys):
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
    if self.timestamp is None:
      try:
        self.timestamp = os.path.getmtime(self.source_path)
      except os.error:
        logging.warning('Could not access image''s timestamp' +
                        ' by any means, setting it to the epoch start.')
        self.timestamp = 0
      
  def get_hash(self):
    fo = open(self.source_path, 'r')
    m = hashlib.md5()
    stuff = fo.read(8192)
    while len(stuff) > 0:
            m.update(stuff)
            stuff = fo.read(8192)
    fo.close()
    return (m.hexdigest())


def read_photos(search_dir, lib_base_dir):
  r = Repository()
  r.open(lib_base_dir)
  photos = os.listdir(search_dir)
  logging.info('Found these photo files: %s' % photos)
  for path in photos:
    path = os.path.join(search_dir, path)
    if os.path.isfile(path):
      photo = Photo(path)
      photo.load_metadata()
      copy_photo(photo, lib_base_dir)
      photo.db_id = r.add(photo)
      if photo.db_id > 0 and os.path.isfile(photo.dest_path):
        dest_photo = Photo(photo.dest_path)
        dest_photo.load_metadata()
        if dest_photo.md5 is not None and dest_photo.md5 == photo.md5:
          print 'photo.source_path = ', photo.source_path
          print 'photo.dest_path = ', photo.dest_path
          logging.info(('%s was successfully copied to destination %s, ' +
                       'deleting the source file %s.')
                       % (photo.source_path, photo.dest_path,
                          photo.source_path))
          os.remove(photo.source_path)
        else:
          logging.warning(('Destination photo file %s didn''t match ' +
                          'the hash of or wasn''t properly transferred ' +
                          'from %s') % (photo.dest_path, photo.source_path))
      else:
        logging.warning(('%s was not copied to %s or it failed to be ' +
                        'inserted into the database, skipping deletion ' +
                        'of the original')
                        % (photo.source_path, photo.dest_path))
    else:
      logging.warning(('Found a non-file when looking for photos: %s, ' +
                      'it will not be modified') % path)


def copy_photo(photo, lib_base_dir):
  relative_path = "%04d/%02d/%s" % photo.get_path_parts()
  dest_path = os.path.join(lib_base_dir, 'photos', relative_path)
  photo.dest_path = dest_path
  dest_dir = os.path.dirname(photo.dest_path)
  if not os.path.exists(dest_dir):
    print 'Creating directory %s' % dest_dir
    os.makedirs(dest_dir)
  print 'copying from %s to %s' % (photo.source_path, photo.dest_path)
  shutil.copy(photo.source_path, photo.dest_path)


"""Configures logging to stderr, file.

"""
def configure_logging():
  root = logging.getLogger('')
  h = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s' +
                                ':%(lineno)d %(levelname)s %(message)s')
  h.setFormatter(formatter)
  root.addHandler(h)
  fh = logging.FileHandler('/var/tmp/photoman.log')
  fh.setFormatter(formatter)
  root.addHandler(fh)
  root.setLevel(logging.WARNING)


def main(argv):
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, e:
    print '%s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], FLAGS)
    sys.exit(1)
  configure_logging()
  read_photos(FLAGS.src_dir, FLAGS.media_dir)

if __name__ == '__main__':
  main(sys.argv)
