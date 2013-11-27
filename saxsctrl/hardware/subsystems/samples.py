import os
import logging
from .. import sample
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import ConfigParser

from gi.repository import GObject
from ..sample import SAXSSample
from .subsystem import SubSystem, SubSystemError

CONFIGPATH = os.path.expanduser('~/.config/credo/sample2rc')

__all__ = ['SubSystemSamples', 'SubSystemSamplesError']

class SubSystemSamplesError(SubSystemError):
    pass

class SubSystemSamples(SubSystem):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'selected':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'sample-in-beam':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'notify':'override',
                   }
    motor_samplex = GObject.property(type=str, default='Sample_X', blurb='Motor name for horizontal positioning')
    motor_sampley = GObject.property(type=str, default='Sample_Y', blurb='Motor name for vertical positioning')
    def __init__(self, credo, offline=True):
        SubSystem.__init__(self, credo, offline)
        self._list = []
        self._selected = None
        self.configfile = 'samples.conf'
    def do_changed(self):
        logger.debug('SubSystemSamples: emitting signal "changed"!')
    def do_selected(self, sam):
        logger.debug('SubSystemSamples: emitting signal "selected" (%s)!' % (str(sam)))
    def do_sample_in_beam(self, sam):
        logger.debug('SubSystemSamples: emitting signal "sample-in-beam" (%s)!' % (str(sam)))
    def do_notify(self, prop):
        if prop.name == 'configfile':
            if not os.path.isabs(self.configfile):
                self.configfile = os.path.join(self.credo().subsystems['Files'].configpath, self.configfile)
            else:
                self.load()
    def load(self, filename=None):
        if filename is None: filename = self.configfile
        logger.debug('Loading samples.')
        for sam in sample.SAXSSample.new_from_cfg(filename):
            self.add(sam)
        try:
            self.set(self._list[0])
        except IndexError:
            pass
        self.emit('changed')
    def save(self, filename=None):
        if self.offline:
            logger.warning('Not saving samples: we are off-line.')
            return
        if filename is None: filename = self.configfile
        cp = ConfigParser.ConfigParser()
        for i, sam in enumerate(self):
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
        if sam is None:  # no sample
            self._selected = None
            return
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
    def clear(self):
        self._list = []
        self._selected = None
        self.emit('changed')
    def moveto(self, blocking=False):
        sam = self.get()
        if sam is None:
            logger.info('Skipping moving sample: no sample selected.')
            return
        logger.info('Moving sample %s into the beam.' % sam.title)
        ssmot = self.credo().subsystems['Motors']
        if not ssmot.is_idle():
            logger.info('Waiting for motors to settle.')
            ssmot.wait_for_idle()
        try:
            motors = [ssmot.get(motname) for motname in [self.motor_samplex, self.motor_sampley]]
        except (IndexError, NotImplementedError):
            raise SubSystemError('No motor "' + motname + '" defined.')
        
        self._ssmotconn = ssmot.connect('idle', self._ssmot_idle, sam)
        for motor, pos in zip(motors, [sam.positionx, sam.positiony]):
            if pos is None:
                logger.debug('Sample %s has None for %s, skipping movement.' % (str(sam), motor.alias))
                continue
            motor.moveto(pos)
        logger.info('Motors are on their way...')
        if blocking:
            logger.debug('Waiting for sample to get into beam position')
            if callable(blocking):
                ssmot.wait_for_idle(blocking)
            else:
                ssmot.wait_for_idle()
            logger.debug('Sample is in the beam.')
        else:
            return True
    def _ssmot_idle(self, ssmot, sam):
        if hasattr(self, '_ssmotconn'):
            ssmot.disconnect(self._ssmotconn)
            del self._ssmotconn
        self.emit('sample-in-beam', sam)
        return True
    def savestate(self, configparser, sectionprefix=''):
        SubSystem.savestate(self, configparser, sectionprefix)
        if self._selected is None:
            configparser.set(sectionprefix + self._get_classname(), 'Selected', '__None__')
        else:
            configparser.set(sectionprefix + self._get_classname(), 'Selected', self._selected.title)
    def loadstate(self, configparser, sectionprefix=''):
        SubSystem.loadstate(self, configparser, sectionprefix)
        if configparser.has_option(sectionprefix + self._get_classname(), 'Selected'):
            sel = configparser.get(sectionprefix + self._get_classname(), 'Selected')
            if sel == '__None__':
                sel = None
            self.set(sel)
    def get_xmotor(self):
        ssmot = self.credo().subsystems['Motors']
        return ssmot.get(self.motor_samplex)
    def get_ymotor(self):
        ssmot = self.credo().subsystems['Motors']
        return ssmot.get(self.motor_sampley)
