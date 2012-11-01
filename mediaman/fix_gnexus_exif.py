#! /usr/bin/python
""" Script that creates 'sanitized' copies of Galaxy Nexus jpeg's.

The Galaxy Nexus phone's default camera app puts an array of values
into the ISO EXIF Tag, and some applications can't handle that. This
script creates copies in the same directory with the name
    <basename>_isoremoved<extension>

Requires the gflags and pyexiv2 third-party python libraries
"""

import gflags
import logging
import os.path
import pyexiv2
import shutil
import sys

gflags.DEFINE_string('search_dir', None, 'Directory of media library')
gflags.MarkFlagAsRequired('search_dir')
FLAGS = gflags.FLAGS

def _create_parsable_gnexus_copies(search_dir):
  """ Walk a directory tree, finding photos that have arrays for ISO EXIF
  data, and make ISO-free copies.
  
  Useful for the PS3 Media Server, which currently cannot parse (and
  therefore serve) files with array ISO EXIF data. """
  paths = os.walk(search_dir)
  for (dirpath, _, filenames) in paths:
    for filename in filenames:
      filepath = os.path.join(dirpath, filename)
      prefix, suffix = os.path.splitext(filepath)
      is_array = _is_array_iso(filepath)
      if is_array:
        sanitized_filepath = os.path.join(dirpath, '%s_isoremoved%s'
                                          % (prefix, suffix))
        if not os.path.exists(sanitized_filepath):
          logging.info('Sanitizing %s to %s.', filepath, sanitized_filepath)
          shutil.copy2(filepath, sanitized_filepath)
          image = pyexiv2.ImageMetadata(sanitized_filepath)
          image.read()
          del image['Exif.Photo.ISOSpeedRatings']
          image.write()


def _is_array_iso(filepath):
  """Returns a True if the photo contains an array of multiple ISO values.
  """
  try:
    image = pyexiv2.ImageMetadata(filepath)
    image.read()
    logging.debug('Photo has an ISO SPeed Ratings Tag of %s',
                 image['Exif.Photo.ISOSpeedRatings'].value)
    return len(image['Exif.Photo.ISOSpeedRatings'].value) != 1
  except Exception:
    return False


def _configure_logging():
  """Configures logging to stderr, file."""
  root = logging.getLogger('')
  handler = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s' +
                                ':%(lineno)d %(levelname)s %(message)s')
  handler.setFormatter(formatter)
  root.addHandler(handler)
  file_handler = logging.FileHandler('/var/tmp/fix_gnexus_exif.log')
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
  try:
    _configure_logging()
    _create_parsable_gnexus_copies(FLAGS.search_dir)
  except Exception:
    logging.exception('An unexpected error occurred while fixing'
                      + ' Galaxy Nexus photos')
    raise

if __name__ == '__main__':
  _main(sys.argv)
