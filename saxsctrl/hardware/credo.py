
import logging
import scipy
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
import os
import nxs
import datetime
import numpy as np
import gc
from gi.repository import GObject
import ConfigParser
import pkg_resources
import dateutil

from . import subsystems
from ..utils import objwithgui


RCFILE = os.path.expanduser('config/credorc')


class CredoError(Exception):
    pass


class Credo(objwithgui.ObjWithGUI):
    __gsignals__ = {'setup-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    'shutter': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'equipment-connection': (GObject.SignalFlags.RUN_FIRST,
                                             None, (str, bool, object)),
                    'scan-fail': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'transmission-report': (GObject.SignalFlags.RUN_FIRST,
                                            None, (object, object, object)),
                    'transmission-end': (GObject.SignalFlags.RUN_FIRST, None,
                                         (object, object, object, object,
                                          bool)),
                    'idle': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    }
    # offline mode. In this mode settings files cannot be written and
    # connections to instruments cannot be made.
    offline = GObject.property(type=bool, default=False, blurb='Offline mode')

    # Accounting properties
    username = GObject.property(
        type=str, default='Anonymous', blurb='User name')
    projectname = GObject.property(
        type=str, default='No project', blurb='Project name')

    # Instrument parameters
    pixelsize = GObject.property(
        type=float, default=172, minimum=0,
        blurb=u'Pixel size (μm)'.encode('utf-8'))
    dist = GObject.property(
        type=float, default=1000, minimum=0,
        blurb='Sample-detector distance (mm)')
    filter = GObject.property(type=str, default='No filter', blurb='Filters')
    beamposx = GObject.property(
        type=float, default=348.38, blurb='Beam position X (vertical, pixels)')
    beamposy = GObject.property(
        type=float, default=242.47, blurb='Beam position Y (horizontal, pixels')
    wavelength = GObject.property(
        type=float, default=0.154182, minimum=0, blurb='X-ray wavelength (nm)')
    # Inhibiting parameters
    shuttercontrol = GObject.property(
        type=bool, default=True, blurb='Open/close shutter')
    motorcontrol = GObject.property(
        type=bool, default=True, blurb='Move motors')

    # changing any of the properties in this list will trigger a setup-changed
    # event.
    setup_properties = [
        'username', 'projectname', 'pixelsize', 'dist', 'filter',
        'beamposx', 'beamposy', 'wavelength', 'shuttercontrol',
        'motorcontrol', 'scanfile', 'scandevice', 'virtdetcfgfile',
                        'imagepath', 'filepath']

    # changing any of the properties in this list will trigger a path-changed
    # event.
    path_properties = ['filepath', 'imagepath']

    def __init__(self, offline=True, createdirsifnotpresent=False):
        objwithgui.ObjWithGUI.__init__(self)
        self._OWG_nogui_props.append('offline')
        self._OWG_nosave_props.append('offline')
        self.offline = offline
        self._OWG_hints['username'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 0}
        self._OWG_hints['projectname'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 0}
        self._OWG_hints['beamposx'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 1,
            objwithgui.OWG_Hint_Type.Digits: 3}
        self._OWG_hints['beamposy'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 2,
            objwithgui.OWG_Hint_Type.Digits: 3}
        self._OWG_hints['dist'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 3,
            objwithgui.OWG_Hint_Type.Digits: 3}
        self._OWG_hints['pixelsize'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 4}
        self._OWG_hints['wavelength'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 5,
            objwithgui.OWG_Hint_Type.Digits: 4}
        self._OWG_hints['default-mask'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 5,
            objwithgui.OWG_Hint_Type.Digits: 5}
        self._OWG_entrytypes['default-mask'] = objwithgui.OWG_Param_Type.File
        self._OWG_hints['shuttercontrol'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 6}
        self._OWG_hints['motorcontrol'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 6}
        self._OWG_hints['bs-in'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 7,
            objwithgui.OWG_Hint_Type.Digits: 3}
        self._OWG_hints['bs-out'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 8,
            objwithgui.OWG_Hint_Type.Digits: 3}
        # initialize subsystems
        logger.debug('Initializing subsystems of Credo')
        self.subsystems = {}
        self.subsystems['Files'] = subsystems.SubSystemFiles(
            self, offline=self.offline, createdirsifnotpresent=createdirsifnotpresent)
        self.subsystems['Samples'] = subsystems.SubSystemSamples(
            self, offline=self.offline)
        self.subsystems['Equipments'] = subsystems.SubSystemEquipments(
            self, offline=self.offline)
        self.subsystems['Motors'] = subsystems.SubSystemMotors(
            self, offline=self.offline)
        self.subsystems['VirtualDetectors'] = subsystems.SubSystemVirtualDetectors(
            self, offline=self.offline)
        self.subsystems['Exposure'] = subsystems.SubSystemExposure(
            self, offline=self.offline)
        self.subsystems['Scan'] = subsystems.SubSystemScan(
            self, offline=self.offline)
        self.subsystems['Imaging'] = subsystems.SubSystemImaging(
            self, offline=self.offline)
        self.subsystems['Transmission'] = subsystems.SubSystemTransmission(
            self, offline=self.offline)
        self.subsystems['DataReduction'] = subsystems.SubSystemDataReduction(
            self, offline=self.offline)
        logger.debug('All Credo subsystems initialized.')
        self._OWG_parts = self.subsystems.values()

        # load state: this will load the state information of all the
        # subsystems as well.
        self.loadstate()
        if not self.offline:
            try:
                self.subsystems['Equipments'].connect_to_all()
            except subsystems.SubSystemError as err:
                logger.warning(str(err))

    def _get_classname(self):
        return 'CREDO'

    def get_equipment(self, equipment):
        return self.subsystems['Equipments'].get(equipment)

    def loadstate(self, configparser=None, sectionprefix=''):
        logger.debug('Loading Credo state...')
        if configparser is None:
            configparser = ConfigParser.ConfigParser()
            configparser.read(RCFILE)
        objwithgui.ObjWithGUI.loadstate(self, configparser, sectionprefix)
#         for ss in self.subsystems.values():
#             ss.loadstate(cp)
        logger.debug('Credo state loaded.')
        del configparser

    def savestate(self):
        if self.offline:
            logger.warning(
                'Not saving settings, since we are in off-line mode.')
            return
        cp = ConfigParser.ConfigParser()
        cp.read(RCFILE)
        objwithgui.ObjWithGUI.savestate(self, cp)
#         for ss in self.subsystems.values():
#             ss.savestate(cp)
        if not os.path.exists(os.path.split(RCFILE)[0]):
            os.makedirs(os.path.split(RCFILE)[0])
        with open(RCFILE, 'wt') as f:
            cp.write(f)
            logger.info('Saved settings to %s.' % RCFILE)
        del cp

    def expose(self, exptime, nimages=1, dwelltime=0.003, mask=None,
               header_template=None, filebegin=None, write_nexus=True):
        if filebegin is not None and (self.subsystems['Files'].filebegin != filebegin):
            self.subsystems['Files'].filebegin = filebegin
        self.subsystems['Exposure'].exptime = exptime
        self.subsystems['Exposure'].nimages = nimages
        self.subsystems['Exposure'].dwelltime = dwelltime
        return self.subsystems['Exposure'].start(header_template, mask,
                                                 write_nexus=write_nexus)

    def trim_detector(self, threshold=4024, gain=None, blocking=False):
        if gain is None:
            gain = self.pilatus.getthreshold()['gain']
        self.pilatus.setthreshold(threshold, gain, blocking)

    def __del__(self):
        self.savestate()
        for ss in self.subsystems.keys():
            self.subsystems[ss].destroy()
            del self.subsystems[ss]
        gc.collect()

    def update_nexustree(self, root, data, header):
        root.entry.end_time = datetime.datetime.now().isoformat()
        root.entry.duration = (dateutil.parser.parse(root.entry.end_time)
                               - dateutil.parser.parse(root.entry.start_time)).total_seconds()
        root.entry.control.end_time = root.entry.end_time
        if header['Flat_field'] == '(nil)':
            det.flatfield_applied = 0
        else:
            det.flatfield_applied = 1
        if root.entry.title.startswith('scan'):
            pass
        elif root.entry.title.startswith('imaging'):
            pass
        else:
            pass

    def prepare_nexustree(self, mask, number, sample_or_title, exposuretype='single'):
        """To be called just before an exposure or a scan. This initializes what it can,
        and leaves the other things to complete at the end of the measurement, when the cbf file is loaded
        etc.

        Inputs:
        -------
            mask: the mask matrix (1 is non-masked, 0 is masked)
            number: the index number, depending on the exposure type. It is the FSN for a single exposure
                or a scan or imaging run number for scan or imaging.
            sample_or_title: either an instance of saxsctrl.hardware.sample.Sample or a string.
            exposuretype: 'single', 'scan' or 'imaging' (2D scan)

        """
        nulldate = datetime.datetime.fromtimestamp(0).isoformat()
        nowdate = datetime.datetime.now().isoformat()
        root = nxs.NXroot()
        root.entry = nxs.NXentry()
        root.entry.start_time = nowdate
        root.entry.end_time = nulldate  # TO UPDATE
        root.entry.experiment_identifier = self.projectname
        if exposuretype == 'scan':
            root.entry.definition = 'NXscan'
            root.entry.definition.attrs['version'] = '1.0b'
            root.entry.definition.attrs[
                'URL'] = 'http://svn.nexusformat.org/definitions/trunk/applications/NXscan.nxdl.xml'
            root.entry.title = 'scan%d' % number
        elif exposuretype == 'imaging':
            root.entry.definition = 'NXscan'
            root.entry.definition.attrs['version'] = '1.0b'
            root.entry.definition.attrs[
                'URL'] = 'http://svn.nexusformat.org/definitions/trunk/applications/NXscan.nxdl.xml'
            root.entry.title = 'imaging%d' % number
        elif exposuretype == 'single':
            root.entry.definition = 'NXsas'
            root.entry.definition.attrs['version'] = '1.0b'
            root.entry.definition.attrs[
                'URL'] = 'http://svn.nexusformat.org/definitions/trunk/applications/NXsas.nxdl.xml'
            root.entry.title = self.subsystems[
                'Files'].filebegin + '_%d' % number
        root.entry_identifier = str(number)
        root.entry.duration = 0  # TO UPDATE
        root.entry.duration.attrs['units'] = 's'
        root.entry.program_name = 'SAXSCtrl'
        root.entry.program_name.attrs[
            'version'] = pkg_resources.get_distribution('saxsctrl').version
        root.entry.revision = 'raw'
        # root.entry.pre_sample_flightpath=None # TODO: make this a link to the
        # appropriate place in root.entry.instrument
        root.entry.user = nxs.NXuser()
        root.entry.user.name = self.username
        root.entry.user.role = 'operator'
        # TODO: user management.
        root.entry.control = nxs.NXmonitor()
        root.entry.control.mode = 'timer'

        root.entry.control.start_time = nowdate
        root.entry.control.end_time = nulldate  # TO UPDATE
        root.entry.control.distance = np.nan
        if exposuretype == 'scan':
            root.entry.control.data = nxs.NXfield(
                dtype='float32', shape=(nxs.UNLIMITED,))
            root.entry.control.count_time = nxs.NXfield(
                dtype='float32', shape=(nxs.UNLIMITED,))
        elif exposuretype == 'imaging':
            ssi = self.subsystems['Imaging']
            root.entry.control.data = nxs.NXfield(
                dtype='float32', shape=(ssi.nstep1, ssi.nstep2))
            root.entry.control.count_time = nxs.NXfield(
                dtype='float32', shape=(ssi.nstep1, ssi.nstep2))
        elif exposuretype == 'single':
            root.entry.control.data = 0  # TO UPDATE
            root.entry.control.count_time = 0  # TO UPDATE
        root.entry.instrument = nxs.NXinstrument()
        root.entry.instrument.name = 'Creative Research Equipment for DiffractiOn'
        root.entry.instrument.name.attrs['short_name'] = 'CREDO'
        root.entry.instrument.source = nxs.NXsource()
        root.entry.instrument.source.name = 'GeniX3D Cu ULD'
        root.entry.instrument.source.name.attrs['short_name'] = 'GeniX'
        root.entry.instrument.source.type = 'Fixed Tube X-ray'
        root.entry.instrument.source.probe = 'x-ray'
        genix = self.subsystems['Equipments'].get('genix')
        root.entry.instrument.source.current = genix.current
        root.entry.instrument.source.current.attrs['units'] = 'A'
        # root.entry.instrument.source.distance=None #TODO: better collimation
        # description.
        root.entry.instrument.source.power = genix.current * genix.ht
        root.entry.instrument.source.power.attrs['units'] = 'W'
        root.entry.instrument.source.energy = genix.ht
        root.entry.instrument.source.energy.attrs['units'] = 'eV'
        root.entry.instrument.source.voltage = genix.ht
        root.entry.instrument.source.voltage.attrs['units'] = 'V'
        root.entry.instrument.positioners = nxs.NXcollection()
        positioners = {}
        for mot in self.credo().subsystems['Motors']:
            positioners[mot] = mot.to_NeXus()
            root.entry.instrument.positioners[mot.name] = positioners[mot]
        root.entry.instrument.monochromator = nxs.NXmonochromator()
        root.entry.instrument.monochromator.wavelength = self.wavelength
        root.entry.instrument.monochromator.wavelength.attrs[
            'units'] = 'Angstrom'
        root.entry.instrument.monochromator.wavelength_spread = root.entry.instrument.monochromator.wavelength * \
            0.015  # The FOX3D optics used in GeniX has a spectral purity of 97%.
        root.entry.instrument.monochromator.wavelength_spread.attrs[
            'units'] = 'Angstrom'
        root.entry.instrument.monochromator.energy = scipy.constants.codata.value(
            'Planck constant in eV s') * scipy.constants.codata.value('speed of light in vacuum') * 1e10 / self.wavelength
        root.entry.instrument.monochromator.energy.attrs['units'] = 'eV'
        root.entry.instrument.monochromator.energy_spread = root.entry.instrument.monochromator.energy * \
            0.015
        root.entry.instrument.monochromator.energy_spread.attrs['units'] = 'eV'
        root.entry.instrument.collimator = nxs.NXcollimator(
        )  # TODO: better description of the collimator
        root.entry.instrument.beam_stop = nxs.NXbeam_stop(
        )  # TODO: better description of the geometry
        root.entry.instrument.vacuum = nxs.NXsensor()
        vg = self.credo().subsystems['Equipments'].get('vacgauge')
        if vg.connected():
            root.entry.instrument.vacuum.model = vg.get_version()
            root.entry.instrument.vacuum.name = 'TPG-201 Handheld Pirani Gauge'
            root.entry.instrument.vacuum.short_name = 'Vacuum Gauge'
            root.entry.instrument.vacuum.measurement = 'pressure'
            root.entry.instrument.vacuum.type = 'Pirani'
            root.entry.instrument.vacuum.value = vg.pressure
            root.entry.instrument.vacuum.value.attrs['units'] = 'mbar'
        root.entry.instrument.thermostat = nxs.NXsensor()
        ts = self.credo().subsystems['Equipments'].get('haakephoenix')
        if ts.connected():
            root.entry.instrument.thermostat.model = ts.get_version()
            root.entry.instrument.thermostat.name = 'Haake Phoenix Circulator'
            root.entry.instrument.thermostat.short_name = 'haakephoenix'
            root.entry.instrument.thermostat.measurement = 'temperature'
            root.entry.instrument.thermostat.type = 'Pt100'
            root.entry.instrument.thermostat.value = ts.temperature
            root.entry.instrument.thermostat.value.attrs['units'] = '°C'
        root.entry.sample = nxs.NXsample()
        if isinstance(sample_or_title, basestring):
            root.entry.sample.name = sample_or_title
        else:
            root.entry.sample.name = sample_or_title.title
            root.entry.sample.preparation_date = sample_or_title.preparetime.isoformat(
            )
            root.entry.sample.thickness = sample_or_title.thickness
            root.entry.sample.thickness.attrs['units'] = 'cm'
            root.entry.sample.transmission = float(
                sample_or_title.transmission)
            root.entry.sample.geometry = nxs.NXgeometry()
            root.entry.sample.geometry.description = 'Sample position'
            root.entry.sample.geometry.component_index = 0
            root.entry.sample.geometry.translation = nxs.NXtranslation()
            root.entry.sample.geometry.translation.distances = np.array(
                [sample_or_title.positionx,
                 sample_or_title.positiony,
                 sample_or_title.distminus])
        root.entry.sample.positioners = nxs.NXcollection()
        root.entry.sample.positioners.makelink(
            positioners[self.credo().subsystems['Samples'].get_xmotor()])
        root.entry.sample.positioners.makelink(
            positioners[self.credo().subsystems['Samples'].get_ymotor()])

        if ts.connected():
            root.entry.sample.temperature = ts.temperature
        else:
            root.entry.sample.temperature = np.nan
        root.entry.sample.temperature.attrs['units'] = '°C'

        root.entry.data = nxs.NXdata()

        pilatus = self.subsystems['Equipments'].get('pilatus')
        det = nxs.NXdetector()
        root.entry.instrument.insert(det)
        det.description = ''  # TOUPdate
        det.type = 'pixel'
        det.layout = 'area'
        det.aequatorial_angle = 0
        det.azimuthal_angle = 0
        det.polar_angle = 0
        det.rotation_angle = 0
        det.beam_center_x = self.beamposy * self.pixelsize * 1e-3
        det.beam_center_y = self.beamposx * self.pixelsize * 1e-3
        det.distance = self.dist
        det.count_time = self.subsystems['Exposure'].exptime
        det.count_time.attrs['units'] = 's'
        det.saturation_value = pilatus.cutoff
        det.saturation_value.attrs['units'] = 'count'
        det.sensor_material = 'Si'
        det.sensor_thickness = 450
        det.sensor_thickness.attrs['units'] = 'micron'
        det.threshold_energy = pilatus.threshold
        det.threshold_energy.attrs['units'] = 'eV'
        det.gain_setting = str(pilatus.gain)
        det.frame_time = self.subsystems[
            'Exposure'].exptime + self.subsystems['Exposure'].dwelltime
        det.bit_depth_readout = 20
        det.angular_calibration_applied = 0
        det.acquisition_mode = 'summed'
        det.dead_time = pilatus.tau
        det.dead_time.attrs['units'] = 's'
        det.x_pixel_size = self.pixelsize
        det.x_pixel_size.attrs['units'] = 'micron'
        det.y_pixel_size = self.pixelsize
        det.y_pixel_size.attrs['units'] = 'micron'
        det.detector_readout_time = 2.3
        det.detector_readout_time.attrs['units'] = 'ms'

        det.x = np.arange(pilatus.hpix)
        det.y = np.arange(pilatus.wpix)
        root.entry.data.makelink(root.entry.instrument.detector.x)
        root.entry.data.makelink(root.entry.instrument.detector.y)
        if exposuretype == 'scan':
            det.data = nxs.NXfield(dtype='int32', shape=(
                nxs.UNLIMITED, pilatus.hpix, pilatus.wpix))
            sss = self.subsystems['Scan']
            det.data.attrs['axes'] = sss.scandevice.name() + ':x:y'
            root.entry.data.insert(
                sss.scandevice.name(), nxs.NXfield(dtype='float32', shape=(nxs.UNLIMITED,)))
        elif exposuretype == 'imaging':
            det.data = nxs.NXfield(dtype='int32', shape=(
                ssi.nstep1, ssi.nstep2, pilatus.hpix, pilatus.wpix))
            name1 = ssi.scandevice1.name()
            name2 = ssi.scandevice2.name()
            det.data.attrs['axes'] = name1 + ':' + name2 + ':x:y'
            root.entry.data.insert(
                name1, nxs.NXfield(dtype='float32', shape=(ssi.nstep1,)))
            root.entry.data.insert(
                name2, nxs.NXfield(dtype='float32', shape=(ssi.nstep2,)))
            root.entry.data[name1].attrs['long_name'] = ssi.devicename1
            root.entry.data[name2].attrs['long_name'] = ssi.devicename2
        else:
            det.data = nxs.NXfield(
                dtype='int32', shape=(pilatus.hpix, pilatus.wpix))
            det.data.attrs['axes'] = 'x:y'
            det.data.attrs['signal'] = 1
        det.data.attrs['long_name'] = 'Counts'
        det.data.attrs['units'] = 'count'
        det.data.attrs['calibration_status'] = 'Measured'
        det.data.attrs['interpretation'] = 'image'

        det.pixel_mask_applied = 1
        det.pixel_mask = (mask == 0) << 6
        if pilatus.tau == 0:
            det.countrate_correction_applied = 0
        else:
            det.countrate_correction_applied = 1
        root.entry.data.makelink(root.entry.instrument.detector.data)

        for vd in self.subsystems['VirtualDetectors']:
            root.entry.instrument.insert(vd.name, vd.get_nexus())
            if self.exposuretype == 'scan':
                root.entry.instrument[vd.name].insert(
                    vd.name, nxs.NXfield(dtype='float32', shape=nxs.UNLIMITED,))
