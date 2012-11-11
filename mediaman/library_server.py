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
import media_common

PIDFILE = '/var/run/media_library_server.pid'

gflags.DEFINE_string('group_name', '', 'The name of the group to use' +
                     ' for the daemon process')
gflags.DEFINE_string('user_name', '', 'The name of the user to use' +
                     ' for the daemon process')
gflags.DEFINE_string('media_dir', None, 'Directory of media library')
gflags.DEFINE_boolean('daemon', True, 'Run the server as a daemon')

gflags.MarkFlagAsRequired('media_dir')
gflags.MarkFlagAsRequired('group_name')
gflags.MarkFlagAsRequired('user_name')

FLAGS = gflags.FLAGS

repository = media_common.Repository()

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


def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  try:
    if FLAGS.daemon:
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
      os.setegid(media_common.get_group_id(FLAGS.group_name))
      os.seteuid(media_common.get_group_id(FLAGS.user_name))
    media_common.configure_logging('media_library_server.log')
    # start the daemon main loop
    run_server(FLAGS.media_dir)
  except:
    logging.exception('An unexpected error occurred during photo archiving')


if __name__ == "__main__":
    _main(sys.argv)
