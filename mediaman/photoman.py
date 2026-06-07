#!/usr/bin/env python3
"""Photo organization utility.

Organizes source photos by date and updates a sqlite database with
metadata about the photos. Detects duplicates and ignores them.
"""
import argparse
import calendar
import logging
import os
import os.path
import shutil
import sys

import media_common


def _find_and_archive_photos(search_dir, lib_base_dir,
                             delete_source_on_success, group_name):
    """Sets up or opens a media library and adds new photos
    to the library and its database.

    The source image files will be deleted if --del_src is specified.
    """
    rep = media_common.Repository()
    rep.open(lib_base_dir)
    group_id = media_common.get_group_id(group_name)
    files_to_delete = []
    archive_count = 0
    for (dirpath, _dirnames, filenames) in os.walk(search_dir):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            if not os.path.isfile(path):
                logging.warning('Found a non-file when looking for photos: '
                                '%s, it will not be modified', path)
                continue

            photo = media_common.Photo(path)
            photo.load_metadata()
            if photo.md5 is None:
                logging.warning('Could not compute hash for %s, skipping',
                                path)
                continue

            db_result = rep.lookup_hash(photo.md5, size=photo.size)
            if (db_result is not None
                    and os.path.abspath(db_result[1]) == os.path.abspath(path)):
                logging.info('Found existing archived photo %s, ignoring',
                             db_result[1])
            elif (db_result is not None
                  and os.path.isfile(db_result[1])
                  and delete_source_on_success):
                logging.info('Deleting the source file %s, which is a '
                             'duplicate of existing file %s',
                             photo.source_path, db_result[1])
                os.remove(photo.source_path)
            elif (db_result is not None
                  and os.path.isfile(db_result[1])):
                logging.info('Ignoring the source file %s, which is a '
                             'duplicate of existing file %s',
                             photo.source_path, db_result[1])
            elif db_result is not None:
                logging.info('Photo %s was deleted from the archive, '
                             'replacing it with the new one.', db_result[1])
                if (_archive_photo(photo, lib_base_dir, rep, group_id)
                        and delete_source_on_success):
                    files_to_delete.append(photo.source_path)
            else:
                archive_count += 1
                if (_archive_photo(photo, lib_base_dir, rep, group_id)
                        and delete_source_on_success):
                    files_to_delete.append(photo.source_path)

    rep.close()
    for filepath in files_to_delete:
        try:
            os.remove(filepath)
        except OSError as e:
            logging.warning('Could not delete %s: %s', filepath, e)
    logging.info('Successfully completed archiving %d files', archive_count)


def _archive_photo(photo, lib_base_dir, repository, group_id):
    """Copies the photo to the archive and adds it to the repository."""
    _copy_photo(photo, lib_base_dir, group_id)
    photo.db_id = repository.add_or_update(photo)
    if photo.db_id > 0 and os.path.isfile(photo.archive_path):
        dest_photo = media_common.Photo(photo.archive_path)
        dest_photo.load_metadata()
        if (dest_photo.md5 is not None
                and dest_photo.md5 == photo.md5):
            logging.info('%s was successfully copied to destination %s',
                         photo.source_path, photo.archive_path)
            return True
        else:
            logging.warning("Destination photo file %s didn't match "
                            "the hash of or wasn't properly transferred "
                            "from %s", photo.archive_path,
                            photo.source_path)
            return False
    else:
        logging.warning('%s was not copied to %s or it failed to be '
                        'inserted into the database, skipping deletion '
                        'of the original',
                        photo.source_path, photo.archive_path)
        return False


def _copy_photo(photo, lib_base_dir, group_id):
    """Copies a photo file to its destination, computing the destination
    from the file's metadata"""
    parts = photo.get_path_parts()
    relative_path = os.path.join('%04d' % parts[0],
                                 _get_month_name(parts[1]),
                                 parts[2])
    archive_path = os.path.join(lib_base_dir, 'photos', relative_path)
    photo.archive_path = archive_path
    dest_dir = os.path.dirname(photo.archive_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    if photo.source_path != photo.archive_path:
        photo.archive_path = _copy_file(photo.source_path, dest_dir)
        try:
            os.chown(photo.archive_path, -1, group_id)
        except OSError:
            pass


def _copy_file(filepath, dest_dir):
    """Copies a file, keeping its metadata and renaming it if there's a
    conflict."""
    _dirname, filename = os.path.split(filepath)
    prefix, suffix = os.path.splitext(filename)
    counter = 1
    destpath = os.path.join(dest_dir, filename)
    while os.path.exists(destpath):
        destpath = os.path.join(dest_dir,
                                prefix + '_' + str(counter) + suffix)
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
    # Guard: verify the archive directory is actually accessible
    photos_dir = os.path.join(lib_base_dir, 'photos')
    if not os.path.isdir(photos_dir):
        logging.error('Archive photos directory %s does not exist. '
                       'Refusing to scan for missing photos — is the '
                       'disk mounted?', photos_dir)
        return
    # Additional guard: if the directory exists but is empty (unmounted disk
    # pointing at an empty mountpoint), a subdirectory check adds confidence
    subdirs = [d for d in os.listdir(photos_dir)
               if os.path.isdir(os.path.join(photos_dir, d))]
    if not subdirs:
        logging.error('Archive photos directory %s contains no '
                       'subdirectories. Refusing to scan for missing '
                       'photos — is the disk mounted?', photos_dir)
        return

    rep = media_common.Repository()
    try:
        rep.open(lib_base_dir)
        missing_files = []
        for (db_id, filepath) in rep.iter_all_photos():
            if not os.path.isfile(filepath):
                logging.warning('The photo %s was deleted from the '
                                'archive unexpectedly. It will be removed '
                                'from the database.', filepath)
                missing_files.append(db_id)
        if missing_files:
            logging.warning('Removing %d missing photos from database',
                            len(missing_files))
            rep.remove_photos(missing_files)
    finally:
        rep.close()


def main():
    parser = argparse.ArgumentParser(
        description='Organize photos into a media library.')
    parser.add_argument('--src_dir', required=True,
                        help='Directory to scan for photos')
    parser.add_argument('--media_dir', required=True,
                        help='Directory of media library')
    parser.add_argument('--del_src', action='store_true',
                        help='Delete source images after archiving')
    parser.add_argument('--scan_missing', action='store_true',
                        help='Scan for deleted files in the archive')
    parser.add_argument('--group_name', default='',
                        help='Group for destination file ownership')
    args = parser.parse_args()

    # Safety: refuse to run if src_dir is inside the archive itself
    archive_photos = os.path.abspath(os.path.join(args.media_dir, 'photos'))
    src_abs = os.path.abspath(args.src_dir)
    if src_abs.startswith(archive_photos + os.sep) or src_abs == archive_photos:
        logging.error('Source directory %s is inside the archive %s. '
                       'Refusing to run — this would delete archived '
                       'photos if --del_src is set.', args.src_dir,
                       archive_photos)
        sys.exit(1)

    try:
        media_common.configure_logging('photoman.log')
        _find_and_archive_photos(args.src_dir, args.media_dir,
                                 args.del_src, args.group_name)
        if args.scan_missing:
            _scan_missing_photos(args.media_dir)
    except Exception:
        logging.exception('An unexpected error occurred during '
                          'photo archiving')
        sys.exit(1)


if __name__ == '__main__':
    main()
