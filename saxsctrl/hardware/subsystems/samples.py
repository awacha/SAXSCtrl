import ConfigParser
import os
import weakref

from gi.repository import GObject
from ..sample import SAXSSample

CONFIGPATH = os.path.expanduser('~/.config/credo/sample2rc')

__all__ = ['SubSystemSamples', 'SubSystemSamplesError']

class SubSystemSamplesError(StandardError):
    pass

class SubSystemSamples(GObject.GObject):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'selected':(GObject.SignalFlags.RUN_FIRST, None, ()),
                   }
    def __init__(self, credo):
        GObject.GObject.__init__()
        self.credo = weakref.ref(credo)
        self._list = []    
        self._selected = None
    def load(self, filename=None):
        if filename is None: filename = CONFIGPATH
        logger.debug('Loading samples.')
        for sam in sample.SAXSSample.new_from_cfg(filename):
            self.add(sam)
        try:
            self.set(self._list[0])
        except IndexError:
            pass
        self.emit('changed')
    def save(self, filename=None):
        if filename is None: filename = CONFIGPATH
        cp = ConfigParser.ConfigParser()
        for i, sam in enumerate(self.get_samples()):
            sam.save_to_ConfigParser(cp, 'Sample_%03d' % i)
        with open(filename, 'wt') as f:
            cp.write(f)
    def add(self, sam):
        if not isinstance(sam, SAXSSample):
            logger.warning('Not adding sample: ' + str(sam) + ' because not a SAXSSample instance.')
            return
        # only add the sample to the list if no equivalent is present. Equivalency is
        # determined via the __eq__() method of SAXSSample.
        if not [s for s in self._list if s == sam]:
            # logger.debug('Sample ' + str(sam) + ' added.')
            self._list.append(sam)
            self._list.sort()
            self.emit('changed')
        else:
            logger.warning('Not adding duplicate sample: ' + str(sam))
    def remove(self, sam):
        try:
            todelete = [s == sam for s in self._list][0]
            self._list.remove(todelete)
            if self._selected == todelete: self._selected = None
            self._list.sort()
        except IndexError:
            raise ValueError('Sample %s not in list!' % str(sam))
        else:
            self.emit('changed')
    def __iter__(self):
        return iter(self._list)
    def set(self, sam):
        sams = [s for s in self._list if s == sam]
        if not sams:
            raise SubSystemSamplesError('No sample %s defined.' % str(sam))
        if len(sams) > 1:
            raise SubSystemSamplesError('Ambiguous sample: %s.' % str(sam))
        sam = sams[0]
        if not isinstance(sam, SAXSSample):
            return None
        if self._selected != sam:
            self._selected = sam
            self.emit('selected', self._selected)
        return sam
    def get(self):
        return self._selected
    def clear_samples(self):
        self._list = []
        self._selected = None
        self.emit('changed')
    
