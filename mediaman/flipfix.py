#!/usr/bin/env python3
"""Data fix for bad date on Flip camera"""
import calendar
import os
import time

files = os.listdir('.')
for filepath in files:
    filestat = os.stat(filepath)
    mtime = filestat.st_mtime
    atime = filestat.st_atime
    mstruct_time = time.gmtime(mtime)
    mstruct_time_list = list(mstruct_time)
    mstruct_time_list = (mstruct_time_list[0] + 1,) + mstruct_time_list[1:]
    new_mtime = calendar.timegm(time.struct_time(mstruct_time_list))
    print(filepath, time.ctime(atime), time.ctime(new_mtime))
    os.utime(filepath, (atime, new_mtime))
