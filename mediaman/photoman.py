
import sys
import os
import time
import shutil
import hashlib
import logging
from exceptions import IOError
from logging import StreamHandler
from sqlite3 import dbapi2 as sqlite

 
def store_open(dataloc):  # opens, returns biggest ID or -1 on error
  # create data store if it doesn't exist
  if not os.access(dataloc, os.R_OK|os.W_OK|os.X_OK):
    logging.warning("can't open %s, will attempt to create it" % dataloc)
    tree_setup()
    # initialize the database
    con = sqlite.connect(dataloc + "/media.db")
    cur = con.cursor()
    r = cur.execute('''create table photos
      (id integer primary key,
      flags text,
      md5 varchar(16),
      constraint 'md5_UNIQUE' unique ('md5')
      size integer,
      description text,
      source_info text,
      source_path text,
      timestamp integer)
      ''')
  else:  
    con = sqlite.connect(dataloc + "/media.db")
  if con > 0:
    return con
  else:
    return -1


def tree_setup(dataloc):
  os.mkdir(dataloc, 0755)
  os.mkdir(dataloc + '/photos', 0755)


"""Configures logging to stderr, file.

"""
def configure_logging():
  root = logging.getLogger('')
  h = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s')
  h.setFormatter(formatter)
  root.addHandler(h)
  fh = logging.FileHandler('/var/tmp/myapp.log')
  fh.setFormatter(formatter)
  root.addHandler(fh)
  root.setLevel(logging.WARNING)


