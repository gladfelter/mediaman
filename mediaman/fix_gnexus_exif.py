#! /usr/bin/python
import pyexiv2
import sys

def _main(argv):
  image = pyexiv2.ImageMetadata(argv[1])
  image.read()
  del image['Exif.Photo.ISOSpeedRatings']
  image.write()
  print reduce(lambda coll, next: "%s\n%s=%s" % (coll, next[0], next[1].value), image.items())


if __name__ == '__main__':
  _main(sys.argv)
