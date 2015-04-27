# coding: utf-8
import threading
import multiprocessing.queues
import sastool
import datetime
from ..instruments.pilatus import PilatusError
import logging
import os
import time
from ...utils import objwithgui
import nxs
import numpy as np
import scipy
import traceback

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
    __gsignals__ = {'exposure-image': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'exposure-fail': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'exposure-end': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
                    'notify': 'override', }
    exptime = GObject.property(
        type=float, minimum=0, default=1, blurb='Exposure time (sec)')
    dwelltime = GObject.property(
        type=float, minimum=0.003, default=0.003, blurb='Dwell time between exposures (sec)')
    nimages = GObject.property(
        type=int, minimum=1, default=1, blurb='Number of images to take (sec)')
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
        self._thread = None
        for k in kwargs:
            self.set_property(k, kwargs[k])
        self._stopswitch = multiprocessing.Event()
        self._queue = multiprocessing.queues.Queue()
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
                        'Cannot load default mask from file: ' + self.default_mask)
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
        except PilatusError:
            pass
        if stop_processing_results:
            self._stopswitch.set()

    def start(self, header_template=None, mask=None, write_nexus=False):
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
        if mask is not None:
            header_template['maskid'] = mask.maskid
        logger.debug('Header prepared.')
        GLib.idle_add(self._check_if_exposure_finished)
        logger.debug('Starting exposure of %s. Files will be named like: %s' % (
            str(sample), self.credo().subsystems['Files'].get_fileformat() % fsn))
        self._stopswitch.clear()
        pilatus.prepare_exposure(self.exptime, self.nimages, self.dwelltime)
        self._thread = threading.Thread(
            target=self._thread_worker, args=(
                os.path.join(self.credo().subsystems['Files'].imagespath,
                             exposureformat),
                os.path.join(self.credo().subsystems['Files'].parampath,
                             headerformat),
                self._stopswitch, self._queue, self.exptime, self.nimages,
                self.dwelltime, fsn, self.cbf_file_timeout, header_template,
                mask, write_nexus))
        self._thread.daemon = True
        if ((self.operate_shutter and genix.shutter_state() == False) and
                (header_template['Title'] != self.dark_sample_name)):
            genix.shutter_open()
        self._pilatus_idle_handler = pilatus.connect(
            'idle', self._pilatus_idle, genix)
        self.credo().subsystems['Files'].increment_next_fsn()
        pilatus.execute_exposure(exposureformat % fsn)
        self._thread.start()
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
        # In this case the thread is already dead, so we have to kill the
        # pilatus exposure sequence.
        try:
            self.credo().get_equipment('pilatus').stopexposure()
        except PilatusError:
            # exposure already finished.
            pass

    def do_exposure_end(self, endstatus):
        # this is the last signal emitted during an exposure. The _check_if_exposure_finished() idle handler
        # has already deregistered itself.
        logger.debug('Exposure ended.')

    def do_exposure_image(self, ex):
        pass

    def _process_exposure(self, exposurename, headername, stopswitch, queue, headertemplate, cbf_file_timeout, mask, write_nexus):
        # try to load the header from the CBF file.
        logger.debug('process_exposure starting')
        t0 = time.time()
        cbfdata = cbfheader = None
        while (time.time() - t0) < cbf_file_timeout:
            try:
                cbfdata, cbfheader = sastool.io.twodim.readcbf(
                    exposurename, load_header=True, load_data=True)
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
            ex = sastool.classes.SASExposure(
                {'Intensity': cbfdata, 'Error': cbfdata ** 0.5, 'header': sastool.classes.SASHeader(headertemplate), 'mask': mask})
        else:
            ex = sastool.classes.SASExposure(
                {'Intensity': cbfdata, 'Error': cbfdata ** 0.5, 'header': sastool.classes.SASHeader(headertemplate), 'mask': mask})

        # do some fine adjustments on the header template:
        # a) include the CBF header written by camserver.
        logger.debug('updating header')
        ex.header.update(cbfheader)
        # b) get instrument states
        logger.debug('Getting equipment status')
        ex.header.update(
            self.credo().subsystems['Equipments'].get_current_parameters())
        # c) readout virtual detectors
        if not self.timecriticalmode:
            logger.debug('Reading out virtual detectors')
            vdresults = self.credo().subsystems['VirtualDetectors'].readout_all(
                ex, self.credo().get_equipment('genix'))
            ex.header.update(
                {('VirtDet_' + k): vdresults[k] for k in vdresults})
        # d) set the end date to the current time.
        ex.header['EndDate'] = datetime.datetime.now()
        # and save the header to the parampath.
        logger.debug('Writing header')
        ex.header.write(headername)
        logger.debug('Header %s written.' % (headername))
        if write_nexus:
            nexusname = os.path.join(self.credo().subsystems[
                                     'Files'].nexuspath, os.path.splitext(os.path.split(exposurename)[1])[0] + '.nx5')
            self.write_nexus(nexusname, cbfdata, ex.header, mask)
        queue.put((ExposureMessageType.Image, ex))
        logger.debug('Process_exposure took %f seconds.' % (time.time() - t0))
        del ex
        return True

    def update_nexustree(self, nexustree, data, header, mask):
        pass

    def write_nexus(self, nexusname, data, header, mask):
        root = nxs.NXroot()
        root.entry = nxs.NXentry()
        root.entry.start_time = header['StartDate'].isoformat()
        root.entry.end_time = header['EndDate'].isoformat()
        root.entry.experiment_identifier = header['Project']
        root.entry.definition = 'NXsas'
        root.entry.definition.attrs['version'] = '1.0b'
        root.entry.definition.attrs[
            'URL'] = 'http://svn.nexusformat.org/definitions/trunk/applications/NXsas.nxdl.xml'
        root.entry.duration = (
            header['EndDate'] - header['StartDate']).total_seconds()
        root.entry.duration.attrs['units'] = 's'
        root.entry.program_name = 'SAXSCtrl'
        root.entry.program_name.attrs['version'] = 0  # TODO
        root.entry.revision = 'raw'
        root.entry.title = header['Title']
        # root.entry.pre_sample_flightpath=None # TODO: make this a link to the
        # appropriate place in root.entry.instrument
        root.entry.user = nxs.NXuser()
        root.entry.user.name = header['Owner']
        root.entry.user.role = 'operator'
        # TODO: user management.
        root.entry.control = nxs.NXmonitor()
        root.entry.control.mode = 'timer'
        root.entry.control.start_time = header['StartDate'].isoformat()
        root.entry.control.end_time = header['EndDate'].isoformat()
        root.entry.control.preset = header['MeasTime']
        root.entry.control.distance = np.nan
        root.entry.control.integral = header['MeasTime']
        root.entry.control.data = header['MeasTime']
        root.entry.control.count_time = header['MeasTime']
        root.entry.instrument = nxs.NXinstrument()
        root.entry.instrument.name = 'Creative Research Equipment for DiffractiOn'
        root.entry.instrument.name.attrs['short_name'] = 'CREDO'
        root.entry.instrument.source = nxs.NXsource()
        root.entry.instrument.source.current = header['GeniX_Current']
        root.entry.instrument.source.current.attrs['units'] = 'A'
        # root.entry.instrument.source.distance=None #TODO: better collimation
        # description.
        root.entry.instrument.source.name = 'GeniX3D Cu ULD'
        root.entry.instrument.source.name.attrs['short_name'] = 'GeniX'
        root.entry.instrument.source.type = 'Fixed Tube X-ray'
        root.entry.instrument.source.probe = 'x-ray'
        root.entry.instrument.source.power = header[
            'GeniX_HT'] * header['GeniX_Current']
        root.entry.instrument.source.power.attrs['units'] = 'W'
        root.entry.instrument.source.energy = header['GeniX_HT']
        root.entry.instrument.source.energy.attrs['units'] = 'eV'
        root.entry.instrument.source.voltage = header['GeniX_HT']
        root.entry.instrument.source.voltage.attrs['units'] = 'V'
        root.entry.instrument.positioners = nxs.NXcollection()
        positioners = {}
        for mot in self.credo().subsystems['Motors']:
            positioners[mot] = mot.to_NeXus()
            root.entry.instrument.positioners[mot.name] = positioners[mot]
        root.entry.instrument.monochromator = nxs.NXmonochromator()
        root.entry.instrument.monochromator.wavelength = header['Wavelength']
        root.entry.instrument.monochromator.wavelength.attrs[
            'units'] = 'Angstrom'
        # The FOX3D optics used in GeniX has a spectral purity of 97%.
        root.entry.instrument.monochromator.wavelength_spread = root.entry.instrument.monochromator.wavelength * \
            0.015
        root.entry.instrument.monochromator.wavelength_spread.attrs[
            'units'] = 'Angstrom'
        root.entry.instrument.monochromator.energy = scipy.constants.codata.value(
            'Planck constant in eV s') * scipy.constants.codata.value('speed of light in vacuum') * 1e10 / header['Wavelength']
        root.entry.instrument.monochromator.energy.attrs['units'] = 'eV'
        root.entry.instrument.monochromator.energy_spread = root.entry.instrument.monochromator.energy * \
            0.015
        root.entry.instrument.monochromator.energy_spread.attrs['units'] = 'eV'
        # TODO: better description of the collimator
        root.entry.instrument.collimator = nxs.NXcollimator()
        # TODO: better description of the geometry
        root.entry.instrument.beam_stop = nxs.NXbeam_stop()
        root.entry.instrument.vacuum = nxs.NXsensor()
        vg = self.credo().subsystems['Equipments'].get('vacgauge')
        if vg.connected():
            try:
                root.entry.instrument.vacuum.model = vg.get_version()
            except Exception as ex:
                logger.warn(
                    'Cannot get version of the vacuum gauge (error: %s).' % str(ex))
            root.entry.instrument.vacuum.name = 'TPG-201 Handheld Pirani Gauge'
            root.entry.instrument.vacuum.short_name = 'Vacuum Gauge'
            root.entry.instrument.vacuum.measurement = 'pressure'
            root.entry.instrument.vacuum.type = 'Pirani'
            try:
                root.entry.instrument.vacuum.value = vg.pressure
            except Exception as ex:
                logger.warn(
                    'Cannot get pressure from the vacuum gauge (error: %s).' % str(ex))
            root.entry.instrument.vacuum.value.attrs['units'] = 'mbar'
        root.entry.instrument.thermostat = nxs.NXsensor()
        ts = self.credo().subsystems['Equipments'].get('haakephoenix')
        if ts.connected():
            try:
                root.entry.instrument.thermostat.model = ts.get_version()
            except Exception as ex:
                logger.warn(
                    'Cannot get version of the thermostat (error: %s).' % str(ex))
            root.entry.instrument.thermostat.name = 'Haake Phoenix Circulator'
            root.entry.instrument.thermostat.short_name = 'haakephoenix'
            root.entry.instrument.thermostat.measurement = 'temperature'
            root.entry.instrument.thermostat.type = 'Pt100'
            try:
                root.entry.instrument.thermostat.value = ts.temperature
                root.entry.instrument.thermostat.value.attrs['units'] = '°C'
            except Exception as ex:
                logger.warn(
                    'Cannot get temperature of the thermostat (error: %s).' % str(ex))
        root.entry.sample = nxs.NXsample()
        root.entry.sample.name = header['Title']
        if 'Temperature' in header:
            root.entry.sample.temperature = header['Temperature']
        else:
            root.entry.sample.temperature = np.nan
        root.entry.sample.temperature.attrs['units'] = '°C'
        root.entry.sample.preparation_date = header['Preparetime'].isoformat()
        root.entry.sample.thickness = header['Thickness']
        root.entry.sample.thickness.attrs['units'] = 'cm'
        root.entry.sample.transmission = float(header['Transm'])
        root.entry.sample.geometry = nxs.NXgeometry()
        root.entry.sample.geometry.description = 'Sample position'
        root.entry.sample.geometry.component_index = 0
        root.entry.sample.geometry.translation = nxs.NXtranslation()
        root.entry.sample.geometry.translation.distances = np.array(
            [header['PosSampleX'], header['PosSample'], header['DistMinus']])
        root.entry.sample.positioners = nxs.NXcollection()
        root.entry.sample.positioners.makelink(
            positioners[self.credo().subsystems['Samples'].get_xmotor()])
        root.entry.sample.positioners.makelink(
            positioners[self.credo().subsystems['Samples'].get_ymotor()])

        det = nxs.NXdetector()
        root.entry.instrument.insert(det)
        det.description = header['Detector']
        det.type = 'pixel'
        det.layout = 'area'
        det.aequatorial_angle = 0
        det.azimuthal_angle = 0
        det.polar_angle = 0
        det.rotation_angle = 0
        det.beam_center_x = header['BeamPosX'] * header['XPixel']
        det.beam_center_y = header['BeamPosY'] * header['YPixel']
        det.distance = header['Dist']
        det.count_time = header['Exposure_time']
        det.count_time.attrs['units'] = 's'
        det.saturation_value = header['Count_cutoff']
        det.saturation_value.attrs['units'] = 'count'
        det.sensor_material = 'Si'
        det.sensor_thickness = header['Silicon sensor, thickness']
        det.sensor_thickness.attrs['units'] = 'micron'
        if header['Threshold_setting'] == 'not set':
            det.threshold_energy = np.nan
        else:
            det.threshold_energy = header['Threshold_setting']
        det.threshold_energy.attrs['units'] = 'eV'
        det.gain_setting = header['Gain_setting']
        det.frame_time = header['Exposure_period']
        det.bit_depth_readout = 20
        det.angular_calibration_applied = 0
        det.acquisition_mode = 'summed'
        det.dead_time = header['Tau']
        det.dead_time.attrs['units'] = 's'
        det.x_pixel_size = header['XPixel']
        det.x_pixel_size.attrs['units'] = 'micron'
        det.y_pixel_size = header['YPixel']
        det.y_pixel_size.attrs['units'] = 'micron'
        det.data = np.require(data, requirements='C')
        det.data.attrs['signal'] = 1
        det.data.attrs['long_name'] = 'Counts'
        det.data.attrs['axes'] = 'x:y'
        det.data.attrs['units'] = 'count'
        det.data.attrs['calibration_status'] = 'Measured'
        det.data.attrs['interpretation'] = 'image'
        det.x = np.arange(data.shape[0])
        det.y = np.arange(data.shape[1])
        det.detector_readout_time = 2.3
        det.detector_readout_time.attrs['units'] = 'ms'
        if header['Excluded_pixels'] == '(nil)':
            det.pixel_mask_applied = 0
        else:
            det.pixel_mask_applied = 1
        det.pixel_mask = (mask == 0) << 6
        if header['Tau'] == 0:
            det.countrate_correction_applied = 0
        else:
            det.countrate_correction_applied = 1
        if header['Flat_field'] == '(nil)':
            det.flatfield_applied = 0
        else:
            det.flatfield_applied = 1
        nxdata = nxs.NXdata()
        root.entry.insert(nxdata)
        nxdata.makelink(root.entry.instrument.detector.data)
        nxdata.makelink(root.entry.instrument.detector.x)
        nxdata.makelink(root.entry.instrument.detector.y)
        nt = nxs.NeXusTree(nexusname, 'w5')
        try:
            nt.writefile(root)
        except ValueError as ve:
            logger.error(
                'Error writing nexus file: %s. Error is: %s' % (nexusname, str(ve)))

    def _thread_worker(self, expname_template, headername_template, stopswitch, outqueue, exptime, nimages, dwelltime, firstfsn, cbf_file_timeout, header_template, mask, write_nexus):
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
                                                stopswitch, outqueue, header_template, cbf_file_timeout, mask, write_nexus)
                if is_userbreak or not result:
                    # process_exposure() returns False if a userbreak occurs.
                    outqueue.put((ExposureMessageType.End, False))
                    return
                header_template[
                    'StartDate'] += datetime.timedelta(seconds=exptime + dwelltime)
        except Exception, exc:
            # catch all exceptions and put an error state in the output queue,
            # then re-raise.
            outqueue.put((ExposureMessageType.Failure, traceback.format_exc()))
            outqueue.put((ExposureMessageType.End, False))
            raise
        outqueue.put((ExposureMessageType.End, True))
        logger.debug('Returning from work.')
