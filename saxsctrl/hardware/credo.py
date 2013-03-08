from . import genix
from . import pilatus
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
import gio
import ConfigParser

from . import datareduction
from . import sample
logger = logging.getLogger('credo')
# logger.setLevel(logging.DEBUG)

class CredoError(Exception):
    pass

class CBFreeze(object):
    def __init__(self, obj, name):
        self.obj = obj
        self.name = name
    def __enter__(self):
        self.obj.freeze_callbacks(self.name)
    def __exit__(self, *args):
        self.obj.thaw_callbacks(self.name)

class Credo(object):
    _exposurethread = None
    # _recent_exposures = []
    _callbacks = {}
    _filewatchers = None
    _fileformat = None
    _fileformat_re = None
    _nextfsn_cache = None
    _username = 'Anonymous'
    _projectname = 'No project'
    _pixelsize = 172
    _dist = 1000
    _exposure_user_break = None
    def __init__(self, genixhost=None, pilatushost=None, genixport=502, pilatusport=41234, imagepath='/net/pilatus300k.saxs/disk2/images',
                 filepath='/home/labuser/credo_data/current', filebegin='crd', digitsinfsn=5):
        if isinstance(genixhost, genix.GenixConnection):
            self.genix = genixhost
        elif genixhost is not None:
            self.genix = genix.GenixConnection(genixhost, genixport)
        if isinstance(pilatushost, pilatus.PilatusConnection):
            self.pilatus = pilatushost
        elif pilatushost is not None:
            self.pilatus = pilatus.PilatusConnection(pilatushost, pilatusport)
        self._filepath = filepath
        self._imagepath = imagepath
        self.set_fileformat(filebegin, digitsinfsn)
        self._beamposx = 348.38
        self._beamposy = 242.47
        self._wavelength = 1.54182
        self._filter = 'No filter'
        self._shuttercontrol = True
        self._callbacks = {}
        self._kill_exposure_notifier = threading.Event()
        self._samples = []
        self.sample = None
        self.load_settings()
        self.datareduction = datareduction.DataReduction(fileformat=self.fileformat, headerformat=self.fileformat.replace('.cbf', '.param'),
                                                         datadirs=self.get_exploaddirs())
        self.datareduction.load_state(keep=['fileformat', 'headerformat', 'datadirs'])
        self.datareduction.save_state()
        self.connect_callback('setup-changed', self.save_settings)
        self.connect_callback('path-changed', self.on_path_changed)
        self.connect_callback('setup-changed', self._setup_filewatchers)
        self._setup_filewatchers()
        self.load_samples()
    def on_path_changed(self, *args):
        self.load_samples(*args)
        self.datareduction.datadirs = self.get_exploaddirs()
    def load_settings(self):
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.expanduser('~/.config/credo/credorc'))
        for attrname, option in [('_username', 'User'), ('_projectname', 'Project'), ('_filepath', 'File_path'), ('_imagepath', 'Image_path'),
                                ('_filter', 'Filter')]:
            if cp.has_option('CREDO', option):
                self.__setattr__(attrname, cp.get('CREDO', option))
        for attrname, option in [('_dist', 'Distance'), ('_pixelsize', 'Pixel_size'), ('_beamposx', 'Beam_X'), ('_beamposy', 'Beam_Y'),
                                ('_wavelength', 'Wavelength')]:
            if cp.has_option('CREDO', option):
                self.__setattr__(attrname, cp.getfloat('CREDO', option))
        for attrname, option in [('_shuttercontrol', 'Shutter_control')]:
            if cp.has_option('CREDO', option):
                self.__setattr__(attrname, cp.getboolean('CREDO', option))
        del cp
        self.emit('setup-changed')
        self.emit('path-changed')
    def save_settings(self, *args):
        cp = ConfigParser.ConfigParser()
        cp.read(os.path.expanduser('~/.config/credo/credorc'))
        if not cp.has_section('CREDO'):
            cp.add_section('CREDO')
        for attrname, option in [('_username', 'User'), ('_projectname', 'Project'), ('_filepath', 'File_path'), ('_imagepath', 'Image_path'),
                                ('_filter', 'Filter'), ('_dist', 'Distance'), ('_pixelsize', 'Pixel_size'), ('_beamposx', 'Beam_X'), ('_beamposy', 'Beam_Y'),
                                ('_wavelength', 'Wavelength'), ('_shuttercontrol', 'Shutter_control')]:
            cp.set('CREDO', option, self.__getattribute__(attrname))
        if not os.path.exists(os.path.expanduser('~/.config/credo')):
            os.makedirs(os.path.expanduser('~/.config/credo'))
        with open(os.path.expanduser('~/.config/credo/credorc'), 'wt') as f:
            cp.write(f)
        del cp
        return False
    def _setup_filewatchers(self, *args):
        if self._filewatchers is None:
            self._filewatchers = []
        for fw, cbid in self._filewatchers:
            fw.disconnect(cbid)
            fw.cancel()
            self._filewatchers.remove((fw, cbid))
            del fw
        for folder in [self.imagepath] + sastool.misc.find_subdirs(self.filepath):
            fw = gio.File(folder).monitor_directory()
            self._filewatchers.append((fw, fw.connect('changed', self._on_filewatch)))
    def _on_filewatch(self, monitor, filename, otherfilename, event):
        if event in (gio.FILE_MONITOR_EVENT_CHANGED, gio.FILE_MONITOR_EVENT_CREATED) and self._nextfsn_cache is not None:
            basename = filename.get_basename()
            if basename:
                for regex in self._nextfsn_cache.keys():
                    m = regex.match(basename)
                    if m is not None:
                        print "Updating nextfsn cache. Pattern: ", regex.pattern, "Previous: ", self._nextfsn_cache[regex], "Current: ", int(m.group(1)) + 1
                        self._nextfsn_cache[regex] = int(m.group(1)) + 1
        if event in (gio.FILE_MONITOR_EVENT_CHANGED, gio.FILE_MONITOR_EVENT_CREATED, gio.FILE_MONITOR_EVENT_DELETED, gio.FILE_MONITOR_EVENT_MOVED):
            self.emit('files-changed', filename, event)
    def load_samples(self, *args):
        for sam in sample.SAXSSample.new_from_cfg(os.path.expanduser('~/.config/credo/samplerc')):
            self.add_sample(sam)
        
        if self._samples:
            self.set_sample(self._samples[0])
        self.emit('samples-changed')
        return False
    def save_samples(self, *args):
        cp = ConfigParser.ConfigParser()
        for i, sam in enumerate(self.get_samples()):
            sam.save_to_ConfigParser(cp, 'Sample_%03d' % i)
        with open(os.path.expanduser('~/.config/credo/samplerc'), 'w+') as f:
            cp.write(f)
    def freeze_callbacks(self, name):
        if name not in self._callbacks:
            return
        self._callbacks[name][1] = False
    def thaw_callbacks(self, name):
        if name not in self._callbacks:
            return
        self._callbacks[name][1] = True
    def callbacks_frozen(self, name):
        return CBFreeze(self, name)
    def connect_callback(self, name, func, *args):
        if name not in self._callbacks:
            self._callbacks[name] = [[], True]
        u = uuid.uuid1()
        self._callbacks[name][0].append((u, func, args))
        return u
    def emit(self, name, *args):
        if name not in self._callbacks:
            return
        if not self._callbacks[name][1]:
            return
        for u, func, userargs in self._callbacks[name][0]:
            ret = func.__call__(args, userargs)
            if bool(ret):
                break
    def disconnect_callback(self, name, u):
        if name not in self._callbacks:
            return
        try:
            cb_to_delete = [x for x in self._callbacks[name][0] if x[0] == u][0]
        except IndexError:
            raise
        self._callbacks[name][0].remove(cb_to_delete)
        
    def is_pilatus_connected(self):
        return self.pilatus is not None and self.pilatus.connected()
    def is_genix_connected(self):
        return self.genix is not None
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
            return
        if not [s for s in self._samples if s == sam]:
            self._samples.append(sam)
            self._samples.sort()
            self.emit('samples-changed')
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
    @property
    def filter(self):
        return self._filter
    @filter.setter
    def filter(self, value):
        if self._filter != value:
            self._filter = value
            self.emit('setup-changed')
    @property
    def pixelsize(self):
        return self._pixelsize
    @pixelsize.setter
    def pixelsize(self, value):
        if self._pixelsize != value:
            self._pixelsize = value
            self.emit('setup-changed')
    @property
    def configpath(self):
        return self._get_subpath('config')
    @property
    def moviepath(self):
        return self._get_subpath('movie')
    @property
    def parampath(self):
        return self._get_subpath('param')
    @property
    def maskpath(self):
        return self._get_subpath('mask')
    @property
    def scanpath(self):
        return self._get_subpath('scan')
    @property
    def eval2dpath(self):
        return self._get_subpath('eval2d')
    @property
    def offlineimagepath(self):
        return self._get_subpath('images')
    @property
    def eval1dpath(self):
        return self._get_subpath('eval1d')
    
    @property
    def filepath(self):
        return self._filepath
    @filepath.setter
    def filepath(self, value):
        if self._filepath != value:
            self._filepath = value
            self.emit('path-changed')
    @property
    def imagepath(self):
        return self._imagepath
    @imagepath.setter
    def imagepath(self, value):
        if self._imagepath != value:
            self._imagepath = value
            self.emit('path-changed')
    @property
    def username(self):
        return self._username
    @username.setter
    def username(self, value):
        if self._username != value:
            self._username = value
            self.emit('setup-changed')
    @property
    def projectname(self):
        return self._projectname
    @projectname.setter
    def projectname(self, value):
        if self._projectname != value:
            self._projectname = value
            self.emit('setup-changed')
    @property
    def fileformat(self):
        return self._fileformat
    @property
    def fileformat_re(self):
        return self._fileformat_re
    @property
    def shutter(self):
        return self.genix.shutter_state()
    @shutter.setter
    def shutter(self, val):
        if bool(val):
            self.genix.shutter_open()
        else:
            self.genix.shutter_close()
        self.emit('shutter')
    @property
    def wavelength(self):
        return self._wavelength
    @wavelength.setter
    def wavelength(self, value):
        if self._wavelength != value:
            self._wavelength = value
            self.emit('setup-changed')
    @property
    def beamposx(self):
        return self._beamposx
    @beamposx.setter
    def beamposx(self, value):
        if self._beamposx != value:
            self._beamposx = value
            self.emit('setup-changed')
    @property
    def beamposy(self):
        return self._beamposy
    @beamposy.setter
    def beamposy(self, value):
        if self._beamposy != value:
            self._beamposy = value
            self.emit('setup-changed')
    @property
    def dist(self):
        return self._dist
    @dist.setter
    def dist(self, value):
        if self._dist != value:
            self._dist = value
            self.emit('setup-changed')
    @property
    def shuttercontrol(self):
        return self._shuttercontrol
    @shuttercontrol.setter
    def shuttercontrol(self, value):
        self._shuttercontrol = bool(value)
        self.emit('setup-changed')
    def killexposure(self):
        self.pilatus.stopexposure()
        self._exposure_user_break.set()
    def _exposure_notifier(self, header, exptime, expnum, dwelltime, filenameformat, headernameformat, firstfsn, callback=None):
        logger.debug('Notifier thread starting. Exptime: %f; expnum: %d; dwelltime: %f; filenameformat: %s; headernameformat: %s; firstfsn: %d.' % (exptime, expnum, dwelltime, filenameformat, headernameformat, firstfsn))
        t0 = time.time()
        for i in range(0, expnum):
            t1 = time.time()
            nextend = t0 + exptime * (i + 1) + dwelltime * i + 0.005
            logger.debug('Sleeping %f seconds' % (nextend - t1))
            if nextend > t1:
                res = self._exposure_user_break.wait(nextend - t1)
            if res is True:
                # user break occurred
                callback(None)
                return
            filename = os.path.join(self.imagepath, filenameformat % (firstfsn + i))
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
                if self._kill_exposure_notifier.isSet():
                    logger.debug('Killing notifier thread.')
                    if callback is not None:
                        callback(None)
                    return
                time.sleep(0.01)
            pilatusheader = sastool.io.twodim.readcbf(filename, load_header=True, load_data=False)[0]
            header.update(pilatusheader)
            header['EndDate'] = datetime.datetime.now()
            header['GeniX_HT_end'] = self.genix.get_ht()
            header['GeniX_Current_end'] = self.genix.get_current()
            header.write(os.path.join(self.parampath, headernameformat % header['FSN']))
            logger.debug('Header %s written.' % (headernameformat % header['FSN']))
            header['FSN'] += 1
            if callback is not None:
                try:
#                    callback(filename)
                    logger.debug('Loading file.')
                    ex = sastool.classes.SASExposure(filename, dirs=(self.parampath, self.imagepath, self.offlineimagepath))
                except IOError as ioe:
                    print "Tried to load file:", filename
                    print "Folders:", (self.parampath, self.imagepath, self.offlineimagepath)
                    print "Error text:", ioe.message
                    callback(None)
                else:
                    # self._recent_exposures.append(ex)
                    logger.debug('File loaded, calling callback.')
                    callback(ex)
                    del ex
        logger.debug('Notifier thread exiting cleanly.')
    def _exposurethread_worker(self, header, exptime, expnum, dwelltime, filenameformat, headernameformat, callback=None):
        logger.debug('Exposure thread running.')
        expnotifier_thread = None
        try:
            firstfsn = header['FSN']
            if self.shuttercontrol:
                self.shutter = 1
            expstartdata = self.pilatus.expose(exptime, filenameformat % firstfsn, expnum, dwelltime)
            self._kill_exposure_notifier.clear()
            expnotifier_thread = threading.Thread(name='Credo_exposure_notifier',
                                                  target=self._exposure_notifier,
                                                  args=(header, exptime, expnum, dwelltime,
                                                        filenameformat, headernameformat, firstfsn,
                                                        callback))
            expnotifier_thread.setDaemon(True)
            expnotifier_thread.start()
            expenddata = self.pilatus.wait_for_event('exposure_finished', (exptime + dwelltime) * expnum + 3)
            if self.shuttercontrol:
                self.shutter = 0
        finally:
            if expnotifier_thread is not None:
                self._kill_exposure_notifier.set()
                expnotifier_thread.join()
            self._exposurethread = None
        return
    def expose(self, exptime, expnum=1, dwelltime=0.003, blocking=True, callback=None, header_template=None):
        logger.debug('Credo.exposure running.')
        if self._exposure_user_break is None:
            self._exposure_user_break = threading.Event()
        if self._exposurethread is not None:
            logger.warning('Another exposure is running, waiting for it to end.')
            self._exposurethread.join()
        # self._recent_exposures = []
        if self.sample is None:
            raise CredoError('No sample defined.')
        logger.debug('Getting next FSN')
        fsn = self.get_next_fsn()
        logger.debug('Next FSN is ' + str(fsn))
        filename = (self.fileformat % fsn) + '.cbf'
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
        headernameformat = self.fileformat + '.param'
        logger.debug('Header prepared.')
        
        if callback is None:
            callback = self._default_expend_callback
        self._exposure_user_break.clear()
        self._exposurethread = threading.Thread(name='Credo_exposure',
                                                target=self._exposurethread_worker,
                                                args=(h, exptime, expnum, dwelltime,
                                                      self.fileformat + '.cbf',
                                                      headernameformat, callback))
        self._exposurethread.setDaemon(True)
        logger.debug('Launching exposure thread.')
        self._exposurethread.start()
        if not blocking:
            return
        logger.debug('Waiting for exposure thread to finish')
        self._exposurethread.join()
        # data = self._recent_exposures
        # self._recent_exposures = []
        # return tuple(data)
        return None
    def _default_expend_callback(self, exposure):
        if exposure is None:
            return
        print "Lowest count: ", exposure.Intensity.min()
        print "Highest count: ", exposure.Intensity.max()
        print "Saturation limit: ", exposure['Count_cutoff']
        sat = exposure['Count_cutoff']
        saturated = (exposure.Intensity >= sat).sum()
        if saturated:
            print "SATURATION!!! Saturated pixels: ", saturated
        fig = plt.figure()
        exposure.plot2d()
        fig.canvas.set_window_title((self.fileformat % exposure['FSN']) + '.cbf')
    def is_pilatus_idle(self):
        if self._exposurethread is not None:
            return False
        return self.pilatus.camstate == 'idle'
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
        if (self._fileformat != ff) or (self._fileformat_re != ff_re):
            self._fileformat = ff
            self._fileformat_re = ff_re
            self.emit('setup-changed')
    def __del__(self):
        self.pilatus.disconnect()
        if self.shuttercontrol:
            self.shutter = 0
        del self.pilatus
        del self.genix
        gc.collect()
