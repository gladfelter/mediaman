from lxml import etree
import gflags
import sys

gflags.DEFINE_string('src', None, 'File to convert')

FLAGS = gflags.FLAGS

def _main(argv):
  """Main script entry point """
  try:
    argv = FLAGS(argv)  # parse flags
  except gflags.FlagsError, error:
    print '%s\nUsage: %s ARGS\n%s' % (error, sys.argv[0], FLAGS)
    sys.exit(1)
  f = open(FLAGS.src, 'r')
  outf = open(FLAGS.src[0:FLAGS.src.rfind('.')] + '.txt', 'w')
  tree = etree.parse(f)
  media = tree.xpath('/smil/body/seq/media')
  for medium in media:
    outf.write("%s | %s\n" % (
        str(medium.xpath('@trackTitle')[0]), str(medium.xpath('@trackArtist')[0])))
    
if __name__ == '__main__':
  _main(sys.argv)
