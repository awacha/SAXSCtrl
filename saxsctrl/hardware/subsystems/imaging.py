from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Notify

from .subsystem import SubSystem, SubSystemError
# import all defined scan devices
from .scan import ScanDevice, ScanDeviceError
from ..instruments.genix import GenixError
import logging
import sastool
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ['SubSystemImaging']


class SubSystemImaging(SubSystem):
    __gsignals__ = {'imaging-end': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'imaging-report': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'imaging-fail': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'notify': 'override',
                    }
    countingtime = GObject.property(
        type=float, minimum=0, default=1, blurb='Counting time (sec)')
    value_begin1 = GObject.property(type=float, blurb='Starting position #1')
    value_end1 = GObject.property(type=float, blurb='End position #1')
    value_begin2 = GObject.property(type=float, blurb='Starting position #2')
    value_end2 = GObject.property(type=float, blurb='End position #2')
    nstep1 = GObject.property(
        type=int, minimum=2, default=2, blurb='Number of steps #1 (>=2)')
    nstep2 = GObject.property(
        type=int, minimum=2, default=2, blurb='Number of steps #2 (>=2)')
    waittime = GObject.property(
        type=float, minimum=0, default=0, blurb='Wait time (sec)')
    devicename1 = GObject.property(
        type=str, default='Time:Clock', blurb='Device name #1')
    devicename2 = GObject.property(
        type=str, default='Time:Clock', blurb='Device name #1')
    operate_shutter = GObject.property(
        type=bool, default=False, blurb='Open/close shutter between exposures')
    autoreturn = GObject.property(type=bool, default=True, blurb='Auto-return')
    comment = GObject.property(
        type=str, default='--please fill--', blurb='Comment')
    _current_step = None
    _original_shuttermode = None
    currentscan = None
    _header_template = None
    _mask = None
    _ex_conn = None

    def __init__(self, credo, offline=True):
        self.scandevice1 = None
        self.scandevice2 = None
        SubSystem.__init__(self, credo, offline)
        self._init_scan_devices()
        self._ex_conn = []

    def __del__(self):
        try:
            sse = self.credo().subsystems['Exposure']
            for c in self._ex_conn:
                sse.disconnect(c)
            self._ex_conn = []
        except (AttributeError, KeyError):
            return

    def do_notify(self, prop):
        try:
            if prop.name.startswith('devicename'):
                self._init_scan_devices()
        except SubSystemError:
            pass

    def _init_scan_devices(self):
        self.scandevice1 = ScanDevice.new_from_name(
            self.credo(), self.devicename1)
        self.scandevice2 = ScanDevice.new_from_name(
            self.credo(), self.devicename2)

    def get_supported_devices(self):
        return [x for x in ScanDevice.possible_devices(self.credo()) if not (x.startswith('Time:'))]

    def prepare(self, header_template={}, mask=None):
        if (self.scandevice1 is None) or (self.scandevice2 is None):
            self._init_scan_devices()
        logger.debug('Initializing scan.')
        if (self.scandevice1 is None) or (self.scandevice2 is None):
            raise SubSystemError('No scan device!')
        if str(self.scandevice1) == str(self.scandevice2):
            raise SubSystemError('Cannot use the same scan device twice!')
        vdnames = [
            vd.name for vd in self.credo().subsystems['VirtualDetectors']]
        columns = [
            self.scandevice1.name(), self.scandevice2.name(), 'FSN'] + vdnames
        try:
            if ((not self.scandevice1.validate_interval(self.value_begin1, self.value_end1, self.nstep1, self.countingtime, self.waittime)) or
                    (not self.scandevice2.validate_interval(self.value_begin2, self.value_end2, self.nstep2, self.countingtime, self.waittime))):
                raise ValueError('Invalid scan interval')
        except Exception as exc:
            raise SubSystemError(
                'Validation of scan interval failed: ' + str(exc))

        logger.debug('Initializing scan object.')
        # Initialize the scan object
        self.currentscan = sastool.classes.scan.SASScan(
            columns, (self.nstep1, self.nstep2))
        self.currentscan.motors = [
            m.alias for m in self.credo().subsystems['Motors'].get_motors()]
        self.currentscan.motorpos = [m.get_parameter(
            'Current_position') for m in self.credo().subsystems['Motors'].get_motors()]
        step1 = (self.value_end1 - self.value_begin1) / (self.nstep1 - 1)
        step2 = (self.value_end2 - self.value_begin2) / (self.nstep2 - 1)
        command = 'imaging (' + str(self.scandevice1) + ', ' + str(self.scandevice2) + ') from (' + str(self.value_begin1) + ', ' + str(self.value_begin2) + \
            ') to (' + str(self.value_end1) + ', ' + str(self.value_end2) + ') by (' + str(step1) + \
            ', ' + str(step2) + ') ct = ' + \
            str(self.countingtime) + ' wt = ' + str(self.waittime)
        self.currentscan.countingtype = self.currentscan.COUNTING_TIME
        self.currentscan.countingvalue = self.countingtime
        self.currentscan.comment = self.comment
        self.currentscan.fsn = None
        self.currentscan.start_record_mode(
            command, (self.nstep1, self.nstep2), self.credo().subsystems['Files'].scanfile)

        logger.info('Starting scan #%d: %s' % (self.currentscan.fsn, command))

        self.credo().subsystems['Exposure'].exptime = self.countingtime
        if self.scandevice1.name() == 'Time' or self.scandevice2.name() == 'Time':
            raise SubSystemError('Time device not supported for imaging')
        self.credo().subsystems['Exposure'].nimages = 1
        self.credo().subsystems['Exposure'].timecriticalmode = True
        self.credo().subsystems['Files'].filebegin = 'imaging'
        self._original_shuttermode = self.credo().subsystems[
            'Exposure'].operate_shutter

        self._ex_conn = [self.credo().subsystems['Exposure'].connect('exposure-fail', self._exposure_fail),
                         self.credo().subsystems['Exposure'].connect(
                             'exposure-image', self._exposure_image),
                         self.credo().subsystems['Exposure'].connect('exposure-end', self._exposure_end)]

        self._current_step = None
        self._header_template = header_template.copy()
        self._header_template['imagingfsn'] = self.currentscan.fsn
        self._mask = mask
        self._firsttime = None

    def start(self):
        """Set-up and start a scan measurement.
        """
        self._do_next_step()

    def execute(self, header_template={}, mask=None):
        self.prepare(header_template, mask)
        self.start()

    def is_last_step(self):
        if self._current_step is None:
            return False
        return (self._current_step[1] >= self.nstep2 - 1) and (self._current_step[0] >= self.nstep1)

    def _exposure_fail(self, sse, message):
        self.emit('imaging-fail', message)

    def _exposure_end(self, sse, status):
        self._current_step[0] += 1
        if self.is_last_step() or not status:
            # we are at the last step
            if self._original_shuttermode:
                self.credo().get_equipment('genix').shutter_close()
            self.emit('imaging-end', status)
            return
        elif self._current_step[0] >= self.nstep1:
            self._current_step[0] = 0
            self._current_step[1] += 1
        self._do_next_step()

    def _exposure_image(self, sse, ex):
        where = self._where
        logger.debug('WHERE: ' + str(where[0]) + str(where[1]))
        vdreadout = self.credo().subsystems['VirtualDetectors'].readout_all(
            ex, self.credo().get_equipment('genix'))
        vdreadout.update({self.scandevice1.name(): where[
                         0], self.scandevice2.name(): where[1], 'FSN': ex['FSN']})
        cols = self.currentscan.columns()
        self.currentscan.append(tuple(vdreadout[c] for c in cols))
        self.emit('imaging-report', self.currentscan)

    def _do_next_step(self):
        logger.debug('Do-next-step starting.')
        if hasattr(self, '_kill'):
            logger.debug('Do-next-step: found _kill, emitting imaging-end.')
            self.emit('imaging-end', False)
            del self._kill
            return
        if self._current_step is None:
            logger.debug('Very first step.')
            # we are starting:
            self._current_step = [0, 0]
            # if an exposure should open the shutter but we leave it open
            # during exposures
            if self._original_shuttermode and not self.operate_shutter:
                self.credo().subsystems['Exposure'].operate_shutter = False
            # otherwise we either 1) should not touch the shutter 2) can rely
            # on the open/close behaviour of the Exposure subsystem
        elif (self._current_step[1] == self.nstep2) and (self._current_step[0] == (self.nstep1 - 1)):
            logger.debug('Last step.')
            # last exposure, set back operate_shutter of Exposure subsystem
            self.credo().subsystems[
                'Exposure'].operate_shutter = self._original_shuttermode
        try:
            logger.debug('Imaging step (%d,%d)/(%d,%d)' %
                         (self._current_step[0] + 1, self._current_step[1] + 1, self.nstep1, self.nstep2))
            self._where = [self.scandevice1.moveto(self.value_begin1 + (self.value_end1 - self.value_begin1) / (self.nstep1 - 1) * self._current_step[0]),
                           self.scandevice2.moveto(self.value_begin2 + (self.value_end2 - self.value_begin2) / (self.nstep2 - 1) * self._current_step[1])]
        except ScanDeviceError as sde:
            self.emit('imaging-fail', str(sde))
        logger.debug('Adding timeout for starting exposure')
        GLib.timeout_add(int(self.waittime * 1000), self._start_exposure)

    def _start_exposure(self):
        logger.debug('Starting exposure in imaging sequence.')
        if (self._current_step[0] == 0) and (self._current_step[1] == 0) and self._original_shuttermode and not self.operate_shutter:
            self.credo().get_equipment('genix').shutter_open()
            logger.debug(
                'Opened shutter before starting of the first exposure.')
        self.credo().subsystems['Exposure'].start(
            self._header_template, self._mask, write_nexus=False)
        logger.debug('Done starting exposure in imaging sequence')
        return False

    def kill(self):
        logger.debug('Killing of scan sequence requested')
        self._kill = True
        try:
            self.credo().subsystems['Exposure'].kill()
        except:
            raise
        logger.info('Stopping scan sequence on user request.')

    def do_imaging_end(self, status):
        if self._ex_conn is not None:
            for c in self._ex_conn:
                self.credo().subsystems['Exposure'].disconnect(c)
            self._ex_conn = None
        if self.autoreturn:
            logger.info('Auto-returning...')
            try:
                self.scandevice1.moveto(self.value_begin1)
                self.scandevice2.moveto(self.value_begin2)
            except ScanDeviceError:
                self.emit('imaging-fail', 'Error on auto-return.')
        self._firsttime = None
        self._where = None
        self.currentscan.stop_record_mode()
        if self.credo().subsystems['Exposure'].operate_shutter != self._original_shuttermode:
            self.credo().subsystems[
                'Exposure'].operate_shutter = self._original_shuttermode
        if self.credo().subsystems['Exposure'].operate_shutter:
            try:
                if self.credo().get_equipment('genix').shutter_state():
                    logger.warning(
                        'Shutter left open at the end of scan, closing.')
                    self.credo().get_equipment('genix').shutter_close()
            except GenixError:
                logger.warning('Error closing shutter.')
        logger.info('Imaging #%d finished.' % self.currentscan.fsn)
        if Notify.is_initted():
            if status:
                n = Notify.Notification.new('Imaging #%d finished' % self.currentscan.fsn,
                                            'Sequence ended normally.',
                                            'dialog-information')
            else:
                n = Notify.Notification.new('Imaging #%d finished' % self.currentscan.fsn,
                                            'Abnormal termination.',
                                            'dialog-warning')
            n.show()
            del n

    def do_imaging_fail(self, message):
        logger.error('Imaging failure: ' + message)
        if Notify.is_initted():
            n = Notify.Notification.new('Imaging failure',
                                        'Reason: ' + message,
                                        'dialog-error')
            n.show()
            del n

    @property
    def stepsize1(self):
        return (self.value_end1 - self.value_begin1) / (self.nstep1 - 1)

    @property
    def stepsize2(self):
        return (self.value_end2 - self.value_begin2) / (self.nstep2 - 1)
