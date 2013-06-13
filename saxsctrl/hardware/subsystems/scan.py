from gi.repository import GObject

from .subsystem import SubSystem
import os
import weakref

__all__ = ['SubSystemScan']

# Scan device names:
# <type>:<what>
# e.g.:   Time:Clock,   Pilatus:Threshold,   Motor:Sample_X  ...

class ScanDevice(GObject.GObject):
    def __init__(self,credo):
        GObject.GObject.__init__(self)
        self.credo=weakref.ref(credo)
    def moveto(self, position):
        raise NotImplementedError
    def where(self):
        raise NotImplementedError
    
class ScanDeviceTime(ScanDevice):
    pass

class ScanDeviceMotor(ScanDevice):
    pass

class SubSystemScan(SubSystem):
    __gsignals__ = {'scan-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'scan-report':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'scan-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'notify':'override',
                  }
    countingtime = GObject.property(type=float, minimum=0, default=1)
    value_begin = GObject.property(type=float)
    value_end = GObject.property(type=float)
    nstep = GObject.property(type=int, minimum=2, default=2)
    waittime = GObject.property(type=float, minimum=0, default=0)
    devicename = GObject.property(type=str, default='Time:Clock')
    scanfilename = GObject.property(type=str, default='credoscan.spec')
    operate_shutter = GObject.property(type=bool, default=False)
    autoreturn = GObject.property(type=bool, default=True)
    scandevice = None
    def __init__(self, credo):
        SubSystem.__init__(self, credo)
    def do_notify(self, prop):
        if prop.name == 'scanfile':
            if not os.path.isabs(self.scanfilename):
                self.scanfilename = os.path.join(self.credo().subsystems['Files'].scanpath, self.scanfilename)
            else:
                self.scanfile = self.reload_scanfile()
        if prop.name == 'devicename':
            devicetype, devicename = self.devicename.split(':', 1)
            devicetype = devicetype.lower()
            if devicetype == 'time':
                pass
            elif devicetype == 'motor':
                self.scandevice=
                pass
            elif devicetype == 'pilatus':
                pass
            elif devicetype == 'genix':
                pass
            else:
                raise NotImplementedError('Invalid device type: ' + devicetype)
            
    def get_scandevices(self):
        lis = ['Time'] + self.get_motors()
        if self.pilatus.connected():
            lis += ['Pilatus threshold']
        return lis
    def start(self, value_begin, value_end, nstep, countingtime, waittime, header_template={}):
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

        # interpret self.scandevice (which is always a string). If it corresponds to a motor, get it.
        scandevice = self.scandevice
        if scandevice in [m.name for m in self.get_motors()]:
            scandevice = [m for m in self.get_motors() if m.name == scandevice][0]
        elif scandevice in [m.alias for m in self.get_motors()]:
            scandevice = [m for m in self.get_motors() if m.alias == scandevice][0]
        elif scandevice in [str(m) for m in self.get_motors()]:
            scandevice = [m for m in self.get_motors() if str(m) == scandevice][0]

        # now adjust parameters depending on the scan device selected.
        vdnames = [vd.name for vd in self.virtualpointdetectors]
        if scandevice == 'Time':
            columns = ['Time', 'FSN'] + vdnames 
            start = 0
            end = step
            step = 1
            autoreturn = None
        elif scandevice == 'Pilatus threshold':
            columns = ['Threshold', 'FSN'] + vdnames
            if autoreturn:
                autoreturn = self.pilatus.getthreshold()['threshold']
            else:
                autoreturn = None
        elif scandevice in self.get_motors():
            columns = [self.scandevice, 'FSN'] + vdnames
            if autoreturn:
                autoreturn = scandevice.get_pos()
            else:
                autoreturn = None
        else:
            raise NotImplementedError('Invalid scan device: ' + repr(scandevice))
        
        # check if the scan will end.
        if step * (end - start) <= 0:
            raise ValueError('Invalid start, step, end values for scanning.')
        
        logger.debug('Initializing scan object.')
        # Initialize the scan object
        scan = sastool.classes.scan.SASScan(columns, (end - start) / step + 1)
        scan.motors = self.get_motors()
        scan.motorpos = [m.get_pos() for m in self.get_motors()]
        command = 'scan ' + str(scandevice) + ' from ' + str(start) + ' to ' + str(end) + ' by ' + str(step) + ' ct = ' + str(countingtime) + 'wt = ' + str(waittime)
        scan.countingtype = scan.COUNTING_TIME
        scan.countingvalue = countingtime
        scan.fsn = None
        scan.start_record_mode(command, (end - start) / step + 1, self._scanstore)

        # initialize the internal scan state dictionary.
        self.scanning = {'device':scandevice, 'start':start, 'end':end, 'step':step,
                         'countingtime':countingtime, 'waittime':waittime,
                         'virtualdetectors':self.virtualpointdetectors, 'oldshutter':self.shuttercontrol,
                         'scan':scan, 'idx':0, 'header_template':header_template, 'kill':False, 'where':None, 'shutter':shutter, 'autoreturn':autoreturn}
        logger.debug('Initialized the internal state dict.')
        
        if self.shuttercontrol != shutter:
            with self.freeze_notify():
                self.shuttercontrol = shutter
                
        # go to the next step.
        logger.debug('Going to the first step.')
        if self.scan_to_next_step():
            if self.scanning['oldshutter']:
                self.shutter = True
            if self.scanning['device'] == 'Time' and not shutter:
                self.expose(self.scanning['countingtime'], self.scanning['end'], self.scanning['waittime'],
                            self.scanning['header_template'])
            else:
                self.expose(self.scanning['countingtime'], 1, 0.003, self.scanning['header_template'])
            logger.info('Scan sequence #%d started.' % self.scanning['scan'].fsn)
        else:
            self.emit('scan-fail', 'Could not start scan #%d: moving to first step did not succeed.' % self.scanning['scan'].fsn)
            self.emit('scan-end', self.scanning['scan'], False)
        return scan
    def killscan(self, wait_for_this_exposure_to_end=False):
        if not wait_for_this_exposure_to_end:
            self.killexposure()
        if self.scanning is not None:
            self.scanning['kill'] = True
        logger.info('Stopping scan sequence on user request.')
    def scan_to_next_step(self):
        logger.debug('Going to next step.')
        if self.scanning['kill']:
            logger.debug('Not going to next step: kill!')
            return False    
        if self.scanning['device'] == 'Time':
            self.scanning['where'] = time.time()
            return True
        elif self.scanning['device'] == 'Pilatus threshold':
            
            threshold = self.scanning['start'] + self.scanning['idx'] * self.scanning['step']
            if threshold > self.scanning['end']:
                return False
            try:
                logger.info('Setting threshold to %.0f eV (%s)' % (threshold, gain))
                for i in range(100):
                    GObject.main_context_default().iteration(False)
                    if not GObject.main_context_default().pending():
                        break
                self.trim_detector(threshold, None, blocking=True)
                if abs(self.pilatus.getthreshold()['threshold'] - threshold) > 1:
                    self.emit('scan-fail', 'Error setting threshold: could not set to desired value.')
                    return False
            except pilatus.PilatusError as pe:
                self.emit('scan-fail', 'PilatusError while setting threshold: ' + pe.message)
                return False
            self.scanning['where'] = threshold
            self.scanning['idx'] += 1
            logger.debug('Set threshold successfully.')
            return True
        else:
            pos = self.scanning['start'] + self.scanning['idx'] * self.scanning['step']
            if pos > self.scanning['end']:
                return False
            logger.info('Moving motor %s to %.3f' % (str(self.scanning['device']), pos))
            try:
                self.move_motor(self.scanning['device'], pos)
            except CredoError as ce:
                self.emit('scan-fail', 'Cannot move motor: ' + ce.message)
                return False
            self.scanning['where'] = pos
            self.scanning['idx'] += 1
            logger.debug('Moved motor successfully.')
            return True
        
    def do_exposure_done(self, ex):
        if self.scanning is not None:
            logger.debug('Exposure in scanning is done, preparing to emit scan-dataread signal.')
            dets = tuple([float(ex.header['VirtDet_' + vd.name]) for vd in self.scanning['virtualdetectors']])
            if self.scanning['device'] == 'Time':
                e = float(ex['CBF_Date'].strftime('%s.%f'))
                if self.scanning['start'] == 0:
                    self.scanning['start'] = e
                res = (e - self.scanning['start'], ex['FSN']) + dets
            else:
                res = (self.scanning['where'], ex['FSN']) + dets
            self.scanning['scan'].append(res)
            logger.debug('Emitting scan-dataread signal')
            self.emit('scan-dataread', self.scanning['scan'])
            logger.debug('Emitted scan-dataread signal')
        if hasattr(self, 'transmdata'):
            if self.transmdata['mode'] == 'sum':
                I = ex.sum(mask=self.transmdata['mask']) / ex['MeasTime']
            elif self.transmdata['mode'] == 'max':
                I = ex.max(mask=self.transmdata['mask']) / ex['MeasTime']
            if 'Isample' not in self.transmdata: self.transmdata['Isample'] = []
            if 'Iempty' not in self.transmdata: self.transmdata['Iempty'] = []
            if 'Idark' not in self.transmdata: self.transmdata['Idark'] = []
            if self.transmdata['next_is'] == 'S': self.transmdata['Iempty'].append(I)
            elif self.transmdata['next_is'] == 'E': self.transmdata['Idark'].append(I)
            elif self.transmdata['next_is'] == 'D': self.transmdata['Isample'].append(I)
            self.emit('transmission-report', self.transmdata['Iempty'], self.transmdata['Isample'], self.transmdata['Idark'])
        return False
    
    def do_exposure_end(self, status):
        self.exposing = None
        if self.scanning is not None:
            if self.scanning['device'] == 'Time' and not self.shuttercontrol:
                pass  # do nothing, we are finished with the timed scan
            elif not status:
                pass
            elif self.scan_to_next_step():
                self.emit('scan-phase', 'Waiting for %.3f seconds' % self.scanning['waittime'])
                def _handler(exptime, nimages, dwelltime, headertemplate):
                    self.emit('scan-phase', 'Exposing for %.3f seconds' % exptime)
                    self.expose(exptime, nimages, dwelltime, headertemplate, quick=True)
                    return False
                logger.debug('Queueing next exposure.')
                GObject.timeout_add(int(self.scanning['waittime'] * 1000), _handler,
                                    self.scanning['countingtime'], 1, 0.003,
                                    self.scanning['header_template'])
                return False
            if self.scanning['kill']: status = False
            logger.debug('Emitting scan-end signal.')
            self.emit('scan-end', self.scanning['scan'], status)
        if hasattr(self, 'transmdata'):
            if not status:
                self.transmdata['kill'] = True
            self.do_transmission()
        return False
    
    def do_scan_end(self, scn, status):
        try:
            if self.scanning['oldshutter']:
                logger.debug('Closing shutter at the end of scan.')
                self.shutter = False
            with self.freeze_notify():
                self.shuttercontrol = self.scanning['oldshutter']
            self.scanning['scan'].stop_record_mode()
            if self.scanning['autoreturn'] is not None:
                logger.info('Auto-returning...')
                if self.scanning['device'] == 'Pilatus threshold':
                    gain = self.pilatus.getthreshold()['gain']
                    self.pilatus.setthreshold(self.scanning['autoreturn'], gain, blocking=True)
                else:
                    self.move_motor(self.scanning['device'], self.scanning['autoreturn'])
        finally:
            logger.debug('Removing internal scan state dict.')
            logger.info('Scan sequence #%d done.' % self.scanning['scan'].fsn)
            self.scanning = None
        return False
    def do_scan_fail(self, message):
        logger.error(message)
    def reload_scanfile(self):
        if isinstance(self.scanfile, sastool.classes.SASScanStore):
            self.scanfile.finalize()
            del self.scanfile
        self.scanfile = sastool.classes.SASScanStore(self.scanfilename, 'CREDO spec file', [str(m) for m in self.credo().get_motors()])
            
    def start(self,):
        pass
    def kill(self):
        pass

