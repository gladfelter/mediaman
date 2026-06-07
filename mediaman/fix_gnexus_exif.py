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
    for (dirpath, _dirnames, filenames) in os.walk(search_dir):
        total += len(filenames)
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            prefix, suffix = os.path.splitext(filepath)
            if not _is_array_iso(filepath):
                continue

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
                 'skipped=%d errors=%d',
                 total, fixed, skipped, errors)


def _is_array_iso(filepath):
    """Returns True if the photo contains an array of multiple ISO values."""
    try:
        exif_dict = piexif.load(filepath)
        iso = exif_dict.get('Exif', {}).get(piexif.ExifIFD.ISOSpeedRatings)
        if iso is not None and not isinstance(iso, int):
            return True
        return False
    except Exception:
        return False


def _configure_logging():
    """Configures logging to stderr, file."""
    root = logging.getLogger('')
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(asctime)s %(filename)s'
                                  ':%(lineno)d %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)
    file_handler = logging.FileHandler('/var/tmp/fix_gnexus_exif.log')
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)


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
