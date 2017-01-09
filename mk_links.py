#!/usr/bin/python

from sys import argv, stderr
from os import path, remove, listdir, symlink, link, chdir, stat, makedirs
from shutil import copy
import re
import getopt

usageMess = '''[--full|-f] [--short|-s] [--fold|-F] [--addfold|-a] [--servicenames|-S] [--hardlinks|-H] [--cleanall|-c] [--help|-h] picon-defs picon-dir ...
    --full|-f          use normal full serviceref picon links
    --short|-s         use short-form serviceref picon links
                       (REFTYPE:SID:TSID:ONID:NS)
    --fold|-f          fold all service types other than '2' to
                       '1', otherwise like --full
    --allfold|-a       add a folded serviceref link for all service
                       types other than '2' and '1', otherwise like --full
    --servicenames|-S  create service name picon links
    --hardlinks|-H     create hard picon links rather than soft links
    --cleanall|-c      remove all picon links first
    --copyimages=src-picon-dir|-C src-picon-dir
                       before creating links in each picon-dir,
                       clean out its channel_picons directory and
                       copy the contents of src-picon-dir/channel_picons
                       to picon-dir/channel_picons, with the
                       side-effect of creating the path
                       picon-dir/channel_picons if it doesn't already
                       exist
    --help|-h          print this message and exit

If none of --full, --short, --fold, --allfold or --servicenames are
specified, --full is assumed.'''


def usage(status):
        print >>stderr, "Usage:", argv[0], usageMess
        exit(status)

class LinkMaker:
    TITLES = {
        'buttonPicons': 'Australian picons, white background, button shading',
        'flatBlackPicons': 'Australian picons, black background',
        'flatPicons': 'Australian picons, white background',
        'maskPicons': 'Australian picons, with mask',
        'lcdPicons': 'Australian Front Panel picons',
    }

    CHAN_PICON_DIR = 'channel_picons'

    IS_FILE = 0
    IS_HLINK = 1
    IS_SLINK = 2
    IS_OTHER = 3
    IS_ERROR = 4

    # Indicators of the picon source:
    # ''      Unknown (implicit)
    # '_ab'   Aboriginal Broadcasting/Larrakia
    # '_fv'   Freeview
    # '_gm'   Goolarri Media
    # '_lw'   LogoWikea
    # '_nine' Nine Newtork
    # '_rc'   Racing.com
    # '_sbs'  SBS Network
    # '_wp'   WikiPedia
    # '_ys'   Yesshop

    PICON_SRCS = frozenset(('_ab', '_fv', '_gm', '_lw', '_nine', '_rc', '_sbs', '_wp', '_ys'))

    def __init__(self, piconDefsFile, piconPath, options):

        self.options = options

        if not piconPath:
            piconPath = '.'
        self.piconPath = piconPath

        piconSet, piconBase = path.split(piconPath)
        if piconSet:
            piconSet = path.split(piconSet)[1]
        else:
            piconSet = piconBase

        print >>stderr, piconSet + ':'

        self.linkedPiconNames = set()
        self.origPiconLinks = {}
        self.overrides = set()

        title = self.TITLES[piconSet] if piconSet in self.TITLES else piconSet

        self.htmlHead = '''<!DOCTYPE html PUBLIC "-//w3c//dtd html 4.0 transitional//en">
<html>
<head>
  <title>''' + title + '''</title>
</head>
<body text="#ffffff" bgcolor="#303030" link="#0000ff" vlink="#800080" alink="#ff00ff">
<h1><center>''' + title + '''</center></h1>
<table border="0" align="center" cellspacing="0" cellpadding="0">
  <tbody>'''

        self.htmlTail = '''  </tbody>
</table></body></html>'''

        if self.options.get("copyImages") is not None:
            self.copyImages(self.options.get("copyImages"))

        try:
            self.servrefFile = open(piconDefsFile)
        except Exception as err:
            print >>stderr, argv[0] + ':', "Can't open service reference file", piconDefsFile, '-', str(err)
            exit(1)

	self._makePiconFileList()

	self._cleanWrongLinks()

    def _makePiconFileList(self):
	try:
	    chanDir = path.join(self.piconPath, self.CHAN_PICON_DIR)
	    self.piconFiles = {}
	    for piconName in listdir(chanDir):
		basename, ext = path.splitext(piconName)
		if ext != ".png":
		    continue
		piconPath = path.join(chanDir, piconName)
		if path.isfile(piconPath):
		    origIndex = basename.rfind('_')
		    if origIndex > 0 and basename[origIndex:] in self.PICON_SRCS:
			piconBasename = basename[:origIndex]
		    else:
			piconBasename = basename
		    self.piconFiles[piconBasename] = (piconName, self.getLinkRef(piconPath))
	except Exception as err:
	    print >>stderr, "Can't process image directory", chanDir, '-', str(err)
	    exit(1)

    def _cleanWrongLinks(self):
        wrongLinks = []
        try:
            useHardLinks = self.options.get("useHardLinks", False)
            for servRefName in (name for name in listdir(self.piconPath) if path.splitext(name)[1] == ".png"):
                servRefPath = path.join(self.piconPath, servRefName)
                fileType = self.refType(servRefPath)
                if fileType in (self.IS_SLINK, self.IS_HLINK):
                    linkRef = self.getLinkRef(servRefPath)
                else:
                    continue
                if useHardLinks == (fileType == self.IS_HLINK):
                    self.origPiconLinks[servRefName] = linkRef
                else:
                    wrongLinks.append(servRefName)
            self._clean(wrongLinks)
            if self.options.get("cleanAll"):
                self.clean()
        except Exception as err:
            print >>stderr, "Can't process link directory", self.piconPath, "to get current link list -", str(err)
            exit(1)

    def refType(self, servRefPath):
        try:
            if path.islink(servRefPath):
                return self.IS_SLINK
            if path.isfile(servRefPath):
                return self.IS_HLINK if stat(servRefPath).st_nlink > 1 else self.IS_FILE
            return self.IS_OTHER
        except:
            return self.IS_ERROR

    def getLinkRef(self, servRefPath):
        st = stat(servRefPath)
        return st.st_dev, st.st_ino

    def isOverride(self, servRefPath):
        if servRefPath not in self.overrides and self.refType(servRefPath) == self.IS_FILE:
            self.overrides.add(servRefPath)
        return servRefPath in self.overrides

    def makeLinks(self):
        full = self.options.get("full")
        short = self.options.get("short")
        addfold = self.options.get("addfold")
        fold = self.options.get("fold")
        useServiceNameLinks = self.options.get("useServiceNameLinks")
        useHardLinks = self.options.get("useHardLinks")

        piconLinks = {}
        linksMade = 0  # ZZ
        commentRe = re.compile('#.*')

        for line in self.servrefFile:
            line = commentRe.sub('', line).rstrip()
            if not line:
                continue
            F = line.split()
            if len(F) > 3:
                print >>stderr, "Too many fields in server reference file:", line
                continue
            if len(F) < 3:
                print >>stderr, "Too few fields in server reference file:", line
                continue
            servRef, serviceName, picon = F
            servRefName = servRef
            servRefParts = servRefName.split(':')[0:10]
            servRefs = []
            if useServiceNameLinks:
                    servRefs.append([serviceName])
            if full or addfold:
                servRefs.append(servRefParts)
            if short:
                servRefs.append(servRefParts[0:1] + servRefParts[3:7])
            if addfold and (int(servRefParts[0]) & ~0x0100) == 1:
                stype = int(servRefParts[2], 16)
                if stype not in (1, 2):
                    servRefPartsFold = servRefParts[:]
                    servRefPartsFold[2] = "1"
                    servRefs.append(servRefPartsFold)
            if fold and (int(servRefParts[0]) & ~0x0100) == 1:
                stype = int(servRefParts[2], 16)
                if stype not in (1, 2):
                    servRefPartsFold = servRefParts[:]
                    servRefPartsFold[2] = "1"
                servRefs.append(servRefPartsFold)

            for srp in servRefs:
                servRefName = '_'.join(srp) + '.png'

                if piconLinks.get(servRefName) == picon:
                    continue

                if servRefName not in piconLinks:
                    linked = False
                    servRefPath = path.join(self.piconPath, servRefName)

                    exists = path.exists(servRefPath)

                    alreadyOverridden = servRefPath in self.overrides
                    if exists and self.isOverride(servRefPath):
                        if not alreadyOverridden:
                            print >>stderr, "Picon", picon, "over-ridden by specific servref icon", servRefName
                        continue

                    lexists = exists or path.lexists(servRefPath)

                    if (not exists or lexists) and picon in self.piconFiles:
			piconName, piconRef = self.piconFiles[picon]
			piconPath = path.join(self.CHAN_PICON_DIR, piconName)
			if useHardLinks:
			    piconPath = path.join(self.piconPath, piconPath)

			if servRefName in self.origPiconLinks:
			    if self.origPiconLinks[servRefName] == piconRef:
				linked = True
			    del self.origPiconLinks[servRefName]

			if not linked:
			    try:
				if lexists:
				    remove(servRefPath)

				linksMade += 1  # ZZ
				if useHardLinks:
				    link(piconPath, servRefPath)
				else:
				    symlink(piconPath, servRefPath)
				linked = True
			    except Exception as err:
				print >>stderr, ("Link" if useHardLinks else "Symlink"), piconName, "->", servRefName, "failed -", str(err)

                    if linked:
			# ZZ print >>stderr, "linked:", piconName, linked  # ZZ
                        self.linkedPiconNames.add(piconName)
                        piconLinks[servRefName] = picon
                    else:
                        if picon not in ("tba", "tobeadvised"):
                            print >>stderr, "No picon", picon, "for", servRef
                else:
                    print >>stderr, "Servref link", servRef, "->", piconLinks[servRefName], "exists; new link requested for", picon
        self.servrefFile.close()
        print >>stderr, "linksMade:", linksMade  # ZZ

    def checkUnused(self):
        piconNames = set(fileinfo[0] for fileinfo in self.piconFiles.values())
	for piconName in sorted(piconNames - self.linkedPiconNames):
            print >>stderr, "Picon", piconName, "unused"

    def makeHtmlIndex(self, index):
        try:
            htmlFile = open(path.join(self.piconPath, "index.html"), 'w')
        except Exception as err:
            print >>stderr, "Can't write to index.html -", str(err)
            exit(1)

        print >>htmlFile, self.htmlHead
        row = 0
        item = 0
        for piconName in sorted(fileinfo[0] for fileinfo in self.piconFiles.values()):
            piconPath = path.join(self.CHAN_PICON_DIR, piconName)
            if item == 0:
                htmlFile.write("  ")
                if row != 0:
                    htmlFile.write("</tr>")
                print >>htmlFile, "<tr>"
            print >>htmlFile, '    <td><img src="' + piconPath + '"></td>'
            item += 1
            if item >= 6:
                row += 1
                item = 0
        if row != 0:
            print >>htmlFile, "  </tr>"
        print >>htmlFile, self.htmlTail
        htmlFile.close()

    def copyImages(self, fromPath):
        chanPath = path.join(self.piconPath, self.CHAN_PICON_DIR)
        fromPath = path.join(fromPath, self.CHAN_PICON_DIR)
        if path.exists(chanPath):
            if path.isdir(chanPath):
                try:
                    for imageName in (name for name in listdir(chanPath) if path.splitext(name)[1] == ".png"):
                        imagePath = path.join(chanPath, imageName)
                        try:
                            remove(imagePath)
                        except Exception as err:
                            print >>stderr, "Can't remove", imagePath, "-", str(err)
                            exit(1)
                except Exception as err:
                    print >>stderr, "Can't access", chanPath, "-", str(err)
                    exit(1)
        else:
            try:
                makedirs(chanPath, 0755)
            except Exception as err:
                print >>stderr, "Can't create", chanPath, "-", str(err)
                exit(1)

        try:
            for imageName in (name for name in listdir(fromPath) if path.splitext(name)[1] == ".png"):
                imageFromPath = path.join(fromPath, imageName)
                copy(imageFromPath, chanPath)
        except Exception as err:
            print >>stderr, "Can't copy", imageFromPath, "to", chanPath, "-", str(err)
            exit(1)

    def _clean(self, servRefNames):
        print "removing:", len(servRefNames)  # ZZ
        for servRefName in servRefNames:
            servRefPath = path.join(self.piconPath, servRefName)
            try:
                remove(servRefPath)
            except Exception as err:
                print >>stderr, "Can't remove", servRefPath, "-", str(err)

    def clean(self):
        self._clean(self.origPiconLinks)
        self.origPiconLinks = {}


options = {
    "full": False,
    "short": False,
    "fold": False,
    "addfold": False,
    "useServiceNameLinks": False,
    "useHardLinks": False,
    "cleanAll": False,
    "copyImages": None
}

try:
    opts, args = getopt.getopt(argv[1:], "fsFaSHhcC:", ["full", "short", "fold", "addfold", "servicenames", "hardlinks", "cleanall", "copyimages=", "help"])
except getopt.GetoptError as err:
    print str(err)
    usage(2)

for o, a in opts:
    if o in ("--full", "-f"):
        options["full"] = True
    elif o in ("--short", "-s"):
        options["short"] = True
    elif o in ("--fold", "-F"):
        options["fold"] = True
    elif o in ("--addfold", "-a"):
        options["addfold"] = True
    elif o in ("--servicenames", "-S"):
        options["useServiceNameLinks"] = True
    elif o in ("--hardlinks", "-H"):
        options["useHardLinks"] = True
    elif o in ("--cleanall", "-c"):
        options["cleanAll"] = True
    elif o in ("--copyimages", "-C"):
        options["copyImages"] = a
    elif o in ("--help", "-h"):
        usage(0)
    else:
        assert False, argv[0] + ": Unknown option " + o
        usage(1)

if not any((options[linktype] for linktype in ("full", "short", "fold", "addfold", "useServiceNameLinks"))):
    options["full"] = True

if options["short"]:
    print >>stderr, "Picon links generated by --short (-s) are not yet supported by Beyonwiz firmware"

if len(args) < 2:
    usage(1)

piconDefsFile = args[0]

for i in range(1, len(args)):
    piconPath = args[i]

    linkMaker = LinkMaker(piconDefsFile, piconPath, options)

    linkMaker.makeLinks()
    linkMaker.checkUnused()
    linkMaker.makeHtmlIndex('index.html')
    linkMaker.clean()
