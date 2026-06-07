#! /usr/bin/python
#
"""Data fix for bad date on Flip camera"""

import calendar
import os
import time
from stat import *


files = os.listdir('.')
for filepath in files:
  filestat = os.stat(filepath)
  mstruct_time = time.gmtime(filestat[ST_MTIME])
  atime = filestat[ST_ATIME]
  mstruct_time_list = list(mstruct_time)
  mstruct_time_list[0] += 1
  mtime = calendar.timegm(time.struct_time(mstruct_time_list))
  print filepath, time.ctime(atime), time.ctime(mtime)
  os.utime(filepath, (atime, mtime))
