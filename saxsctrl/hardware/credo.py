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

from . import datareduction
from . import sample
from . import virtualpointdetector
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class CredoError(Exception):
    pass

class CredoFileWatch(GObject.GObject):
    __gsignals__ = {'monitor-event':(GObject.SignalFlags.RUN_FIRST, None, (str, object)),
                  }    
    def __init__(self, folders=[]):
        GObject.GObject.__init__(self)
        self.monitors = []
        self.setup(folders)
    def setup(self, folders):
        for monitor, connection in self.monitors:
            monitor.cancel()
            monitor.disconnect(connection)
        self.monitors = []
        for folder in folders:
            dirmonitor = Gio.file_new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitors.append((dirmonitor, dirmonitor.connect('changed', self.on_monitor_event)))
    def on_monitor_event(self, monitor, filename, otherfilename, event):
        if event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED, Gio.FileMonitorEvent.MOVED):
            self.emit('monitor-event', filename, event)


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
                    'files-changed':(GObject.SignalFlags.RUN_FIRST, None, (str, object)),
                    'samples-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'sample-changed':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'shutter':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-done':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'exposure-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'equipment-connection':(GObject.SignalFlags.RUN_FIRST, None, (str, bool, object)),
                    'scan-dataread':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'scan-end':(GObject.SignalFlags.RUN_FIRST, None, (object, bool)),
                    'virtualpointdetectors-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'scan-phase':(GObject.SignalFlags.RUN_LAST, None, (str,)),
                    'scan-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,))
                   }
    __equipments__ = {'GENIX':{'class':genix.GenixConnection, 'attrib':'genix', 'port':502, 'connectfunc':'connect_to_controller', 'disconnectfunc':'disconnect_from_controller'},
                      'PILATUS':{'class':pilatus.PilatusConnection, 'attrib':'pilatus', 'port':41234, 'connectfunc':'connect_to_camserver', 'disconnectfunc':'disconnect_from_camserver'},
                      'TMCM':{'class':tmcl_motor.TMCM351_TCP, 'attrib':'tmcm', 'port':2001, 'connectfunc':'connect_to_controller', 'disconnectfunc':'disconnect_from_controller'},
                      }
    _credo_state = None
    exposurethread = None
    _filewatchers = None
    _nextfsn_cache = None
    _samples = None
    filebegin = GObject.property(type=str, default='crd')
    fsndigits = GObject.property(type=int, default=5, minimum=1, maximum=100)
    username = GObject.property(type=str, default='Anonymous')
    projectname = GObject.property(type=str, default='No project')
    pixelsize = GObject.property(type=float, default=172, minimum=0)
    dist = GObject.property(type=float, default=1000, minimum=0)
    filter = GObject.property(type=str, default='No filter')
    beamposx = GObject.property(type=float, default=348.38)
    beamposy = GObject.property(type=float, default=242.47)
    filepath = GObject.property(type=str, default=os.path.expanduser('~/credo_data/current'))
    imagepath = GObject.property(type=str, default='/net/pilatus300k.saxs/disk2/images')
    wavelength = GObject.property(type=float, default=1.54182, minimum=0)
    shuttercontrol = GObject.property(type=bool, default=True)
    motorcontrol = GObject.property(type=bool, default=True)
    scanning = GObject.property(type=object)
    exposing = GObject.property(type=object)
    scanfile = GObject.property(type=str, default='')
    scandevice = GObject.property(type=str, default='Time')
    pilatushost = GObject.property(type=str, default='')
    genixhost = GObject.property(type=str, default='')
    tmcmhost = GObject.property(type=str, default='')
    virtdetcfgfile = GObject.property(type=str, default='')
    virtualpointdetectors = None
    _scanstore = None
    # changing any of the properties in this list will trigger a setup-changed event.
    setup_properties = ['username', 'projectname', 'pixelsize', 'dist', 'filter', 'beamposx', 'beamposy', 'wavelength', 'shuttercontrol', 'motorcontrol', 'scanfile', 'scandevice', 'virtdetcfgfile', 'imagepath', 'filepath']
    # changing any of the properties in this list will trigger a path-changed event.
    path_properties = ['filepath', 'imagepath']
    def __init__(self, genixhost=None, pilatushost=None, motorhost=None, imagepath='/net/pilatus300k.saxs/disk2/images',
                 filepath='/home/labuser/credo_data/current'):
        GObject.GObject.__init__(self)
        self.exposing = None
        self.scanning = None
        self.filewatch = CredoFileWatch()
        self.filewatch.connect('monitor-event', self.on_filemonitor)
        self.load_settings()
        self._credo_state = {}
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
        
    def do_fileformatchange(self, crd=None, param=None):
        ff = self.filebegin + '_' + '%%0%dd' % self.fsndigits
        ff_re = re.compile(self.filebegin + '_' + '(\d{%d,%d})' % (self.fsndigits, self.fsndigits))
        if ('fileformat' not in self._credo_state or self._credo_state['fileformat'] != ff) or ('fileformat_re' not in self._credo_state or self._credo_state['fileformat_re'] != ff_re):
            self._credo_state['fileformat'] = ff
            self._credo_state['fileformat_re'] = ff_re
            self.emit('setup-changed')
    @GObject.property
    def fileformat(self): return self._credo_state['fileformat']
    @GObject.property
    def fileformat_re(self): return self._credo_state['fileformat_re']
    @GObject.property
    def headerformat(self): return self._credo_state['fileformat'] + '.param'
    @GObject.property
    def exposureformat(self): return self._credo_state['fileformat'] + '.cbf'
    @GObject.property
    def headerformat_re(self): return re.compile(self._credo_state['fileformat_re'].pattern + '\.param')
    @GObject.property
    def exposureformat_re(self): return re.compile(self._credo_state['fileformat_re'].pattern + '\.cbf')
    def do_path_changed(self):
        if hasattr(self, 'datareduction'):
            self.datareduction.datadirs = self.get_exploaddirs()
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
                           ('wavelength', 'Wavelength')],
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
                                ('scandevice', 'ScanDevice'), ('pilatushost', 'PilatusHost'), ('genixhost', 'GeniXHost'), ('tmcmhost', 'TMCMHost'), ('virtdetcfgfile', 'VirtDetCfg')]:
            cp.set('CREDO', option, str(self.get_property(attrname)))
        if not os.path.exists(os.path.expanduser('~/.config/credo')):
            os.makedirs(os.path.expanduser('~/.config/credo'))
        with open(os.path.expanduser('~/.config/credo/credo2rc'), 'wt') as f:
            print "SAVING SETTINGS."
            cp.write(f)
        del cp
        return False
    def on_filemonitor(self, monitor, filename, event):
        if event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED) and self._nextfsn_cache is not None:
            basename = os.path.split(filename)[1]
            if basename:
                for regex in self._nextfsn_cache.keys():
                    m = regex.match(basename)
                    if m is not None:
                        self._nextfsn_cache[regex] = int(m.group(1)) + 1
                        self.emit('files-changed', filename, event)
    def load_samples(self, *args):
        logger.debug('Loading samples.')
        for sam in sample.SAXSSample.new_from_cfg(os.path.expanduser('~/.config/credo/sample2rc')):
            self.add_sample(sam)
        if self._samples:
            self.set_sample(self._samples[0])
        self.emit('samples-changed')
        return False
    def save_samples(self, *args):
        cp = ConfigParser.ConfigParser()
        for i, sam in enumerate(self.get_samples()):
            sam.save_to_ConfigParser(cp, 'Sample_%03d' % i)
        with open(os.path.expanduser('~/.config/credo/sample2rc'), 'w+') as f:
            cp.write(f)
    def _get_subpath(self, subdir):
        pth = os.path.join(self.filepath, subdir)
        if not os.path.isdir(pth):
            if not os.path.exists(pth):
                os.mkdir(pth)  # an OSError is raised if no permission.
            else:
                raise OSError('%s exists and is not a directory!' % pth)
        return pth
    def add_sample(self, sam):
        if not isinstance(sam, sample.SAXSSample):
            logger.debug('Not adding sample: ' + str(sam) + ' because not a SAXSSample instance.')
            return
        if not [s for s in self._samples if s == sam]:
            logger.debug('Sample ' + str(sam) + ' added.')
            self._samples.append(sam)
            self._samples.sort()
            self.emit('samples-changed')
        else:
            logger.debug('Not adding duplicate sample: ' + str(sam))
    def remove_sample(self, sam):
        modified = False
        for todelete in [s == sam for s in self._samples]:
            self._samples.remove(todelete)
            if self.sample == todelete:
                self.sample = None
            modified = True
        if modified:
            self._samples.sort()
            self.emit('samples-changed')
    def get_samples(self):
        return self._samples[:]            
    def set_sample(self, sam):
        if not isinstance(sam, sample.SAXSSample):
            return
        # if not [s for s in self._samples if s == sam]:
        #    self._samples.append(sam)
        #    self.emit('samples-changed')
        #    self._samples.sort()
        if self.sample != sam:
            self.sample = sam
            self.emit('sample-changed', self.sample)
    def clear_samples(self):
        self.sample = None
        self._samples = []
        self.emit('samples-changed')
    def get_exploaddirs(self): return [self.imagepath, self.offlineimagepath, self.eval1dpath, self.eval2dpath, self.parampath, self.maskpath]
    @GObject.property
    def configpath(self): return self._get_subpath('config')
    @GObject.property
    def moviepath(self): return self._get_subpath('movie')
    @GObject.property
    def parampath(self): return self._get_subpath('param')
    @GObject.property
    def maskpath(self): return self._get_subpath('mask')
    @GObject.property
    def scanpath(self): return self._get_subpath('scan')
    @GObject.property
    def eval2dpath(self): return self._get_subpath('eval2d')
    @GObject.property
    def offlineimagepath(self): return self._get_subpath('images')
    @GObject.property
    def eval1dpath(self): return self._get_subpath('eval1d')
    
    def killexposure(self):
        self.pilatus.stopexposure()
        # self.exposurethread.userbreakswitch.set()

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
        logger.debug('Queue-ing exposure.')
        self.exposing = expparams
        GObject.idle_add(self._check_if_exposure_finished)
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
    def get_next_fsn(self, regex=None):
        if self._nextfsn_cache is None:
            self._nextfsn_cache = {}
        if regex is None:
            regex = self.fileformat_re
        if regex not in self._nextfsn_cache:
            maxfsns = [0]
            for pth in [self.imagepath, self.offlineimagepath] + sastool.misc.find_subdirs(self.filepath):
                fsns = [int(f.group(1)) for f in [regex.match(f) for f in os.listdir(pth)] if f is not None]
                if fsns:
                    maxfsns.append(max(fsns))
            self._nextfsn_cache[regex] = max(maxfsns) + 1
        return self._nextfsn_cache[regex]
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
            self.emit('scan-phase', 'Scan sequence started.')
        else:
            self.emit('scan-phase', 'Premature scan end!')
            self.emit('scan-end', self.scanning['scan'], False)
        return scan
    def killscan(self, wait_for_this_exposure_to_end=False):
        if not wait_for_this_exposure_to_end:
            self.killexposure()
        if self.scanning is not None:
            self.scanning['kill'] = True
        self.emit('scan-phase', 'Stopping scan sequence.')
    def scan_to_next_step(self):
        logger.debug('Going to next step.')
        if self.scanning['kill']:
            logger.debug('Not going to next step: kill!')
            return False    
        if self.scanning['device'] == 'Time':
            self.scanning['where'] = time.time()
            return True
        elif self.scanning['device'] == 'Pilatus threshold':
            gain = self.pilatus.getthreshold()['gain']
            threshold = self.scanning['start'] + self.scanning['idx'] * self.scanning['step']
            if threshold > self.scanning['end']:
                return False
            try:
                self.emit('scan-phase', 'Setting threshold to %.0f eV (%s)' % (threshold, gain))
                self.pilatus.setthreshold(threshold, gain, blocking=True)
                if abs(self.pilatus.getthreshold()['threshold'] - threshold) > 1:
                    logger.error('Cannot set threshold for pilatus to the desired value.')
                    self.emit('scan-fail', 'Error setting threshold: could not set to desired value.')
                    return False
            except pilatus.PilatusError as pe:
                logger.error('Cannot set threshold: PilatusError(' + pe.message + ')')
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
            try:
                self.emit('scan-phase', 'Moving motor %s to %.3f' % (str(self.scanning['device']), pos))
                self.scanning['device'].moveto(pos)
                while self.scanning['device'].is_moving():
                    for i in range(100):
                        GObject.main_context_default().iteration(False)
                        if not GObject.main_context_default().pending():
                            break
                if abs(pos - self.scanning['device'].get_pos()) > 0.001:
                    self.emit('scan-fail', 'Motor positioning failure, could not move to destination.')
                    logger.error('Motor positioning failure, could not move to destination.')
                    return False
            except tmcl_motor.MotorError as me:
                logger.error('Cannot move motor. MotorError(' + me.message + ')')
                self.emit('scan-fail', 'MotorError while moving motor: ' + me.message)
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
        return False
    def do_scan_end(self, scn, status):
        if self.scanning['oldshutter']:
            logger.debug('Closing shutter at the end of scan.')
            self.shutter = False
        with self.freeze_notify():
            self.shuttercontrol = self.scanning['oldshutter']
        self.scanning['scan'].stop_record_mode()
        if self.scanning['autoreturn'] is not None:
            self.emit('scan-phase', 'Auto-returning...')
            if self.scanning['device'] == 'Pilatus threshold':
                gain = self.pilatus.getthreshold()['gain']
                self.pilatus.setthreshold(self.scanning['autoreturn'], gain, blocking=True)
            else:
                self.scanning['device'].moveto(self.scanning['autoreturn'])
                while self.scanning['device'].is_moving():
                    for i in range(100):
                        GObject.main_context_default().iteration(False)
                        if not GObject.main_context_default().pending():
                            break
        logger.debug('Removing internal scan state dict.')
        self.scanning = None
        self.emit('scan-phase', 'Scan sequence done.')
        return False
    def do_scan_phase(self, phase):
        logger.debug('Scan phase: ' + phase)
        for i in range(100):
            GObject.main_context_default().iteration(False)
            if not GObject.main_context_default().pending():
                break
    def do_exposure_fail(self, msg):
        if self.scanning is not None:
            self.scanning = None
        return False
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
        del self.pilatus
        del self.genix
        del self.tmcm
        gc.collect()
    def add_virtdet(self, vd):
        if vd not in self.virtualpointdetectors:
            self.virtualpointdetectors.append(vd)
            self.emit('virtualpointdetectors-changed')
    def del_virtdet(self, vd):
        if vd in self.virtualpointdetectors:
            self.virtualpointdetectors.remove(vd)
            self.emit('virtualpointdetectors-changed')
    def clear_virtdet(self):
        self.virtualpointdetectors = []
    def load_virtdetcfg(self, filename=None, clear=True, dontset=False):
        if dontset:
            lis = []
        else:
            lis = self.virtualpointdetectors
        if filename is None:
            filename = self.virtdetcfgfile
        cp = ConfigParser.ConfigParser()
        cp.read(filename)
        if clear and not dontset:
            self.virtualpointdetectors = []
            lis = self.virtualpointdetectors
        elif clear and dontset:
            lis = []
            
        vpdschanged = False
        for vpdname in [sec for sec in cp.sections() if sec.startswith('VPD_')]:
            vpd = virtualpointdetector.virtualpointdetector_new_from_configparser(vpdname[4:], cp)
            if vpd not in lis:
                lis.append(vpd)
                vpdschanged = True
        if vpdschanged and not dontset:
            self.emit('virtualpointdetectors-changed')
        if not dontset:
            self.virtdetcfgfile = filename
        return lis
    def save_virtdetcfg(self, filename=None, detectors=None):
        if filename is None:
            filename = self.virtdetcfgfile
        if detectors is None:
            detectors = self.virtualpointdetectors
            self.virtdetcfgfile = filename
        cp = ConfigParser.ConfigParser()
        for vpd in self.virtualpointdetectors:
            vpd.write_to_configparser(cp)
        with open(filename, 'w') as f:
            cp.write(f)
    
