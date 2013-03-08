import sastool
import numpy as np
import os
import gc
import re
import ConfigParser
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from sasgui import PyGTKCallback
import functools

class ExpSelector(object):
    """Select an exposure (using headers) which fulfills several criteria."""
    def __init__(self, headerformat='crd_%05d.param', datadirs=['.']):
        self.headerformat = headerformat
        self.datadirs = datadirs
        self._headercache = None
    def refresh_cache(self):
        if self._headercache is not None:
            del self._headercache
            gc.collect()
        regex = re.compile(sastool.misc.re_from_Cformatstring_numbers(self.headerformat))
        headerfiles = []
        for d in self.datadirs:
            headerfiles.extend([os.path.join(d, f) for f in os.listdir(d) if regex.match(f) is not None])
        self._headercache = [sastool.classes.SASHeader(hf) for hf in headerfiles]
    def select(self, hdr_to_compare, equal=[], less=[], greater=[], func=[], sort='Date', reversesort=False):
        """Select an exposure (using the headers) which fulfills several criteria.
        
        Inputs:
            hdr_to_compare: a header (or simply a dictionary) to which all headers will be compared
            equal: list of header attributes (such as 'Title', 'Dist' etc.) the values of which should be equal 
                to the corresponding ones in hdr_to_compare
            less: list of header attributes the values of which should be less than the corresponding ones in
                hdr_to_compare
            greater: list of header attributes the values of which should be greater than the corresponding ones
                in hdr_to_compare
            func: list of boolean functions. Each one will be called in turn with two arguments: hdr_to_compare and
                the current header to be tested. Returning True means the header is valid, False means invalid.
            sort: the attribute name (or a key function of a similar call arguments as in func), by which the 
                valid headers will be sorted
            reversesort: if the sort order is to be reversed
        
        Output:
            the first header from the sorted, valid headers.
        """
        if self._headercache is None:
            self.refresh_cache()
        lis = self._headercache[:]
        for attr in equal:
            lis = [l for l in lis if (attr in l) and (l[attr] == hdr_to_compare[attr])]
        for attr in less:
            lis = [l for l in lis if (attr in l) and (l[attr] < hdr_to_compare[attr])]
        for attr in greater:
            lis = [l for l in lis if (attr in l) and (l[attr] > hdr_to_compare[attr])]
        for f in func:
            lis = [l for l in lis if func(hdr_to_compare, l)]
        if sort is None:
            return lis
        if not callable(sort):
            lis = [l for l in lis if sort in l]
            lis.sort(key=lambda l:l[sort], reverse=reversesort)
        if callable(sort):
            lis.sort(key=lambda l:sort(hdr_to_compare, l), reverse=reversesort)
        return lis[0]
    
@PyGTKCallback.PyGTKCallback        
class DataReduction(object):
    _fileformat = 'crd_%05d.cbf'
    _headerformat = 'crd_%05d.param'
    _datadirs = None
    _do_bgsub = True
    _do_absint = True
    _do_solidangle = True
    _do_transmission = True
    _do_thickness = True
    _do_monitor = True
    _bg_select_method = 'nearest'  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename.
    _bg_name = 'Empty beam'
    _bg_dist_tolerance = 20  # mm
    _bg_energy_tolerance = 2  # eV
    _absint_select_method = 'nearest'  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename.
    _absint_name = 'Glassy carbon'
    _absint_dist_tolerance = 20  # mm
    _absint_energy_tolerance = 2  # eV
    _absint_reffile = None  # should be a file name or a SASCurve.
    _monitor_attr = 'MeasTime'
    _transmission_selfabsorption = True
    def get_property(name, self):
        return self.__getattribute__('_' + name)
    def set_property(name, self, value):
        self.__setattr__('_' + name, value)
    fileformat = property(functools.partial(get_property, 'fileformat'), functools.partial(set_property, 'fileformat'))
    headerformat = property(functools.partial(get_property, 'headerformat'), functools.partial(set_property, 'headerformat'))
    datadirs = property(functools.partial(get_property, 'datadirs'), functools.partial(set_property, 'datadirs'))
    do_bgsub = property(functools.partial(get_property, 'do_bgsub'), functools.partial(set_property, 'do_bgsub'))
    do_absint = property(functools.partial(get_property, 'do_absint'), functools.partial(set_property, 'do_absint'))
    do_solidangle = property(functools.partial(get_property, 'do_solidangle'), functools.partial(set_property, 'do_solidangle'))
    do_transmission = property(functools.partial(get_property, 'do_transmission'), functools.partial(set_property, 'do_transmission'))
    do_thickness = property(functools.partial(get_property, 'do_thickness'), functools.partial(set_property, 'do_thickness'))            
    do_monitor = property(functools.partial(get_property, 'do_monitor'), functools.partial(set_property, 'do_monitor'))            
    bg_select_method = property(functools.partial(get_property, 'bg_select_method'), functools.partial(set_property, 'bg_select_method'))            
    bg_name = property(functools.partial(get_property, 'bg_name'), functools.partial(set_property, 'bg_name'))            
    bg_dist_tolerance = property(functools.partial(get_property, 'bg_dist_tolerance'), functools.partial(set_property, 'bg_dist_tolerance'))            
    bg_energy_tolerance = property(functools.partial(get_property, 'bg_energy_tolerance'), functools.partial(set_property, 'bg_energy_tolerance'))            
    absint_select_method = property(functools.partial(get_property, 'absint_select_method'), functools.partial(set_property, 'absint_select_method'))            
    absint_name = property(functools.partial(get_property, 'absint_name'), functools.partial(set_property, 'absint_name'))            
    absint_dist_tolerance = property(functools.partial(get_property, 'absint_dist_tolerance'), functools.partial(set_property, 'absint_dist_tolerance'))            
    absint_energy_tolerance = property(functools.partial(get_property, 'absint_energy_tolerance'), functools.partial(set_property, 'absint_energy_tolerance'))            
    absint_reffile = property(functools.partial(get_property, 'absint_reffile'), functools.partial(set_property, 'absint_reffile'))            
    monitor_attr = property(functools.partial(get_property, 'monitor_attr'), functools.partial(set_property, 'monitor_attr'))            
    transmission_selfabsorption = property(functools.partial(get_property, 'transmission_selfabsorption'), functools.partial(set_property, 'transmission_selfabsorption'))            
    def __init__(self, **kwargs):
        for k in kwargs:
            self.__setattr__(k, kwargs[k])
        if self.datadirs is None:
            self.datadirs = ['.']
    def load_state(self, cfg=os.path.expanduser('~/.config/credo/dataredrc'), keep=[]):
        cp = ConfigParser.ConfigParser()
        cp.read(cfg)
        for sec, opt, attr in [('IO', 'File_format', 'fileformat'),
                             ('IO', 'Header_format', 'headerformat'),
                             ('Background subtraction', 'Enabled', 'do_bgsub'),
                             ('Absolute intensity', 'Enabled', 'do_absint'),
                             ('Solid angle', 'Enabled', 'do_solidangle'),
                             ('Transmission', 'Enabled', 'do_transmission'),
                             ('Transmission', 'Self_absorption_correction', 'transmission_selfabsorption'),
                             ('Scaling', 'Monitor', 'do_monitor'),
                             ('Scaling', 'Thickness', 'do_thickness')]:
            if attr in keep:
                continue
            if cp.has_option(sec, opt):
                self.__setattr__('_' + attr, cp.getboolean(sec, opt))
        for sec, opt, attr in [('Background subtraction', 'Select_method', 'bg_select_method'),
                             ('Background subtraction', 'Name', 'bg_name'),
                             ('Absolute intensity', 'Select_method', 'absint_select_method'),
                             ('Absolute intensity', 'Name', 'absint_name'),
                             ('Absolute intensity', 'Ref_filename', 'absint_reffile'),
                             ('Monitor', 'Header_attribute_name', 'monitor_attr')]:
            if attr in keep:
                continue
            if cp.has_option(sec, opt):
                self.__setattr__('_' + attr, cp.get(sec, opt))
        for sec, opt, attr in [('Background subtraction', 'Dist_tolerance_mm', 'bg_dist_tolerance'),
                             ('Background subtraction', 'Energy_tolerance_eV', 'bg_energy_tolerance'),
                             ('Absolute intensity', 'Dist_tolerance_mm', 'absint_dist_tolerance'),
                             ('Absolute intensity', 'Energy_tolerance_eV', 'absint_energy_tolerance')]:
            if attr in keep:
                continue
            if cp.has_option(sec, opt):
                self.__setattr__('_' + attr, cp.getfloat(sec, opt))
        if 'datadirs' not in keep:
            if cp.has_section('IO'):
                self.datadirs = []
                for name, val in sorted([(n, v) for (n, v) in cp.items('IO') if n.startswith('Dir')], key=lambda (n, v): n[3:]):
                    self.datadirs.append(val)
        self.emit('changed')
    def save_state(self, cfg=os.path.expanduser('~/.config/credo/dataredrc')):
        cp = ConfigParser.ConfigParser()
        for sec, opt, attr in [('IO', 'File_format', 'fileformat'),
                             ('IO', 'Header_format', 'headerformat'),
                             ('Background subtraction', 'Enabled', 'do_bgsub'),
                             ('Absolute intensity', 'Enabled', 'do_absint'),
                             ('Solid angle', 'Enabled', 'do_solidangle'),
                             ('Transmission', 'Enabled', 'do_transmission'),
                             ('Transmission', 'Self_absorption_correction', 'transmission_selfabsorption'),
                             ('Scaling', 'Monitor', 'do_monitor'),
                             ('Scaling', 'Thickness', 'do_thickness'),
                             ('Background subtraction', 'Select_method', 'bg_select_method'),
                             ('Background subtraction', 'Name', 'bg_name'),
                             ('Absolute intensity', 'Select_method', 'absint_select_method'),
                             ('Absolute intensity', 'Name', 'absint_name'),
                             ('Absolute intensity', 'Ref_filename', 'absint_reffile'),
                             ('Monitor', 'Header_attribute_name', 'monitor_attr'),
                             ('Background subtraction', 'Select_method', 'bg_select_method'),
                             ('Background subtraction', 'Name', 'bg_name'),
                             ('Absolute intensity', 'Select_method', 'absint_select_method'),
                             ('Absolute intensity', 'Name', 'absint_name'),
                             ('Absolute intensity', 'Ref_filename', 'absint_reffile'),
                             ('Monitor', 'Header_attribute_name', 'monitor_attr'),
                             ]:
            if not cp.has_section(sec):
                cp.add_section(sec)
            cp.set(sec, opt, self.__getattribute__(attr))
        for i, d in enumerate(self.datadirs):
            if not cp.has_section('IO'):
                cp.add_section('IO')
            cp.set('IO', 'Dir%05d' % i, d)
        with open(cfg, 'w+') as f:
            cp.write(f)
    def _reduction_step1(self, exposure):
        logger.info('Reductions step #1 (scaling & geometry) on ' + str(exposure.header) + ' starting.')
        if self.do_monitor:
            logger.info('Normalizing intensities according to \'%s\'.' % self.monitor_attr)
            exposure = exposure / exposure[monitor_attr]
        if self.do_solidangle:
            logger.info('Doing solid angle correction.')
            exposure = exposure * sastool.corrections.solidangle(exposure.tth, exposure['DistCalibrated'])
        if self.do_transmission:
            logger.info('Normalizing by transmission.')
            exposure = exposure / ErrorValue(exposure['Transm'], exposure['TransmError'])
            if self.transmission_selfabsorption:
                logger.info('Self-absorption correction.')
                exposure *= sastool.corrections.angledependentabsorption(exposure.tth, exposure['Transm'])
        logger.info('Reduction step #1 (scaling & geometry) on ' + str(exposure.header) + ' done.')
        return exposure
    def _reduction_step2(self, exposure, es):
        if self.do_bgsub:
            if exposure['Title'] == self.bg_name:
                logger.info('Skipping background subtraction from background.')
                return exposure
            logger.info('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' starting.')
            if self.bg_select_method == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.bg_name
                bgheader = es.select(header, equal=['Title'],
                                     func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.bg_energy_tolerance,
                                           lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.bg_dist_tolerance],
                                     sort=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.fileformat % bgheader['FSN'], dirs=datadirs)
            elif self.bg_select_method == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.bg_name
                bgheader = es.select(header, equal=['Title'], less=['Date'],
                                     func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.bg_energy_tolerance,
                                           lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.bg_dist_tolerance],
                                     sort=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.fileformat % bgheader['FSN'], dirs=datadirs)
            elif self.bg_select_method == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.bg_name
                bgheader = es.select(header, equal=['Title'], greater=['Date'],
                                     func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.bg_energy_tolerance,
                                           lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.bg_dist_tolerance],
                                     sort=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(self.fileformat % bgheader['FSN'], dirs=datadirs)
            else:
                bg = sastool.classes.SASExposure(self.bg_select_method, dirs=datadirs)
            logger.info('Found background: ' + str(bg.header))
            bg = self._reduction_step1(bg)
            exposure = exposure - bg
            logger.info('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' done.')
        if self.do_thickness:
            logger.info('Normalizing by thickness.')
            exposure /= exposure.header['Thickness']
        return exposure
    def _reduction_step3(self, exposure, es):
        if exposure['Title'] == self.bg_name:
            logger.info('Skipping absolute normalization of a background measurement.')
            return exposure
        if self.do_absint:
            logger.info('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' starting.')
            if self.absint_select_method == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.absint_name
                refheader = es.select(header, equal=['Title'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.absint_energy_tolerance,
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.absint_dist_tolerance],
                                      sort=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.fileformat % refheader['FSN'], dirs=datadirs)
            elif self.absint_select_method == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.absint_name
                refheader = es.select(header, equal=['Title'], less=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.absint_energy_tolerance,
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.absint_dist_tolerance],
                                      sort=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.fileformat % refheader['FSN'], dirs=datadirs)
            elif self.absint_select_method == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = self.absint_name
                refheader = es.select(header, equal=['Title'], greater=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < self.absint_energy_tolerance,
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < self.absint_dist_tolerance],
                                      sort=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(self.fileformat % refheader['FSN'], dirs=datadirs)
            else:
                ref = sastool.classes.SASExposure(self.absint_select_method, dirs=datadirs)
            ref = self._reduction_step1(ref)
            ref = self._reduction_step2(ref, es)
            reffile = sastool.classes.SASCurve(self.absint_reffile)
            radref = ref.radial_average(reffile.q)
            scalefactor = radref.scalefactor(reffile)
            logger.info('Absolute scaling factor:' + str(scalefactor))
            exposure = exposure * scalefactor
            logger.info('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' done.')
        return exposure
    def do_reduction(self, exposure):
        es = ExposureSelector(self.headerformat, self.datadirs)
        logger.info('Data reduction of ' + str(exposure.header) + ' starting.')
        exposure = self._reduction_step1(exposure)
        exposure = self._reduction_step2(exposure, es)
        exposure = self._reduction_step3(exposure, es)
        return exposure
