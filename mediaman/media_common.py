""" Common operations and types for media collection and management
"""

import logging
import os
import os.path
import sys
import time
import grp
import hashlib
import sqlite3 as sqlite
from PIL import Image
from PIL.ExifTags import TAGS

# Map of PIL EXIF tag names to their numeric IDs (for faster lookup)
_EXIF_TAG_TO_ID = {v: k for k, v in TAGS.items()}

_RELEVANT_TAGS = {
    'Make', 'Model', 'DateTimeOriginal', 'DateTime', 'DateTimeDigitized',
    'ISOSpeedRatings'
}


class Repository():
    """Represents a repository of media items, such as photos"""

    def __init__(self):
        self.con = None

    def open(self, lib_base_dir):
        """Opens or creates the repository and media library"""
        self._tree_setup(lib_base_dir)
        db_path = os.path.join(lib_base_dir, 'media.db')
        if not os.access(db_path, os.R_OK | os.W_OK):
            logging.warning("can't open %s, will attempt to create it",
                            lib_base_dir)
            self.con = sqlite.connect(os.path.join(lib_base_dir, "media.db"))
            cur = self.con.cursor()
            cur.execute('''create table photos
                (id integer primary key,
                flags text,
                md5 varchar(32),
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
            self.con = sqlite.connect(os.path.join(lib_base_dir, "media.db"))
        if self.con is None:
            raise RuntimeError("Could not open the media database"
                               " for an unknown reason")

    def close(self):
        """Closes the repository."""
        if self.con:
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
        cur.execute('DELETE FROM photos WHERE md5 = ?', [photo.md5])

    def lookup_hash(self, md5):
        """Returns the filepath and id of the existing file with the
        provided hash, or None if no such file exists"""
        cur = self.con.cursor()
        logging.info('looking for hash %s', md5)
        rows = cur.execute(
            'SELECT id, archive_path FROM photos WHERE md5 = :md5 ',
            {'md5': md5})
        row = rows.fetchone()
        if row is not None:
            logging.debug('Found row object %s', row)
            return row
        return None

    def iter_all_photos(self):
        """Returns an iterator returning (id, filepath) for all photos"""
        cur = self.con.cursor()
        cur.execute('SELECT id, archive_path FROM photos')
        return cur

    def remove_photos(self, photo_ids):
        cur = self.con.cursor()
        query = ('DELETE from photos where id in ('
                 + ','.join('?' * len(photo_ids)) + ')')
        cur.execute(query, photo_ids)

    @staticmethod
    def _tree_setup(lib_base_dir):
        """Creates the media library directories"""
        if not os.path.exists(lib_base_dir):
            os.mkdir(lib_base_dir, 0o755)
        photos_dir = os.path.join(lib_base_dir, 'photos')
        if not os.path.exists(photos_dir):
            os.mkdir(photos_dir, 0o755)


class Photo():
    """Represents a file containing a photo"""

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
        self._load_exif_metadata()
        self._load_filesystem_timestamp()
        self._load_file_size()
        self.md5 = self._get_hash()
        self.metadata_read = True

    def _load_exif_metadata(self):
        """Reads EXIF data using Pillow."""
        image = None
        try:
            image = Image.open(self.source_path)
            exif_data = image._getexif()
            if exif_data is None:
                return
            # Map numeric tag IDs to names
            tagged = {}
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, '')
                if tag_name in _RELEVANT_TAGS:
                    tagged[tag_name] = value

            # Timestamp
            timestamp_str = (tagged.get('DateTimeOriginal')
                             or tagged.get('DateTime')
                             or tagged.get('DateTimeDigitized'))
            if timestamp_str and isinstance(timestamp_str, str):
                try:
                    ts = time.strptime(timestamp_str,
                                       '%Y:%m:%d %H:%M:%S')
                    self.timestamp = time.mktime(ts)
                except (ValueError, OverflowError):
                    logging.warning('Bad EXIF timestamp in %s: %s',
                                    self.source_path, timestamp_str)

            # Camera make
            if 'Make' in tagged:
                self.camera_make = str(tagged['Make']).strip()

            # Camera model
            if 'Model' in tagged:
                self.camera_model = str(tagged['Model']).strip()

        except (IOError, OSError) as e:
            logging.warning("%s: cannot read EXIF: %s",
                            self.source_path, e)
        except Exception:
            logging.warning('Unexpected error reading EXIF from %s',
                            self.source_path)
        finally:
            if image is not None:
                image.close()

    def _load_file_size(self):
        """Gets the size in bytes of the photo from the filesystem"""
        try:
            self.size = os.path.getsize(self.source_path)
        except os.error:
            self.size = 0
            logging.warning('Could not read file size of %s',
                            self.source_path)

    def _load_filesystem_timestamp(self):
        """Gets the last modified timestamp for the photo."""
        if self.timestamp is None:
            try:
                self.timestamp = os.path.getmtime(self.source_path)
            except os.error:
                logging.warning("Could not access image's timestamp"
                                " by any means, setting it to epoch.")
                self.timestamp = 0

    def _get_hash(self):
        """Computes the md5 hash."""
        md5_hash = hashlib.md5()
        with open(self.source_path, 'rb') as fh:
            while True:
                chunk = fh.read(8192)
                if not chunk:
                    break
                md5_hash.update(chunk)
        return md5_hash.hexdigest()


def configure_logging(filename):
    """Configures logging to stderr, file."""
    root = logging.getLogger('')
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(asctime)s %(filename)s'
                                  ':%(lineno)d %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)
    log_dir = '/var/tmp'
    file_handler = logging.FileHandler(os.path.join(log_dir, filename))
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)


def get_group_id(group_name):
    """Returns the group id for the given group name"""
    if group_name:
        return grp.getgrnam(group_name)[2]
    else:
        # means 'don't change group'
        return -1
