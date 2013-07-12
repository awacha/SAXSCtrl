import time
import sastool
from ..utils import objwithgui
from gi.repository import GObject
import logging
logger = logging.getLogger(__name__)


class VirtualPointDetector(objwithgui.ObjWithGUI):
    name = GObject.property(type=str, default='--please set name--', blurb='Detector name')
    scaler = GObject.property(type=float, default=1, blurb='Scaling factor')
    visible = GObject.property(type=bool, default=True, blurb='Visible on graphs')
    def __init__(self, name, scaler=None):
        self._OWG_init_lists()
        self._OWG_hints['name'] = {objwithgui.OWG_Hint_Type.OrderPriority:0}
        self._OWG_hints['scaler'] = {objwithgui.OWG_Hint_Type.OrderPriority:1}
        self._OWG_hints['visible'] = {objwithgui.OWG_Hint_Type.OrderPriority:2}
        objwithgui.ObjWithGUI.__init__(self)
        self.name = name
        if scaler is None:
            self.visible = False
            self.scaler = 1
        else:
            self.scaler = scaler
            self.visible = True
    def _get_classname(self):
        return 'VPD_' + self.name
    def readout(self, *args):
        raise NotImplementedError
    def savestate(self, configparser):
        objwithgui.ObjWithGUI.savestate(self, configparser)
        configparser.set(self._get_classname(), 'VPD_Type', self.__class__.__name__)
    def __ne__(self, other):
        return not self.__eq__(other)
    def __eq__(self, other):
        return False
    def __str__(self):
        return 'VirtualPointDetector base class'
    
class VirtualPointDetectorExposure(VirtualPointDetector):
    mode = GObject.property(type=str, default='max', blurb='Image manipulation mode')
    mask = GObject.property(type=str, default='', blurb='Mask file')
    __gsignals__ = {'notify':'override'}
    def __init__(self, name, scaler=None, mask=None, mode=None):
        """Define a virtual point detector, which analyzes a portion of a 2D scattering
        pattern and returns a single number.
        
        Inputs:
            mask: sastool.classes.SASMask
                this defines the portion to be analyzed.
            mode: 'max' or 'min' or 'mean' or 'sum' or 'barycenter_x' or 'barycenter_y'
                what to do with the portion selected by the mask.
        """
        self._OWG_init_lists()
        self._OWG_entrytypes['mode'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints['mode'] = {objwithgui.OWG_Hint_Type.ChoicesList:['max', 'min', 'mean', 'sum', 'barycenter_x', 'barycenter_y', 'sigma_x', 'sigma_y', 'sigma_tot']}
        self._OWG_entrytypes['mask'] = objwithgui.OWG_Param_Type.File
        VirtualPointDetector.__init__(self, name, scaler)
        if mask is not None: self.mask = mask
        if mode is not None: self.mode = mode
    def do_notify(self, prop):
        if prop.name == 'mask':
            try:
                self._mask = sastool.classes.SASMask(self.mask)
            except IOError as ioe:
                logger.error('Cannot load mask: ' + self.mask)
                self._mask = None
    def readout(self, exposure):
        if self.mode == 'max':
            return exposure.max(mask=self._mask)
        elif self.mode == 'min':
            return exposure.min(mask=self._mask)
        elif self.mode == 'mean':
            return exposure.mean(mask=self._mask)
        elif self.mode == 'sum':
            return exposure.sum(mask=self._mask)
        elif self.mode == 'barycenter_x':
            x, y = exposure.barycenter(mask=self._mask)
            return x
        elif self.mode == 'barycenter_y':
            x, y = exposure.barycenter(mask=self._mask)
            return y
        elif self.mode == 'sigma_x':
            x, y = exposure.sigma(mask=self._mask)
            return x
        elif self.mode == 'sigma_y':
            x, y = exposure.sigma(mask=self._mask)
            return y
        elif self.mode == 'sigma_tot':
            x, y = exposure.sigma(mask=self._mask)
            return (x ** 2 + y ** 2) ** 0.5
        else:
            raise NotImplementedError
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorExposure):
            return False
        return other.name == self.name
    def __str__(self):
        return self.name + '; mask: ' + self.mask + '; mode: ' + self.mode
        
class VirtualPointDetectorEpoch(VirtualPointDetector):
    def __init__(self, name, scaler=None):
        VirtualPointDetector.__init__(self, name, scaler)
    def readout(self):
        return time.time()
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorEpoch):
            return False
        return self.name == other.name
    def __str__(self):
        return self.name

class VirtualPointDetectorGenix(VirtualPointDetector):
    genixparam = GObject.property(type=str, default='HT', blurb='GeniX parameter to record')
    def __init__(self, name, scaler=None, genixparam=None):
        self._OWG_init_lists()
        self._OWG_entrytypes['genixparam'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints['genixparam'] = {objwithgui.OWG_Hint_Type.ChoicesList:['HT', 'Status', 'Current', 'TubeTime']}
        VirtualPointDetector.__init__(self, name, scaler)
        if genixparam is not None: self.genixparam = genixparam
        
    def readout(self, genix):
        if self.genixparam == 'HT':
            return genix.get_ht()
        elif self.genixparam == 'Status':
            return genix.get_status_int()
        elif self.genixparam == 'Current':
            return genix.get_current()
        elif self.genixparam == 'Tubetime':
            return genix.get_tube_time()
        else:
            raise NotImplementedError
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorGenix):
            return False
        return self.name == other.name
    def __str__(self):
        return self.name + '; ' + self.genixparam

class VirtualPointDetectorHeader(VirtualPointDetector):
    headerfield = GObject.property(type=str, default='FSN', blurb='Header field')
    def __init__(self, name, scaler=None, headerfield=None):
        self._OWG_init_lists()
        self._OWG_entrytypes['headerfield'] = objwithgui.OWG_Param_Type.ListOfStrings
        self._OWG_hints['headerfield'] = {objwithgui.OWG_Hint_Type.ChoicesList:['FSN', 'MeasTime', 'Dist', 'BeamPosX', 'BeamPosY', 'Wavelength', 'PixelSize'],
                                          objwithgui.OWG_Hint_Type.Editable:True}
        VirtualPointDetector.__init__(self, name, scaler)
        if headerfield is not None: self.headerfield = headerfield
    def readout(self, header):
        return header[self.headerfield]
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorHeader):
            return False
        return self.name == other.name
    def __str__(self):
        return self.name + '; ' + self.headerfield

def virtualpointdetector_new(name, **kwargs):
    if 'scaler' not in kwargs:
        kwargs['scaler'] = 1.0
    if 'genixparam' in kwargs:
        return VirtualPointDetectorGenix(name, kwargs['scaler'], kwargs['genixparam'])
    elif 'mask' in kwargs and 'mode' in kwargs:
        return VirtualPointDetectorExposure(name, kwargs['scaler'], kwargs['mask'], kwargs['mode'])
    elif 'headerfield' in kwargs:
        return VirtualPointDetectorHeader(name, kwargs['scaler'], kwargs['headerfield'])
    else:
        return VirtualPointDetectorEpoch(name, kwargs['scaler'])
    
def virtualpointdetector_new_from_configparser(name, cp):
    if not cp.has_section('VPD_' + name):
        raise ValueError('No definition for detector "' + name + '" in config file.')
    if cp.has_option('VPD_' + name, 'Scaler'):
        scaler = cp.get('VPD_' + name, 'Scaler')
        if scaler == 'None':
            scaler = None
        else:
            scaler = float(scaler)
    if not cp.has_option('VPD_' + name, 'VPD_Type'):
        raise ValueError('Unspecified detector type in config file.')
    try:
        cls = [c for c in VirtualPointDetector.__subclasses__() if c.__name__ == cp.get('VPD_' + name, 'VPD_Type')][0]
    except IndexError:
        raise ValueError('Detector type %s not implemented!' % (cp.get('VPD_' + name, 'VPD_Type')))
    det = cls(name, scaler)
    det.loadstate(cp)
    return det
