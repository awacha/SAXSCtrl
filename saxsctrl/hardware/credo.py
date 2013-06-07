from . import genix
from . import pilatus
from . import tmcl_motor
import sastool
import re
import os
import gc
import matplotlib.pyplot as plt
import datetime
import dateutil.parser
import threading
import uuid
import time
import logging
import cPickle as pickle
from gi.repository import Gio
from gi.repository import GObject
import ConfigParser
import multiprocessing
import numpy as np

from . import subsystems
from . import datareduction
from . import sample
from . import virtualpointdetector
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class CredoError(Exception):
    pass

    


class CredoExpose(multiprocessing.Process):
    EXPOSURE_END = -1
    EXPOSURE_FAIL = -2
    EXPOSURE_BREAK = -3
    EXPOSURE_DONE = -4
    def __init__(self, pilatus, genix, group=None, name='CredoExpose'):
        multiprocessing.Process.__init__(self, group=group, name=name)
        self.inqueue = multiprocessing.Queue()
        self.outqueue = multiprocessing.Queue()
        self.killswitch = multiprocessing.Event()
        self.isworking = multiprocessing.Semaphore(1)
        self.userbreakswitch = multiprocessing.Event()
        self.pilatus = pilatus
        self.genix = genix
    def operate_shutter(self, to_state):
        if to_state:
            logger.debug('Opening shutter')
            try:
                self.genix.shutter_open()
            except genix.GenixError as ge:
                self.outqueue.put((self.EXPOSURE_FAIL, ge.message))
                logger.error('Shutter timeout on opening.')
            logger.debug('Shutter should now be open.')
        else:
            logger.debug('Closing shutter')
            try:
                self.genix.shutter_close()
            except genix.GenixError as ge:
                self.outqueue.put((self.EXPOSURE_FAIL, ge.message))
                logger.error('Shutter timeout on closing.')
            logger.debug('Shutter should now be closed.')
    def try_to_read_header(self, filename):
        try:
            return sastool.io.twodim.readcbf(filename, load_header=True, load_data=False)[0]
        except IOError:
            return None
    def process_exposure(self, filename):
        # try to load the header from the CBF file.
        pilatusheader = self.try_to_read_header(filename)
        while pilatusheader is None:
            # if not successful, wait a bit and try again.
            logger.debug('Waiting for file: ' + filename)
            # not a simple sleep but wait on the userbreak switch.
            if self.userbreakswitch.wait(0.01):
                logger.debug('Killing notifier thread.')
                self.outqueue.put((CredoExpose.EXPOSURE_BREAK, None))
                return False
            pilatusheader = self.try_to_read_header(filename)
        
        # do some fine adjustments on the header template:
        # a) include the CBF header written by camserver.
        self.headertemplate.update(pilatusheader)
        # b) set the end date to the current time.
        self.headertemplate['EndDate'] = datetime.datetime.now()
        # and save the header to the parampath.
        self.headertemplate.write(os.path.join(self.expparams['parampath'], self.expparams['headerformat'] % self.headertemplate['FSN']))
        logger.debug('Header %s written.' % (self.expparams['headerformat'] % self.headertemplate['FSN']))
        # Increment the file sequence number.
        self.headertemplate['FSN'] += 1
        
        # Now try to load the exposure, with the header.
        try:
            logger.debug('Loading file.')
            ex = sastool.classes.SASExposure(filename, dirs=[self.expparams['parampath'], self.expparams['imagepath']])
        except IOError as ioe:
            # This should not happen, since we have written the header and read the CBF file before. But noone knows...
            self.outqueue.put((CredoExpose.EXPOSURE_FAIL, ioe.message))
        else:
            logger.debug('Reading out virtual detectors.')
            for vd in self.expparams['virtualdetectors']:
                if isinstance(vd, virtualpointdetector.VirtualPointDetectorExposure):
                    ex.header['VirtDet_' + vd.name] = vd.readout(ex)
                elif isinstance(vd, virtualpointdetector.VirtualPointDetectorEpoch):
                    ex.header['VirtDet_' + vd.name] = vd.readout()
                elif isinstance(vd, virtualpointdetector.VirtualPointDetectorGenix):
                    ex.header['VirtDet_' + vd.name] = vd.readout(self.genix)
            # put the final exposure object to the output queue.
            self.outqueue.put((CredoExpose.EXPOSURE_DONE, ex))
            del ex
        return True
    def run(self):
        while not self.killswitch.is_set():
            try:
                self.expparams, self.headertemplate = self.inqueue.get(block=True, timeout=1)
            except multiprocessing.queues.Empty:
                continue
            with self.isworking:
                self.userbreakswitch.clear()  # reset user break state.
                logger.debug('Starting exposure in CredoExposure process.')
                try:
                    filenameformat = os.path.join(self.expparams['imagepath'], self.expparams['exposureformat'])
                    self.expparams['firstfsn'] = self.headertemplate['FSN']
                    # open the safety shutter if needed.
                    if self.expparams['shuttercontrol']: self.operate_shutter(True)
                    if 'quick' in self.expparams and self.expparams['quick']:
                        logger.debug('Quick exposure')
                        self.pilatus.expose_defaults(self.expparams['exposureformat'] % self.expparams['firstfsn'])
                    else:
                        logger.debug('Normal exposure')
                        self.pilatus.expose(self.expparams['exptime'], self.expparams['exposureformat'] % self.expparams['firstfsn'], self.expparams['expnum'], self.expparams['dwelltime'])
                    t0 = time.time()
                    for i in range(0, self.expparams['expnum']):
                        # wait for each exposure. Check for user break inbetween.
                        t1 = time.time()
                        nextend = t0 + self.expparams['exptime'] * (i + 1) + self.expparams['dwelltime'] * i + 0.005
                        if nextend > t1:
                            logger.debug('Sleeping %f seconds' % (nextend - t1))
                            is_userbreak = self.userbreakswitch.wait(nextend - t1)
                        else:
                            logger.warning('Exposure lag: %f seconds' % (t1 - nextend))
                            is_userbreak = self.userbreakswitch.is_set()
                        if is_userbreak or not self.process_exposure(filenameformat % (self.expparams['firstfsn'] + i)):
                            # process_exposure() returns False if a userbreak occurs.
                            self.outqueue.put((CredoExpose.EXPOSURE_BREAK, None))
                            break  # break the for loop.
                    # close the safety shutter if needed.
                    if self.expparams['shuttercontrol']: self.operate_shutter(False)
                except Exception, exc:
                    # catch all exceptions and put an error state in the output queue, then re-raise.
                    self.outqueue.put((CredoExpose.EXPOSURE_FAIL, exc.message))
                    raise
                finally:
                    # signal the end.
                    self.outqueue.put((CredoExpose.EXPOSURE_END, None))
                    logger.debug('Returning from work.')


       
class Credo(GObject.GObject):
    __gsignals__ = {'path-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'setup-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'shutter':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-done':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'exposure-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'equipment-connection':(GObject.SignalFlags.RUN_FIRST, None, (str, bool, object)),
                    'scan-dataread':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'scan-end':(GObject.SignalFlags.RUN_FIRST, None, (object, bool)),
                    'virtualpointdetectors-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'scan-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'transmission-report':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object)),
                    'transmission-end':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object, object, bool)),
                    'idle':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'notify':'override',
                   }
    __equipments__ = {'GENIX':{'class':genix.GenixConnection, 'attrib':'genix', 'port':502, 'connectfunc':'connect_to_controller', 'disconnectfunc':'disconnect_from_controller'},
                      'PILATUS':{'class':pilatus.PilatusConnection, 'attrib':'pilatus', 'port':41234, 'connectfunc':'connect_to_camserver', 'disconnectfunc':'disconnect_from_camserver'},
                      'TMCM':{'class':tmcl_motor.TMCM351_TCP, 'attrib':'tmcm', 'port':2001, 'connectfunc':'connect_to_controller', 'disconnectfunc':'disconnect_from_controller'},
                      }
    
    # Connection properties
    filebegin = GObject.property(type=str, default='crd')
    ndigits = GObject.property(type=int, default=5, minimum=1, maximum=100)
    username = GObject.property(type=str, default='Anonymous')
    projectname = GObject.property(type=str, default='No project')
    rootpath = GObject.property(type=str, default=os.path.expanduser('~/credo_data/current'))
    
    #instrument parameters
    pixelsize = GObject.property(type=float, default=172, minimum=0)
    dist = GObject.property(type=float, default=1000, minimum=0)
    filter = GObject.property(type=str, default='No filter')
    beamposx = GObject.property(type=float, default=348.38)
    beamposy = GObject.property(type=float, default=242.47)
    wavelength = GObject.property(type=float, default=1.54182, minimum=0)
    shuttercontrol = GObject.property(type=bool, default=True)
    motorcontrol = GObject.property(type=bool, default=True)

    #connection parameters
    pilatushost = GObject.property(type=str, default='')
    genixhost = GObject.property(type=str, default='')
    tmcmhost = GObject.property(type=str, default='')
    
    virtdetcfgfile = GObject.property(type=str, default='')
    bs_out = GObject.property(type=float, default=0)
    bs_in = GObject.property(type=float, default=50)
    virtualpointdetectors = None
    _scanstore = None

    scanning = GObject.property(type=object)
    exposing = GObject.property(type=object)
    scanfile = GObject.property(type=str, default='')
    scandevice = GObject.property(type=str, default='Time')
    
    
    # changing any of the properties in this list will trigger a setup-changed event.
    setup_properties = ['username', 'projectname', 'pixelsize', 'dist', 'filter',
                        'beamposx', 'beamposy', 'wavelength', 'shuttercontrol',
                        'motorcontrol', 'scanfile', 'scandevice', 'virtdetcfgfile',
                        'imagepath', 'filepath', 'bs_out', 'bs_in']
    # changing any of the properties in this list will trigger a path-changed event.
    path_properties = ['filepath', 'imagepath']
    def __init__(self):
        GObject.GObject.__init__(self)
        # initialize subsystems
        
        self.files = subsystems.SubSystemFiles() 
        self.samples = subsystems.SubSystemSamples()
        
        self.exposing = None
        self.scanning = None
        
        
        self.load_settings()
        self.load_virtdetcfg(None, True)

        if genixhost is not None: self.genixhost = genixhost
        if pilatushost is not None: self.pilatushost = pilatushost
        if motorhost is not None: self.tmcmhost = motorhost
        
        for equipment, exc in [('GeniX', genix.GenixError), ('Pilatus', pilatus.PilatusError), ('TMCM', tmcl_motor.MotorError)]:
            try:
                self.connect_equipment(self.get_property(equipment.lower() + 'host'), equipment)
            except exc as ex:
                logger.error('Cannot contact ' + equipment + ' controller: ' + ex.message)
                self.connect_equipment(None, equipment)
        
        self.tmcm.load_settings(os.path.expanduser('~/.config/credo/motorrc'))
        
        # file format changing
        self.do_fileformatchange()
        self.connect('notify::filebegin', self.do_fileformatchange)
        self.connect('notify::fsndigits', self.do_fileformatchange)
        
        self.connect('notify::scanfile', lambda obj, param:self.reload_scanfile())
        self.reload_scanfile()
        # samples
        self._samples = []
        self.sample = None
        
        # data reduction
        self.datareduction = datareduction.DataReduction()
        self.datareduction.load_state()
        self.datareduction.set_property('fileformat', self.fileformat + '.cbf')
        self.datareduction.set_property('headerformat', self.fileformat + '.param')
        self.datareduction.set_property('datadirs', self.get_exploaddirs())
        self.datareduction.save_state()
        self.emit('path-changed')
        
        self.load_samples()
        # emit signals if parameters change
        for name in self.setup_properties:
            self.connect('notify::' + name, lambda crd, prop:crd.emit('setup-changed'))
        for name in self.path_properties:
            self.connect('notify::' + name, lambda crd, prop:crd.emit('path-changed'))
    def do_notify(self,param):
        if param.name=='rootpath':
            self.files.rootpath=self.rootpath
        if param.name=='filebegin':
            self.files.filebegin=self.filebegin
        if param.name=='ndigits':
            self.files.ndigits=self.ndigits
    
    def is_idle(self):
        for eq in self.__equipments__:
            if hasattr(self, eq.lower()):
                if not getattr(self, eq.lower()).is_idle():
                    return False
        return True
    def _equipment_idle(self, equipment):
        if self.is_idle():
            self.emit('idle')
    def disconnect_equipment(self, type_=None):
        type_ = type_.upper()
        if type_ not in self.__equipments__:
            raise NotImplementedError('Unknown equipment ' + type_)
        attrib = self.__equipments__[type_]['attrib']
        logger.info('Disconnecting from equipment: ' + type_)
        if not hasattr(self, attrib):
            raise ValueError('No such equipment: ' + type_)
        if getattr(self, attrib).connected():
            getattr(getattr(self, attrib), self.__equipments__[type_]['disconnectfunc'])()
    def connect_equipment(self, host=None, type_=None):
        type_ = type_.upper()
        if type_ not in self.__equipments__:
            raise NotImplementedError('Unknown equipment ' + type_)
        attrib = self.__equipments__[type_]['attrib']
        cls = self.__equipments__[type_]['class']
        equip = None
        if isinstance(host, cls):
            setattr(self, attrib, host)
            host = host.host
            port = host.port
        elif isinstance(host, basestring):
            if ':' in host:
                host, port = host.rsplit(':', 1)
                port = int(port)
            else:
                port = self.__equipments__[type_]['port']
            logger.info('Connecting to equipment: ' + type_ + ' at ' + host + ':' + str(port))
            if not hasattr(self, attrib):
                equip = cls(host, port)
                setattr(self, attrib, equip)
            else:
                setattr(getattr(self, attrib), 'host', host)
                setattr(getattr(self, attrib), 'port', port)
                getattr(getattr(self, attrib), self.__equipments__[type_]['connectfunc'])()
        elif host is None:
            if not hasattr(self, attrib):
                logger.info('Creating dummy connection to equipment: ' + type_)
                equip = cls(None)
                setattr(self, attrib, equip)
            elif getattr(getattr(self, attrib), 'connected')():
                logger.info('Disconnecting from equipment: ' + type_)
                getattr(getattr(self, attrib), self.__equipments__[type_]['disconnectfunc'])()
        else:
            raise ValueError('Invalid type for ' + attrib + ' connection!')
        
        with self.freeze_notify():
            if host is not None:
                self.set_property(attrib + 'host', host + ':' + str(port))
            else:
                self.set_property(attrib + 'host', '__None__')
        if equip is not None:
            equip.connect('connect-equipment', self.on_equipment_connection_change, True)
            equip.connect('disconnect-equipment', self.on_equipment_connection_change, False)
            equip.connect('idle', self._equipment_idle)
            if equip.connected():
                self.on_equipment_connection_change(equip, True)
        if not getattr(self, attrib).connected():
            logger.error('Equipment not connected at the end of connection procedure: ' + type_)
        self.save_settings()
    def on_equipment_connection_change(self, equipment, connstate):
        if hasattr(self, 'pilatus') and hasattr(self, 'genix') and equipment in [self.pilatus, self.genix]:
            if self.pilatus.connected() and self.genix.connected() and self.exposurethread is None:
                logger.debug('Creating and starting CredoExpose process.')
                self.exposurethread = CredoExpose(self.pilatus, self.genix)
                self.exposurethread.daemon = True
                self.exposurethread.start()
                logger.debug('CredoExpose process started.')
            elif not (self.pilatus.connected() and self.genix.connected()) and self.exposurethread is not None:
                logger.debug('Setting killswitch for CredoExpose process')
                self.exposurethread.killswitch.set()
                if self.exposurethread.is_alive():
                    logger.debug('Waiting for CredoExpose to stop')
                    self.exposurethread.join()
                    logger.debug('CredoExpose stopped.')
                self.exposurethread = None
        if hasattr(self, 'pilatus') and equipment == self.pilatus:
            self.emit('equipment-connection', 'pilatus', connstate, self.pilatus)
        elif hasattr(self, 'genix') and equipment == self.genix:
            self.emit('equipment-connection', 'genix', connstate, self.genix)
        elif hasattr(self, 'tmcm') and equipment == self.tmcm:
            self.emit('equipment-connection', 'motors', connstate, self.tmcm)
        else:
            raise NotImplementedError
        return False
    
    def do_virtualpointdetectors_changed(self):
        self.save_settings()
        
    def do_path_changed(self):
        if hasattr(self, 'datareduction'):
            self.datareduction.datadirs = 
        self.filewatch.setup([self.imagepath] + sastool.misc.find_subdirs(self.filepath))
    def do_setup_changed(self): self.save_settings()
    def load_settings(self):
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.expanduser('~/.config/credo/credo2rc'))
        setupchanged = False
        pathchanged = False
        with self.freeze_notify():
            args = {'':[('username', 'User'), ('projectname', 'Project'),
                      ('filepath', 'File_path'), ('imagepath', 'Image_path'),
                      ('filter', 'Filter'), ('scanfile', 'ScanFile'), ('scandevice', 'ScanDevice'),
                      ('pilatushost', 'PilatusHost'), ('genixhost', 'GeniXHost'),
                      ('tmcmhost', 'TMCMHost'), ('virtdetcfgfile', 'VirtDetCfg')],
                  'float':[('dist', 'Distance'), ('pixelsize', 'Pixel_size'),
                           ('beamposx', 'Beam_X'), ('beamposy', 'Beam_Y'),
                           ('wavelength', 'Wavelength'), ('bs_out', 'BeamStopOut'), ('bs_in', 'BeamStopIn')],
                  'boolean':[('shuttercontrol', 'Shutter_control'),
                             ('motorcontrol', 'Move_motors')]}
            for argtype in args:
                for attrname, option in args[argtype]:
                    if cp.has_option('CREDO', option):
                        val = getattr(cp, 'get' + argtype)('CREDO', option)
                        if self.get_property(attrname) != val:
                            self.set_property(attrname, val)
                            if attrname in self.setup_properties:
                                setupchanged = True
                            if attrname in self.path_properties:
                                pathchanged = True
        if setupchanged:
            self.emit('setup-changed')
        if pathchanged:
            self.emit('path-changed')
        del cp
    def save_settings(self):
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.expanduser('~/.config/credo/credo2rc'))
        if not cp.has_section('CREDO'):
            cp.add_section('CREDO')
        for attrname, option in [('username', 'User'), ('projectname', 'Project'),
                                 ('filepath', 'File_path'), ('imagepath', 'Image_path'),
                                 ('filter', 'Filter'), ('dist', 'Distance'),
                                 ('pixelsize', 'Pixel_size'), ('beamposx', 'Beam_X'),
                                 ('beamposy', 'Beam_Y'), ('wavelength', 'Wavelength'), ('shuttercontrol', 'Shutter_control'), ('motorcontrol', 'Move_motors'), ('scanfile', 'ScanFile'),
                                 ('scandevice', 'ScanDevice'), ('pilatushost', 'PilatusHost'), ('genixhost', 'GeniXHost'), ('tmcmhost', 'TMCMHost'), ('virtdetcfgfile', 'VirtDetCfg'),
                                 ('bs_out', 'BeamStopOut'), ('bs_in', 'BeamStopIn')]:
            cp.set('CREDO', option, str(self.get_property(attrname)))
        if not os.path.exists(os.path.expanduser('~/.config/credo')):
            os.makedirs(os.path.expanduser('~/.config/credo'))
        with open(os.path.expanduser('~/.config/credo/credo2rc'), 'wt') as f:
            print "SAVING SETTINGS."
            cp.write(f)
        del cp
        return False
    
    def killexposure(self):
        self.pilatus.stopexposure()
        self.exposurethread.userbreakswitch.set()

    def expose(self, exptime, expnum=1, dwelltime=0.003, header_template=None, quick=False):
        logger.debug('Credo.exposure running.')
        expparams = {'shuttercontrol':bool(self.shuttercontrol), 'exptime':exptime, 'expnum':expnum,
                     'dwelltime':dwelltime, 'exposureformat':self.exposureformat, 'headerformat':self.headerformat,
                     'imagepath':self.imagepath, 'parampath':self.parampath, 'exploaddirs':self.get_exploaddirs(),
                     'virtualdetectors':self.virtualpointdetectors, 'quick':quick}
        if self.exposurethread.isworking.get_value() == 0:
            raise CredoError('Another exposure is running!')
        if self.sample is None:
            raise CredoError('No sample defined.')
        logger.debug('Getting next FSN')
        fsn = self.get_next_fsn()
        logger.debug('Next FSN is ' + str(fsn))
        if header_template is None:
            header_template = {}
        header_template.update(self.sample.get_header())
        h = sastool.classes.SASHeader(header_template)
        h['__Origin__'] = 'CREDO'
        h['__particle__'] = 'photon'
        h['Dist'] = self.dist - self.sample.distminus
        h['BeamPosX'] = self.beamposx
        h['BeamPosY'] = self.beamposy
        h['PixelSize'] = self.pixelsize / 1000.
        h['Wavelength'] = self.wavelength
        h['Owner'] = self.username
        h['GeniX_HT'] = self.genix.get_ht()
        h['GeniX_Current'] = self.genix.get_current()
        h['MeasTime'] = exptime
        h['FSN'] = fsn
        h['Project'] = self.projectname
        h['Filter'] = self.filter
        h['Monitor'] = h['MeasTime']
        logger.debug('Header prepared.')
        self.exposing = expparams
        GObject.idle_add(self._check_if_exposure_finished)
        logger.info('Starting exposure of %s' % str(self.sample))
        self.exposurethread.inqueue.put((expparams, h))
        return False
    def _check_if_exposure_finished(self):
        try:
            id, data = self.exposurethread.outqueue.get_nowait()
        except multiprocessing.queues.Empty:
            return True
        if id == CredoExpose.EXPOSURE_FAIL:
            self.emit('exposure-fail', data)
            return True
        elif id == CredoExpose.EXPOSURE_END:
            self.emit('exposure-end', True)
            return False
        elif id == CredoExpose.EXPOSURE_BREAK:
            self.emit('exposure-end', False)
            return False
        elif id == CredoExpose.EXPOSURE_DONE:
            self.emit('exposure-done', data)
            return True
        else:
            raise NotImplementedError('Invalid exposure phase')
    def trim_detector(self, threshold=4024, gain=None, blocking=False):
        if gain is None:
            gain = self.pilatus.getthreshold()['gain']
        self.pilatus.setthreshold(threshold, gain, blocking)
    def set_fileformat(self, begin='crd', digitsinfsn=5):
        ff = begin + '_' + '%%0%dd' % digitsinfsn
        ff_re = re.compile(begin + '_' + '(\d{%d,%d})' % (digitsinfsn, digitsinfsn))
        if ('fileformat' in self._credo_state and self._credo_state['fileformat'] != ff) or ('fileformat_re' in self._credo_state and self._credo_state['fileformat_re'] != ff_re):
            self._credo_state['fileformat'] = ff
            self._credo_state['fileformat_re'] = ff_re
            self.emit('setup-changed')
    def set_shutter(self, state):
        if bool(state):
            self.genix.shutter_open()
        else:
            self.genix.shutter_close()
        self.emit('shutter', state)
    def get_shutter(self):
        return self.genix.shutter_state()
    shutter = GObject.property(type=bool, default=False, getter=get_shutter, setter=set_shutter)
    def get_motors(self):
        if self.tmcm.connected():
            return self.tmcm.motors.values()
        else:
            return []
    def get_scandevices(self):
        lis = ['Time'] + self.get_motors()
        if self.pilatus.connected():
            lis += ['Pilatus threshold']
        return lis
    
    def scan(self, start, end, step, countingtime, waittime, header_template={}, shutter=False, autoreturn=False):
        """Set-up and start a scan measurement.
        
        Inputs:
            start: the starting value. In 'Time' mode this is ignored.
            end: the ending value. In 'Time' mode this is ignored.
            step: the step size. In 'Time' mode this is the number of exposures.
            countingtime: the counting time in seconds.
            waittime: least wait time in seconds. Moving the motors does not contribute to this!
            header_template: template header for expose()
            shutter: if the shutter is to be closed between exposures.
            autoreturn: if the scan device should be returned to the starting state at the end.
        """
        logger.debug('Initializing scan.')
        if self.scanning is not None:
            # do not run two scans parallelly.
            raise CredoError('Already executing a scan!')

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
        if isinstance(self._scanstore, sastool.classes.SASScanStore):
            self._scanstore.finalize()
            del self._scanstore
        self._scanstore = sastool.classes.SASScanStore(self.scanfile, 'CREDO spec file', [str(m) for m in self.get_motors()])
        return
    def __del__(self):
        self.pilatus.disconnect()
        if self.shuttercontrol:
            self.shutter = 0
        if hasattr(self, 'pilatus'):
            del self.pilatus
        if hasattr(self, 'genix'):
            del self.genix
        if hasattr(self, 'tmcm'):
            del self.tmcm
        gc.collect()
    def moveto_sample(self, sam=None, blocking=True):
        if sam is None:
            sam = self.sample
        logger.info('Moving sample %s into the beam.' % sam.title)
        for motname, pos in [('Sample_X', sam.positionx), ('Sample_Y', sam.positiony)]:
            if pos is None:
                logger.debug('Sample %s has None for %s, skipping movement.' % (str(sam), motname))
                continue
            try:
                motor = [m for m in self.get_motors() if m.alias == motname][0]
            except IndexError:
                raise CredoError('No motor with alias "' + motname + '".')
            self.move_motor(motor, pos, blocking)
        if not blocking:
            logger.info('Sample %s is in the beam.' % sam.title)
        else:
            logger.info('Returning from moveto_sample() before actual movement is done.')
    def wait_for_event(self, eventfunc, Niter=100):
        """Wait until eventfunc() returns True. During that time the GObject main loop is run.
        Between two checks of eventfunc() at most Niter iterations are executed."""
        while not eventfunc():
            for i in range(100):
                GObject.main_context_default().iteration(False)
                if not GObject.main_context_default().pending():
                    break
    def move_motor(self, motor, position, blocking=True):
        if not self.motorcontrol:
            logger.warning('Moving motors is disabled!')
            return
        try:
            if blocking:
                logger.info('Waiting for motor controller to become idle.')
                self.wait_for_event(lambda : self.tmcm.state == 'idle')
                logger.info('Moving motor %s to %f.' % (str(motor), position))
                motor.moveto(position)
                self.wait_for_event(lambda :not motor.is_moving())
                if abs(motor.get_pos() - position) > 0.001:
                    raise CredoError('Could not move motor %s to position %f.' % (str(motor), position))
                logger.info('Motor %s is at %f.' % (str(motor), position))
            else:
                motor.moveto(position)
                logger.info('Motor movement command sent to TMCM subsystem.')
        except tmcl_motor.MotorError as me:
            raise CredoError('Error moving motor %s: %s' % (str(motor), me.message))
    def move_beamstop(self, state=False):
        try:
            beamstopymotor = [m for m in self.get_motors() if m.alias == 'BeamStop_Y'][0]
        except IndexError:
            raise CredoError('No motor with alias "BeamStop_Y".')
        if not state:
            # should move the beamstop out. Ensure that the X-ray source is in low-power mode.
            if (self.genix.get_ht() > 30 or self.genix.get_current() > 0.3):
                logger.info('Putting GeniX into low-power mode.')
                self.genix.do_standby()
                self.wait_for_event(lambda :self.genix.whichstate() == genix.GENIX_STANDBY)
                logger.info('Low-power mode reached.')
            logger.info('Moving out beamstop.')
            self.move_motor(beamstopymotor, self.bs_out, blocking=True)
            logger.info('Beamstop is out.')
        else:
            logger.info('Moving in beamstop.')
            self.move_motor(beamstopymotor, self.bs_in, blocking=True)
            logger.info('Beamstop is in.')
            self.wait_for_event(lambda :not beamstopymotor.is_moving())
            logger.info('Putting GeniX into full-power mode.')
            self.genix.do_rampup()
            self.wait_for_event(lambda :self.genix.whichstate() == genix.GENIX_FULLPOWER)
            logger.info('Full-power mode reached.')
    
    def is_beamstop_in(self):
        try:
            beamstopymotor = [m for m in self.get_motors() if m.alias == 'BeamStop_Y'][0]
        except IndexError:
            raise CredoError('No motor with alias "BeamStop_Y".')
        return beamstopymotor.get_pos() == self.bs_in
    def do_transmission(self):
        if not hasattr(self, 'transmdata'):
            return
        if self.transmdata['next_is'] == 'D':
            if self.transmdata['repeat'] > 0:
                logger.info('Transmission: Dark current')
            sam = sample.SAXSSample('Dark current', None, None, None, None, 'SYSTEM', None, 0)
            with self.freeze_notify():
                self.shuttercontrol = False
            if self.transmdata['manageshutter']:
                self.shutter = False
            self.transmdata['next_is'] = 'E'
        elif self.transmdata['next_is'] == 'E':
            logger.info('Transmission: Empty beam (%s)' % self.transmdata['emptysample'].title)
            sam = self.transmdata['emptysample']
            self.transmdata['next_is'] = 'S'
            if self.transmdata['manageshutter']:
                with self.freeze_notify():
                    self.shuttercontrol = True
        else:
            logger.info('Transmission: Sample (%s)' % self.transmdata['sample'].title)
            sam = self.transmdata['sample']
            self.transmdata['repeat'] -= 1
            self.transmdata['next_is'] = 'D'
            if self.transmdata['manageshutter']:
                with self.freeze_notify():
                    self.shuttercontrol = True
        if (self.transmdata['repeat'] == 0 and self.transmdata['next_is'] == 'E') or self.transmdata['kill']:
            if self.transmdata['Isample'] and self.transmdata['Iempty'] and self.transmdata['Idark']:
                data = {}
                for n in ['sample', 'empty', 'dark']:
                    data[n] = sastool.classes.ErrorValue(np.mean(self.transmdata['I' + n]),
                                                       np.std(self.transmdata['I' + n]))
                Iempty = data['empty'] - data['dark']
                if Iempty.is_zero():
                    transm = None
                else:
                    transm = (data['sample'] - data['dark']) / Iempty
            else:
                transm = None
            self.emit('transmission-end', self.transmdata['Iempty'], self.transmdata['Isample'], self.transmdata['Idark'],
                      transm, not self.transmdata['kill'])
            return

        self.moveto_sample(sam)
        self.set_sample(sam)
        if self.transmdata['firstexposure']:
            self.expose(self.transmdata['exptime'], self.transmdata['expnum'], 0.003, None, quick=False)
            self.transmdata['firstexposure'] = False
        else:
            self.expose(self.transmdata['exptime'], self.transmdata['expnum'], 0.003, None, quick=True)
    def do_transmission_end(self, Iempty, Isample, Transmission, state):
        logger.info('End of transmission measurement.')
        del self.transmdata
    def transmission(self, sample, emptysample, exptime, expnum, mask, mode='max', repeat=1):
        # if self.is_beamstop_in():
        #    self.move_beamstop(False)
        self.transmdata = {'sample':sample, 'emptysample':emptysample, 'exptime':exptime,
                           'expnum':expnum, 'repeat':repeat, 'next_is':'D', 'firstexposure':True,
                           'mode':mode, 'mask':mask, 'kill':False, 'manageshutter':self.shuttercontrol}
        self.do_transmission()
    def killtransmission(self):
        self.transmdata['kill'] = True
        self.killexposure()
