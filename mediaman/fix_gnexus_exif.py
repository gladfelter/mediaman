#!/usr/bin/env python3
"""Script that creates sanitized copies of Galaxy Nexus jpegs.

The Galaxy Nexus phone's default camera app puts an array of values
into the ISO EXIF Tag, and some applications can't handle that. This
script creates copies in the same directory with the name
    <basename>_isoremoved<extension>
"""

import argparse
import logging
import os
import os.path
import shutil
import sys

import piexif


def _create_parsable_gnexus_copies(search_dir):
    """Walk a directory tree, finding photos that have arrays for ISO EXIF
    data, and make ISO-free copies.

    Useful for the PS3 Media Server, which currently cannot parse (and
    therefore serve) files with array ISO EXIF data.
    """
    total = 0
    fixed = 0
    errors = 0
    skipped = 0
    non_photo = 0
    for (dirpath, _dirnames, filenames) in os.walk(search_dir):
        total += len(filenames)
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            array_iso, is_photo = _is_array_iso(filepath)
            if not is_photo:
                non_photo += 1
                continue
            if not array_iso:
                continue

            prefix, suffix = os.path.splitext(filepath)
            sanitized_filepath = os.path.join(
                dirpath, '%s_isoremoved%s' % (prefix, suffix))
            if os.path.exists(sanitized_filepath):
                skipped += 1
                continue

            logging.info('Sanitizing %s to %s.', filepath,
                         sanitized_filepath)
            shutil.copy2(filepath, sanitized_filepath)
            try:
                exif_dict = piexif.load(sanitized_filepath)
                if 'Exif' in exif_dict and piexif.ExifIFD.ISOSpeedRatings in exif_dict['Exif']:
                    del exif_dict['Exif'][piexif.ExifIFD.ISOSpeedRatings]
                    exif_bytes = piexif.dump(exif_dict)
                    piexif.insert(exif_bytes, sanitized_filepath)
                fixed += 1
            except Exception:
                logging.warning('Could not strip ISO from %s',
                                sanitized_filepath)
                errors += 1

    logging.info('fix_gnexus_exif complete: scanned=%d fixed=%d '
                 'skipped=%d non_photo=%d errors=%d',
                 total, fixed, skipped, non_photo, errors)


def _is_array_iso(filepath):
    """Returns (is_array_iso, is_photo).

    is_array_iso — True if the file has a multi-valued ISO EXIF tag.
    is_photo     — False if the file could not be parsed as an EXIF image
                   at all (e.g. non-JPEG, corrupt, permissions error).
    """
    try:
        exif_dict = piexif.load(filepath)
        iso = exif_dict.get('Exif', {}).get(piexif.ExifIFD.ISOSpeedRatings)
        if iso is not None and not isinstance(iso, int):
            return (True, True)
        return (False, True)
    except Exception:
        logging.debug('Skipping non-photo or unparseable file: %s', filepath)
        return (False, False)


def _configure_logging():
    """Configures logging to stderr, file."""
    media_common.configure_logging('fix_gnexus_exif.log')


def main():
    parser = argparse.ArgumentParser(
        description='Sanitize Galaxy Nexus ISO EXIF data.')
    parser.add_argument('--search_dir', required=True,
                        help='Directory to scan for photos')
    args = parser.parse_args()

    try:
        _configure_logging()
        _create_parsable_gnexus_copies(args.search_dir)
    except Exception:
        logging.exception('An unexpected error occurred while fixing'
                          ' Galaxy Nexus photos')
        sys.exit(1)


if __name__ == '__main__':
    main()
