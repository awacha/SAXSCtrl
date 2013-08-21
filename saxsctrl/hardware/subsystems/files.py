import os
import re
import logging
from .subsystem import SubSystem
import ConfigParser
import sastool

from gi.repository import GObject
from gi.repository import Gio

__all__ = ['SubSystemFiles']

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SubSystemFiles(SubSystem):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),  # emitted whenever properties filebegin or ndigits, or the list of watched folders change
                    'new-nextfsn':(GObject.SignalFlags.RUN_FIRST, None, (int, str)),  # emitted whenever the next fsn from the current format changes.
                    'new-firstfsn':(GObject.SignalFlags.RUN_FIRST, None, (int, str)),  # emitted whenever the first fsn from the current format changes.
                    'notify':'override',
                  }
    filebegin = GObject.property(type=str, default='crd', blurb='First part of exposure names')
    ndigits = GObject.property(type=int, default=5, minimum=1, blurb='Number of digits in exposure names')
    rootpath = GObject.property(type=str, default='~/credo_data/current', blurb='Data root path')
    scanfilename = GObject.property(type=str, default='credoscan.spec', blurb='Scan file')
    def __init__(self, credo, offline=True, rootpath=None, filebegin=None, ndigits=None):
        SubSystem.__init__(self, credo, offline)
        self.monitors = []
        if filebegin is not None: self.filebegin = filebegin
        if ndigits is not None: self.ndigits = ndigits
        if rootpath is not None: self.rootpath = rootpath
        self._setup(self.rootpath)
        self.scanfile = None
        self.scanfilename = 'credoscan.spec'
        self._lastevents = []
    def do_notify(self, prop):
        if prop.name in ['rootpath']:
            if os.path.expanduser(self.rootpath) != self.rootpath:
                self.rootpath = os.path.expanduser(self.rootpath)
            elif os.path.realpath(self.rootpath) != self.rootpath:
                self.rootpath = os.path.realpath(self.rootpath)
            else:
                self._setup(self.rootpath)
        if prop.name in ['filebegin', 'ndigits', 'rootpath']:
            self.emit('changed')
        if prop.name in ['scanfilename']:
            if not os.path.isabs(self.scanfilename):
                self.scanfilename = os.path.join(self.scanpath, self.scanfilename)
            else:
                self.reload_scanfile()
    def reload_scanfile(self):
        if isinstance(self.scanfile, sastool.classes.SASScanStore):
            self.scanfile.finalize()
            del self.scanfile
        logger.debug('Reloading scan file from ' + self.scanfilename + '')
        self.scanfile = sastool.classes.SASScanStore(self.scanfilename, 'CREDO spec file', [])
        logger.debug('Scan file reloaded: ' + str(self.scanfile))
        return self.scanfile
    def _setup(self, rootpath):
        logger.debug('Running SubSystemFiles._setup()')
        for monitor, connection in self.monitors:
            monitor.cancel()
            monitor.disconnect(connection)
        if self.rootpath != rootpath:
            logger.debug('SubSystemFiles._setup(): setting rootpath to %s (was: %s)' % (rootpath, self.rootpath))
            self.rootpath = rootpath
        self.monitors = []
        for folder in self._watchpath():
            dirmonitor = Gio.file_new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitors.append((dirmonitor, dirmonitor.connect('changed', self._on_monitor_event)))
            logger.debug('SubSystemFiles._setup(): Added directory monitor for path %s' % folder)
        self._nextfsn_cache = {}
        self._firstfsn_cache = {}
        for f in self._search_formats():
            self.get_next_fsn(self.get_format_re(f, self.ndigits, False))
            self.get_first_fsn(self.get_format_re(f, self.ndigits, False))
    def _watchpath(self):
        return [self._get_subpath(subdir) for subdir in ['images', 'param', 'eval2d', 'eval1d']]
    def _search_formats(self):
        regex = re.compile('(?P<begin>[a-zA-Z0-9]+)_(?P<fsn>\d+)')
        formats = set()
        for pth in self.exposureloadpath:
            formats.update({m.groupdict()['begin'] for m in [regex.match(f) for f in os.listdir(pth)] if (m is not None)})
        return sorted(list(formats))
    def _known_regexes(self):
        return set(self._nextfsn_cache.keys()).union(set(self._firstfsn_cache.keys()))
    def formats(self):
        return sorted([p.pattern.split('_')[0] for p in self._known_regexes()])
    def _on_monitor_event(self, monitor, filename, otherfilename, event):
        if otherfilename is not None:
            logger.debug('SubSystemFiles._on_monitor_event() starting: filename: ' + filename.get_path() + ', otherfilename: ' + otherfilename.get_path() + ', event: ' + str(event))
        else:
            logger.debug('SubSystemFiles._on_monitor_event() starting: filename: ' + filename.get_path() + ', otherfilename: None, event: ' + str(event))
            
        if (event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED)):
            basename = filename.get_basename()
            if basename:
                for regex in self._known_regexes():
                    m = regex.match(basename)
                    if m is not None:
                        newfsn = int(m.group(1))
                        if regex in self._nextfsn_cache:
                            if newfsn >= self._nextfsn_cache[regex]:
                                self._nextfsn_cache[regex] = int(m.group(1)) + 1
                                self.emit('new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
                            else:
                                logger.debug('Not updating nextfsn: %d <= %d' % (newfsn + 1, self._nextfsn_cache[regex]))
                        if regex in self._firstfsn_cache:
                            if (self._firstfsn_cache[regex] is None) or (newfsn < self._firstfsn_cache[regex]):
                                self._firstfsn_cache[regex] = int(m.group(1))
                                self.emit('new-firstfsn', self._firstfsn_cache[regex], regex.pattern)
                            else:
                                logger.debug('Not updating firstfsn: %d >= %d' % (newfsn, self._firstfsn_cache[regex]))
        else:
            logger.debug('SubSystemFiles._on_monitor_event(): nothing to be done.')
        self._lastevents.append(event)
    def do_new_nextfsn(self, nextfsn, repattern):
        logger.debug('SubSystemFiles: new nextfsn: %d for pattern %s' % (nextfsn, repattern))
    def do_new_firstfsn(self, firstfsn, repattern):
        logger.debug('SubSystemFiles: new firstfsn: %d for pattern %s' % (firstfsn, repattern))
    def get_first_fsn(self, regex=None):
        if regex is None:
            regex = self.get_fileformat_re()
        currentpattern = (regex.pattern == self.get_fileformat_re().pattern)
        if regex in self._firstfsn_cache:
            return self._firstfsn_cache[regex]
        logger.debug('SubSystemFiles: finding lowest fsn for files matching pattern %s' % regex.pattern)
        minfsns = []
        for pth in self.exposureloadpath:
            fsns = [int(m.group(1)) for m in [regex.match(f) for f in os.listdir(pth)] if m is not None]
            if fsns:
                minfsns.append(min(fsns))
        if minfsns:
            self._firstfsn_cache[regex] = min(minfsns)
        else:
            self._firstfsn_cache[regex] = None
        if currentpattern and (self._firstfsn_cache[regex] is not None):
            self.emit('new-firstfsn', self._firstfsn_cache[regex], regex.pattern)
        return self._firstfsn_cache[regex]
    def get_next_fsn(self, regex=None):
        if regex is None:
            regex = self.get_fileformat_re()
        currentpattern = (regex.pattern == self.get_fileformat_re().pattern)
        if regex in self._nextfsn_cache:
            return self._nextfsn_cache[regex]
        logger.debug('SubSystemFiles: finding highest fsn for files matching pattern %s' % regex.pattern)
        maxfsns = [0]
        for pth in self.exposureloadpath:
            fsns = [int(m.group(1)) for m in [regex.match(f) for f in os.listdir(pth)] if m is not None]
            if fsns:
                maxfsns.append(max(fsns))
        self._nextfsn_cache[regex] = max(maxfsns) + 1
        if currentpattern:
            self.emit('new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
        return self._nextfsn_cache[regex]
    def increment_next_fsn(self, regex=None):
        if regex is None:
            regex = self.get_fileformat_re()
        self._nextfsn_cache[regex] = self.get_next_fsn(regex) + 1
        if (regex.pattern == self.get_fileformat_re().pattern):
            self.emit('new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
        return self._nextfsn_cache[regex]
        
    def _get_subpath(self, subdir):
        pth = os.path.join(os.path.expanduser(self.rootpath), subdir)
        while os.path.islink(pth):
            pth = os.readlink(pth)
        if not os.path.isdir(pth):
            if not os.path.exists(pth):
                os.mkdir(pth)  # an OSError is raised if no permission.
            else:
                raise OSError('%s exists and is not a directory!' % pth)
        return pth
    @property
    def configpath(self): return self._get_subpath('config')
    @property
    def exposureloadpath(self):
        ret = []
        for p in ['eval2d', 'eval1d', 'param', 'images']:
            try:
                ret.append(self._get_subpath(p))
            except OSError:
                logger.warning('Subpath %s cannot be found, not including it to exposureloadpath!' % p)
        ret.extend(sastool.misc.find_subdirs(self._get_subpath('mask'), None))
        return ret
    @property
    def rawloadpath(self):
        ret = []
        for p in ['param', 'images']:
            try:
                ret.append(self._get_subpath(p))
            except OSError:
                logger.warning('Subpath %s cannot be found, not including it to exposureloadpath!' % p)
        ret.extend(sastool.misc.find_subdirs(self._get_subpath('mask'), None))
        return ret
    @property
    def reducedloadpath(self):
        ret = []
        for p in ['eval2d', 'eval1d']:
            try:
                ret.append(self._get_subpath(p))
            except OSError:
                logger.warning('Subpath %s cannot be found, not including it to exposureloadpath!' % p)
        ret.extend(sastool.misc.find_subdirs(self._get_subpath('mask'), None))
        return ret
    @property
    def moviepath(self): return self._get_subpath('movie')
    @property
    def parampath(self): return self._get_subpath('param')
    @property
    def maskpath(self): return self._get_subpath('mask')
    @property
    def scanpath(self): return self._get_subpath('scan')
    @property
    def eval2dpath(self): return self._get_subpath('eval2d')
    @property
    def eval1dpath(self): return self._get_subpath('eval1d')
    @property
    def imagespath(self): return self._get_subpath('images')
    def get_fileformat(self, filebegin=None, ndigits=None):
        if filebegin is None: filebegin = self.filebegin
        if ndigits is None: ndigits = self.ndigits
        return filebegin + '_' + '%%0%dd' % ndigits
    def get_fileformat_re(self, strict=False):
        return self.get_format_re(self.filebegin, self.ndigits, strict)
    def get_headerformat(self, filebegin=None, ndigits=None): return self.get_fileformat(filebegin, ndigits) + '.param'
    def get_exposureformat(self, filebegin=None, ndigits=None): return self.get_fileformat(filebegin, ndigits) + '.cbf'
    def get_headerformat_re(self, strict=False): return re.compile(self.get_fileformat_re().pattern + '\.param', strict)
    def get_exposureformat_re(self, strict=False): return re.compile(self.get_fileformat_re().pattern + '\.cbf', strict)
    def get_eval2dformat(self, filebegin='crd', ndigits=5): return self.get_fileformat(filebegin, ndigits) + '.npz'
    def get_evalheaderformat(self, filebegin='crd', ndigits=5): return self.get_fileformat(filebegin, ndigits) + '.param'
    def get_format_re(self, filebegin, ndigits, strict=False):
        if strict:
            return re.compile(filebegin + '_' + '(?P<fsn>\d{%d})' % ndigits)
        else:
            return re.compile(filebegin + '_' + '(?P<fsn>\d+)')
    def writeheader(self, header, raw=True):
        if raw:
            header.write(os.path.join(self.parampath, self.get_headerformat() % header['FSN']))
        else:
            header.write(os.path.join(self.eval2dpath, self.get_headerformat() % header['FSN']))
    def writereduced(self, exposure):
        exposure.write(os.path.join(self.eval2dpath, self.get_eval2dformat() % exposure['FSN']))
        exposure.header.write(os.path.join(self.eval2dpath, self.get_evalheaderformat() % exposure['FSN']))
    def writeradial(self, exposure):
        exposure.radial_average().save(os.path.join(self.eval1dpath, 'crd_%d.txt' % exposure['FSN']))
        