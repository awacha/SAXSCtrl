import logging
import weakref
import ConfigParser

from gi.repository import GObject
from ..virtualpointdetector import VirtualPointDetector, virtualpointdetector_new_from_configparser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class SubSystemVirtualDetectors(GObject.GObject):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None ()),
                   }
    configfile = GObject.property(type=str, default='')
    def __init__(self, credo):
        GObject.GObject.__init__()
        self.credo = weakref.ref(credo)
        self._list = []
    def add(self, vd, noemit=False):
        if not [d for d in self._list if d == vd]:
            self.virtualpointdetectors.append(vd)
            if not noemit:
                self.emit('changed')
            return True
        else:
            logger.warning('Not adding duplicate detector: %s' % str(vd))
            return False
    def remove(self, vd):
        try:
            todelete = [d for d in self._list if d == vd][0]
            self._list.remove(todelete)
        except IndexError:
            raise ValueError('Virtual detector %s not in list!' % str(vd))
        else:
            self.emit('changed')
    def clear(self):
        self._list = []
    def load(self, filename=None, clear=True):
        if filename is None:
            filename = self.configfile
        cp = ConfigParser.ConfigParser()
        cp.read(filename)
        if clear:
            self.clear()
        changed = False
        for vpdname in [sec for sec in cp.sections() if sec.startswith('VPD_')]:
            vpd = virtualpointdetector_new_from_configparser(vpdname[4:], cp)
            self.add(vpd)
            changed |= self.add(vpd)
        if changed:
            self.emit('changed')
            if self.configfile != filename:
                self.configfile = filename
    def save(self, filename=None):
        if filename is None:
            filename = self.configfile
        cp = ConfigParser.ConfigParser()
        for vpd in self._list:
            vpd.write_to_configparser(cp)
        with open(filename, 'wt') as f:
            cp.write(f)
    def readout_all(self):
        
