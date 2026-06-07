#!/usr/bin/env python3
"""Data fix for bad date on Flip camera.

Adds 1 year to every file's mtime in the specified directory.

Usage:
    python flipfix.py --dir /path/to/photos
"""
import argparse
import calendar
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(
        description='Add 1 year to every file\'s mtime in a directory.')
    parser.add_argument('--dir', required=True,
                        help='Directory containing files to fix')
    parser.add_argument('--yes', action='store_true',
                        help='Skip the confirmation prompt')
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f'Error: {args.dir} is not a directory', file=sys.stderr)
        sys.exit(1)

    files = [f for f in os.listdir(args.dir)
             if os.path.isfile(os.path.join(args.dir, f))]
    if not files:
        print(f'No files found in {args.dir}')
        sys.exit(0)

    print(f'Will add 1 year to mtime of {len(files)} file(s) in {args.dir}')
    if not args.yes:
        response = input('Proceed? [y/N] ')
        if response.lower() not in ('y', 'yes'):
            print('Aborted.')
            sys.exit(0)

    for filepath in files:
        full_path = os.path.join(args.dir, filepath)
        filestat = os.stat(full_path)
        mtime = filestat.st_mtime
        atime = filestat.st_atime
        mstruct_time = time.gmtime(mtime)
        mstruct_time_list = list(mstruct_time)
        mstruct_time_list = (mstruct_time_list[0] + 1,) + mstruct_time_list[1:]
        new_mtime = calendar.timegm(time.struct_time(mstruct_time_list))
        print(filepath, time.ctime(atime), time.ctime(new_mtime))
        os.utime(full_path, (atime, new_mtime))


if __name__ == '__main__':
    main()
