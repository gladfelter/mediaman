#! /usr/bin/python
#
"""Photo organization utility.

Organizes source photos by date and updates a sqlite database with
metadata about the photos. Detects duplicates and ignores them.
"""
import calendar
import media_common
import gflags
import logging
import os
import os.path
import shutil
import sys

gflags.DEFINE_string('src_dir', None, 'Directory to scan for photos')
gflags.DEFINE_string('media_dir', None, 'Directory of media library')
gflags.DEFINE_boolean('del_src', False, 'Delete the source image if' +
                      ' succesfully archived')
gflags.DEFINE_boolean('scan_missing', False, 'Scan for deleted files in' +
                      ' the archive and remove them from the database')
gflags.DEFINE_string('group_name', '', 'The name of the group to use' +
                     ' for the destination file')

gflags.MarkFlagAsRequired('src_dir')
gflags.MarkFlagAsRequired('media_dir')

FLAGS = gflags.FLAGS

def _find_and_archive_photos(search_dir,
                             lib_base_dir,
                             delete_source_on_success,
                             group_name):
  """Sets up or opens a media library and adds new photos
  to the library and its database.
  
  The source image files will be deleted if --del_src is
  specified.
  """
  

  rep = media_common.Repository()
  rep.open(lib_base_dir)
  paths = os.walk(search_dir)
  results = []
  group_id = media_common.get_group_id(group_name)
  files_to_delete = []
  archive_count = 0
  for (dirpath, dirnames, filenames) in paths:
    for filename in filenames:
      path = os.path.join(dirpath, filename)
      if os.path.isfile(path):
        photo = media_common.Photo(path)
        photo.load_metadata()
        db_result = rep.lookup_hash(photo.md5)
        if (db_result is not None
            and os.path.abspath(db_result[1]) == os.path.abspath(path)):
          logging.info('Found existing archived photo %s, ignoring',
                       db_result[1])
        elif (db_result is not None
            and os.path.isfile(db_result[1])
            and delete_source_on_success):
          # file is a duplicate and the original is still around
          logging.info('Deleting the source file %s, which is a ' +
                       'duplicate of existing file %s',
                       photo.source_path, db_result[1])
          os.remove(photo.source_path)
        elif (db_result is not None
              and os.path.isfile(db_result[1])):
          # same as above, but client didn't request deletion
          logging.info('Ignoring the source file %s, which is a ' +
                       'duplicate of existing file %s',
                       photo.source_path, db_result[1])
        elif db_result is not None:
          # file was deleted from archive, remove it from repository
          logging.info('Photo %s was deleted from the archive, replacing' +
                       ' it with the new one.', db_result[1])
          if (_archive_photo(photo, lib_base_dir, rep, group_id) and
              delete_source_on_success):
            files_to_delete.append(photo.source_path)
        else:
          archive_count += 1
          if (_archive_photo(photo, lib_base_dir, rep, group_id) and
              delete_source_on_success):
            files_to_delete.append(photo.source_path)
      else:
        logging.warning('Found a non-file when looking for photos: %s, ' +
                        'it will not be modified', path)

  rep.close()
  for filepath in files_to_delete:
    os.remove(filepath)
  logging.info('Successfully completed archiving %d files', archive_count)



def _archive_photo(photo,
                   lib_base_dir,
                   repository,
                   group_id):
  """Copies the photo to the archive and adds it to the repository.

  The source file will be deleted if it was successfully archived
  and the --del_src flag is specified.
  """
  _copy_photo(photo, lib_base_dir, group_id)
  photo.db_id = repository.add_or_update(photo)
  if photo.db_id > 0 and os.path.isfile(photo.archive_path):
    dest_photo = media_common.Photo(photo.archive_path)
    dest_photo.load_metadata()
    if dest_photo.md5 is not None and dest_photo.md5 == photo.md5:
      logging.info('%s was successfully copied to destination %s', 
                   photo.source_path, photo.archive_path)
      return True
    else:
      logging.warning('Destination photo file %s didn''t match ' +
                      'the hash of or wasn''t properly transferred ' +
                      'from %s', photo.archive_path, photo.source_path)
      return False
  else:
    logging.warning('%s was not copied to %s or it failed to be ' +
                    'inserted into the database, skipping deletion ' +
                    'of the original',
                    photo.source_path, photo.archive_path)
    return False


def _copy_photo(photo, lib_base_dir, group_id):
  """Copies a photo file to its destination, computing the destination
  from the file's metadata"""
  parts = photo.get_path_parts()
  relative_path = os.path.join('%04d' % parts[0], _get_month_name(parts[1]),
                               parts[2])
  archive_path = os.path.join(lib_base_dir, 'photos', relative_path)
  photo.archive_path = archive_path
  dest_dir = os.path.dirname(photo.archive_path)
  if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)
  if photo.source_path != photo.archive_path:
    photo.archive_path = _copy_file(photo.source_path, dest_dir)
    os.chown(photo.archive_path, -1, group_id)


def _copy_file(filepath, dest_dir):
  """Copies a file, keeping its metadata and renaming it if there's a
  conflict."""
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
  return destpath


def _get_month_name(month):
  """Returns a month identifier for a given decimal month"""
  return "%02d_%s" % (month, calendar.month_name[month])


def _scan_missing_photos(lib_base_dir):
  """Removes photos from the repository that don't exist in the archive"""
  rep = media_common.Repository()
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


def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  try:
    media_common.configure_logging('photoman.log')
    _find_and_archive_photos(FLAGS.src_dir, FLAGS.media_dir,
                             FLAGS.del_src, FLAGS.group_name)
    if FLAGS.scan_missing:
      _scan_missing_photos(FLAGS.media_dir)
  except:
    logging.exception('An unexpected error occurred during photo archiving')


if __name__ == '__main__':
  _main(sys.argv)
