import genix
import pilatus
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

logger = logging.getLogger('credo')
# logger.setLevel(logging.DEBUG)

class Credo(object):
    _exposurethread = None
    # _recent_exposures = []
    _callbacks = {}
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
        self._username = 'Anonymous'
        self._projectname = 'No project'
        self._filepath = filepath
        self._imagepath = imagepath
        self.set_fileformat(filebegin, digitsinfsn)
        self._dist = 1000
        self._pixelsize = 172
        self._beamposx = 308.29815843244432
        self._beamposy = 243.63065376104609
        self._wavelength = 1.54182
        self._filter = 'No filter'
        self._shuttercontrol = True
        self._callbacks = {}
        self._kill_exposure_notifier = threading.Event()
    def connect_callback(self, name, func, *args):
        if name not in self._callbacks:
            self._callbacks[name] = []
        u = uuid.uuid1()
        self._callbacks[name].append((u, func, args))
    def emit(self, name, *args):
        if name not in self._callbacks:
            return
        for u, func, userargs in self._callbacks[name]:
            ret = func.__call__(args, userargs)
            if bool(ret):
                break
    def disconnect_callback(self, name, u):
        if name not in self._callbacks:
            return
        try:
            cb_to_delete = [x for x in self._callbacks[name] if x[0] == u][0]
        except IndexError:
            raise
        self._callbacks[name].remove(cb_to_delete)
        
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
    def set_sample(self, sample):
        self.sample = sample
        self.emit('sample-changed', sample)
    @property
    def filter(self):
        return self._filter
    @filter.setter
    def filter(self, value):
        self._filter = value
        self.emit('setup-changed')
    @property
    def pixelsize(self):
        return self._pixelsize
    @pixelsize.setter
    def pixelsize(self, value):
        self._pixelsize = value
        self.emit('setup-changed')
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
    def eval1dimagepath(self):
        return self._get_subpath('eval1d')
    
    @property
    def filepath(self):
        return self._filepath
    @filepath.setter
    def filepath(self, value):
        self._filepath = value
        self.emit('setup-changed')
    @property
    def imagepath(self):
        return self._imagepath
    @imagepath.setter
    def imagepath(self, value):
        self._imagepath = value
        self.emit('setup-changed')
    @property
    def username(self):
        return self._username
    @username.setter
    def username(self, value):
        self._username = value
        self.emit('setup-changed')
    @property
    def projectname(self):
        return self._projectname
    @projectname.setter
    def projectname(self, value):
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
        self._wavelength = value
        self.emit('setup-changed')
    @property
    def beamposx(self):
        return self._beamposx
    @beamposx.setter
    def beamposx(self, value):
        self._beamposx = value
        self.emit('setup-changed')
    @property
    def beamposy(self):
        return self._beamposy
    @beamposy.setter
    def beamposy(self, value):
        self._beamposy = value
        self.emit('setup-changed')
    @property
    def dist(self):
        return self._dist
    @dist.setter
    def dist(self, value):
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
    def _exposure_notifier(self, header, exptime, expnum, dwelltime, filenameformat, headernameformat, firstfsn, callback=None):
        logger.debug('Notifier thread starting. Exptime: %f; expnum: %d; dwelltime: %f; filenameformat: %s; headernameformat: %s; firstfsn: %d.' % (exptime, expnum, dwelltime, filenameformat, headernameformat, firstfsn))
        t0 = time.time()
        for i in range(0, expnum):
            t1 = time.time()
            nextend = t0 + exptime * (i + 1) + dwelltime * i + 0.005
            logger.debug('Sleeping %f seconds' % (nextend - t1))
            if nextend > t1:
                time.sleep(nextend - t1)
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
    def expose(self, exptime, expnum=1, dwelltime=0.003, blocking=True, callback=None):
        if self._exposurethread is not None:
            self._exposurethread.join()
        # self._recent_exposures = []
        fsn = self.get_next_fsn()
        filename = (self.fileformat % fsn) + '.cbf'
        h = sastool.classes.SASHeader()
        h['__Origin__'] = 'CREDO'
        h['__particle__'] = 'photon'
        h['Dist'] = self.dist
        h['BeamPosX'] = self.beamposx
        h['BeamPosY'] = self.beamposy
        h['PixelSize'] = self.pixelsize / 1000.
        h['Wavelength'] = self.wavelength
        h['Title'] = self.sample.title
        h['Owner'] = self.username
        h['GeniX_HT'] = self.genix.get_ht()
        h['GeniX_Current'] = self.genix.get_current()
        h['MeasTime'] = exptime
        h['FSN'] = fsn
        h['Temperature'] = self.sample.temperature
        h['Project'] = self.projectname
        h['Filter'] = self.filter
        h['Thickness'] = self.sample.thickness
        h['PosSample'] = self.sample.position
        h['Monitor'] = h['MeasTime']
        headernameformat = self.fileformat + '.param'
        
        if callback is None:
            callback = self._default_expend_callback
        self._exposurethread = threading.Thread(name='Credo_exposure',
                                                target=self._exposurethread_worker,
                                                args=(h, exptime, expnum, dwelltime,
                                                      self.fileformat + '.cbf',
                                                      headernameformat, callback))
        self._exposurethread.setDaemon(True)
        self._exposurethread.start()
        if not blocking:
            return
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
    def get_next_fsn(self):
        maxfsns = [0]
        for pth in [self.imagepath, self.offlineimagepath] + sastool.misc.find_subdirs(self.filepath):
            fsns = [int(f.group(1)) for f in [self.fileformat_re.match(f) for f in os.listdir(pth)] if f is not None]
            if fsns:
                maxfsns.append(max(fsns))
        return max(maxfsns) + 1
    def set_fileformat(self, begin='crd', digitsinfsn=5):
        self._fileformat = begin + '_' + '%%0%dd' % digitsinfsn
        self._fileformat_re = re.compile(begin + '_' + '(\d{%d,%d})' % (digitsinfsn, digitsinfsn))
        self.emit('setup-changed')
    def __del__(self):
        self.pilatus.disconnect()
        if self.shuttercontrol:
            self.shutter = 0
        del self.pilatus
        del self.genix
        gc.collect()
