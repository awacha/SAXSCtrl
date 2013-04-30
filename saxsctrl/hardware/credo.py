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

class CredoExposureNotifier(threading.Thread):
    def __init__(self, expparams, headertemplate, outqueue, userbreak, expfinished, name='CredoExposureNotifier', group=None):
        threading.Thread.__init__(self, name=name, group=group)
        self.headertemplate = headertemplate
        self.expparams = expparams
        self.outqueue = outqueue
        self.userbreakswitch = userbreak
        self.exposurefinishedswitch = expfinished
    def run(self):
        try:
            self.expparams['firstfsn'] = self.headertemplate['FSN']
            logger.debug('Notifier thread starting. Exptime: %(exptime)f; expnum: %(expnum)d; dwelltime: %(dwelltime)f; filenameformat: %(exposureformat)s; headernameformat: %(headerformat)s; firstfsn: %(firstfsn)d.' % self.expparams)
            t0 = time.time()
            for i in range(0, self.expparams['expnum']):
                t1 = time.time()
                nextend = t0 + self.expparams['exptime'] * (i + 1) + self.expparams['dwelltime'] * i + 0.005
                if nextend > t1:
                    logger.debug('Sleeping %f seconds' % (nextend - t1))
                    is_userbreak = self.userbreakswitch.wait(nextend - t1)
                else:
                    logger.warning('Exposure lag: %f seconds' % (t1 - nextend))
                    is_userbreak = self.userbreakswitch.is_set()
                if is_userbreak:
                    self.outqueue.put((CredoExpose.EXPOSURE_BREAK, None))
                    return
                filename = os.path.join(self.expparams['imagepath'], self.expparams['exposureformat'] % (self.expparams['firstfsn'] + i))
                try:
                    f = open(filename, 'r')
                    exists = True
                    f.close()
                except IOError:
                    exists = False
                while not exists:
                    logger.debug('Waiting for file: ' + filename)
                    try:
                        f = open(filename, 'r')
                        exists = True
                        f.close()
                    except IOError:
                        exists = False
                    if self.userbreakswitch.wait(0.01): 
                        logger.debug('Killing notifier thread.')
                        self.outqueue.put((CredoExpose.EXPOSURE_BREAK, None))
                        return
                pilatusheader = sastool.io.twodim.readcbf(filename, load_header=True, load_data=False)[0]
                self.headertemplate.update(pilatusheader)
                self.headertemplate['EndDate'] = datetime.datetime.now()
                self.headertemplate.write(os.path.join(self.expparams['parampath'], self.expparams['headerformat'] % self.headertemplate['FSN']))
                logger.debug('Header %s written.' % (self.expparams['headerformat'] % self.headertemplate['FSN']))
                self.headertemplate['FSN'] += 1
                try:
                    logger.debug('Loading file.')
                    ex = sastool.classes.SASExposure(filename, dirs=self.expparams['exploaddirs'])
                except IOError as ioe:
                    print "Tried to load file:", filename
                    print "Folders:", self.expparams['exploaddirs']
                    print "Error text:", ioe.message
                    self.outqueue.put((CredoExpose.EXPOSURE_FAIL, ioe.message))
                else:
                    logger.debug('Reading out virtual detectors.')
                    for vd in self.expparams['virtualdetectors']:
                        ex.header['VirtDet_' + vd.name] = vd.readout(ex)
                    self.outqueue.put((CredoExpose.EXPOSURE_DONE, ex))
                    del ex
            logger.debug('Notifier thread exiting cleanly.')
        except Exception, exc:
            self.outqueue.put((CredoExpose.EXPOSURE_FAIL, exc.message))
            raise
        finally:
            self.exposurefinishedswitch.set()

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
        self.notifierthread = None
        self._exposurefinished_switch = multiprocessing.Event()
        self._exposurefinished_handle = None
        self._statelock = multiprocessing.Lock()
    def run(self):
        while not self.killswitch.is_set():
            try:
                expparams, headertemplate = self.inqueue.get(block=True, timeout=1)
            except multiprocessing.queues.Empty:
                continue
            with self.isworking:
                logger.info('Starting exposure.')
                self.notifierthread = CredoExposureNotifier(expparams, headertemplate, self.outqueue, self.userbreakswitch, self._exposurefinished_switch)
                self.notifierthread.daemon = True
                try:
                    firstfsn = headertemplate['FSN']
                    if expparams['shuttercontrol']:
                        logger.info('Opening shutter')
                        try:
                            self.genix.shutter_open()
                        except genix.GenixError as ge:
                            self.outqueue.put((self.EXPOSURE_FAIL, ge.message))
                            logger.error('Shutter timeout on opening.')
                            continue
                        logger.info('Shutter should now be opened.')
                    self.userbreakswitch.clear()
                    self._exposurefinished_switch.clear()
                    logger.info('Executing pilatus.expose()')
                    with self._statelock:
                        self._exposurefinished_handle = self.pilatus.connect('camserver-exposurefinished', self.on_exposurefinished)
                    self.pilatus.expose(expparams['exptime'], expparams['exposureformat'] % firstfsn, expparams['expnum'], expparams['dwelltime'])
                    logger.info('Starting notifier thread.')
                    self.notifierthread.start()
                    logger.debug('Waiting for exposurefinished_switch.')
                    self._exposurefinished_switch.wait((expparams['exptime'] + expparams['dwelltime']) * expparams['expnum'] + 3)
                    if self._exposurefinished_switch.is_set():
                        logger.debug('Exposurefinished switch was set.')
                    else:
                        logger.debug('Exposurefinished switch timeout.')
                    if expparams['shuttercontrol']:
                        try:
                            self.genix.shutter_close()
                        except genix.GenixError as ge:
                            self.outqueue.put((self.EXPOSURE_FAIL, ge.message))
                            logger.error('Shutter timeout on closing.')
                            continue
                finally:
                    self.notifierthread.userbreakswitch.set()
                    if self.notifierthread.is_alive():
                        self.notifierthread.join()
                    self.notifierthread = None
                    self._exposurefinished_switch.clear()
                    self.outqueue.put((CredoExpose.EXPOSURE_END, None))
                    
    def on_exposurefinished(self, pilatus, state, message):
        with self._statelock:
            self.pilatus.disconnect(self._exposurefinished_handle)
            self._exposurefinished_switch.set()
        return True
        
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
                    'scan-end':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'virtualpointdetectors-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
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
    # changing any of the properties in this list will trigger a setup-changed event.
    setup_properties = ['username', 'projectname', 'pixelsize', 'dist', 'filter', 'beamposx', 'beamposy', 'wavelength', 'shuttercontrol', 'motorcontrol', 'scanfile', 'scandevice', 'virtdetcfgfile']
    # changing any of the properties in this list will trigger a path-changed event.
    path_properties = ['filepath', 'imagepath']
    def __init__(self, genixhost=None, pilatushost=None, motorhost=None, imagepath='/net/pilatus300k.saxs/disk2/images',
                 filepath='/home/labuser/credo_data/current'):
        GObject.GObject.__init__(self)
        self.exposing = None
        self.scanning = None
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
        
        self.connect('notify::scanfile', lambda obj, param:self.init_scanfile())
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

        self._setup_filewatchers()
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
                setattr(self, attrib, cls(host, port))
            else:
                setattr(getattr(self, attrib), 'host', host)
                setattr(getattr(self, attrib), 'port', port)
                getattr(getattr(self, attrib), self.__equipments__[type_]['connectfunc'])()
        elif host is None:
            if not hasattr(self, attrib):
                logger.info('Creating dummy connection to equipment: ' + type_)
                setattr(self, attrib, cls(None))
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
        
        getattr(self, attrib).connect('connect-equipment', self.on_equipment_connection_change, True)
        getattr(self, attrib).connect('disconnect-equipment', self.on_equipment_connection_change, False)
        if not getattr(self, attrib).connected():
            logger.error('Equipment not connected at the end of connection procedure: ' + type_)
        self.save_settings()
    def on_equipment_connection_change(self, equipment, connstate):
        if equipment in [self.pilatus, self.genix]:
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
        if equipment == self.pilatus:
            self.emit('equipment-connection', 'pilatus', connstate, self.pilatus)
        elif equipment == self.genix:
            self.emit('equipment-connection', 'genix', connstate, self.genix)
        elif equipment == self.tmcm:
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
        self._setup_filewatchers()
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
    def _setup_filewatchers(self):
        if self._filewatchers is None:
            self._filewatchers = []
        for fw, cbid in self._filewatchers:
            fw.disconnect(cbid)
            fw.cancel()
            self._filewatchers.remove((fw, cbid))
            del fw
        for folder in [self.imagepath] + sastool.misc.find_subdirs(self.filepath):
            fw = Gio.file_new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._filewatchers.append((fw, fw.connect('changed', self._on_filewatch)))
    def _on_filewatch(self, monitor, filename, otherfilename, event):
        if event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED) and self._nextfsn_cache is not None:
            basename = filename.get_basename()
            if basename:
                for regex in self._nextfsn_cache.keys():
                    m = regex.match(basename)
                    if m is not None:
                        self._nextfsn_cache[regex] = int(m.group(1)) + 1
        if event in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED, Gio.FileMonitorEvent.DELETED, Gio.FileMonitorEvent.MOVED):
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
        self.exposurethread.userbreakswitch.set()

    def expose(self, exptime, expnum=1, dwelltime=0.003, header_template=None):
        logger.debug('Credo.exposure running.')
        expparams = {'shuttercontrol':bool(self.shuttercontrol), 'exptime':exptime, 'expnum':expnum,
                     'dwelltime':dwelltime, 'exposureformat':self.exposureformat, 'headerformat':self.headerformat,
                     'imagepath':self.imagepath, 'parampath':self.parampath, 'exploaddirs':self.get_exploaddirs(),
                     'virtualdetectors':self.virtualpointdetectors}
        if not self.exposurethread.isworking.get_value():
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
            raise NotImplementedError
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
        if bool(val):
            self.genix.shutter_open()
        else:
            self.genix.shutter_close()
        self.emit('shutter')
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
    def scan(self, start, end, step, countingtime, waittime, header_template, shutter=False):
        """Set-up and start a scan measurement.
        
        Inputs:
            start: the starting value. In 'Time' mode this is ignored.
            end: the ending value. In 'Time' mode this is ignored.
            step: the step size. In 'Time' mode this is the number of exposures.
            countingtime: the counting time in seconds.
            waittime: least wait time in seconds. Moving the motors does not contribute to this!
            header_template: template header for expose()
            shutter: if the shutter is to be closed between exposures.
        """
        if self.scanning is not None:
            raise CredoError('Already executing a scan!')
        scandevice = self.scandevice
        virtualdetectors = self.virtualpointdetectors
        if scandevice in [m.name for m in self.get_motors()]:
            scandevice = [m for m in self.get_motors() if m.name == scandevice][0]
        elif scandevice in [m.alias for m in self.get_motors()]:
            scandevice = [m for m in self.get_motors() if m.alias == scandevice][0]
        elif scandevice in [str(m) for m in self.get_motors()]:
            scandevice = [m for m in self.get_motors() if str(m) == scandevice][0]
        
        if scandevice == 'Time':
            columns = ['Time'] + [vd.name for vd in virtualdetectors]
            start = 0
            end = step
            step = 1
        elif scandevice == 'Pilatus threshold':
            columns = ['Threshold'] + [vd.name for vd in virtualdetectors]
        elif scandevice in [m.name for m in self.get_motors()]:
            columns = [self.scanning] + [vd.name for vd in virtualdetectors]
        self.init_scanfile()
        scan = sastool.classes.scan.SASScan(columns, (end - start) / step + 1)
        scan.motors = self.get_motors()
        scan.motorpos = [m.get_pos() for m in self.get_motors()]
        command = 'scan ' + str(scandevice) + ' from ' + str(start) + ' to ' + str(end) + ' by ' + str(step) + ' ct = ' + str(countingtime) + 'wt = ' + str(waittime)
        scan.countingtype = scan.COUNTING_TIME
        scan.countingvalue = countingtime
        scan.fsn = None
        scan.start_record_mode(command, (end - start) / step + 1, self.scanfile)
        self.scanning = {'device':scandevice, 'start':start, 'end':end, 'step':step,
                         'countingtime':countingtime, 'waittime':waittime,
                         'virtualdetectors':virtualdetectors, 'oldshutter':self.shuttercontrol,
                         'scan':scan, 'idx':0, header_template:header_template, 'kill':False}
        if self.shuttercontrol != shutter:
            self.shuttercontrol = shutter
        if self.scan_to_next_step():
            if self.scanning['device'] == 'Time' and not shutter:
                self.expose(self.scanning['countingtime'], self.scanning['end'], self.scanning['waittime'],
                            self.scanning['header_template'], self.scanning['virtualdetectors'])
            else:
                self.expose(self.scanning['countingtime'], 1, 0.003, self.scanning['header_template'],
                            self.scanning['virtualdetectors'])
    def killscan(self, wait_for_this_exposure_to_end=False):
        if not wait_for_this_exposure_to_end:
            self.killexposure()
        if self.scanning is not None:
            self.scanning['kill'] = True
    def scan_to_next_step(self):
        if self.scanning['kill']:
            return False    
        if self.scanning['device'] == 'Time':
            return True
        elif self.scanning['device'] == 'Pilatus threshold':
            gain = self.pilatus.getthreshold()['gain']
            threshold = self.scanning['start'] + self.scanning['idx'] * self.scanning['step']
            if threshold > self.scanning['end']:
                return False
            try:
                self.pilatus.setthreshold(threshold, gain, blocking=True)
            except pilatus.PilatusError as pe:
                raise CredoError('Cannot set threshold: ' + pe.message)
            return True
        else:
            pos = self.scanning['start'] + self.scanning['idx'] * self.scanning['step']
            if pos > self.scanning['end']:
                return False
            try:
                self.scanning['device'].moveto(pos)
                while self.scanning['device'].is_moving():
                    GObject.main_context_default.iteration(True)
            except tmcl_motor.MotorError as me:
                raise CredoError('Cannot move motor:' + me.message)
            return True
    
    def do_exposure_done(self, ex):
        if self.scanning is not None:
            self.scanning['scan'].append([ex.header['VirtDet_' + vd.name] for vd in self.scanning['virtualdetectors']])
            self.emit('scan-dataread', self.scanning['scan'])
        return False
    def do_exposure_end(self, status):
        self.exposing = None
        if self.scanning is not None:
            if self.scanning['device'] == 'Time' and not shutter:
                pass  # do nothing, we are finished with the timed scan
            else:
                if self.scan_to_next_step():
                    GObject.timeout_add(int(self.scanning['waittime'] * 1000), self.expose,
                                        self.scanning['countingtime'], 1, 0.003,
                                        self.scanning['header_template'], self.scanning['virtualdetectors'])
                    return False
                else:
                    # scan ended, no next step.
                    pass
            self.scanning['scan'].stop_record_mode()
            self.emit('scan-end', self.scanning['scan'])
            self.scanning = None
        return False
    def do_scan_end(self, scn):
        self.scanning = None
        return False
    def do_exposure_fail(self, msg):
        if self.scanning is not None:
            self.scanning = None
        return False
    def init_scanfile(self):
        if not os.path.exists(self.scanfile):
            sastool.classes.scan.init_spec_file(self.scanfile, 'CREDO spec file', self.get_motors())
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
        
