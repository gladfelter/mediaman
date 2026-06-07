#!/usr/bin/env python3
"""Fix filesystem mtimes for Google Takeout exports.

Google Takeout exports photos and videos alongside .json sidecar files that
contain the original capture timestamp.  The exported files get mtime=now,
which breaks date-based organization for any file lacking embedded EXIF
DateTimeOriginal (videos and EXIF-less photos).

This script walks a directory tree, reads each .json sidecar, finds the
corresponding media file, and updates its mtime to the capture timestamp if
the file lacks an embedded EXIF date.  Files that already have valid EXIF
DateTimeOriginal are left alone.

Usage:
    python google_takeout_fix_mtimes.py --src_dir /path/to/extracted_takeout
"""

import argparse
import json
import logging
import os
import sys
import time


logger = logging.getLogger(__name__)


def _has_exif_date(filepath: str) -> bool:
    """Return True if *filepath* has a parseable EXIF DateTimeOriginal."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        image = Image.open(filepath)
        try:
            exif = image._getexif()
            if exif is None:
                return False
            for tag_id, value in exif.items():
                if TAGS.get(tag_id) == 'DateTimeOriginal':
                    if value and isinstance(value, str):
                        time.strptime(value, '%Y:%m:%d %H:%M:%S')
                        return True
            return False
        finally:
            image.close()
    except Exception:
        return False


_VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.3gp', '.mts', '.mpg',
    '.mpeg', '.webm', '.m4v', '.flv',
}

_JSON_EXT = '.json'
_SUPPLEMENT_JSON = '.json'  # Used by Google for edited-photo sidecars


def fix_mtimes(src_dir: str, *, delete_json: bool = False) -> tuple[int, int, int]:
    """Fix mtimes for files in *src_dir* using Google Takeout JSON sidecars.

    Returns (fixed, already_ok, skipped).
    """
    fixed = 0
    already_ok = 0
    skipped = 0

    for dirpath, _dirnames, filenames in os.walk(src_dir):
        # Collect json → media file mapping for this directory
        json_files = [f for f in filenames if f.lower().endswith(_JSON_EXT)]
        for json_name in json_files:
            json_path = os.path.join(dirpath, json_name)

            # The corresponding media file is the JSON filename minus the
            # final .json extension.  E.g. IMG_1234.JPG.json → IMG_1234.JPG
            media_name = json_name[:-len(_JSON_EXT)]
            if not media_name:
                continue
            media_path = os.path.join(dirpath, media_name)

            if not os.path.isfile(media_path):
                # JSON without a corresponding media file — likely an album
                # metadata file.  Skip.
                skipped += 1
                continue

            # Read the capture timestamp from the JSON sidecar
            try:
                with open(json_path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                timestamp_str = data.get('photoTakenTime', {}).get('timestamp')
                if timestamp_str is None:
                    logger.debug('No photoTakenTime in %s, skipping', json_path)
                    skipped += 1
                    continue
                capture_ts = int(timestamp_str)
            except (json.JSONDecodeError, ValueError, KeyError, OSError) as e:
                logger.warning('Could not parse %s: %s', json_path, e)
                skipped += 1
                continue

            # Determine if this file needs mtime fixing
            ext = os.path.splitext(media_name)[1].lower()
            needs_fix = ext in _VIDEO_EXTENSIONS or not _has_exif_date(media_path)

            if not needs_fix:
                already_ok += 1
                if delete_json:
                    _remove_json(json_path)
                continue

            # Apply the timestamp
            try:
                os.utime(media_path, (capture_ts, capture_ts))
                logger.info('Fixed mtime: %s → %s',
                            media_path, time.ctime(capture_ts))
                fixed += 1
                if delete_json:
                    _remove_json(json_path)
            except OSError as e:
                logger.warning('Could not set mtime on %s: %s', media_path, e)
                skipped += 1

    return fixed, already_ok, skipped


def _remove_json(json_path: str) -> None:
    """Delete a JSON sidecar file after successful processing."""
    try:
        os.remove(json_path)
        logger.debug('Removed sidecar: %s', json_path)
    except OSError as e:
        logger.warning('Could not remove sidecar %s: %s', json_path, e)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description='Fix mtimes on Google Takeout exports using JSON sidecars.')
    parser.add_argument(
        '--src_dir', required=True,
        help='Directory containing the extracted Google Takeout files',
    )
    parser.add_argument(
        '--delete_json', action='store_true',
        help='Delete JSON sidecar files after successfully fixing the mtime',
    )
    args = parser.parse_args(argv)

    if not os.path.isdir(args.src_dir):
        print(f'Error: {args.src_dir} is not a directory', file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    logger.info('Scanning %s for Google Takeout JSON sidecars...', args.src_dir)
    fixed, already_ok, skipped = fix_mtimes(args.src_dir,
                                            delete_json=args.delete_json)
    logger.info(
        'Done: %d mtimes fixed, %d already had EXIF dates, %d skipped',
        fixed, already_ok, skipped,
    )


if __name__ == '__main__':
    main()
