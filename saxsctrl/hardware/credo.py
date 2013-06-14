# coding: utf-8
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
import numpy as np

from . import subsystems
from . import sample
from . import virtualpointdetector
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


RCFILE = os.path.expanduser('~/.config/credo/credo3rc')

class CredoError(Exception):
    pass

class Credo(GObject.GObject):
    __gsignals__ = {'setup-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'shutter':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'equipment-connection':(GObject.SignalFlags.RUN_FIRST, None, (str, bool, object)),
                    'scan-dataread':(GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    'scan-end':(GObject.SignalFlags.RUN_FIRST, None, (object, bool)),
                    'virtualpointdetectors-changed':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'scan-fail':(GObject.SignalFlags.RUN_FIRST, None, (str,)),
                    'transmission-report':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object)),
                    'transmission-end':(GObject.SignalFlags.RUN_FIRST, None, (object, object, object, object, bool)),
                    'idle':(GObject.SignalFlags.RUN_FIRST, None, ()),
                    'notify':'override',
                   }
    
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
    
    bs_out = GObject.property(type=float, default=0, blurb='Beam-stop out-of-beam position')
    bs_in = GObject.property(type=float, default=50, blurb='Beam-stop in-beam position')
    
    
    # changing any of the properties in this list will trigger a setup-changed event.
    setup_properties = ['username', 'projectname', 'pixelsize', 'dist', 'filter',
                        'beamposx', 'beamposy', 'wavelength', 'shuttercontrol',
                        'motorcontrol', 'scanfile', 'scandevice', 'virtdetcfgfile',
                        'imagepath', 'filepath', 'bs_out', 'bs_in']
    
    # changing any of the properties in this list will trigger a path-changed event.
    path_properties = ['filepath', 'imagepath']
    def __init__(self):
        GObject.GObject.__init__(self)
        # initialize subsystems
        self.subsystems = {}
        self.subsystems['Files'] = subsystems.SubSystemFiles(self)
        self.subsystems['Samples'] = subsystems.SubSystemSamples(self)
        self.subsystems['Equipments'] = subsystems.SubSystemEquipments(self)
        self.subsystems['Scan'] = subsystems.SubSystemScan(self)
        self.subsystems['Exposure'] = subsystems.SubSystemExposure(self)
        self.subsystems['VirtualDetectors'] = subsystems.SubSystemVirtualDetectors(self)
        # load state: this will load the state information of all the subsystems as well.
        self.loadstate()
        try:
            self.subsystems['Equipments'].connect_to_all()
        except subsystems.SubSystemError as err:
            logger.warning(err.message)
        
#        self.tmcm.load_settings(os.path.expanduser('~/.config/credo/motorrc'))
        
        
#         self.connect('notify::scanfile', lambda obj, param:self.reload_scanfile())
#         self.reload_scanfile()
#         # samples
#         
#         # data reduction
#         self.datareduction = datareduction.DataReduction()
#         self.datareduction.load_state()
#         self.datareduction.set_property('fileformat', self.fileformat + '.cbf')
#         self.datareduction.set_property('headerformat', self.fileformat + '.param')
#         self.datareduction.set_property('datadirs', self.get_exploaddirs())
#         self.datareduction.save_state()
#         self.emit('path-changed')
#         
#         self.load_samples()
#         # emit signals if parameters change
#         for name in self.setup_properties:
#             self.connect('notify::' + name, lambda crd, prop:crd.emit('setup-changed'))
#         for name in self.path_properties:
#             self.connect('notify::' + name, lambda crd, prop:crd.emit('path-changed'))

    def do_notify(self, param):
        if param.name == 'rootpath':
            self.files.rootpath = self.rootpath
        if param.name == 'filebegin':
            self.files.filebegin = self.filebegin
        if param.name == 'ndigits':
            self.files.ndigits = self.ndigits
    
    def get_equipment(self, equipment):
        return self.subsystems['Equipments'].get(equipment)
    def get_motors(self):
        mots = self.get_equipment('tmcm351')
        return [mots[m] for m in sorted(mots)]
    def get_motor(self, name):
        return [m for m in self.get_motors() if ((m.name == name) or (m.alias == name) or (str(m) == name))][0]
    def loadstate(self):
        cp = ConfigParser.ConfigParser()
        cp.read(RCFILE)
        for ss in self.subsystems.values():
            ss.loadstate(cp)
        if not cp.has_section('CREDO'):
            return
        for p in self.props:
            if not cp.has_option('CREDO', p.name):
                continue
            if p.value_type.name == 'gboolean':
                val = cp.getboolean('CREDO', p.name)
            elif p.value_type.name in ['gint', 'guint', 'glong', 'gulong',
                                       'gshort', 'gushort', 'gint8', 'guint8',
                                       'gint16', 'guint16', 'gint32', 'guint32',
                                       'gint64', 'guint64']:
                val = cp.getint('CREDO', p.name)
            elif p.value_type.name in ['gfloat', 'gdouble']:
                val = cp.getfloat('CREDO', p.name)
            else:
                val = cp.get('CREDO', p.name)
            if self.get_property(p.name) != val:
                self.set_property(p.name, val)
        del cp
    def savestate(self):
        cp = ConfigParser.ConfigParser()
        cp.read(RCFILE)
        if cp.has_section('CREDO'):
            cp.remove_section('CREDO')
        cp.add_section('CREDO')
        for p in self.props:
            cp.set('CREDO', p.name, self.get_property(p.name))
        for ss in self.subsystems.values():
            ss.savestate(cp)
        if not os.path.exists(os.path.split(RCFILE)[0]):
            os.makedirs(os.path.split(RCFILE)[0])
        with open(RCFILE, 'wt') as f:
            print "SAVING SETTINGS."
            cp.write(f)
        del cp
        return True

    def expose(self, exptime, nimages=1, dwelltime=0.003, mask=None, header_template=None):
        self.subsystems['Exposure'].exptime = exptime
        self.subsystems['Exposure'].nimages = nimages
        self.subsystems['Exposure'].dwelltime = dwelltime
        self.subsystems['Exposure'].start(header_template, mask)
    
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
    def move_beamstop(self, state=False):
        try:
            beamstopymotor = [m for m in self.get_motors() if m.alias == 'BeamStop_Y'][0]
        except IndexError:
            raise CredoError('No motor with alias "BeamStop_Y".')
        if not state:
            # should move the beamstop out. Ensure that the X-ray source is in low-power mode.
            if (self.genix.get_ht() > 30 or self.genix.get_current() > 0.3):
                logger.info('Putting GeniX into low-power mode.')
                self.genix.do_standby()
                self.wait_for_event(lambda :self.genix.whichstate() == genix.GENIX_STANDBY)
                logger.info('Low-power mode reached.')
            logger.info('Moving out beamstop.')
            self.move_motor(beamstopymotor, self.bs_out, blocking=True)
            logger.info('Beamstop is out.')
        else:
            logger.info('Moving in beamstop.')
            self.move_motor(beamstopymotor, self.bs_in, blocking=True)
            logger.info('Beamstop is in.')
            self.wait_for_event(lambda :not beamstopymotor.is_moving())
            logger.info('Putting GeniX into full-power mode.')
            self.genix.do_rampup()
            self.wait_for_event(lambda :self.genix.whichstate() == genix.GENIX_FULLPOWER)
            logger.info('Full-power mode reached.')
    
    def is_beamstop_in(self):
        try:
            beamstopymotor = [m for m in self.get_motors() if m.alias == 'BeamStop_Y'][0]
        except IndexError:
            raise CredoError('No motor with alias "BeamStop_Y".')
        return beamstopymotor.get_pos() == self.bs_in
    def do_transmission(self):
        if not hasattr(self, 'transmdata'):
            return
        if self.transmdata['next_is'] == 'D':
            if self.transmdata['repeat'] > 0:
                logger.info('Transmission: Dark current')
            sam = sample.SAXSSample('Dark current', None, None, None, None, 'SYSTEM', None, 0)
            with self.freeze_notify():
                self.shuttercontrol = False
            if self.transmdata['manageshutter']:
                self.shutter = False
            self.transmdata['next_is'] = 'E'
        elif self.transmdata['next_is'] == 'E':
            logger.info('Transmission: Empty beam (%s)' % self.transmdata['emptysample'].title)
            sam = self.transmdata['emptysample']
            self.transmdata['next_is'] = 'S'
            if self.transmdata['manageshutter']:
                with self.freeze_notify():
                    self.shuttercontrol = True
        else:
            logger.info('Transmission: Sample (%s)' % self.transmdata['sample'].title)
            sam = self.transmdata['sample']
            self.transmdata['repeat'] -= 1
            self.transmdata['next_is'] = 'D'
            if self.transmdata['manageshutter']:
                with self.freeze_notify():
                    self.shuttercontrol = True
        if (self.transmdata['repeat'] == 0 and self.transmdata['next_is'] == 'E') or self.transmdata['kill']:
            if self.transmdata['Isample'] and self.transmdata['Iempty'] and self.transmdata['Idark']:
                data = {}
                for n in ['sample', 'empty', 'dark']:
                    data[n] = sastool.classes.ErrorValue(np.mean(self.transmdata['I' + n]),
                                                       np.std(self.transmdata['I' + n]))
                Iempty = data['empty'] - data['dark']
                if Iempty.is_zero():
                    transm = None
                else:
                    transm = (data['sample'] - data['dark']) / Iempty
            else:
                transm = None
            self.emit('transmission-end', self.transmdata['Iempty'], self.transmdata['Isample'], self.transmdata['Idark'],
                      transm, not self.transmdata['kill'])
            return

        self.moveto_sample(sam)
        self.set_sample(sam)
        if self.transmdata['firstexposure']:
            self.expose(self.transmdata['exptime'], self.transmdata['expnum'], 0.003, None, quick=False)
            self.transmdata['firstexposure'] = False
        else:
            self.expose(self.transmdata['exptime'], self.transmdata['expnum'], 0.003, None, quick=True)
    def do_transmission_end(self, Iempty, Isample, Transmission, state):
        logger.info('End of transmission measurement.')
        del self.transmdata
    def transmission(self, sample, emptysample, exptime, expnum, mask, mode='max', repeat=1):
        # if self.is_beamstop_in():
        #    self.move_beamstop(False)
        self.transmdata = {'sample':sample, 'emptysample':emptysample, 'exptime':exptime,
                           'expnum':expnum, 'repeat':repeat, 'next_is':'D', 'firstexposure':True,
                           'mode':mode, 'mask':mask, 'kill':False, 'manageshutter':self.shuttercontrol}
        self.do_transmission()
    def killtransmission(self):
        self.transmdata['kill'] = True
        self.killexposure()
