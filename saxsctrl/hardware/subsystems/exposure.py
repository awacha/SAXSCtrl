import threading
import multiprocessing.queues
import sastool
import datetime
from ..instruments.pilatus import PilatusError
import logging
import os
import time
from ...utils import objwithgui

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from gi.repository import GObject
from gi.repository import GLib
from .subsystem import SubSystem, SubSystemError

__all__ = ['SubSystemExposure']

class SubSystemExposureError(SubSystemError):
    pass

class ExposureMessageType(object):
    End = 'end'
    Failure = 'failure'
    Image = 'image'

class SubSystemExposure(SubSystem):
    __gsignals__ = {'exposure-image':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'exposure-end':(GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'notify':'override', }
    exptime = GObject.property(type=float, minimum=0, default=1, blurb='Exposure time (sec)')
    dwelltime = GObject.property(type=float, minimum=0.003, default=0.003, blurb='Dwell time between exposures (sec)')
    nimages = GObject.property(type=int, minimum=1, default=1, blurb='Number of images to take (sec)')
    operate_shutter = GObject.property(type=bool, default=True, blurb='Open/close shutter')
    cbf_file_timeout = GObject.property(type=float, default=3, blurb='Timeout for cbf files')
    timecriticalmode = GObject.property(type=bool, default=False, blurb='Time-critical mode')
    default_mask = GObject.property(type=str, default='mask.mat', blurb='Default mask file')
    def __init__(self, credo, offline=True, **kwargs):
        SubSystem.__init__(self, credo, offline)
        self._OWG_nogui_props.append('configfile')
        self._OWG_hints['default-mask'] = {objwithgui.OWG_Hint_Type.OrderPriority:None}
        self._OWG_entrytypes['default-mask'] = objwithgui.OWG_Param_Type.File
        self._thread = None
        for k in kwargs:
            self.set_property(k, kwargs[k])
        self._stopswitch = multiprocessing.Event()
        self._queue = multiprocessing.queues.Queue()
        self._default_mask = None
    def do_notify(self, param):
        if param.name == 'default-mask':
            if not os.path.isabs(self.default_mask):
                self.default_mask = os.path.join(self.credo().subsystems['Files'].maskpath, self.default_mask)
            else:
                try:
                    self._default_mask = sastool.classes.SASMask(self.default_mask)
                except IOError:
                    logger.error('Cannot load default mask from file: ' + self.default_mask)
                else:
                    logger.info('Loaded default mask from file: ' + self.default_mask)
        else:
            logger.debug('Other parameter modified: ' + param.name)
    def get_mask(self):
        return self._default_mask
    def kill(self, stop_processing_results=True):
        try:
            self.credo().get_equipment('pilatus').stopexposure()
        except PilatusError:
            pass
        if stop_processing_results:
            self._stopswitch.set()

    def start(self, header_template=None, mask=None):
        logger.debug('Exposure subsystem: starting exposure.')
        pilatus = self.credo().get_equipment('pilatus')
        genix = self.credo().get_equipment('genix')
        sample = self.credo().subsystems['Samples'].get()
        if not pilatus.is_idle():
            raise SubSystemExposureError('Detector is busy.')
        if mask is None:
            mask = self._default_mask

        fsn = self.credo().subsystems['Files'].get_next_fsn()
        exposureformat = self.credo().subsystems['Files'].get_exposureformat()
        headerformat = self.credo().subsystems['Files'].get_headerformat()
        if header_template is None:
            header_template = {}
        else:
            header_template = header_template.copy()
        if sample is not None:
            header_template.update(sample.get_header())
        else:
            header_template.update({'Title':'None'})
        header_template['__Origin__'] = 'CREDO'
        header_template['__particle__'] = 'photon'
        if sample is not None:
            header_template['Dist'] = self.credo().dist - sample.distminus
        else:
            header_template['Dist'] = self.credo().dist
        header_template['BeamPosX'] = self.credo().beamposx
        header_template['BeamPosY'] = self.credo().beamposy
        header_template['PixelSize'] = self.credo().pixelsize / 1000.
        header_template['Wavelength'] = self.credo().wavelength
        header_template['Owner'] = self.credo().username
        header_template['GeniX_HT'] = genix.get_ht()
        header_template['GeniX_Current'] = genix.get_current()
        header_template['MeasTime'] = self.exptime
        header_template['FSN'] = fsn
        header_template['Project'] = self.credo().projectname
        header_template['Filter'] = self.credo().filter
        header_template['Monitor'] = header_template['MeasTime']
        if mask is not None:
            header_template['maskid'] = mask.maskid
        logger.debug('Header prepared.')
        GLib.idle_add(self._check_if_exposure_finished)
        logger.info('Starting exposure of %s. Files will be named like: %s' % (str(sample), self.credo().subsystems['Files'].get_fileformat() % fsn))
        self._stopswitch.clear()
        pilatus.prepare_exposure(self.exptime, self.nimages, self.dwelltime)
        self._thread = threading.Thread(target=self._thread_worker, args=(os.path.join(self.credo().subsystems['Files'].imagespath, exposureformat),
                                                                          os.path.join(self.credo().subsystems['Files'].parampath, headerformat),
                                                                          self._stopswitch, self._queue, self.exptime, self.nimages, self.dwelltime,
                                                                          fsn, self.cbf_file_timeout, header_template, mask,
                                                                          ))
        self._thread.daemon = True
        if self.operate_shutter and genix.shutter_state() == False:
            genix.shutter_open()
        self._pilatus_idle_handler = pilatus.connect('idle', self._pilatus_idle, genix)
        self.credo().subsystems['Files'].increment_next_fsn()
        pilatus.execute_exposure(exposureformat % fsn)
        self._thread.start()
        return fsn
    def _pilatus_idle(self, pilatus, genix):
        # we get this signal when the exposure is finished.
        pilatus.disconnect(self._pilatus_idle_handler)
        if self.operate_shutter:
            genix.shutter_close()
    def _check_if_exposure_finished(self):
        try:
            id, data = self._queue.get_nowait()
        except multiprocessing.queues.Empty:
            return True
        if id == ExposureMessageType.Failure:
            self.emit('exposure-fail', data)
            return True
        elif id == ExposureMessageType.End:
            self.emit('exposure-end', data)
            return False
        elif id == ExposureMessageType.Image:
            self.emit('exposure-image', data)
            return True
        else:
            raise NotImplementedError('Invalid exposure message type')
    def do_exposure_fail(self, message):
        # this signal is emitted whenever the cbf file collector thread encounters a serious error.
        # In this case the thread is already dead, so we have to kill the pilatus exposure sequence.
        try:
            self.credo().get_equipment('pilatus').stopexposure()
        except PilatusError:
            # exposure already finished.
            pass
    def do_exposure_end(self, endstatus):
        # this is the last signal emitted during an exposure. The _check_if_exposure_finished() idle handler
        # has already deregistered itself.
        logger.info('Exposure ended.')
        pass
    def do_exposure_image(self, ex):
        pass
    def _process_exposure(self, exposurename, headername, stopswitch, queue, headertemplate, cbf_file_timeout, mask):
        # try to load the header from the CBF file.
        logger.debug('process_exposure starting')
        t0 = time.time()
        cbfdata = cbfheader = None
        while (time.time() - t0) < cbf_file_timeout:
            try:
                cbfdata, cbfheader = sastool.io.twodim.readcbf(exposurename, load_header=True, load_data=True)
                break
            except IOError:
                logger.debug('Waiting for image...')
                if stopswitch.wait(0.01):
                    # break signaled.
                    return False 
                # continue with the next try.
        if cbfdata is None:
            # timeout.
            raise SubSystemExposureError('Timeout on waiting for CBF file.')
        # create the exposure object
        logger.debug('Creating exposure')
        if self.timecriticalmode:
            ex = sastool.classes.SASExposure({'Intensity':cbfdata, 'Error':cbfdata ** 0.5, 'header':sastool.classes.SASHeader(headertemplate), 'mask':mask})
        else:
            ex = sastool.classes.SASExposure({'Intensity':cbfdata, 'Error':cbfdata ** 0.5, 'header':sastool.classes.SASHeader(headertemplate), 'mask':mask})
        
        # do some fine adjustments on the header template:
        # a) include the CBF header written by camserver.
        logger.debug('updating header')
        ex.header.update(cbfheader)
        # b) get instrument states
        logger.debug('Getting equipment status')
        ex.header.update(self.credo().subsystems['Equipments'].get_current_parameters())
        # c) readout virtual detectors
        if not self.timecriticalmode:
            logger.debug('Reading out virtual detectors')
            vdresults = self.credo().subsystems['VirtualDetectors'].readout_all(ex, self.credo().get_equipment('genix'))
            ex.header.update({('VirtDet_' + k): vdresults[k] for k in vdresults})
        # d) set the end date to the current time.
        ex.header['EndDate'] = datetime.datetime.now()
        # and save the header to the parampath.
        logger.debug('Writing header')
        ex.header.write(headername)
        logger.debug('Header %s written.' % (headername))
        queue.put((ExposureMessageType.Image, ex))
        logger.debug('Process_exposure took %f seconds.' % (time.time() - t0))
        del ex
        return True
    def _thread_worker(self, expname_template, headername_template, stopswitch, outqueue, exptime, nimages, dwelltime, firstfsn, cbf_file_timeout, header_template, mask):
        """Wait for the availability of scattering image files (especially when doing multiple exposures).
        If a new file is available, try to load and process it (using _process_exposure), and resume waiting.
        
        The thread can be stopped in three ways:
        
        1) by setting stopswitch: this by itself does not stop the exposure procedure in Pilatus.
        2) if _process_exposure() returns False.
        3) by an exception
        
        """
        try:
            t0 = time.time()
            for i in range(0, nimages):
                # wait for each exposure. Check for user break inbetween.
                t1 = time.time()
                nextend = t0 + exptime * (i + 1) + dwelltime * i
                wait = nextend - t1
                if wait > 0:
                    logger.debug('Sleeping %f seconds' % wait)
                    is_userbreak = stopswitch.wait(wait)
                else:
                    logger.warning('Exposure lag: %f seconds' % (-wait))
                    is_userbreak = stopswitch.is_set()
                header_template['FSN'] = (firstfsn + i)
                result = self._process_exposure(expname_template % (firstfsn + i), headername_template % (firstfsn + i),
                                                stopswitch, outqueue, header_template, cbf_file_timeout, mask)
                if is_userbreak or not result:
                    # process_exposure() returns False if a userbreak occurs.
                    outqueue.put((ExposureMessageType.End, False))
                    return
        except Exception, exc:
            # catch all exceptions and put an error state in the output queue, then re-raise.
            outqueue.put((ExposureMessageType.Failure, exc.message))
            outqueue.put((ExposureMessageType.End, False))
            raise
        outqueue.put((ExposureMessageType.End, True))
        logger.debug('Returning from work.')
