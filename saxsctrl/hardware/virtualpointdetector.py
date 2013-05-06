import time
import sastool

class VirtualPointDetector(object):
    def __init__(self, name, scaler=None):
        self.name = name
        self.scaler = scaler
    def readout(self, *args):
        raise NotImplementedError
    def write_to_configparser(self, cp):
        if cp.has_section('VPD_' + self.name):
            cp.remove_section('VPD_' + self.name)
        cp.add_section('VPD_' + self.name)
        if self.scaler is None:
            cp.set('VPD_' + self.name, 'Scaler', 'None')
        else:
            cp.set('VPD_' + self.name, 'Scaler', self.scaler)
    def __ne__(self, other):
        return not self.__eq__(other)
    def __eq__(self, other):
        return False
    def __str__(self):
        return 'VirtualPointDetector base class'
    
class VirtualPointDetectorExposure(VirtualPointDetector):
    def __init__(self, name, scaler, mask, mode='max'):
        """Define a virtual point detector, which analyzes a portion of a 2D scattering
        pattern and returns a single number.
        
        Inputs:
            mask: sastool.classes.SASMask
                this defines the portion to be analyzed.
            mode: 'max' or 'min' or 'mean' or 'sum' or 'barycenter_x' or 'barycenter_y'
                what to do with the portion selected by the mask.
        """
        VirtualPointDetector.__init__(self, name, scaler)
        self.mask = mask
        self.mode = mode
    def readout(self, exposure):
        if self.mode == 'max':
            return exposure.max(mask=self.mask)
        elif self.mode == 'min':
            return exposure.min(mask=self.mask)
        elif self.mode == 'mean':
            return exposure.mean(mask=self.mask)
        elif self.mode == 'sum':
            return exposure.sum(mask=self.mask)
        elif self.mode == 'barycenter_x':
            x, y = exposure.barycenter(mask=self.mask)
            return x
        elif self.mode == 'barycenter_y':
            x, y = exposure.barycenter(mask=self.mask)
            return y
        elif self.mode == 'sigma_x':
            x, y = exposure.sigma(mask=self.mask)
            return x
        elif self.mode == 'sigma_y':
            x, y = exposure.sigma(mask=self.mask)
            return y
        elif self.mode == 'sigma_tot':
            x, y = exposure.sigma(mask=self.mask)
            return (x ** 2 + y ** 2) ** 0.5
        else:
            raise NotImplementedError
    def write_to_configparser(self, cp):
        VirtualPointDetector.write_to_configparser(self, cp)
        cp.set('VPD_' + self.name, 'mask', self.mask.filename)
        cp.set('VPD_' + self.name, 'mode', self.mode)
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorExposure):
            return False
        for attr in ['mask', 'mode']:
            if self.__getattribute__(attr) != other.__getattribute__(attr):
                return False
        return True
    def __str__(self):
        return self.name + '; mask: ' + self.mask.filename + '; mode: ' + self.mode
        
class VirtualPointDetectorEpoch(VirtualPointDetector):
    def __init__(self, name, scaler):
        VirtualPointDetector.__init__(self, name, scaler)
    def readout(self):
        return time.time()
    def write_to_configparser(self, cp):
        VirtualPointDetector.write_to_configparser(self, cp)
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorEpoch):
            return False
        else:
            return True
    def __str__(self):
        return self.name

class VirtualPointDetectorGenix(VirtualPointDetector):
    def __init__(self, name, scaler, genixparam):
        VirtualPointDetector.__init__(self, name, scaler)
        self.genixparam = genixparam
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
    def write_to_configparser(self, cp):
        VirtualPointDetector.write_to_configparser(self, cp)
        cp.set('VPD_' + self.name, 'genixparam', self.genixparam)
    def __eq__(self, other):
        if not isinstance(other, VirtualPointDetectorGenix):
            return False
        for attr in ['genixparam']:
            if self.__getattribute__(attr) != other.__getattribute__(attr):
                return False
        return True
    def __str__(self):
        return self.name + '; ' + self.genixparam

def virtualpointdetector_new(name, **kwargs):
    if 'scaler' not in kwargs:
        kwargs['scaler'] = 1.0
    if 'genixparam' in kwargs:
        return VirtualPointDetectorGenix(name, kwargs['scaler'], kwargs['genixparam'])
    elif 'mask' in kwargs and 'mode' in kwargs:
        return VirtualPointDetectorExposure(name, kwargs['scaler'], kwargs['mask'], kwargs['mode'])
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
    else:
        scaler = 1.0
    if cp.has_option('VPD_' + name, 'genixparam'):
        return VirtualPointDetectorGenix(name, scaler, cp.get('VPD_' + name, 'genixparam'))
    elif cp.has_option('VPD_' + name, 'mask') and cp.has_option('VPD_' + name, 'mode'):
        return VirtualPointDetectorExposure(name, scaler, sastool.classes.SASMask(cp.get('VPD_' + name, 'mask')), cp.get('VPD_' + name, 'mode'))
    else:
        return VirtualPointDetectorEpoch(name, scaler)
