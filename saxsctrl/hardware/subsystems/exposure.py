# coding: utf-8
import multiprocessing
import queue
import sastool
import datetime
import dateutil.tz
import dateutil.parser
from ..instruments.pilatus import PilatusError
import logging
import os
import time
from ...utils import objwithgui
import h5py
import numpy as np
import scipy
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from gi.repository import GObject
from gi.repository import GLib
from .subsystem import SubSystem, SubSystemError

__all__ = ['SubSystemExposure']


class SubSystemExposureError(SubSystemError):
    pass


class StopSwitchException(Exception):
    pass


class ExposureMessageType(object):
    End = 'end'
    Failure = 'failure'
    Image = 'image'


class SubSystemExposure(SubSystem):
    __gsignals__ = {'exposure-image': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-fail': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'exposure-end': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'notify': 'override', }
    exptime = GObject.property(
        type=float, minimum=0, default=1, blurb='Exposure time (sec)')
    dwelltime = GObject.property(
        type=float, minimum=0.003, default=0.003, blurb='Dwell time between exposures (sec)')
    nimages = GObject.property(
        type=int, minimum=1, default=1, blurb='Number of images to take (sec)', maximum=20)
    operate_shutter = GObject.property(
        type=bool, default=True, blurb='Open/close shutter')
    cbf_file_timeout = GObject.property(
        type=float, default=3, blurb='Timeout for cbf files')
    timecriticalmode = GObject.property(
        type=bool, default=False, blurb='Time-critical mode')
    default_mask = GObject.property(
        type=str, default='mask.mat', blurb='Default mask file')
    dark_sample_name = GObject.property(
        type=str, default='Dark', blurb='Sample name for dark measurement')

    def __init__(self, credo, offline=True, **kwargs):
        SubSystem.__init__(self, credo, offline)
        self._OWG_nogui_props.append('configfile')
        self._OWG_hints[
            'default-mask'] = {objwithgui.OWG_Hint_Type.OrderPriority: None}
        self._OWG_entrytypes['default-mask'] = objwithgui.OWG_Param_Type.File
        for k in kwargs:
            self.set_property(k, kwargs[k])
        self._stopswitch = multiprocessing.Event()
        self._queue = multiprocessing.Queue()
        self._default_mask = None

    def do_notify(self, param):
        if param.name == 'default-mask':
            if not os.path.isabs(self.default_mask):
                self.default_mask = os.path.join(
                    self.credo().subsystems['Files'].maskpath, self.default_mask)
            else:
                try:
                    self._default_mask = sastool.classes.SASMask(
                        self.default_mask)
                except IOError:
                    logger.error(
                        'Cannot load default mask from file: ' + self.default_mask + ' (' + traceback.format_exc() + ')')
                else:
                    logger.debug(
                        'Loaded default mask from file: ' + self.default_mask)
        else:
            logger.debug('Other parameter modified: ' + param.name)

    def get_mask(self):
        return self._default_mask

    def kill(self, stop_processing_results=True):
        try:
            self.credo().get_equipment('pilatus').stopexposure()
        except PilatusError as pe:
            logger.warning(
                'PilatusError while killing exposure: ' + traceback.format_exc())
        if stop_processing_results:
            self._stopswitch.set()

    def _kill_subprocesses(self):
        try:
            self._stopswitch.set()
            for s in self._subprocesses:
                s.join()
                self._subprocesses.remove(s)
            del self._subprocesses
        except AttributeError as ae:
            pass

    def start(self, header_template=None, mask=None, write_nexus=False):
        logger.debug('Exposure subsystem: starting exposure.')
        pilatus = self.credo().get_equipment('pilatus')
        genix = self.credo().get_equipment('genix')
        sample = self.credo().subsystems['Samples'].get()
        if not pilatus.is_idle():
            raise SubSystemExposureError('Detector is busy.')
        self._kill_subprocesses()
        if mask is None:
            mask = self._default_mask
        fsn = self.credo().subsystems['Files'].get_next_fsn()
        if header_template is None:
            header_template = {}
        else:
            header_template = header_template.copy()
        if sample is not None:
            header_template.update(sample.get_header())
        else:
            header_template.update({'Title': 'None'})
        header_template['__Origin__'] = 'CREDO'
        header_template['__particle__'] = 'photon'
        dist = sastool.ErrorValue(self.credo().dist, self.credo().dist_error)
        if sample is not None:
            dist = dist - sample.distminus
        header_template['Dist'] = dist.val
        header_template['DistError'] = dist.err
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
        header_template['SetupDescription'] = self.credo().setup_description
        header_template['Monitor'] = header_template['MeasTime']
        header_template['MonitorError'] = 0
        header_template['StartDate'] = datetime.datetime.now()
        header_template.update(
            self.credo().subsystems['Equipments'].get_current_parameters())
        if mask is not None:
            header_template['maskid'] = mask.maskid
        logger.debug('Header prepared.')
        GLib.idle_add(self._check_if_exposure_finished)
        logger.debug('Starting exposure of %s. Files will be named like: %s' % (
            str(sample), self.credo().subsystems['Files'].get_fileformat() % fsn))
        self._stopswitch.clear()
        pilatus.prepare_exposure(self.exptime, self.nimages, self.dwelltime)
        self._subprocesses = []
        for idx in range(self.nimages):
            if write_nexus:
                self.credo().subsystems[
                    'Files'].create_nexus_template(fsn + idx)
                logger.debug(
                    'Created NeXus template file for FSN #%d' % (fsn + idx))
            self._subprocesses.append(multiprocessing.Process(
                target=self._thread_worker, args=(
                    self.credo().subsystems['Files'].imagespath,
                    self.credo().subsystems['Files'].parampath,
                    self.credo().subsystems['Files'].nexuspath,
                    self.credo().subsystems['Files'].filebegin,
                    self.credo().subsystems['Files'].ndigits,
                    self._stopswitch, self._queue, self.exptime +
                    (self.exptime + self.dwelltime) * idx, fsn + idx,
                    self.cbf_file_timeout, header_template.copy(
                    ), mask.mask, write_nexus,
                    idx == self.nimages - 1)))
            self._subprocesses[-1].daemon = True
        if ((self.operate_shutter and genix.shutter_state() == False) and
                (header_template['Title'] != self.dark_sample_name)):
            genix.shutter_open()
        self._pilatus_idle_handler = pilatus.connect(
            'idle', self._pilatus_idle, genix)
        self.credo().subsystems['Files'].increment_next_fsn()
        pilatus.execute_exposure(
            self.credo().subsystems['Files'].get_exposureformat() % fsn)
        for s in self._subprocesses:
            s.start()
        return fsn

    def _pilatus_idle(self, pilatus, genix):
        # we get this signal when the exposure is finished.
        pilatus.disconnect(self._pilatus_idle_handler)
        del self._pilatus_idle_handler
        if self.operate_shutter:
            genix.shutter_close()

    def _check_if_exposure_finished(self):
        try:
            id, data = self._queue.get_nowait()
        except queue.Empty:
            return True
        if id == ExposureMessageType.Failure:
            self.emit('exposure-fail', data)
            return True
        elif id == ExposureMessageType.End:
            self.emit('exposure-end', data)
            return False
        elif id == ExposureMessageType.Image:
            ex = sastool.SASExposure(self.credo().subsystems['Files'].get_exposureformat(
            ) % data, dirs=self.credo().subsystems['Files'].rawloadpath)
            self.emit('exposure-image', ex)
            del ex
            return True
        else:
            raise NotImplementedError('Invalid exposure message type')

    def do_exposure_fail(self, message):
        # this signal is emitted whenever the cbf file collector thread encounters a serious error.
        # In this case the thread is already dead, so we have to kill the
        # pilatus exposure sequence.
        try:
            self.credo().get_equipment('pilatus').stopexposure()
        except PilatusError as pe:
            # exposure already finished.
            logger.warn(
                'PilatusError in do_exposure_fail:' + traceback.format_exc())

    def do_exposure_end(self, endstatus):
        # this is the last signal emitted during an exposure. The _check_if_exposure_finished() idle handler
        # has already deregistered itself.
        logger.debug('Exposure ended.')
        self._kill_subprocesses()

    def do_exposure_image(self, fsn):
        pass

    def update_nexusfile(self, nexusfile, data, header, waittime):
        with h5py.File(nexusfile, 'r+') as f:
            starttime = dateutil.parser.parse(
                f['entry/monitor/start_time'].value)
            f['entry/monitor/start_time'][()] = (starttime + datetime.timedelta(
                waittime - f['entry/monitor/count_time'].value)).isoformat().encode('utf-8')
            f['entry/monitor/end_time'] = datetime.datetime.now(
                dateutil.tz.tzlocal()).isoformat().encode('utf-8')
            f['entry/end_time'] = f['entry/monitor/end_time']
            f['entry/duration'] = (dateutil.parser.parse(f['entry/end_time'].value) -
                                   dateutil.parser.parse(f['entry/start_time'].value)).total_seconds()
            f['entry/duration'].attrs['units'] = 's'
            f['entry/instrument/detector'].create_dataset(
                'data', data=data, compression='gzip')
            f['entry/instrument/detector']['data'].attrs['signal'] = 1
            f['entry/instrument/detector']['data'].attrs[
                'axes'] = 'x_pixel_offset:y_pixel_offset'
            f['entry/instrument/detector']['data'].attrs['units'] = 'counts'
            f['entry/instrument/detector']['data'].attrs['long_name'] = 'Detector counts'
            f['entry/instrument/detector']['data'].attrs['check_sum'] = data.sum()
            err = data.copy()
            idx = err > 0
            err[idx] = err[idx]**0.5
            err[-idx] = np.nan
            f['entry/instrument/detector'].create_dataset(
                'data_error', data=err, compression='gzip')
            f['entry/instrument/detector']['data_error'].attrs['units'] = 'counts'
            f['entry/instrument/detector']['data'].attrs[
                'long_name'] = 'Standard deviation of detector counts'
            f['entry/instrument/detector']['data'].attrs[
                'check_sum'] = np.nansum(err)
            f['entry/instrument/detector'].create_dataset(
                'x_pixel_offset', data=np.arange(data.shape[1]))
            f['entry/instrument/detector/x_pixel_offset'].attrs['primary'] = 1
            f['entry/instrument/detector/x_pixel_offset'].attrs[
                'long_name'] = 'Horizontal pixel coordinate (column index)'
            f['entry/instrument/detector'].create_dataset(
                'y_pixel_offset', data=np.arange(data.shape[0]))
            f['entry/instrument/detector/y_pixel_offset'].attrs['primary'] = 1
            f['entry/instrument/detector/y_pixel_offset'].attrs[
                'long_name'] = 'Vertical pixel coordinate (row index)'
            f['entry/data/data'] = f['entry/instrument/detector/data']
            f['entry/data/errors'] = f['entry/instrument/detector/data_error']
            f['entry/data/x_pixel_offset'] = f['entry/instrument/detector/x_pixel_offset']
            f['entry/data/y_pixel_offset'] = f['entry/instrument/detector/y_pixel_offset']

    def _thread_worker(self, imagespath, parampath, nexuspath, filebegin, ndigits, stopswitch, outqueue, waittime, fsn, cbf_file_timeout, header_template, maskmatrix, write_nexus, this_is_the_last=False):
        """Wait for the availability of scattering image files (especially when doing multiple exposures).
        If a new file is available, try to load and process it (using _process_exposure), and resume waiting.

        The thread can be stopped in three ways:

        1) by setting stopswitch: this by itself does not stop the exposure procedure in Pilatus.
        2) if _process_exposure() returns False.
        3) by an exception

        """
        cbfdata = cbfheader = None
        try:
            logger.debug(
                'Exposure subprocess for FSN #%d started, waiting for %.2f seconds' % (fsn, waittime))
            is_userbreak = stopswitch.wait(waittime)
            header_template['FSN'] = fsn
            if is_userbreak:
                raise StopSwitchException

            t0 = time.time()
            os.stat(imagespath)  # a work-around for NFS
            while (time.time() - t0) < cbf_file_timeout:
                try:
                    cbfdata, cbfheader = sastool.io.twodim.readcbf(os.path.join(imagespath,
                                                                                self.credo().subsystems['Files'].get_exposureformat() % fsn), load_header=True, load_data=True, for_nexus=True)
                    break
                except IOError:
                    logger.debug('Waiting for image...')
                    if stopswitch.wait(0.01):
                        # break signaled.
                        raise StopSwitchException
                # continue with the next try.
            if cbfdata is None:
                # timeout.
                raise SubSystemExposureError(
                    'Timeout on waiting for CBF file.')
            # create the exposure object
            logger.debug('Creating exposure')
            header = sastool.classes.SASHeader(header_template)
            # do some fine adjustments on the header template:
            # a) include the CBF header written by camserver.
            logger.debug('updating header')
            header.update(cbfheader)
            # d) set the end date to the current time.
            header['EndDate'] = datetime.datetime.now()
            # and save the header to the parampath.
            logger.debug('Writing header')
            headername = os.path.join(parampath, self.credo().subsystems[
                                      'Files'].get_headerformat(filebegin, ndigits) % fsn)
            header.write(headername)
            logger.debug('Header %s written.' % (headername))
            if write_nexus:
                nexusname = os.path.join(nexuspath, self.credo().subsystems[
                                         'Files'].get_nexusformat(filebegin, ndigits) % fsn)
                self.update_nexusfile(
                    nexusname, cbfdata, header, waittime=waittime)
            outqueue.put((ExposureMessageType.Image, fsn))
            logger.debug('Process_exposure took %f seconds.' %
                         (time.time() - t0))
            del cbfdata
        except StopSwitchException:
            # an user break occurred
            outqueue.put((ExposureMessageType.End, False))
            return

        except Exception as exc:
            # catch all exceptions and put an error state in the output queue,
            # then re-raise.
            outqueue.put((ExposureMessageType.Failure, traceback.format_exc()))
            outqueue.put((ExposureMessageType.End, False))
            raise
        else:
            if this_is_the_last:
                outqueue.put((ExposureMessageType.End, True))
        finally:
            del cbfdata
        logger.debug('Exposure subprocess for FSN #%d ended.')
