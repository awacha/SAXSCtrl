import os
import re
import logging
from .subsystem import SubSystem
import ConfigParser

from gi.repository import GObject
from gi.repository import Gio

__all__ = ['SubSystemFiles']

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SubSystemFiles(SubSystem):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),  # emitted whenever properties filebegin or ndigits, or the list of watched folders change
                    'new-nextfsn':(GObject.SignalFlags.RUN_FIRST, None, (int, str)),  # emitted whenever the next fsn from the current format changes.
                    'notify':'override',
                  }
    filebegin = GObject.property(type=str, default='crd', blurb='First part of exposure names')
    ndigits = GObject.property(type=int, default=5, minimum=1, blurb='Number of digits in exposure names')
    rootpath = GObject.property(type=str, default='~/credo_data/current', blurb='Data root path')
    def __init__(self, credo, rootpath=None, filebegin=None, ndigits=None):
        SubSystem.__init__(self, credo)
        self.monitors = []
        if filebegin is not None: self.filebegin = filebegin
        if ndigits is not None: self.ndigits = ndigits
        if rootpath is not None: self.rootpath = rootpath
        self._setup(self.rootpath)
    def do_notify(self, prop):
        if prop.name in ['rootpath']:
            self._setup(self.rootpath)
        if prop.name in ['filebegin', 'ndigits', 'rootpath']:
            self.emit('changed')
    def _setup(self, rootpath):
        logger.debug('Running SubSystemFiles._setup()')
        for monitor, connection in self.monitors:
            monitor.cancel()
            monitor.disconnect(connection)
        if self.rootpath != rootpath:
            logger.debug('SubSystemFiles._setup(): setting rootpath to %s (was: %s)' % (rootpath, self.rootpath))
            self.rootpath = rootpath
        self.monitors = []
        for folder in self.exposureloadpath:
            dirmonitor = Gio.file_new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitors.append((dirmonitor, dirmonitor.connect('changed', self._on_monitor_event)))
            logger.debug('SubSystemFiles._setup(): Added directory monitor for path %s' % folder)
        self._nextfsn_cache = None
    def _on_monitor_event(self, monitor, filename, otherfilename, event):
        if otherfilename is not None:
            logger.debug('SubSystemFiles._on_monitor_event() starting: filename: ' + filename.get_path() + ', otherfilename: ' + otherfilename.get_path() + ', event: ' + str(event))
        else:
            logger.debug('SubSystemFiles._on_monitor_event() starting: filename: ' + filename.get_path() + ', otherfilename: None, event: ' + str(event))
            
        if event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED) and self._nextfsn_cache is not None:
            basename = filename.get_basename()
            if basename:
                for regex in self._nextfsn_cache.keys():
                    m = regex.match(basename)
                    if m is not None:
                        newfsn = int(m.group(1))
                        if newfsn > self._nextfsn_cache[regex]:
                            self._nextfsn_cache[regex] = int(m.group(1)) + 1
                            self.emit('new-nextfsn', self._nextfsn_cache[regex], regex.pattern)
        else:
            logger.debug('SubSystemFiles._on_monitor_event(): nothing to be done.')
    def do_new_nextfsn(self, nextfsn, repattern):
        logger.debug('SubSystemFiles: new nextfsn: %d for pattern %s' % (nextfsn, repattern))
    def get_next_fsn(self, regex=None):
        if self._nextfsn_cache is None:
            self._nextfsn_cache = {}
        if regex is None:
            regex = self.get_fileformat_re()
        if regex.pattern == self.get_fileformat_re().pattern:
            currentpattern = True
        else:
            currentpattern = False
        if regex not in self._nextfsn_cache:
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
    def _get_subpath(self, subdir):
        pth = os.path.join(os.path.expanduser(self.rootpath), subdir)
        if not os.path.isdir(pth):
            if not os.path.exists(pth):
                os.mkdir(pth)  # an OSError is raised if no permission.
            else:
                raise OSError('%s exists and is not a directory!' % pth)
        return pth
    @property
    def configpath(self): return self._get_subpath('config')
    @property
    def exposureloadpath(self): return [self._get_subpath(x) for x in ['param', 'images', 'mask', 'eval2d', 'eval1d']]
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
    def get_fileformat(self):
        return self.filebegin + '_' + '%%0%dd' % self.ndigits
    def get_fileformat_re(self, strict=False):
        if strict:
            return re.compile(self.filebegin + '_' + '(?P<fsn>\d{%d})' % (self.ndigits))
        else:
            return re.compile(self.filebegin + '_' + '(?P<fsn>\d*)')
    def get_headerformat(self): return self.get_fileformat() + '.param'
    def get_exposureformat(self): return self.get_fileformat() + '.cbf'
    def get_headerformat_re(self, strict=False): return re.compile(self.get_fileformat_re().pattern + '\.param', strict)
    def get_exposureformat_re(self, strict=False): return re.compile(self.get_fileformat_re().pattern + '\.cbf', strict)
    
