import os
import logging
from .. import sample
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


from gi.repository import GObject
from ..sample import SAXSSample
from .subsystem import SubSystem, SubSystemException, SubSystemError

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
    motor_samplex = GObject.property(type=str, default='Sample_X')
    motor_sampley = GObject.property(type=str, default='Sample_Y')
    def __init__(self, credo):
        SubSystem.__init__(self, credo)
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
        if filename is None: filename = self.configfile
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
    def moveto(self, blocking=False):
        sam = self.get()
        logger.info('Moving sample %s into the beam.' % sam.title)
        try:
            tmcm = self.credo().get_equipment('tmcm351')
        except SubSystemError as se:
            raise SubSystemError('Cannot move motors!')
        if not tmcm.is_idle():
            logger.info('Waiting for motors to settle.')
            self.credo().subsystems['Equipments'].wait_for_idle('tmcm351')
        try:
            motors = [tmcm.get_motor(motname) for motname in [self.motor_samplex, self.motor_sampley]]
        except (IndexError, NotImplementedError):
            raise SubSystemError('No motor "' + motname + '" defined.')
        
        self._tmcmconn = tmcm.connect('idle', self._tmcm_idle, sam)
        for motor, pos in zip(motors, [sam.positionx, sam.positiony]):
            if pos is None:
                logger.debug('Sample %s has None for %s, skipping movement.' % (str(sam), motor.alias))
                continue
            motor.moveto(pos)
        logger.info('Motors are on their way...')
        if blocking:
            self.credo().subsystems['Equipments'].wait_for_idle('tmcm351')
    def _tmcm_idle(self, tmcm, sam):
        if hasattr(self, '_tmcmconn'):
            tmcm.disconnect(self._tmcmconn)
            del self._tmcmconn
        self.emit('sample-in-beam', sam)
        return True
