# coding: utf-8
import logging
import scipy
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
import os
import datetime
import numpy as np
import gc
from gi.repository import GObject
import configparser
import pkg_resources
import dateutil
import traceback

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
    projectid = GObject.property(
        type=str, default='01', blurb='Project ID')
    proposername = GObject.property(
        type=str, default='John Doe', blurb='Main proposer')

    # Instrument parameters
    pixelsize = GObject.property(
        type=float, default=172, minimum=0,
        blurb='Pixel size (μm)')
    dist = GObject.property(
        type=float, default=1000, minimum=0,
        blurb='Sample-detector distance (mm)')
    dist_error = GObject.property(
        type=float, default=0, minimum=0,
        blurb='Error of the sample-detector distance (mm)'
    )
    setup_description = GObject.property(
        type=str, default='<Description of the set-up>', blurb='Description of the current set-up')
    beamposx = GObject.property(
        type=float, default=348.38, blurb='Beam position X (vertical, pixels)')
    beamposy = GObject.property(
        type=float, default=242.47, blurb='Beam position Y (horizontal, pixels')
    wavelength = GObject.property(
        type=float, default=0.154182, minimum=0, blurb='X-ray wavelength (nm)')
    wavelength_spread = GObject.property(
        type=float, default=0.03, minimum=0, blurb='Relative wavelength spread (Dlambda/lambda)')
    motorcontrol = GObject.property(
        type=bool, default=True, blurb='Move motors')

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
        self._OWG_hints['dist-error'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 4,
            objwithgui.OWG_Hint_Type.Digits: 3}
        self._OWG_hints['pixelsize'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 5}
        self._OWG_hints['wavelength'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 6,
            objwithgui.OWG_Hint_Type.Digits: 4}
        self._OWG_hints['wavelength-spread'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 7,
            objwithgui.OWG_Hint_Type.Digits: 4}
        self._OWG_hints['default-mask'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 8,
            objwithgui.OWG_Hint_Type.Digits: 5}
        self._OWG_entrytypes['default-mask'] = objwithgui.OWG_Param_Type.File
        self._OWG_hints['motorcontrol'] = {
            objwithgui.OWG_Hint_Type.OrderPriority: 9}
        # initialize subsystems
        logger.debug('Initializing subsystems of Credo')
        self.subsystems = {}
        self.subsystems['Collimation'] = subsystems.SubSystemCollimation(
            self, offline=self.offline)
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
        self._OWG_parts = list(self.subsystems.values())

        # load state: this will load the state information of all the
        # subsystems as well.
        self.loadstate()
        if not self.offline:
            try:
                self.subsystems['Equipments'].connect_to_all()
            except subsystems.SubSystemError as err:
                logger.warning('Connecting to some instruments failed.')

    def _get_classname(self):
        return 'CREDO'

    def get_equipment(self, equipment):
        return self.subsystems['Equipments'].get(equipment)

    def loadstate(self, cp=None, sectionprefix=''):
        logger.debug('Loading Credo state...')
        if cp is None:
            cp = self.getstatefile()
        objwithgui.ObjWithGUI.loadstate(self, cp, sectionprefix)
#         for ss in self.subsystems.values():
#             ss.loadstate(cp)
        logger.debug('Credo state loaded.')
        del cp

    def getstatefile(self):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(RCFILE)
        return cp

    def savestate(self):
        if self.offline:
            logger.warning(
                'Not saving settings, since we are in off-line mode.')
            return
        cp = self.getstatefile()
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
        for ss in list(self.subsystems.keys()):
            self.subsystems[ss].destroy()
            del self.subsystems[ss]
        gc.collect()
