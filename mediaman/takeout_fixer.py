"""Library for fixing filesystem mtimes on Google Takeout exports.

Google Takeout exports photos and videos alongside .json sidecar files that
contain the original capture timestamp.  The exported files get mtime=now,
which breaks date-based organization for any file lacking embedded EXIF
DateTimeOriginal (videos and EXIF-less photos).

This module reads the .json sidecars and restores correct mtimes.
"""
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_JSON_EXT = '.json'

_VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.3gp', '.mts', '.mpg',
    '.mpeg', '.webm', '.m4v', '.flv',
})

_PHOTO_EXTENSIONS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
    '.cr2', '.nef', '.arw', '.dng', '.heic', '.heif', '.webp',
})

_MEDIA_EXTENSIONS = _VIDEO_EXTENSIONS | _PHOTO_EXTENSIONS


def has_exif_date(filepath: str) -> bool:
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


def fix_mtimes(src_dir: str, *, delete_json: bool = False) -> tuple[int, int, int]:
    """Fix mtimes for files in *src_dir* using Google Takeout JSON sidecars.

    Walks *src_dir* recursively, finds .json sidecar files, reads
    ``photoTakenTime.timestamp``, and sets the media file's mtime to
    that timestamp *if* the file is a video or lacks embedded EXIF.

    Photos that already have a valid EXIF ``DateTimeOriginal`` are left
    alone (their mtime is not modified).

    Returns ``(fixed, already_ok, skipped)``.
    """
    fixed = 0
    already_ok = 0
    skipped = 0

    for dirpath, _dirnames, filenames in os.walk(src_dir):
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
                # JSON without a corresponding media file — e.g. album
                # metadata.  Skip.
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
            needs_fix = ext in _VIDEO_EXTENSIONS or not has_exif_date(media_path)

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


def iter_media_files(src_dir: str) -> list[str]:
    """Walk *src_dir* and return paths of all media files (non-JSON).

    Media files are identified by extension (see _MEDIA_EXTENSIONS).
    JSON sidecar files are excluded.  Files with unrecognized extensions
    are skipped so that only actual photos and videos reach staging.

    Returns a list of absolute file paths (as strings).
    """
    results: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(src_dir):
        for filename in filenames:
            if filename.lower().endswith(_JSON_EXT):
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in _MEDIA_EXTENSIONS:
                continue
            results.append(os.path.join(dirpath, filename))
    return results


def _remove_json(json_path: str) -> None:
    """Delete a JSON sidecar file after successful processing."""
    try:
        os.remove(json_path)
        logger.debug('Removed sidecar: %s', json_path)
    except OSError as e:
        logger.warning('Could not remove sidecar %s: %s', json_path, e)
