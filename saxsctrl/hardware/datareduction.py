import sastool
import numpy as np
import os
import gc
import re
import ConfigParser
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
import functools
from gi.repository import GObject
import threading
import Queue

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
        regex = re.compile(sastool.misc.re_from_Cformatstring_numbers(self.headerformat)[:-1])
        headerfiles = []
        for d in self.datadirs:
            headerfiles.extend([os.path.join(d, f) for f in os.listdir(d) if regex.match(f) is not None])
        self._headercache = [sastool.classes.SASHeader(hf) for hf in headerfiles]
    def select(self, hdr_to_compare, equal=[], less=[], greater=[], func=[], sorting='Date', reversesort=False):
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
            sorting: the attribute name (or a key function of a similar call arguments as in func), by which the 
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
            lis = [l for l in lis if f(hdr_to_compare, l)]
        if sorting is None:
            return lis
        if not callable(sorting):
            lis = [l for l in lis if sorting in l]
            lis.sort(key=lambda l:l[sorting], reverse=reversesort)
        elif callable(sorting):
            lis.sort(key=lambda l:sorting(hdr_to_compare, l), reverse=reversesort)
        return lis[0]

class DataReductionSettings(GObject.GObject):
    def __init__(self, dr):
        GObject.GObject.__init__(self)
        self.props = dr.props
        self.vals = dr.__propvalues__
    def get_property(self, key):
        if key in self.vals:
            return self.vals[key]
        else:
            return [p for p in self.props if p.name == key][0].default_value
    
class DataReduction(GObject.GObject):
    __gsignals__ = {'changed':(GObject.SignalFlags.RUN_FIRST, None, ()), }
    __gproperties__ = {'fileformat' :(str, 'IO::File_format', '2d file format string including extension', 'crd_%05d.cbf', GObject.PARAM_READWRITE),
                       'headerformat':(str, 'IO::Header_format', 'header file format string including extension', 'crd_%05d.param', GObject.PARAM_READWRITE),
                       'datadirs': (object, 'IO::Dir*', 'search path for data to be loaded', GObject.PARAM_READWRITE),
                       'do-bgsub': (bool, 'Background subtraction::Enabled', 'Do background subtraction?', True, GObject.PARAM_READWRITE),
                       'do-absint': (bool, 'Absolute intensity::Enabled', 'Do absolute intensity scaling?', True, GObject.PARAM_READWRITE),
                       'do-solidangle': (bool, 'Solid angle::Enabled', 'Do solid-angle correction?', True, GObject.PARAM_READWRITE),
                       'do-transmission' : (bool, 'Transmission::Enabled', 'Do transmission correction?', True, GObject.PARAM_READWRITE),
                       'do-thickness': (bool, 'Scaling::Thickness', 'Scale by sample thickness?', True, GObject.PARAM_READWRITE),
                       'do-monitor': (bool, 'Scaling::Monitor', 'Scale by monitor counts?', True, GObject.PARAM_READWRITE),
                       'bg-select-method':(str, 'Background subtraction::Select_method', 'Background exposure selecting method', 'nearest', GObject.PARAM_READWRITE),  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename. 
                       'bg-name' : (str, 'Background subtraction::Name', 'Name of the background measurement', 'Empty beam', GObject.PARAM_READWRITE),
                       'bg-dist-tolerance' : (float, 'Background subtraction::Dist_tolerance_mm', 'Distance tolerance for background subtraction', 0, 1e6, 20, GObject.PARAM_READWRITE),  # mm
                       'bg-energy-tolerance' : (float, 'Background subtraction::Energy_tolerance_eV', 'Energy tolerance for background subtraction', 0, 1e6, 2, GObject.PARAM_READWRITE),  # eV
                       'absint-select-method':(str, 'Absolute intensity::Select_method', 'Absolute intensity exposure selecting method', 'nearest', GObject.PARAM_READWRITE),  # 'prev', 'next', 'nearest'. Otherwise it is treated as a filename. 
                       'absint-name' : (str, 'Absolute intensity::Name', 'Name of the absolute reference measurement', 'Glassy Carbon', GObject.PARAM_READWRITE),
                       'absint-dist-tolerance' : (float, 'Absolute intensity::Dist_tolerance_mm', 'Distance tolerance for absolute intensity calibration', 0, 1e6, 20, GObject.PARAM_READWRITE),  # mm
                       'absint-energy-tolerance' : (float, 'Absolute intensity::Energy_tolerance_eV', 'Energy tolerance for absolute intensity calibration', 0, 1e6, 2, GObject.PARAM_READWRITE),  # eV
                       'absint-reffile':(str, 'Absolute intensity::Ref_filename', 'Absolute intensity reference dataset filename', '', GObject.PARAM_READWRITE),
                       'monitor-attr':(str, 'Monitor::Header_attribute_name', 'Monitor header attribute name', 'MeasTime', GObject.PARAM_READWRITE),
                       'transmission-selfabsorption':(bool, 'Transmission::Self_absorption_correction', 'Do self-absorption correction?', True, GObject.PARAM_READWRITE),
                       'absint-qmin':(float, 'Absolute intensity::Q_min', 'Lower q-cutoff for absolute reference dataset', -1e6, 1e6, 0, GObject.PARAM_READWRITE),
                       'absint-qmax':(float, 'Absolute intensity::Q_max', 'Upper q-cutoff for absolute reference dataset', -1e6, 1e6, 0, GObject.PARAM_READWRITE),
                      }
    __propvalues__ = None
    _reduction_thread = None
    _inqueue = None
    _kill_reduction_thread = None
    def do_get_property(self, prop):
        self.lastget = prop
        if prop.name not in self.__propvalues__:
            self.__propvalues__[prop.name] = prop.default_value
        return self.__propvalues__[prop.name]
    def do_set_property(self, prop, value):
        if prop.value_type.name in ['gdouble', 'gint']:
            if value < prop.minimum or value > prop.maximum:
                raise ValueError('Value for property %s is outside the limits.' % prop.name)
        self.__propvalues__[prop.name] = value
    def __init__(self, *args, **kwargs):
        GObject.GObject.__init__(self)
        self._inqueue = Queue.Queue()
        self._kill_reduction_thread = threading.Event()
        self._reduction_thread = threading.Thread(target=self._reduction_thread_worker)
        self._reduction_thread.setDaemon(True)
        self._reduction_thread.start()
        if args and isinstance(args[0], DataReduction):
            self.__propvalues__ = args[0].__propvalues__.copy()
        else:
            self.__propvalues__ = {}
        for k in kwargs:
            self.set_property(k, kwargs[k])
        # if self.datadirs is None:
        #    self.datadirs = ['.']
    def load_state(self, cfg=os.path.expanduser('~/.config/credo/dataredrc'), keep=[]):
        cp = ConfigParser.ConfigParser()
        cp.read(cfg)
        for prop in self.props:
            sec, opt = prop.nick.split('::')
            if prop.name in keep:
                continue
            if opt.endswith('*'):
                self.set_property(prop.name, [v for (n, v) in cp.items(sec) if n.startswith(opt[:-1])])
                continue
            if not cp.has_option(sec, opt):
                continue
            if prop.value_type.name == 'gchararray':
                self.set_property(prop.name, cp.get(sec, opt))
            elif prop.value_type.name == 'gint':
                self.set_property(prop.name, cp.getint(sec, opt))
            elif prop.value_type.name == 'gdouble':
                self.set_property(prop.name, cp.getfloat(sec, opt))
            elif prop.value_type.name == 'gboolean':
                self.set_property(prop.name, cp.getboolean(sec, opt))
            else:
                self.set_property(prop.name, cp.get(sec, opt))
        self.emit('changed')
    def save_state(self, cfg=os.path.expanduser('~/.config/credo/dataredrc')):
        cp = ConfigParser.ConfigParser()
        for prop in self.props:
            sec, opt = prop.nick.split('::')
            if not cp.has_section(sec):
                cp.add_section(sec)
            if opt.endswith('*'):
                lis = self.get_property(prop.name)
                for i, el in enumerate(lis):
                    cp.set(sec, opt[:-1] + '%05d' % i, el)
            else:
                cp.set(sec, opt, self.get_property(prop.name))
        with open(cfg, 'w+') as f:
            cp.write(f)
    def _reduction_thread_worker(self):
        while not self._kill_reduction_thread.isSet():
            try:
                (exposure, callback, settings) = self._inqueue.get(block=True, timeout=1)
            except Queue.Empty:
                continue
            es = ExpSelector(settings.get_property('headerformat'), settings.get_property('datadirs'))
            logger.info('Data reduction of ' + str(exposure.header) + ' starting.')
            exposure = self._reduction_step1(exposure, callback, settings)
            exposure = self._reduction_step2(exposure, es, callback, settings)
            exposure = self._reduction_step3(exposure, es, callback, settings)
            callback(exposure)
        return
    def _reduction_step1(self, exposure, callback, settings):
        callback('Reductions step #1 (scaling & geometry) on ' + str(exposure.header) + ' starting.')
        if settings.get_property('do-monitor'):
            callback('Normalizing intensities according to \'%s\'.' % settings.get_property('monitor-attr'))
            exposure = exposure / exposure[settings.get_property('monitor-attr')]
            exposure.header.add_history('Corrected for monitor: ' + settings.get_property('monitor-attr'))
        if settings.get_property('do-solidangle'):
            callback('Doing solid angle correction.')
            exposure = exposure * sastool.utils2d.corrections.solidangle(exposure.tth, exposure['DistCalibrated'])
            exposure.header.add_history('Corrected for solid angle.')
        if settings.get_property('do-transmission'):
            callback('Normalizing by transmission.')
            exposure = exposure / sastool.misc.errorvalue.ErrorValue(exposure['Transm'], exposure['TransmError'])
            exposure.header.add_history('Corrected for transmission')
            if settings.get_property('transmission-selfabsorption'):
                callback('Self-absorption correction.')
                exposure *= sastool.utils2d.corrections.angledependentabsorption(exposure.tth, exposure['Transm'])
                exposure.header.add_history('Corrected for angle-dependent self-absorption.')
        callback('Reduction step #1 (scaling & geometry) on ' + str(exposure.header) + ' done.')
        return exposure
    def _reduction_step2(self, exposure, es, callback, settings):
        if settings.get_property('do-bgsub'):
            if exposure['Title'] == settings.get_property('bg-name'):
                callback('Skipping background subtraction from background.')
                return exposure
            callback('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' starting.')
            if settings.get_property('bg-select-method') == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = settings.get_property('bg-name')
                bgheader = es.select(header, equal=['Title'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < settings.get_property('bg-energy-tolerance')),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < settings.get_property('bg-dist-tolerance'))],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(settings.get_property('fileformat') % bgheader['FSN'], dirs=es.datadirs)
            elif settings.get_property('bg-select-method') == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = settings.get_property('bg-name')
                bgheader = es.select(header, equal=['Title'], less=['Date'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < settings.get_property('bg-energy-tolerance')),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < settings.get_property('bg-dist-tolerance'))],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(settings.get_property('fileformat') % bgheader['FSN'], dirs=es.datadirs)
            elif settings.get_property('bg-select-method') == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = settings.get_property('bg-name')
                bgheader = es.select(header, equal=['Title'], greater=['Date'],
                                     func=[lambda h0, h1: (abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < settings.get_property('bg-energy-tolerance')),
                                           lambda h0, h1: (abs(h0['DistCalibrated'] - h1['DistCalibrated']) < settings.get_property('bg-dist-tolerance'))],
                                     sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                bg = sastool.classes.SASExposure(settings.get_property('fileformat') % bgheader['FSN'], dirs=es.datadirs)
            else:
                bg = sastool.classes.SASExposure(settings.get_property('bg-select-method'), dirs=es.datadirs)
            callback('Found background: ' + str(bg.header))
            bg = self._reduction_step1(bg, callback, settings)
            exposure = exposure - bg
            exposure.header.add_history('Subtracted background: ' + str(bg.header))
            exposure.header['FSNempty'] = bg.header['FSN']
            callback('Reduction step #2 (background subtraction) on ' + str(exposure.header) + ' done.')
        if settings.get_property('do-thickness'):
            callback('Normalizing by thickness.')
            exposure /= exposure.header['Thickness']
            exposure.header.add_history('Normalized by thickness.')
        return exposure
    def _reduction_step3(self, exposure, es, callback, settings):
        if exposure['Title'] == settings.get_property('bg-name'):
            callback('Skipping absolute normalization of a background measurement.')
            return exposure
        if settings.get_property('do-absint'):
            callback('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' starting.')
            if settings.get_property('absint-select-method') == 'nearest':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = settings.get_property('absint-name')
                refheader = es.select(header, equal=['Title'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < settings.get_property('absint-energy-tolerance'),
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < settings.get_property('absint-dist-tolerance')],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(settings.get_property('fileformat') % refheader['FSN'], dirs=es.datadirs)
            elif settings.get_property('absint-select-method') == 'prev':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = settings.get_property('absint-name')
                refheader = es.select(header, equal=['Title'], less=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < settings.get_property('absint-energy-tolerance'),
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < settings.get_property('absint-dist-tolerance')],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(settings.get_property('fileformat') % refheader['FSN'], dirs=es.datadirs)
            elif settings.get_property('absint-select-method') == 'next':
                header = sastool.classes.SASHeader(exposure.header)
                header['Title'] = settings.get_property('absint-name')
                refheader = es.select(header, equal=['Title'], greater=['Date'],
                                      func=[lambda h0, h1: abs(h0['EnergyCalibrated'] - h1['EnergyCalibrated']) < settings.get_property('absint-energy-tolerance'),
                                            lambda h0, h1: abs(h0['DistCalibrated'] - h1['DistCalibrated']) < settings.get_property('absint-dist-tolerance')],
                                      sorting=lambda h0, h1:abs((h1['Date'] - h0['Date']).total_seconds()))
                ref = sastool.classes.SASExposure(settings.get_property('fileformat') % refheader['FSN'], dirs=es.datadirs)
            else:
                ref = sastool.classes.SASExposure(settings.get_property('absint-select-method'), dirs=es.datadirs)
            ref = self._reduction_step1(ref, callback, settings)
            ref = self._reduction_step2(ref, es, callback, settings)
            qmin = settings.get_property('absint-qmin')
            if qmin < 0:
                qmin = None
            qmax = settings.get_property('absint-qmax')
            if qmax < 0:
                qmax = None
            reffile = sastool.classes.SASCurve(settings.get_property('absint-reffile')).trim(qmin, qmax)
            callback('Absolute intensity reference dataset loaded from %s; %g <= q <= %g; %d data points.' % (settings.get_property('absint-reffile'), reffile.q.min(), reffile.q.max(), len(reffile)))
            callback('Reference measurement loaded: ' + str(ref.header))
            exposure.header.add_history('Absolute reference measurement: ' + str(ref.header))
            exposure.header.add_history('Absolute reference dataset: ' + settings.get_property('absint-reffile'))
            refq = ref.get_qrange()
            callback('Default q-range for reference measurement: %g <= q <= %g; %d data points.' % (refq.min(), refq.max(), len(refq)))
            radref = ref.radial_average(reffile.q).sanitize(0, np.inf, 'Intensity')
            callback('Radial averaged reference measurement: %g <= q <= %g; %d data points.' % (radref.q.min(), radref.q.max(), len(radref)))
            exposure.header.add_history('Absolute scaling interval: %g <= q <= %g; % data points.' % (radref.q.min(), radref.q.max(), len(radref)))
            scalefactor = radref.scalefactor(reffile)
            exposure.header.add_history('Absolute scaling factor: %s' % str(scalefactor))
            callback('Absolute scaling factor:' + str(scalefactor))
            exposure = exposure * scalefactor
            callback('Reduction step #3 (absolute intensity) on ' + str(exposure.header) + ' done.')
            exposure.header['FSNref1'] = ref.header['FSN']
            exposure.header['NormFactor'] = float(scalefactor)
            exposure.header['NormFactorRelativeError'] = scalefactor.err
            exposure.header['Thicknessref1'] = ref.header['Thickness']
        return exposure
    def _dummy_callback(self, msg, callback=None):
        if isinstance(msg, basestring):
            logger.info(msg)
        if callback is not None:
            callback(msg)
    def do_reduction(self, exposure, callback=None, threaded=False):
        if callback is None:
            callback = self._dummy_callback
        else:
            callback = functools.partial(self._dummy_callback, callback=callback)
        settings = DataReductionSettings(self)
        if not threaded:
            es = ExpSelector(settings.get_property('headerformat'), settings.get_property('datadirs'))
            logger.info('Data reduction of ' + str(exposure.header) + ' starting.')
            exposure = self._reduction_step1(exposure, callback, settings)
            exposure = self._reduction_step2(exposure, es, callback, settings)
            exposure = self._reduction_step3(exposure, es, callback, settings)
            return exposure
        else:
            self._inqueue.put((exposure, callback, settings))
            return None
