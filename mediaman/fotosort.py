# fotosort.py
# Takes a list of photo files and lets you play with them
# What it did goes in a database including user supplied flags and description
# Phil Hughes 25 Dec 2007@0643

import sys
import os
import time
import shutil
import hashlib
from pysqlite2 import dbapi2 as sqlite

dataloc ="/home/fyl/PIXTREE"	# where to build the tree

connection = 0			# will be connection ID

class Rec():		# what we will put in the db
	def __init__(self, source_info):
		self.source_info = source_info	# where it came from (computer, cd, ...)
	# id integer primary key	# will be filename
	# flags text				# letters used for selection
	# md5 text					# MD5 hex digest
	# size integer				# file byte count
	# description text			# caption information
	# source_path text			# path we got it from
	# timestamp integer			# creation timestamp (from image of fs date)

def tree_setup():
	os.mkdir(dataloc, 0755)		# tree base
	for x in range(100):		# build 100 sub-directories
		os.mkdir("%s/%02i" % (dataloc, x), 0755)


def show_pix(path):		# runs display, returns display_pid so kill can work
	# return os.spawnv(os.P_NOWAIT, "/usr/bin/display", ["-resize 80x80", path])
	# return os.spawnv(os.P_NOWAIT, "kview", ["--nograb", path])
	# return os.popen("/usr/local/bin/xv -geometry 80x80 %s" % path, 'w')
	
	return os.spawnv(os.P_NOWAIT, "/usr/bin/gm", ["display", "-geometry", "240x240", path])
	# return os.spawnv(os.P_NOWAIT, "/usr/bin/kstart --nograb", ["/usr/bin/gm", "display", "-geometry", "240x240", path])

def store_open():	# opens, returns biggest ID or -1 on error
	# create data store if it doesn't exist
	if not os.access(dataloc, os.R_OK|os.W_OK|os.X_OK):
		print "can't open %s\n" % dataloc
		if raw_input("Create data structures (y/n): ") == 'y':
			tree_setup()
			# initialize the database
			con = sqlite.connect(dataloc + "/pix.db")
			cur = con.cursor()
			cur.execute('''create table pix
				(id integer primary key,
				flags text,
				md5 text,
				size integer,
				description text,
				source_info text,
				source_path text,
				timestamp integer)
				''')
		else:		# the boss said forget it
			exit(1)
	else:	
		con = sqlite.connect(dataloc + "/pix.db")
	if con > 0:
		return con
	else:
		return -1	

def store_close(con):
	con.close()

def store_add(data): # assigns next id, saves, returns id
	cur = connection.cursor()
	cur.execute('''
	insert into pix (flags, md5, size, description, source_info, source_path, timestamp) values (?, ?, ?, ?, ?, ?, ?)''', (data.flags, data.md5, data.size, data.description, data.source_info, data.source_path, data.timestamp)
	)
	connection.commit()
	return cur.lastrowid

def openfl(path):	# open a file list (getfn gets entries), returns file object
	return open(path, 'r')

def getfn(rec):	# gets the next filename
	return readline(lfo)


def form_fill(rec):		# pass record to fill in
	rec.flags = raw_input("Flags: ")
	rec.description = raw_input("Desc.: ")
	
def file_ts(path):	# returns creation timestamp, file size in bytes
	size = os.stat(path).st_size
	# look for EXIF info but, if not found, uses filesystem timestamp
	exiv2fo = os.popen("/usr/bin/exiv2  %s" % path, 'r')
	for line in exiv2fo:
		if line[0:15] == "Image timestamp":
			cl = line.index(':')
			ts_str = line[cl+2:cl+21]
			ts = time.mktime((int(line[cl+2:cl+6]), int(line[cl+7:cl+9]), int(line[cl+10:cl+12]), int(line[cl+13:cl+15]), int(line[cl+16:cl+18]), int(line[cl+19:cl+21]), 0, 0, 0))
			break
	else:			# use filesystem timestamp			
		ts = os.stat(path).st_mtime
	exiv2fo.close()
	return (long(ts), size)
	
def img_save(image_file, id):	# copy image file to store
	# store location is built from id and some other fun stuff
	
	fname = "z_%06d" % int(id)
	dest = dataloc + "/" + "%02d" % (int(id) % 100) + '/' + fname
	# print dest
	shutil.copyfile(image_file, dest)
	return dest

def img_hash(image_file):	# returns MD5 hash for a file
	fo = open(image_file, 'r')
	m = hashlib.md5()
	stuff = fo.read(8192)
	while len(stuff) > 0:
		m.update(stuff)
		stuff = fo.read(8192)
	fo.close()
	return (m.hexdigest())

###
### This is where the action starts ###

if len(sys.argv) != 2:
	print "usage %s names_file\n" % sys.argv[0]
	exit(1)
	
lfo = openfl(sys.argv[1])		# filename list file
connection = store_open()
if connection < 0:
	print "%s: unable to initialize database" % sys,agrv[0]
	exit(1)

# let's get the string to use for source info
rec = Rec(raw_input("Enter source info: "))

for f in lfo:
	f = f.strip()				# toss possible newline
	display_pid = show_pix(f)
	disp = raw_input("s[ave]/d[iscard]/q[uit]: ")
	if disp != 'q' and disp != 'd':
		rec.timestamp, rec.size = file_ts(f)
		rec.source_path = f
		rec.md5 = img_hash(f)	# hash

		form_fill(rec)				# get user input
		id = store_add(rec)			# insert in db
		savedloc = img_save(f, id)	# copy the image
	
		print "Photo saved as %s\n" % savedloc
	os.system("kill %s" % display_pid)
	if disp == 'q':
		break