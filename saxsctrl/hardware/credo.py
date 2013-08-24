# coding: utf-8
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
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
import cPickle as pickle
from gi.repository import Gio
from gi.repository import GObject
import ConfigParser
import multiprocessing
import numpy as np

from . import subsystems
from . import sample
from . import virtualpointdetector
from ..utils import objwithgui


RCFILE = os.path.expanduser('~/.config/credo/credo3rc')

class CredoError(Exception):
    pass

class Credo(objwithgui.ObjWithGUI):
    __gsignals__ = {'setup-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'shutter':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'equipment-connection':(GObject.SignalFlags.RUN_FIRST, None, (str, bool, object)),
                    'scan-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'transmission-report':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object)),
                    'transmission-end':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object, object, bool)),
                    'idle':(GObject.SignalFlags.RUN_FIRST, None, ()),
                   }
    # offline mode. In this mode settings files cannot be written and connections to instruments cannot be made.
    offline = GObject.property(type=bool, default=False, blurb='Offline mode')
    
    # Accounting properties
    username = GObject.property(type=str, default='Anonymous', blurb='User name')
    projectname = GObject.property(type=str, default='No project', blurb='Project name')
    
    # Instrument parameters
    pixelsize = GObject.property(type=float, default=172, minimum=0, blurb=u'Pixel size (μm)'.encode('utf-8'))
    dist = GObject.property(type=float, default=1000, minimum=0, blurb='Sample-detector distance (mm)')
    filter = GObject.property(type=str, default='No filter', blurb='Filters')
    beamposx = GObject.property(type=float, default=348.38, blurb='Beam position X (vertical, pixels)')
    beamposy = GObject.property(type=float, default=242.47, blurb='Beam position Y (horizontal, pixels')
    wavelength = GObject.property(type=float, default=1.54182, minimum=0, blurb='X-ray wavelength (Å)')
    # Inhibiting parameters
    shuttercontrol = GObject.property(type=bool, default=True, blurb='Open/close shutter')
    motorcontrol = GObject.property(type=bool, default=True, blurb='Move motors')
    
    # changing any of the properties in this list will trigger a setup-changed event.
    setup_properties = ['username', 'projectname', 'pixelsize', 'dist', 'filter',
                        'beamposx', 'beamposy', 'wavelength', 'shuttercontrol',
                        'motorcontrol', 'scanfile', 'scandevice', 'virtdetcfgfile',
                        'imagepath', 'filepath']
    
    # changing any of the properties in this list will trigger a path-changed event.
    path_properties = ['filepath', 'imagepath']
    def __init__(self, offline=True):
        objwithgui.ObjWithGUI.__init__(self)
        self._OWG_nogui_props.append('offline')
        self._OWG_nosave_props.append('offline')
        self.offline = offline
        self._OWG_hints['username'] = {objwithgui.OWG_Hint_Type.OrderPriority:0}
        self._OWG_hints['projectname'] = {objwithgui.OWG_Hint_Type.OrderPriority:0}
        self._OWG_hints['beamposx'] = {objwithgui.OWG_Hint_Type.OrderPriority:1, objwithgui.OWG_Hint_Type.Digits:3}
        self._OWG_hints['beamposy'] = {objwithgui.OWG_Hint_Type.OrderPriority:2, objwithgui.OWG_Hint_Type.Digits:3}
        self._OWG_hints['dist'] = {objwithgui.OWG_Hint_Type.OrderPriority:3, objwithgui.OWG_Hint_Type.Digits:3}
        self._OWG_hints['pixelsize'] = {objwithgui.OWG_Hint_Type.OrderPriority:4}
        self._OWG_hints['wavelength'] = {objwithgui.OWG_Hint_Type.OrderPriority:5, objwithgui.OWG_Hint_Type.Digits:4}
        self._OWG_hints['default-mask'] = {objwithgui.OWG_Hint_Type.OrderPriority:5, objwithgui.OWG_Hint_Type.Digits:5}
        self._OWG_entrytypes['default-mask'] = objwithgui.OWG_Param_Type.File
        self._OWG_hints['shuttercontrol'] = {objwithgui.OWG_Hint_Type.OrderPriority:6}
        self._OWG_hints['motorcontrol'] = {objwithgui.OWG_Hint_Type.OrderPriority:6}
        self._OWG_hints['bs-in'] = {objwithgui.OWG_Hint_Type.OrderPriority:7, objwithgui.OWG_Hint_Type.Digits:3}
        self._OWG_hints['bs-out'] = {objwithgui.OWG_Hint_Type.OrderPriority:8, objwithgui.OWG_Hint_Type.Digits:3}
        # initialize subsystems
        logger.debug('Initializing subsystems of Credo')
        self.subsystems = {}
        self.subsystems['Files'] = subsystems.SubSystemFiles(self, offline=self.offline)
        self.subsystems['Samples'] = subsystems.SubSystemSamples(self, offline=self.offline)
        self.subsystems['Equipments'] = subsystems.SubSystemEquipments(self, offline=self.offline)
        self.subsystems['Motors'] = subsystems.SubSystemMotors(self, offline=self.offline)
        self.subsystems['VirtualDetectors'] = subsystems.SubSystemVirtualDetectors(self, offline=self.offline)
        self.subsystems['Exposure'] = subsystems.SubSystemExposure(self, offline=self.offline)
        self.subsystems['Scan'] = subsystems.SubSystemScan(self, offline=self.offline)
        self.subsystems['Imaging'] = subsystems.SubSystemImaging(self, offline=self.offline)
        self.subsystems['Transmission'] = subsystems.SubSystemTransmission(self, offline=self.offline)
        self.subsystems['DataReduction'] = subsystems.SubSystemDataReduction(self, offline=self.offline)
        logger.debug('All Credo subsystems initialized.')
        self._OWG_parts = self.subsystems.values()
        
        # load state: this will load the state information of all the subsystems as well.
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
            logger.warning('Not saving settings, since we are in off-line mode.')
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

    def expose(self, exptime, nimages=1, dwelltime=0.003, mask=None, header_template=None, filebegin=None):
        if filebegin is not None and (self.subsystems['Files'].filebegin != filebegin):
            self.subsystems['Files'].filebegin = filebegin
        self.subsystems['Exposure'].exptime = exptime
        self.subsystems['Exposure'].nimages = nimages
        self.subsystems['Exposure'].dwelltime = dwelltime
        return self.subsystems['Exposure'].start(header_template, mask)
    
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
