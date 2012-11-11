#! /usr/bin/python
#
""" Provides a daemon that allows querying the media library databse for known
hash values.

Daemon aspects based on http://homepage.hispeed.ch/py430/python/daemon.py
"""

import gflags
from SimpleXMLRPCServer import SimpleXMLRPCServer
import sys
import logging
import os
import photoman
import common.common


gflags.DEFINE_string('group_name', '', 'The name of the group to use' +
                     ' for the daemon process')
gflags.DEFINE_string('user_name', '', 'The name of the user to use' +
                     ' for the daemon process')

FLAGS = gflags.FLAGS

repository = photoman.Repository()

def run_server(lib_base_dir):
  repository.open(lib_base_dir)
  logging.info('opened repository at %s', lib_base_dir)
  server = SimpleXMLRPCServer(('192.168.1.27', 9333), logRequests=True)
  server.register_function(check_file_hash)
  try:
    print 'Use Control-C to exit'
    server.serve_forever()
  except KeyboardInterrupt:
    print 'Exiting'


def check_file_hash(hash):
  return repository.lookup_hash(hash)[1]
  

# Expose a function
def list_contents(dir_name):
  logging.debug('list_contents(%s)', dir_name)
  return os.listdir(dir_name)


def _configure_logging():
  """Configures logging to stderr, file."""
  root = logging.getLogger('')
  handler = logging.StreamHandler(sys.stderr)
  formatter = logging.Formatter('%(asctime)s %(filename)s' +
                                ':%(lineno)d %(levelname)s %(message)s')
  handler.setFormatter(formatter)
  root.addHandler(handler)
  file_handler = logging.FileHandler('/var/tmp/photoman.log')
  file_handler.setFormatter(formatter)
  root.addHandler(file_handler)
  root.setLevel(logging.INFO)


def _main(argv):
  """Main script entry point """
  try:
    gflags.MarkFlagAsRequired('media_dir')
    gflags.MarkFlagAsRequired('group_name')
    gflags.MarkFlagAsRequired('user_name')
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  try:
    # do the UNIX double-fork magic, see Stevens' "Advanced
    # Programming in the UNIX Environment" for details (ISBN 0201563177)
    try:
      pid = os.fork()
      if pid > 0:
        # exit first parent
        sys.exit(0)
    except OSError, e:
      print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror)
      sys.exit(1)

    # decouple from parent environment
    os.chdir("/")   #don't prevent unmounting....
    os.setsid()
    os.umask(0)

    # do second fork
    try:
      pid = os.fork()
      if pid > 0:
        # exit from second parent, print eventual PID before
        #print "Daemon PID %d" % pid
        open(PIDFILE,'w').write("%d"%pid)
        sys.exit(0)
    except OSError, e:
      print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror)
      sys.exit(1)

    #ensure the that the daemon runs a normal user
    os.setegid(photoman.get_group_id(FLAGS.group_name))
    os.seteuid(photoman.get_group_id(FLAGS.user_name))
    _configure_logging()
    # start the daemon main loop
    run_server(FLAGS.media_dir)
  except:
    logging.exception('An unexpected error occurred during photo archiving')

PIDFILE = '/var/run/media_library_server.pid'

if __name__ == "__main__":
    _main(sys.argv)
