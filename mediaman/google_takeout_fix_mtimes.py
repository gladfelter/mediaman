#!/usr/bin/env python3
"""Standalone CLI for fixing Google Takeout mtimes.

For the integrated Windows client with staging-copy support, use::

    photocoll fix-takeout --src_dir ... --staging_dir ...

This script is a thin wrapper that can be used directly on the server.
"""
import argparse
import logging
import os
import sys

from takeout_fixer import fix_mtimes


logger = logging.getLogger(__name__)


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
