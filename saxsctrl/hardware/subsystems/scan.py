from gi.repository import GObject

from .subsystem import SubSystem, SubSystemError
from ..instruments.tmcl_motor import MotorError
from ..instruments.pilatus import PilatusError
import os
import weakref
import time
import logging
import sastool
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

__all__ = ['SubSystemScan']

# Scan device names:
# <type>:<what>
# e.g.:   Time:Clock,   Pilatus:Threshold,   Motor:Sample_X  ...

class ScanDeviceError(SubSystemError):
    pass

class ScanDevice(GObject.GObject):
    def __init__(self, credo):
        GObject.GObject.__init__(self)
        self.credo = weakref.ref(credo)
        self.arg = None
    def moveto(self, position):
        raise NotImplementedError
    def where(self):
        raise NotImplementedError
    @classmethod
    def match_name(cls, name):
        return False
    @classmethod
    def new_from_name(cls, credo, devicename, **args):
        name, arg = devicename.split(':', 1)
        for c in cls.__subclasses__():
            if c.match_name(name):
                return c(credo, arg)
        raise NotImplementedError('No descendant of class ScanDevice matches device %s' % str(devicename))
    def name(self):
        raise NotImplementedError
    def validate_interval(self, start, end, nsteps, ct, wt):
        raise NotImplementedError
    def __str__(self):
        return self.name() + ':' + self.arg
    @classmethod
    def possible_devices(cls, credo):
        return reduce(lambda a, b:a + b, [c.possible_devices(credo) for c in cls.__subclasses__()])

class ScanDeviceTime(ScanDevice):
    def __init__(self, credo, arg):
        ScanDevice.__init__(self, credo)
        self.arg = arg
    def moveto(self, position):
        return self.where()
    def where(self):
        return time.time()
    @classmethod
    def match_name(cls, name):
        return name == 'Time'
    def name(self):
        return 'Time'
    def validate_interval(self, start, end, nsteps, ct, wt):
        if wt != 0:
            logger.warning('Wait time ignored for Time scans.')
        return (start == 0) and (end > start) and (nsteps >= 2) and (end / (nsteps - 1) - ct > 0.003)
    @classmethod
    def possible_devices(cls, credo):
        return ['Time:Clock']
    
class ScanDeviceMotor(ScanDevice):
    def __init__(self, credo, motorname):
        ScanDevice.__init__(self, credo)
        self.motor = self.credo().get_equipment('tmcm351').get_motor(motorname)
        self.arg = self.motor.alias
    def moveto(self, position):
        try:
            self.motor.moveto(position)
            self.credo().get_equipment('tmcm351').wait_for_idle()
        except MotorError as me:
            raise ScanDeviceError('Positioning failure: ' + me.message)
        return self.where()
    def where(self):
        return self.motor.get_pos()
    @classmethod
    def match_name(cls, name):
        return name == 'Motor'
    def name(self):
        return self.arg
    def validate_interval(self, start, end, nsteps, ct, wt):
        softlimits = self.motor.softlimits
        left = min(softlimits)
        right = max(softlimits)
        return (start >= left) and (start <= right) and (end >= left) and (end <= right) and (nsteps >= 2)
    def __str__(self):
        return 'Motor:' + self.arg
    @classmethod
    def possible_devices(cls, credo):
        t = credo.get_equipment('tmcm351')
        if t.connected():
            return ['Motor:' + mot.alias for mot in t.motors.itervalues()]
        else:
            return []
        
class ScanDevicePilatus(ScanDevice):
    def __init__(self, credo, what):
        ScanDevice.__init__(self, credo)
        if what.lower() != 'threshold':
            raise NotImplementedError('Only "threshold" scans are supported for Pilatus scandevices.')
        self.arg = what
    def moveto(self, position):
        try:
            self.credo().get_equipment('pilatus').set_threshold(position)
            self.credo().get_equipment('pilatus').wait_for_idle()
        except PilatusError as pe:
            raise ScanDeviceError('Error setting threshold: ' + pe.message)
        return self.where()
    def where(self):
        return self.credo().get_equipment('pilatus').get_threshold()
    @classmethod
    def match_name(cls, name):
        return name == 'Pilatus'
    def name(self):
        return 'Threshold'
    def validate_interval(self, start, end, nsteps, ct, wt):
        return (start >= 4000) and (start <= 18000) and (end >= 4000) and (end <= 18000) and (nsteps >= 2) and ((abs(end - start) / (nsteps - 1.0)) >= 1)
    def __str__(self):
        return 'Pilatus:Threshold'
    @classmethod
    def possible_devices(cls, credo):
        p = credo.get_equipment('pilatus')
        if p.connected():
            return ['Pilatus:Threshold']
        else:
            return []
        
class SubSystemScan(SubSystem):
    __gsignals__ = {'scan-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'scan-report':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'scan-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'notify':'override',
                  }
    countingtime = GObject.property(type=float, minimum=0, default=1, blurb='Counting time (sec)')
    value_begin = GObject.property(type=float, blurb='Starting position')
    value_end = GObject.property(type=float, blurb='End position')
    nstep = GObject.property(type=int, minimum=2, default=2, blurb='Number of steps (>=2)')
    waittime = GObject.property(type=float, minimum=0, default=0, blurb='Wait time (sec)')
    devicename = GObject.property(type=str, default='Time:Clock', blurb='Device name')
    scanfilename = GObject.property(type=str, default='credoscan.spec', blurb='Scan file name')
    operate_shutter = GObject.property(type=bool, default=False, blurb='Open/close shutter between exposures')
    autoreturn = GObject.property(type=bool, default=True, blurb='Auto-return')
    _current_step = None
    _original_shuttermode = None
    currentscan = None
    _header_template = None
    _mask = None
    _ex_conn = None
    def __init__(self, credo):
        self.scandevice = None
        self.scanfile = None
        SubSystem.__init__(self, credo)
        self._init_scan_device()
    def do_notify(self, prop):
        if prop.name == 'scanfilename':
            self._init_scan_file()
        if prop.name == 'devicename':
            self._init_scan_device()
    def _init_scan_device(self):
        self.scandevice = ScanDevice.new_from_name(self.credo(), self.devicename)
    def _init_scan_file(self):
        if not os.path.isabs(self.scanfilename):
            logger.debug('Initializing scan file: setting scanfilename to absolute path')
            self.scanfilename = os.path.join(self.credo().subsystems['Files'].scanpath, self.scanfilename)
        else:
            logger.debug('Initializing scan file: loading.')
            self.scanfile = self.reload_scanfile()
    def get_supported_devices(self):
        return ScanDevice.possible_devices(self.credo())
    def start(self, header_template={}, mask=None):
        """Set-up and start a scan measurement.
        
        Inputs:
            value_begin: the starting value. In 'Time' mode this is ignored.
            value_end: the ending value. In 'Time' mode this is ignored.
            nstep: the number of steps.
            countingtime: the counting time in seconds.
            waittime: least wait time in seconds. Moving the motors does not contribute to this!
            header_template: template header for expose()
            operate_shutter: if the shutter is to be closed between exposures.
            autoreturn: if the scan device should be returned to the starting state at the end.
        """
        logger.debug('Initializing scan.')
        if self.scandevice is None:
            raise SubSystemError('No scan device!')
        vdnames = [vd.name for vd in self.credo().subsystems['VirtualDetectors']]
        columns = [self.scandevice.name(), 'FSN'] + vdnames
        try:
            if not self.scandevice.validate_interval(self.value_begin, self.value_end, self.nstep, self.countingtime, self.waittime):
                raise ValueError('Invalid scan interval')
        except Exception as exc:
            raise SubSystemError('Validation of scan interval failed: ' + exc.message)
        
        logger.debug('Initializing scan object.')
        # Initialize the scan object
        self.currentscan = sastool.classes.scan.SASScan(columns, self.nstep)
        self.currentscan.motors = [m.alias for m in self.credo().get_motors()]
        self.currentscan.motorpos = [m.get_pos() for m in self.credo().get_motors()]
        step = (self.value_end - self.value_begin) / (self.nstep - 1)
        command = 'scan ' + str(self.scandevice) + ' from ' + str(self.value_begin) + ' to ' + str(self.value_end) + ' by ' + str(step) + ' ct = ' + str(self.countingtime) + ' wt = ' + str(self.waittime)
        self.currentscan.countingtype = self.currentscan.COUNTING_TIME
        self.currentscan.countingvalue = self.countingtime
        self.currentscan.fsn = None
        self.currentscan.start_record_mode(command, self.nstep, self.scanfile)

        logger.info('Starting scan #%d: %s' % (self.currentscan.fsn, command))

        self.credo().subsystems['Exposure'].exptime = self.countingtime
        if self.scandevice.name() == 'Time':
            self.credo().subsystems['Exposure'].nimages = self.nstep
            self.credo().subsystems['Exposure'].dwelltime = self.value_end / (self.nstep - 1) - self.countingtime
        else:
            self.credo().subsystems['Exposure'].nimages = 1
        self.credo().subsystems['Exposure'].timecriticalmode = True
        self.credo().subsystems['Files'].filebegin = 'scan'
        self._original_shuttermode = self.credo().subsystems['Exposure'].operate_shutter
        
        self._ex_conn = [self.credo().subsystems['Exposure'].connect('exposure-fail', self._exposure_fail),
                         self.credo().subsystems['Exposure'].connect('exposure-image', self._exposure_image),
                         self.credo().subsystems['Exposure'].connect('exposure-end', self._exposure_end)]
        
        self._current_step = None
        self._header_template = header_template.copy()
        self._header_template['scanfsn'] = self.currentscan.fsn
        self._mask = mask
        self._firsttime = None
        self._do_next_step()
        
    def is_last_step(self):
        return (self._current_step >= self.nstep - 1) or (self.scandevice.name() == 'Time')
        
    def _exposure_fail(self, sse, message):
        self.emit('scan-fail', status)
    
    def _exposure_end(self, sse, status):
        self._current_step += 1
        if self.is_last_step() or not status:
            # we are at the last step
            if self._ex_conn is not None:
                for c in self._ex_conn:
                    sse.disconnect(c)
                self._ex_conn = None
            if self._original_shuttermode:
                self.credo().get_equipment('genix').shutter_close()
            self.emit('scan-end', status)
        else:
            self._do_next_step()
    
    def _exposure_image(self, sse, ex):
        if self.scandevice.name() == 'Time':
            if self._firsttime is None:
                where = 0
                self._firsttime = float(ex['CBF_Date'].strftime('%s.%f'))
            else:
                where = float(ex['CBF_Date'].strftime('%s.%f')) - self._firsttime
        else:
            where = self._where
        logger.debug('WHERE: ' + str(where))
        vdreadout = self.credo().subsystems['VirtualDetectors'].readout_all(ex, self.credo().get_equipment('genix'))
        vdreadout.update({self.scandevice.name():where, 'FSN':ex['FSN']})
        cols = self.currentscan.columns()
        self.currentscan.append(tuple(vdreadout[c] for c in cols))
        self.emit('scan-report', self.currentscan)
    
    def _do_next_step(self):
        if hasattr(self, '_kill'):
            self.emit('scan-end', False)
            del self._kill
            return
        if self._current_step is None:
            # we are starting:
            self._current_step = 0
            if self._original_shuttermode and not self.operate_shutter:  # if an exposure should open the shutter but we leave it open during exposures
                self.credo().subsystems['Exposure'].operate_shutter = False
                self.credo().get_equipment('genix').shutter_open()
            # otherwise we either 1) should not touch the shutter 2) can rely on the open/close behaviour of the Exposure subsystem
        elif self._current_step == self.nstep - 1:
            # last exposure, set back operate_shutter of Exposure subsystem
            self.credo().subsystems['Exposure'].operate_shutter = self._original_shuttermode
        try:
            logger.info('Scan step %d/%d' % (self._current_step + 1, self.nstep))
            self._where = self.scandevice.moveto(self.value_begin + (self.value_end - self.value_begin) / (self.nstep - 1) * self._current_step)
        except ScanDeviceError as sde:
            self.emit('scan-fail', sde.message)
        GObject.timeout_add(int(self.waittime * 1000), self._start_exposure)
    def _start_exposure(self): 
        self.credo().subsystems['Exposure'].start(self._header_template, self._mask)
        return False    
    def kill(self, stop_processing_results=False):
        try:
            self.credo().subsystems['Exposure'].kill(stop_processing_results)
        except:
            pass
        self._kill = True
        logger.info('Stopping scan sequence on user request.')
    
    def do_scan_end(self, status):
        if self.autoreturn:
            logger.info('Auto-returning...')
            try:
                self.scandevice.moveto(self.value_begin)
            except ScanDeviceError:
                self.emit('scan-fail', 'Error on auto-return.') 
        self._firsttime = None
        self._where = None
        self.currentscan.stop_record_mode()
        if self.credo().subsystems['Exposure'].operate_shutter != self._original_shuttermode:
            self.credo().subsystems['Exposure'].operate_shutter = self._original_shuttermode
        logger.info('Scan #%d finished.' % self.currentscan.fsn)

    def do_scan_fail(self, message):
        logger.error('Scan failure: ' + message)
    def reload_scanfile(self):
        if isinstance(self.scanfile, sastool.classes.SASScanStore):
            self.scanfile.finalize()
            del self.scanfile
        logger.debug('Reloading scan file from ' + self.scanfilename + '')
        self.scanfile = sastool.classes.SASScanStore(self.scanfilename, 'CREDO spec file', [str(m) for m in self.credo().get_motors()])
        logger.debug('Scan file reloaded: ' + str(self.scanfile))
        return self.scanfile
    @property
    def stepsize(self):
        return (self.value_end - self.value_begin) / (self.nstep - 1)
