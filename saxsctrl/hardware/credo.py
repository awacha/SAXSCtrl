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
logger = logging.getLogger('credo')
logger.setLevel(logging.DEBUG)

class CredoError(Exception):
    pass

class CredoExposureNotifier(threading.Thread):
    def __init__(self, expparams, headertemplate, outqueue, userbreak, expfinished, name=None, group=None):
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
                    self.outqueue.put(CredoExpose.EXPOSURE_BREAK)
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
                        self.outqueue.put(CredoExpose.EXPOSURE_BREAK)
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
                    self.outqueue.put(CredoExpose.EXPOSURE_FAIL)
                else:
                    logger.debug('File loaded, calling callback.')
                    self.outqueue.put(ex)
                    del ex
            self.outqueue.put(CredoExpose.EXPOSURE_END)
            logger.debug('Notifier thread exiting cleanly.')
        except:
            self.outqueue.put(CredoExpose.EXPOSURE_FAIL)
            raise
        finally:
            self.exposurefinishedswitch.set()

class CredoExpose(multiprocessing.Process):
    EXPOSURE_END = -1
    EXPOSURE_FAIL = -2
    EXPOSURE_BREAK = -3
    def __init__(self, pilatus, genix, group=None, name=None):
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
                        self.genix.shutter_open()
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
                        self.genix.shutter_close()
                finally:
                    self.notifierthread.userbreakswitch.set()
                    if self.notifierthread.is_alive():
                        self.notifierthread.join()
                    self.notifierthread = None
                    self._exposurefinished_switch.clear()
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
                    'exposure-fail':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'exposure-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'connect-pilatus':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'connect-genix':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'disconnect-pilatus':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'disconnect-genix':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'connect-motors':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'disconnect-motors':(GObject.SignalFlags.RUN_FIRST, None, ()),
                   }
    _credo_state = None
    exposurethread = None
    _filewatchers = None
    _nextfsn_cache = None
    _samples = None
    _setup_changed_blocked = False
    _path_changed_blocked = False
    _setup_changed_needed = False
    _path_changed_needed = False
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
    def __init__(self, genixhost=None, pilatushost=None, motorhost=None, imagepath='/net/pilatus300k.saxs/disk2/images',
                 filepath='/home/labuser/credo_data/current', filebegin='crd', digitsinfsn=5):
        GObject.GObject.__init__(self)
        self.load_settings()
        self._credo_state = {}
        # connect GeniX
        if isinstance(genixhost, genix.GenixConnection):
            self.genix = genixhost
        elif isinstance(genixhost, basestring):
            if ':' in genixhost:
                genixhost, genixport = genixhost.rsplit(':', 1)
                genixport = int(genixport)
            else:
                genixport = 502
            self.genix = genix.GenixConnection(genixhost, genixport)
        elif genixhost is None:
            self.genix = genix.GenixConnection(None)
        else:
            raise ValueError('Invalid type for genixhost!')
        self.genix.connect('connect-controller', self.on_equipment_connection_change, True)
        self.genix.connect('disconnect-controller', self.on_equipment_connection_change, False)
        # connect Pilatus
        if isinstance(pilatushost, pilatus.PilatusConnection):
            self.pilatus = pilatushost
        elif isinstance(pilatushost, basestring):
            if ':' in pilatushost:
                pilatushost, pilatusport = pilatushost.rsplit(':', 1)
                pilatusport = int(pilatusport)
            else:
                pilatusport = 41234
            self.pilatus = pilatus.PilatusConnection(pilatushost, pilatusport)
        elif pilatushost is None:
            self.pilatus = pilatus.PilatusConnection(None)
        else:
            raise ValueError('Invalid type for pilatushost!')
        self.pilatus.connect('connect-camserver', self.on_equipment_connection_change, True)
        self.pilatus.connect('disconnect-camserver', self.on_equipment_connection_change, False)
        
        # connect motors
        if isinstance(motorhost, tmcl_motor.TMCM351):
            self.tmcm = motorhost
        elif isinstance(motorhost, basestring):
            if motorhost.startswith('/dev/'):
                self.tmcm = tmcl_motor.TMCM351_RS232(motorhost, settingsfile=os.path.expanduser('~/.config/credo/motorrc'))
            else:
                if ':' in motorhost:
                    motorhost, motorport = motorhost.rsplit(':', 1)
                    motorport = int(motorport)
                else:
                    motorport = 2001
                self.tmcm = tmcl_motor.TMCM351_TCP(motorhost, motorport, settingsfile=os.path.expanduser('~/.config/credo/motorrc'))
        elif motorhost is None:
            self.tmcm = tmcl_motor.TMCM351_TCP(None, settingsfile=os.path.expanduser('~/.config/credo/motorrc'))
        else:
            raise ValueError('Invalid type for motorhost!')
        self.tmcm.connect('driver-disconnect', self.on_equipment_connection_change, False)
        self.tmcm.connect('driver-connect', self.on_equipment_connection_change, True)

        
        # file format changing
        self.do_fileformatchange()
        self.connect('notify::filebegin', self.do_fileformatchange)
        self.connect('notify::fsndigits', self.do_fileformatchange)
        
        
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
        for name in ['username', 'projectname', 'pixelsize', 'dist', 'filter', 'beamposx', 'beamposy', 'wavelength', 'shuttercontrol', 'motorcontrol']:
            self.connect('notify::' + name, lambda crd, prop:crd.emit('setup-changed'))
        for name in ['filepath', 'imagepath']:
            self.connect('notify::' + name, lambda crd, prop:crd.emit('path-changed'))
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
        if equipment == self.pilatus and connstate:
            self.emit('connect-pilatus')
        elif equipment == self.pilatus and not connstate:
            self.emit('disconnect-pilatus')
        elif equipment == self.genix and connstate:
            self.emit('connect-genix')
        elif equipment == self.genix and not connstate:
            self.emit('disconnect-genix')
        elif equipment == self.tmcm and not connstate:
            self.emit('disconnect-motors')
        elif equipment == self.tmcm and connstate:
            self.emit('connect-motors')
    def do_fileformatchange(self, crd=None, param=None):
        ff = self.filebegin + '_' + '%%0%dd' % self.fsndigits
        ff_re = re.compile(self.filebegin + '_' + '(\d{%d,%d})' % (self.fsndigits, self.fsndigits))
        if ('fileformat' not in self._credo_state or self._credo_state['fileformat'] != ff) or ('fileformat_re' not in self._credo_state or self._credo_state['fileformat_re'] != ff_re):
            self._credo_state['fileformat'] = ff
            self._credo_state['fileformat_re'] = ff_re
            self.emit('setup-changed')
    @GObject.property
    def fileformat(self):
        return self._credo_state['fileformat']
    @GObject.property
    def fileformat_re(self):
        return self._credo_state['fileformat_re']
    @GObject.property
    def headerformat(self):
        return self._credo_state['fileformat'] + '.param'
    @GObject.property
    def exposureformat(self):
        return self._credo_state['fileformat'] + '.cbf'
    @GObject.property
    def headerformat_re(self):
        return re.compile(self._credo_state['fileformat_re'].pattern + '\.param')
    @GObject.property
    def exposureformat_re(self):
        return re.compile(self._credo_state['fileformat_re'].pattern + '\.cbf')
    def do_path_changed(self):
        if self._path_changed_blocked:
            self._path_changed_needed = True
            self.stop_emission('path-changed')
            return True
        if hasattr(self, 'datareduction'):
            self.datareduction.datadirs = self.get_exploaddirs()
    def do_setup_changed(self):
        if self._setup_changed_blocked:
            self._setup_changed_needed = True
            self.stop_emission('setup-changed')
            return True
        self.save_settings()
        self._setup_filewatchers()
    def do_samples_changed(self):
        pass
    def do_sample_changed(self, sam):
        pass
    def do_files_changed(self, filename, event):
        pass
    def do_shutter(self):
        pass
    def load_settings(self):
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.expanduser('~/.config/credo/credo2rc'))
        try:
            self.delay_path_changed(True)
            self.delay_setup_changed(True)
            for attrname, option in [('username', 'User'), ('projectname', 'Project'), ('filepath', 'File_path'), ('imagepath', 'Image_path'),
                                    ('filter', 'Filter')]:
                if cp.has_option('CREDO', option):
                    self.set_property(attrname, cp.get('CREDO', option))
            for attrname, option in [('dist', 'Distance'), ('pixelsize', 'Pixel_size'), ('beamposx', 'Beam_X'), ('beamposy', 'Beam_Y'),
                                    ('wavelength', 'Wavelength')]:
                if cp.has_option('CREDO', option):
                    self.set_property(attrname, cp.getfloat('CREDO', option))
            for attrname, option in [('shuttercontrol', 'Shutter_control'), ('motorcontrol', 'Move_motors')]:
                if cp.has_option('CREDO', option):
                    self.set_property(attrname, cp.getboolean('CREDO', option))
        finally:
            self.delay_path_changed(False)
            self.delay_setup_changed(False)
        del cp
    def save_settings(self):
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.expanduser('~/.config/credo/credo2rc'))
        if not cp.has_section('CREDO'):
            cp.add_section('CREDO')
        for attrname, option in [('username', 'User'), ('projectname', 'Project'), ('filepath', 'File_path'), ('imagepath', 'Image_path'),
                                ('filter', 'Filter'), ('dist', 'Distance'), ('pixelsize', 'Pixel_size'), ('beamposx', 'Beam_X'), ('beamposy', 'Beam_Y'),
                                ('wavelength', 'Wavelength'), ('shuttercontrol', 'Shutter_control'), ('motorcontrol', 'Move_motors')]:
            cp.set('CREDO', option, self.get_property(attrname))
        if not os.path.exists(os.path.expanduser('~/.config/credo')):
            os.makedirs(os.path.expanduser('~/.config/credo'))
        with open(os.path.expanduser('~/.config/credo/credo2rc'), 'wt') as f:
            print "SAVING SETTINGS."
            cp.write(f)
        del cp
        return False
    def delay_setup_changed(self, state):
        self._setup_changed_blocked = state
        if state == False and self._setup_changed_needed:
            self._setup_changed_needed = False
            self.emit('setup-changed')
    def delay_path_changed(self, state):
        self._path_changed_blocked = state
        if state == False and self._path_changed_needed:
            self._path_changed_needed = False
            self.emit('path-changed')
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
    def get_exploaddirs(self):
        return [self.imagepath, self.offlineimagepath, self.eval1dpath, self.eval2dpath, self.parampath, self.maskpath]
    @GObject.property
    def configpath(self):
        return self._get_subpath('config')
    @GObject.property
    def moviepath(self):
        return self._get_subpath('movie')
    @GObject.property
    def parampath(self):
        return self._get_subpath('param')
    @GObject.property
    def maskpath(self):
        return self._get_subpath('mask')
    @GObject.property
    def scanpath(self):
        return self._get_subpath('scan')
    @GObject.property
    def eval2dpath(self):
        return self._get_subpath('eval2d')
    @GObject.property
    def offlineimagepath(self):
        return self._get_subpath('images')
    @GObject.property
    def eval1dpath(self):
        return self._get_subpath('eval1d')
    
    def killexposure(self):
        self.pilatus.stopexposure()
        self.exposurethread.userbreakswitch.set()
    def expose(self, exptime, expnum=1, dwelltime=0.003, header_template=None):
        logger.debug('Credo.exposure running.')
        expparams = {'shuttercontrol':self.shuttercontrol, 'exptime':exptime, 'expnum':expnum,
                     'dwelltime':dwelltime, 'exposureformat':self.exposureformat, 'headerformat':self.headerformat,
                     'imagepath':self.imagepath, 'parampath':self.parampath, 'exploaddirs':self.get_exploaddirs()}
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
        GObject.idle_add(self._check_if_exposure_finished)
        self.exposurethread.inqueue.put((expparams, h))
        return None
    def _check_if_exposure_finished(self):
        try:
            mesg = self.exposurethread.outqueue.get_nowait()
        except multiprocessing.queues.Empty:
            return True
        if mesg == CredoExpose.EXPOSURE_FAIL:
            self.emit('exposure-fail')
            return True
        elif mesg == CredoExpose.EXPOSURE_END:
            self.emit('exposure-end', True)
            return False
        elif mesg == CredoExpose.EXPOSURE_BREAK:
            self.emit('exposure-end', False)
            return False
        else:
            self.emit('exposure-done', mesg)
            return True
    def trim_detector(self, threshold=4024, gain='midg'):
        self.pilatus.setthreshold(threshold, gain)
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

    def __del__(self):
        self.pilatus.disconnect()
        if self.shuttercontrol:
            self.shutter = 0
        del self.pilatus
        del self.genix
        del self.tmcm
        gc.collect()

        
