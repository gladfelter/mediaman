#!/usr/bin/env python3
"""Photo collection utility — scans ~/Pictures and syncs new photos to staging.

Commands:
    (default)      Scan ~/Pictures for new photos, copy to Samba staging share
    collect        Same as default — explicit form
    fix-takeout    Fix mtimes on Google Takeout exports, copy to staging

Usage:
    python photocoll.py --staging_dir \\\\<SERVER_IP>\\photo_staging
    python photocoll.py collect --staging_dir \\\\<SERVER_IP>\\photo_staging
    python photocoll.py fix-takeout --src_dir ~/Downloads/takeout --staging_dir \\\\<SERVER_IP>\\photo_staging
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import takeout_fixer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CollectionState — manages JSON state file tracking last-collection times
# ---------------------------------------------------------------------------


class CollectionState:
    """Tracks the last time each source directory was collected.

    State is stored as a JSON dict mapping source-dir-path → epoch-timestamp.
    Updates happen in memory; call save() to persist to disk.
    """

    def __init__(self, state_path: Path):
        """Load existing state from *state_path*, or initialize empty."""
        self._state_path = state_path
        self._data: dict[str, float] = {}
        if state_path.exists():
            try:
                self._data = json.loads(state_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    'Failed to read state file %s, starting fresh', state_path
                )

    def get_last_collection(self, src_dir: Path) -> float:
        """Return the epoch timestamp of the last collection for *src_dir*.

        Returns 0.0 if this directory has never been collected.
        """
        return self._data.get(str(src_dir), 0.0)

    def set_last_collection(self, src_dir: Path, timestamp: float) -> None:
        """Update the last-collection timestamp for *src_dir* (in memory only)."""
        self._data[str(src_dir)] = timestamp

    def save(self) -> None:
        """Persist the current state to disk.

        If the state file cannot be written (disk full, permissions), a
        warning is logged but the program does not crash — the trade-off
        is that the next run will re-scan and re-copy already-copied files
        (harmless thanks to destination collision handling).
        """
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self._data, indent=2))
        except (OSError, TypeError) as e:
            logger.warning(
                'Could not save collection state to %s: %s',
                self._state_path, e,
            )


# ---------------------------------------------------------------------------
# find_new_photos — scan a directory tree for files newer than a timestamp
# ---------------------------------------------------------------------------


def find_new_photos(
    src_dir: Path,
    last_collection: float,
    ignore_extensions: set[str],
) -> list[Path]:
    """Walk *src_dir* and return files with mtime > *last_collection*.

    Files whose extension (case-insensitive) appears in *ignore_extensions*
    are skipped.  Files whose mtime cannot be read are silently skipped.

    A small epsilon (0.001 s) is subtracted from *last_collection* to
    avoid floating-point comparison edge cases.  Note: on filesystems
    with 1-second mtime granularity (FAT32, some NAS/Samba configs),
    files created in the same whole second as the last collection may
    be missed.  This is accepted as a known limitation.
    """
    # Tiny epsilon for floating-point comparison robustness.
    effective_cutoff = last_collection - 0.001

    results: list[Path] = []
    for dirpath_str, _dirnames, filenames in os.walk(str(src_dir)):
        dirpath = Path(dirpath_str)
        for filename in filenames:
            filepath = dirpath / filename
            suffix = filepath.suffix.lower()
            if suffix in ignore_extensions:
                continue
            try:
                mtime = os.path.getmtime(str(filepath))
            except OSError:
                logger.warning('Could not read mtime for %s, skipping', filepath)
                continue
            if mtime > effective_cutoff:
                logger.info(
                    'Found new photo: %s (mtime=%s)',
                    filepath,
                    time.asctime(time.localtime(mtime)),
                )
                results.append(filepath)
    return results


# ---------------------------------------------------------------------------
# copy_files — copy photos to the staging directory with collision handling
# ---------------------------------------------------------------------------


def copy_files(files: list[Path], dest_dir: Path) -> list[Path]:
    """Copy each file in *files* to *dest_dir*, renaming on name collisions.

    If ``dest_dir / file.name`` already exists, the file is copied as
    ``name_N.suffix`` where N is the smallest integer that avoids a
    collision (1, 2, 3, …).

    Uses ``O_EXCL`` (exclusive create) on the final destination to avoid
    TOCTOU races when multiple processes target the same path.

    Returns a list of destination Paths for the successfully copied files.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for src in files:
        stem = src.stem
        suffix = src.suffix
        dest = dest_dir / src.name
        counter = 0
        while True:
            try:
                fd = os.open(str(dest),
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                break
            except FileExistsError:
                counter += 1
                dest = dest_dir / f'{stem}_{counter}{suffix}'
        try:
            with open(str(src), 'rb') as fsrc:
                while True:
                    chunk = fsrc.read(8192)
                    if not chunk:
                        break
                    os.write(fd, chunk)
        finally:
            os.close(fd)
        shutil.copystat(str(src), str(dest))
        if counter > 0:
            logger.info(
                'Renamed %s → %s to avoid collision', src.name, dest.name
            )
        copied.append(dest)
    return copied


# ---------------------------------------------------------------------------
# collect_photos — orchestrate scan + copy + state update
# ---------------------------------------------------------------------------


def collect_photos(
    src_dir: Path,
    staging_dir: Path,
    ignore_extensions: set[str],
    state_path: Path | None = None,
    log_file: Path | None = None,
) -> list[Path]:
    """Scan *src_dir* for new photos and copy them to *staging_dir*.

    State (last-collection timestamp) is written to *state_path* only after
    a **successful** copy operation.  If copying fails the state is
    left unchanged so the next run will re-attempt those files.

    Parameters
    ----------
    src_dir:
        Directory to scan for photos.
    staging_dir:
        Destination directory (e.g. a Samba staging share).
    ignore_extensions:
        Set of file extensions to skip (e.g. ``{'.txt', '.db'}``).
    state_path:
        Path to the JSON state file.  Defaults to
        ``%LOCALAPPDATA%/mediaman/collection_state.json`` on Windows,
        ``~/.local/share/mediaman/collection_state.json`` elsewhere.
    log_file:
        Optional path for a log file.  When ``None`` logging goes to
        stderr only.

    Returns
    -------
    list[Path]
        Destination paths of the files that were copied.
    """
    # Determine default state path
    if state_path is None:
        if os.name == 'nt':
            local_appdata = os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))
            state_path = Path(local_appdata) / 'mediaman' / 'collection_state.json'
        else:
            xdg_data = os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))
            state_path = Path(xdg_data) / 'mediaman' / 'collection_state.json'

    # Load state
    state = CollectionState(state_path)
    last_coll = state.get_last_collection(src_dir)

    logger.info(
        'Starting photo collection: src_dir=%s, staging_dir=%s, last_collection=%s',
        src_dir, staging_dir, time.ctime(last_coll) if last_coll else 'never',
    )

    # Find new photos
    new_photos = find_new_photos(src_dir, last_coll, ignore_extensions)

    if not new_photos:
        logger.info('No new photos found.')
        return []

    logger.info('Copying %d new photo(s) to staging...', len(new_photos))

    # Copy to staging
    start_time = time.time()
    copied = copy_files(new_photos, staging_dir)

    # Only update state on success
    state.set_last_collection(src_dir, start_time)
    state.save()

    logger.info('Collection complete: %d file(s) copied.', len(copied))
    return copied


# ---------------------------------------------------------------------------
# CLI entry point (argparse)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Parse command-line arguments and run the appropriate command.

    Supports two journeys:
      - collect (default): scan ~/Pictures, copy new photos to staging
      - fix-takeout: fix Google Takeout mtimes, copy to staging

    Exit codes:
        0 — success
        1 — usage error
        2 — runtime failure
    """
    default_src = Path.home() / 'Pictures'

    parser = argparse.ArgumentParser(
        description='Scan a directory for new photos and copy them to staging.',
    )
    sub = parser.add_subparsers(dest='command')

    # ---- collect ----
    collect_parser = sub.add_parser(
        'collect',
        help='Scan ~/Pictures for new photos and copy to staging (default)',
    )
    collect_parser.add_argument(
        '--src_dir',
        type=Path,
        default=default_src,
        help='Directory to scan for photos (default: ~/Pictures)',
    )
    collect_parser.add_argument(
        '--staging_dir',
        type=Path,
        required=True,
        help='Destination directory for staging (e.g. Samba share path)',
    )
    collect_parser.add_argument(
        '--ignore_extensions',
        type=str,
        default='.ini,.db',
        help='Comma-separated extensions to skip (default: .ini,.db)',
    )
    collect_parser.add_argument(
        '--state_path',
        type=Path,
        default=None,
        help='Path to the JSON state file (default: platform-appropriate location)',
    )
    collect_parser.add_argument(
        '--log_file',
        type=Path,
        default=None,
        help='Path to write log output (in addition to stderr)',
    )

    # ---- fix-takeout ----
    fix_parser = sub.add_parser(
        'fix-takeout',
        help='Fix Google Takeout mtimes and copy media to staging',
    )
    fix_parser.add_argument(
        '--src_dir',
        type=Path,
        required=True,
        help='Directory containing the extracted Google Takeout files',
    )
    fix_parser.add_argument(
        '--staging_dir',
        type=Path,
        required=True,
        help='Destination directory for staging (e.g. Samba share path)',
    )
    fix_parser.add_argument(
        '--delete_json',
        action='store_true',
        help='Delete JSON sidecar files after successfully fixing mtimes',
    )
    fix_parser.add_argument(
        '--log_file',
        type=Path,
        default=None,
        help='Path to write log output (in addition to stderr)',
    )

    # ---- top-level (backward compat: runs collect) ----
    parser.add_argument(
        '--src_dir',
        type=Path,
        default=default_src,
        help='Directory to scan for photos (default: ~/Pictures)',
    )
    parser.add_argument(
        '--staging_dir',
        type=Path,
        default=None,
        help='Destination directory for staging (e.g. Samba share path)',
    )
    parser.add_argument(
        '--ignore_extensions',
        type=str,
        default='.ini,.db',
        help='Comma-separated extensions to skip (default: .ini,.db)',
    )
    parser.add_argument(
        '--state_path',
        type=Path,
        default=None,
        help='Path to the JSON state file (default: platform-appropriate location)',
    )
    parser.add_argument(
        '--log_file',
        type=Path,
        default=None,
        help='Path to write log output (in addition to stderr)',
    )

    args = parser.parse_args(argv)

    # Configure logging
    log_file = args.log_file
    _configure_logging(log_file)

    try:
        if args.command == 'fix-takeout':
            _cmd_fix_takeout(args)
        else:
            _cmd_collect(args)
    except Exception:
        logger.exception('Photo collection failed with an unexpected error')
        sys.exit(2)


def _cmd_collect(args) -> None:
    """Run the collect journey (scan ~/Pictures → staging)."""
    if args.staging_dir is None:
        logger.error('--staging_dir is required')
        sys.exit(1)

    ignore_extensions = {
        ('.' + ext.strip().lower()) if not ext.strip().startswith('.') else ext.strip().lower()
        for ext in args.ignore_extensions.split(',')
        if ext.strip()
    }

    collected = collect_photos(
        src_dir=args.src_dir,
        staging_dir=args.staging_dir,
        ignore_extensions=ignore_extensions,
        state_path=args.state_path,
        log_file=args.log_file,
    )
    if collected:
        logger.info('Successfully copied %d file(s).', len(collected))
    else:
        logger.info('No files needed copying.')


def _cmd_fix_takeout(args) -> None:
    """Run the Google Takeout journey (fix mtimes → staging)."""
    src_dir = str(args.src_dir)
    staging_dir = args.staging_dir

    if not os.path.isdir(src_dir):
        logger.error('%s is not a directory', src_dir)
        sys.exit(1)

    # Step 1: Fix mtimes from JSON sidecars
    logger.info('Fixing mtimes from Google Takeout JSON sidecars...')
    fixed, already_ok, skipped = takeout_fixer.fix_mtimes(
        src_dir, delete_json=args.delete_json,
    )
    logger.info(
        'Mtimes: %d fixed, %d already had EXIF dates, %d skipped',
        fixed, already_ok, skipped,
    )

    # Step 2: Find all media files (non-JSON)
    media_files = takeout_fixer.iter_media_files(src_dir)
    if not media_files:
        logger.info('No media files found in %s', src_dir)
        return

    logger.info('Copying %d media file(s) to staging...', len(media_files))

    # Step 3: Copy to staging
    media_paths = [Path(p) for p in media_files]
    copied = copy_files(media_paths, staging_dir)
    logger.info('Copied %d file(s) to staging.', len(copied))


def _configure_logging(log_file: Path | None = None) -> None:
    """Configure logging to stderr, and optionally to a log file."""
    root = logging.getLogger('')
    # Close and remove existing handlers before clearing
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s'
    )

    # Always log to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    # Optionally log to file
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file))
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


if __name__ == '__main__':
    main()
